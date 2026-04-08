"""
URLハンドラーモジュール

メッセージや履歴からURLを抽出し、コンテンツを取得する機能を提供する。
"""

import re
import asyncio
import aiohttp
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

# URLパターン（正規表現）
URL_PATTERN = re.compile(
    r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:[\w.])*)?)?',
    re.IGNORECASE
)

# 除外するURLパターン（画像、動画、ファイルなど）
EXCLUDED_EXTENSIONS = (
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg',
    '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm',
    '.mp3', '.wav', '.ogg', '.flac', '.aac',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.rar', '.7z', '.tar', '.gz',
    '.exe', '.dmg', '.pkg', '.deb', '.rpm'
)

# 除外するドメイン（動画・SNSサイトなど）
EXCLUDED_DOMAINS = (
    'youtube.com', 'youtu.be', 'www.youtube.com',
    'twitter.com', 'x.com', 'www.twitter.com', 'www.x.com',
    'facebook.com', 'www.facebook.com',
    'instagram.com', 'www.instagram.com',
    'tiktok.com', 'www.tiktok.com',
    'twitch.tv', 'www.twitch.tv',
    'nicovideo.jp', 'www.nicovideo.jp', 'nico.ms',
    'bilibili.com', 'www.bilibili.com',
)

# 最大コンテンツ長さ（文字数）
MAX_CONTENT_LENGTH = 8000

# タイムアウト（秒）
FETCH_TIMEOUT = 10


def extract_urls(text: str) -> List[str]:
    """
    テキストからURLを抽出する
    
    Args:
        text: URLを抽出するテキスト
        
    Returns:
        抽出されたURLのリスト
    """
    if not text:
        return []
    
    urls = URL_PATTERN.findall(text)
    # 重複を除去し、有効なURLのみを返す
    unique_urls = []
    seen = set()
    
    for url in urls:
        # 末尾の句読点を削除
        url = url.rstrip('.,;:!?)\'"')
        
        # 重複チェック
        if url.lower() in seen:
            continue
        seen.add(url.lower())
        
        # 除外する拡張子をチェック
        parsed = urlparse(url)
        path = parsed.path.lower()
        if any(path.endswith(ext) for ext in EXCLUDED_EXTENSIONS):
            continue
        
        # 除外するドメインをチェック
        domain = parsed.netloc.lower()
        if any(excluded in domain for excluded in EXCLUDED_DOMAINS):
            print(f"[URL Handler] Excluded domain: {domain}")
            continue
        
        unique_urls.append(url)
    
    return unique_urls


async def fetch_url_content(url: str) -> Optional[Dict[str, Any]]:
    """
    URLにアクセスしてコンテンツを取得する
    
    Args:
        url: 取得するURL
        
    Returns:
        コンテンツ情報の辞書、取得失敗時はNone
        """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, 
                timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT),
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            ) as response:
                if response.status != 200:
                    return None
                
                # コンテンツタイプをチェック
                content_type = response.headers.get('Content-Type', '')
                if not content_type.startswith('text/'):
                    return None
                
                # テキストを取得
                text = await response.text()
                
                # HTMLから主要なテキストを抽出（簡易的）
                content = extract_text_from_html(text)
                
                # 長さを制限
                if len(content) > MAX_CONTENT_LENGTH:
                    content = content[:MAX_CONTENT_LENGTH] + "..."
                
                return {
                    'url': url,
                    'title': extract_title_from_html(text),
                    'content': content,
                    'status': response.status
                }
                
    except asyncio.TimeoutError:
        return None
    except Exception as e:
        print(f"[URL Handler] Error fetching {url}: {e}")
        return None


def extract_text_from_html(html: str) -> str:
    """
    HTMLから主要なテキストを抽出する（簡易版）
    
    Args:
        html: HTML文字列
        
    Returns:
        抽出されたテキスト
    """
    # タグを削除
    text = re.sub(r'<[^>]+>', ' ', html)
    
    # 連続する空白を整理
    text = re.sub(r'\s+', ' ', text)
    
    # 前後の空白を削除
    text = text.strip()
    
    return text


def extract_title_from_html(html: str) -> Optional[str]:
    """
    HTMLからタイトルを抽出する
    
    Args:
        html: HTML文字列
        
    Returns:
        タイトル文字列、取得できない場合はNone
    """
    match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


async def process_urls_in_text(text: str) -> List[Dict[str, Any]]:
    """
    テキスト内のURLを抽出してコンテンツを取得する
    
    Args:
        text: URLを含むテキスト
        
    Returns:
        URLコンテンツのリスト
    """
    urls = extract_urls(text)
    if not urls:
        return []
    
    # 最大3つのURLのみ処理
    urls = urls[:3]
    
    # 並行してコンテンツを取得
    tasks = [fetch_url_content(url) for url in urls]
    results = await asyncio.gather(*tasks)
    
    # Noneを除外
    return [r for r in results if r is not None]


def format_url_contents(url_contents: List[Dict[str, Any]]) -> str:
    """
    URLコンテンツをGemini用にフォーマットする
    
    Args:
        url_contents: URLコンテンツのリスト
        
    Returns:
        フォーマットされた文字列
    """
    if not url_contents:
        return ""
    
    formatted_parts = ["\n\n[Referenced URL Contents:]"]
    
    for i, content in enumerate(url_contents, 1):
        title = content.get('title', 'Untitled')
        url = content['url']
        text = content.get('content', '')
        
        formatted_parts.append(f"\n--- URL {i} ---")
        formatted_parts.append(f"Title: {title}")
        formatted_parts.append(f"URL: {url}")
        formatted_parts.append(f"Content:\n{text}")
    
    return "\n".join(formatted_parts)
