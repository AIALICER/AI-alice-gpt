"""
ゲーム名ファジーマッチングモジュール

特殊文字除去 + thefuzz による類似度計算で
Twitch ゲーム名と Steam アプリ名をマッチング
"""

import re
from typing import Optional

from thefuzz import fuzz


SPECIAL_CHARS_PATTERN = re.compile(
    r"["
    r"\u00AE"  # ®
    r"\u2122"  # ™
    r"\u00A9"  # ©
    r"\u2020"  # †
    r"\u2021"  # ‡
    r"\u2120"  # ℠
    r"\u2122"  # ™
    r"\u212E"  # ℮
    r"]+",
    re.UNICODE,
)

SUBTITLE_PATTERN = re.compile(
    r"\s*[\(\[【][^)\]】]*[\)\]】]\s*$",  # 末尾の括弧書き (steam),【GOTY】など
    re.UNICODE,
)

EXTRA_SPACES_PATTERN = re.compile(r"\s+")


def normalize_game_name(name: str) -> str:
    """
    ゲーム名を正規化（特殊文字除去、空白正規化）

    Args:
        name: 元のゲーム名

    Returns:
        str: 正規化されたゲーム名
    """
    name = SPECIAL_CHARS_PATTERN.sub("", name)
    name = SUBTITLE_PATTERN.sub("", name)
    name = EXTRA_SPACES_PATTERN.sub(" ", name)
    name = name.strip()
    name = name.lower()
    return name


def find_best_match_combined(
    target_name: str,
    candidates: list[dict],
    threshold: int = 85,
    complete_match_threshold: int = 95,
    min_length_ratio: float = 0.85,
    max_length_ratio: float = 1.15,
) -> Optional[dict]:
    """
    完全一致と部分一致の両方を試して最もスコアの高いものを返す

    Args:
        target_name: 検索対象のゲーム名（Twitch 側）
        candidates: 候補リスト（Steam アプリ一覧）
        threshold: 類似度の閾値（0-100）
        complete_match_threshold: 完全一致とみなす閾値（0-100）
        min_length_ratio: 長さ比率の最小値（Steam 名が Twitch 名の何％以上必要か）
        max_length_ratio: 長さ比率の最大値（Steam 名が Twitch 名の何％以下か）

    Returns:
        dict | None: 最も類似度の高い候補、閾値未満なら None
    """
    if not candidates:
        return None

    target_normalized = normalize_game_name(target_name)
    target_len = len(target_normalized)

    best_match = None
    best_score = 0.0

    for candidate in candidates:
        candidate_normalized = candidate.get("normalized", normalize_game_name(candidate["name"]))
        candidate_len = len(candidate_normalized)

        # 長さフィルタリング：Steam 名が短すぎる/長すぎる場合はスキップ
        if candidate_len < target_len * min_length_ratio:
            continue
        if candidate_len > target_len * max_length_ratio:
            continue

        ratio_score = fuzz.ratio(target_normalized, candidate_normalized)
        partial_score = fuzz.partial_ratio(target_normalized, candidate_normalized)

        score = max(ratio_score, partial_score)

        # 完全一致に近い場合は長さチェックを緩和
        if score >= complete_match_threshold:
            length_diff = abs(target_len - candidate_len)
            if length_diff > max(target_len, candidate_len) * 0.3:
                score = int(score * 0.8)

        if score >= threshold and score > best_score:
            best_score = score
            best_match = candidate
            best_match["match_score"] = score
            best_match["match_type"] = "ratio" if ratio_score >= partial_score else "partial"

    return best_match


def find_best_match_partial(
    target_name: str,
    candidates: list[dict],
    threshold: float = 0.65,
) -> Optional[dict]:
    """
    部分一致を重視したマッチング

    Args:
        target_name: 検索対象のゲーム名（Twitch 側）
        candidates: 候補リスト（Steam アプリ一覧）
        threshold: 類似度の閾値（0.0-1.0）

    Returns:
        dict | None: 最も類似度の高い候補、閾値未満なら None
    """
    if not candidates:
        return None

    target_normalized = normalize_game_name(target_name)

    best_match = None
    best_score = 0.0

    for candidate in candidates:
        candidate_normalized = candidate.get("normalized", normalize_game_name(candidate["name"]))

        score = fuzz.partial_ratio(target_normalized, candidate_normalized) / 100.0

        if score >= threshold and score > best_score:
            best_score = score
            best_match = candidate
            best_match["match_score"] = score

    return best_match
