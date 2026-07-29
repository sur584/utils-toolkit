"""Twitter/X 解析器"""

import re
import asyncio
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from ._utils import _follow_redirects, _make_info, _empty_result, _ok
from config import get_active_proxy, SSL_VERIFY


DOMAINS = ["twitter.com", "x.com", "www.twitter.com", "www.x.com", "t.co"]


async def _parse_via_ytdlp(url: str):
    """返回 (info, error_str)。info 为 None 时 error_str 携带最后一次失败原因。"""
    def _extract(proxy: str = ""):
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": not SSL_VERIFY,
            "socket_timeout": 20,
            "format": "best[ext=mp4]/best",
        }
        if proxy:
            ydl_opts["proxy"] = proxy
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        # 先试直连（本地网络/系统代理已在 yt-dlp 层面生效）
        return await asyncio.to_thread(_extract, ""), ""
    except Exception as e_direct:
        # 直连失败，尝试配置的代理
        proxy = get_active_proxy()
        if proxy:
            try:
                return await asyncio.to_thread(_extract, proxy), ""
            except Exception as e_proxy:
                return None, str(e_proxy)
        return None, str(e_direct)


async def parse(url: str) -> Dict[str, Any]:
    url = url.rstrip("/")
    if "t.co" in urlparse(url).netloc:
        url = await _follow_redirects(url)

    m = re.search(r"/status/(\d+)", url)
    if not m:
        return _empty_result("无法提取推文 ID")
    tweet_id = m.group(1)

    canonical_url = f"https://x.com/i/status/{tweet_id}"
    info, err = await _parse_via_ytdlp(canonical_url)
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

        if video_url:
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

    # 按失败原因给出准确提示
    err_l = (err or "").lower()
    if info is not None:
        # yt-dlp 解析成功但没提取到视频 URL：推文不含视频
        msg = "该推文不包含可下载的视频"
    elif "404" in err_l or "not found" in err_l:
        # x.com API 已访问成功，但推文内引用的资源不存在/已删除，或推文无原生视频
        msg = "推文不含原生视频，或其中引用的资源已删除（404）"
    elif "generic" in err_l:
        msg = "该推文不含原生视频（仅含外部链接，且链接无法解析）"
    elif any(k in err_l for k in ("timed out", "timeout", "unable to connect", "connection", "resolve", "ssl")):
        msg = "无法访问 x.com/api.x.com；请检查网络或在部署机器配置可用代理"
    elif "nsfw" in err_l or "login" in err_l or "authorization" in err_l or "age" in err_l:
        msg = "该推文需要登录/受限内容，暂不支持解析"
    else:
        msg = f"Twitter/X 解析失败：{err[:120]}" if err else "Twitter/X 解析失败"
    result = _empty_result(msg)
    result["retry"] = False
    return result
