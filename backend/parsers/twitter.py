"""Twitter/X 解析器"""

import re
import asyncio
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from ._utils import _follow_redirects, _make_info, _empty_result, _ok
from config import get_active_proxy


DOMAINS = ["twitter.com", "x.com", "www.twitter.com", "www.x.com", "t.co"]


async def _parse_via_ytdlp(url: str) -> Optional[Dict[str, Any]]:
    def _extract():
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "socket_timeout": 20,
            "format": "best[ext=mp4]/best",
        }
        proxy = get_active_proxy()
        if proxy:
            ydl_opts["proxy"] = proxy
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        return await asyncio.to_thread(_extract)
    except Exception:
        return None


async def parse(url: str) -> Dict[str, Any]:
    url = url.rstrip("/")
    if "t.co" in urlparse(url).netloc:
        url = await _follow_redirects(url)

    m = re.search(r"/status/(\d+)", url)
    if not m:
        return _empty_result("无法提取推文 ID")
    tweet_id = m.group(1)

    canonical_url = f"https://x.com/i/status/{tweet_id}"
    info = await _parse_via_ytdlp(canonical_url)
    if info:
        video_url = info.get("url") or ""
        formats = info.get("formats") or []
        if not video_url:
            mp4_formats = [f for f in formats if f.get("url") and (f.get("ext") == "mp4" or ".mp4" in f.get("url", ""))]
            if mp4_formats:
                best = max(mp4_formats, key=lambda f: f.get("height") or 0)
                video_url = best.get("url", "")
            elif formats:
                video_url = formats[-1].get("url", "")

        return _ok(_make_info(
            id=tweet_id,
            platform="twitter",
            title=info.get("title") or info.get("description") or "Twitter/X 视频",
            author=info.get("uploader") or info.get("uploader_id") or "未知作者",
            cover=info.get("thumbnail") or "",
            duration=info.get("duration") or 0,
            video_url=f"tw://{tweet_id}",
            video_url_no_watermark=video_url,
            digg_count=info.get("like_count") or 0,
            comment_count=info.get("comment_count") or 0,
            share_count=info.get("repost_count") or 0,
        ))

    embed_url = f"https://platform.twitter.com/embed/Tweet.html?id={tweet_id}"
    result = _ok(_make_info(
        id=tweet_id,
        platform="twitter",
        title="Twitter/X 视频",
        video_url=embed_url,
        video_url_no_watermark=embed_url,
    ))
    result["message"] = "仅获取到推文嵌入页，未解析到视频直链"
    return result
