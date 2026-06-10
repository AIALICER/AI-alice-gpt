"""
GitHub Issue 管理ハンドラ。

認証の優先順位:
1. GitHub App（GITHUB_APP_ID + 秘密鍵）— 推奨
2. Bot 用 PAT（GITHUB_BOT_TOKEN）
3. 後方互換（GITHUB_TOKEN、非推奨）
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import aiohttp
import jwt

GITHUB_API_BASE = "https://api.github.com"
API_VERSION = "2022-11-28"

PLACEHOLDER_TOKENS = frozenset(
    {
        "",
        "YOUR_GITHUB_TOKEN",
        "YOUR_GITHUB_BOT_TOKEN",
        "YOUR_TOKEN",
        "your_github_token",
    }
)

ISSUE_TRIGGER_PATTERN = re.compile(
    r"(?:[Ii]ssue|イシュー)[をは]?(?:出して|作成|登録|作(?:っ|り)|追加|お願い)|"
    r"(?:バグ|障害)報告"
)

ISSUE_SUGGEST_PATTERN = re.compile(r"機能|実装")

AuthMode = Literal["app", "pat"]

# Installation access token キャッシュ（有効期限の1分前まで再利用）
_token_cache: str | None = None
_token_cache_expires_at: float = 0.0


class GitHubBotConfigError(Exception):
    """GitHub 認証情報が不正な場合。"""


@dataclass(frozen=True)
class GitHubRepoConfig:
    owner: str
    repo: str


@dataclass(frozen=True)
class GitHubAppConfig:
    app_id: str
    private_key: str
    installation_id: int | None
    repo: GitHubRepoConfig


@dataclass(frozen=True)
class GitHubPatConfig:
    token: str
    repo: GitHubRepoConfig
    expected_username: str | None = None


def is_issue_request(text: str) -> bool:
    return bool(ISSUE_TRIGGER_PATTERN.search(text))


def should_suggest_issue(text: str) -> bool:
    if is_issue_request(text):
        return False
    return bool(ISSUE_SUGGEST_PATTERN.search(text))


def _load_repo_config() -> GitHubRepoConfig:
    return GitHubRepoConfig(
        owner=os.getenv("GITHUB_OWNER", "Aosy0").strip(),
        repo=os.getenv("GITHUB_REPO", "AI-Alice").strip(),
    )


def _load_private_key() -> str | None:
    raw = os.getenv("GITHUB_APP_PRIVATE_KEY", "").strip()
    if raw and "BEGIN" in raw:
        return raw.replace("\\n", "\n")

    key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH", "").strip()
    if key_path:
        path = Path(key_path)
        if not path.is_file():
            # プロジェクトルートからの相対パスも試す
            root = Path(__file__).resolve().parents[1]
            alt = root / key_path
            path = alt if alt.is_file() else path
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return None


def get_auth_mode() -> AuthMode | None:
    app_id = os.getenv("GITHUB_APP_ID", "").strip()
    if app_id and _load_private_key():
        return "app"
    token = os.getenv("GITHUB_BOT_TOKEN", "").strip() or os.getenv("GITHUB_TOKEN", "").strip()
    if token and token not in PLACEHOLDER_TOKENS:
        return "pat"
    return None


def load_github_app_config() -> GitHubAppConfig:
    app_id = os.getenv("GITHUB_APP_ID", "").strip()
    private_key = _load_private_key()
    if not app_id or not private_key:
        raise GitHubBotConfigError(
            "GitHub App の設定が不足しています。\n"
            "GITHUB_APP_ID と GITHUB_APP_PRIVATE_KEY（または GITHUB_APP_PRIVATE_KEY_PATH）を .env に設定してください。"
        )

    installation_raw = os.getenv("GITHUB_APP_INSTALLATION_ID", "").strip()
    installation_id = int(installation_raw) if installation_raw.isdigit() else None
    return GitHubAppConfig(
        app_id=app_id,
        private_key=private_key,
        installation_id=installation_id,
        repo=_load_repo_config(),
    )


def load_github_pat_config() -> GitHubPatConfig:
    token = os.getenv("GITHUB_BOT_TOKEN", "").strip()
    legacy = False
    if not token:
        token = os.getenv("GITHUB_TOKEN", "").strip()
        legacy = bool(token)

    if not token or token in PLACEHOLDER_TOKENS:
        raise GitHubBotConfigError(
            "GitHub 認証が未設定です。\n"
            "GitHub App（GITHUB_APP_ID + 秘密鍵）または GITHUB_BOT_TOKEN を設定してください。"
        )

    if legacy:
        print(
            "[GitHub Issue] 警告: GITHUB_TOKEN は非推奨です。"
            "GitHub App または GITHUB_BOT_TOKEN に移行してください。"
        )

    expected = os.getenv("GITHUB_BOT_USERNAME", "").strip() or None
    return GitHubPatConfig(
        token=token,
        repo=_load_repo_config(),
        expected_username=expected,
    )


def _create_app_jwt(app_id: str, private_key: str) -> str:
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 9 * 60,
        "iss": app_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


def _api_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
    }


async def _resolve_installation_id(
    session: aiohttp.ClientSession,
    cfg: GitHubAppConfig,
    app_jwt: str,
) -> int:
    if cfg.installation_id is not None:
        return cfg.installation_id

    url = f"{GITHUB_API_BASE}/repos/{cfg.repo.owner}/{cfg.repo.repo}/installation"
    async with session.get(url, headers=_api_headers(app_jwt)) as resp:
        if resp.status != 200:
            error_text = await resp.text()
            raise GitHubBotConfigError(
                f"GitHub App が {cfg.repo.owner}/{cfg.repo.repo} にインストールされていません"
                f"（HTTP {resp.status}）: {error_text}\n"
                "リポジトリの Settings → GitHub Apps から App をインストールしてください。"
            )
        data = await resp.json()
        return int(data["id"])


async def _create_installation_access_token(
    session: aiohttp.ClientSession,
    cfg: GitHubAppConfig,
) -> str:
    global _token_cache, _token_cache_expires_at

    now = time.time()
    if _token_cache and now < _token_cache_expires_at - 60:
        return _token_cache

    app_jwt = _create_app_jwt(cfg.app_id, cfg.private_key)
    installation_id = await _resolve_installation_id(session, cfg, app_jwt)

    url = f"{GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"
    async with session.post(url, headers=_api_headers(app_jwt)) as resp:
        if resp.status not in (200, 201):
            error_text = await resp.text()
            raise GitHubBotConfigError(
                f"Installation access token の取得に失敗しました（HTTP {resp.status}）: {error_text}"
            )
        data = await resp.json()

    token = data["token"]
    expires_at = data.get("expires_at")
    if expires_at:
        # ISO8601 → epoch（ざっくり60分）
        _token_cache_expires_at = now + 55 * 60
    else:
        _token_cache_expires_at = now + 55 * 60
    _token_cache = token
    return token


async def _get_access_token(session: aiohttp.ClientSession) -> tuple[str, AuthMode]:
    mode = get_auth_mode()
    if mode == "app":
        cfg = load_github_app_config()
        token = await _create_installation_access_token(session, cfg)
        return token, "app"
    if mode == "pat":
        cfg = load_github_pat_config()
        return cfg.token, "pat"
    raise GitHubBotConfigError(
        "GitHub 認証が未設定です。\n"
        "GITHUB_APP_ID + 秘密鍵、または GITHUB_BOT_TOKEN を .env に設定してください。"
    )


async def verify_bot_account() -> dict:
    """起動時の認証確認（App / PAT 両対応）。"""
    async with aiohttp.ClientSession() as session:
        token, mode = await _get_access_token(session)

        if mode == "app":
            cfg = load_github_app_config()
            app_jwt = _create_app_jwt(cfg.app_id, cfg.private_key)
            async with session.get(f"{GITHUB_API_BASE}/app", headers=_api_headers(app_jwt)) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise GitHubBotConfigError(
                        f"GitHub App 認証に失敗しました（HTTP {resp.status}）: {error_text}"
                    )
                app_info = await resp.json()
            installation_id = await _resolve_installation_id(session, cfg, app_jwt)
            return {
                "mode": "app",
                "login": f"{app_info.get('slug', 'github-app')}[bot]",
                "app_name": app_info.get("name", ""),
                "app_id": cfg.app_id,
                "installation_id": installation_id,
                "owner": cfg.repo.owner,
                "repo": cfg.repo.repo,
            }

        cfg = load_github_pat_config()
        async with session.get(f"{GITHUB_API_BASE}/user", headers=_api_headers(token)) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise GitHubBotConfigError(
                    f"GitHub PAT が無効です（HTTP {resp.status}）: {error_text}"
                )
            data = await resp.json()

        login = data.get("login", "")
        if cfg.expected_username and login.lower() != cfg.expected_username.lower():
            raise GitHubBotConfigError(
                f"GITHUB_BOT_USERNAME={cfg.expected_username} と一致しません（実際: {login}）"
            )
        return {"mode": "pat", "login": login}


def format_issue_body(
    body: str,
    *,
    discord_user_name: str | None = None,
    discord_user_id: int | None = None,
) -> str:
    parts: list[str] = []
    if body.strip():
        parts.append(body.strip())
    if discord_user_name or discord_user_id:
        meta = "*Discord から作成"
        if discord_user_name:
            meta += f"（依頼: {discord_user_name}"
            if discord_user_id:
                meta += f" / ID: {discord_user_id}"
            meta += "）"
        elif discord_user_id:
            meta += f"（依頼者 ID: {discord_user_id}）"
        meta += "*"
        parts.append(meta)
    return "\n\n".join(parts)


async def create_github_issue(
    title: str,
    body: str = "",
    labels: list[str] | None = None,
    *,
    discord_user_name: str | None = None,
    discord_user_id: int | None = None,
) -> dict:
    """GitHub App または Bot PAT で Issue を作成する。"""
    repo = _load_repo_config()
    issue_body = format_issue_body(
        body,
        discord_user_name=discord_user_name,
        discord_user_id=discord_user_id,
    )

    url = f"{GITHUB_API_BASE}/repos/{repo.owner}/{repo.repo}/issues"
    payload: dict[str, object] = {"title": title, "body": issue_body}
    if labels:
        payload["labels"] = labels

    async with aiohttp.ClientSession() as session:
        token, _mode = await _get_access_token(session)
        async with session.post(url, json=payload, headers=_api_headers(token)) as resp:
            if resp.status in (201, 200):
                return await resp.json()
            error_text = await resp.text()
            raise Exception(f"GitHub API Error {resp.status}: {error_text}")
