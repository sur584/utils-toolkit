"""TikTok 解析器"""

import re
import json
import asyncio
import logging
from typing import Dict, Any, Optional

from ._utils import _headers, _fetch, _follow_redirects, _make_info, _empty_result, _ok

logger = logging.getLogger(__name__)

DOMAINS = ["vm.tiktok.com", "www.tiktok.com", "tiktok.com"]


async def _parse_via_ytdlp(video_id: str, username: str) -> Optional[Dict[str, Any]]:
    """使用 yt-dlp 兜底解析 TikTok 视频信息"""
    page_url = f"https://www.tiktok.com/{username}/video/{video_id}"

    def _extract():
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(page_url, download=False)

    try:
        info = await asyncio.to_thread(_extract)
        if not info:
            return None

        play_addr = info.get("url") or ""
        if not play_addr:
            formats = info.get("formats") or []
            for f in formats:
                if f.get("vcodec") != "none" and f.get("url"):
                    play_addr = f["url"]
                    break
            if not play_addr and formats:
                play_addr = formats[0].get("url", "")

        return {
            "desc": info.get("description") or info.get("title") or "",
            "author": {
                "uniqueId": info.get("uploader_id") or "",
                "nickname": info.get("uploader") or "未知作者",
            },
            "video": {
                "playAddr": play_addr,
                "cover": info.get("thumbnail") or "",
                "duration": info.get("duration") or 0,
            },
            "stats": {
                "diggCount": info.get("like_count") or 0,
                "commentCount": info.get("comment_count") or 0,
                "shareCount": info.get("repost_count") or 0,
            },
        }
    except Exception as e:
        logger.warning(f"yt-dlp 解析 TikTok 失败: {e}")
        return None


async def parse(url: str) -> Dict[str, Any]:
    url = url.rstrip("/")
    if "vm.tiktok.com" in url:
        url = await _follow_redirects(url)

    m = re.search(r"/video/(\d+)", url)
    if not m:
        return _empty_result("无法提取 TikTok 视频 ID")
    video_id = m.group(1)

    # 提取用户名（如 @evelyn103111），@/video 会返回无数据的页面
    user_match = re.search(r"/(@[\w.-]+)/", url)
    username = user_match.group(1) if user_match else "@"

    # 优先使用 yt-dlp 解析（内置反爬处理，比直接 HTTP 抓取可靠）
    item = await _parse_via_ytdlp(video_id, username)

    # yt-dlp 失败时，降级到 HTML 页面抓取
    if not item:
        logger.info("yt-dlp 解析失败，尝试 HTML 页面抓取...")
        html = await _fetch(f"https://www.tiktok.com/{username}/video/{video_id}",
                            headers=_headers(referer="https://www.tiktok.com/", mobile=True))
        if html:
            item = _parse_html(html)

    if not item:
        return _empty_result("TikTok 页面解析失败")

    author = item.get("author", {}) or {}
    video_info = item.get("video", {})
    stats = item.get("stats", {}) or item.get("statsV2", {})

    play_addr = video_info.get("playAddr", "")
    if isinstance(play_addr, list):
        play_addr = play_addr[0] if play_addr else ""
    if isinstance(play_addr, dict):
        play_addr = play_addr.get("url", "")

    return _ok(_make_info(
        id=video_id, platform="tiktok",
        title=item.get("desc", "") or "无标题",
        author=author.get("uniqueId", "") or author.get("nickname", "未知作者"),
        cover=video_info.get("cover", "") or video_info.get("originCover", ""),
        duration=video_info.get("duration", 0),
        video_url=f"tt://{username}/video/{video_id}",
        video_url_no_watermark=play_addr,
        digg_count=stats.get("diggCount", 0) if isinstance(stats, dict) else 0,
        comment_count=stats.get("commentCount", 0) if isinstance(stats, dict) else 0,
        share_count=stats.get("shareCount", 0) if isinstance(stats, dict) else 0,
    ))


def _parse_html(html: str) -> Optional[Dict[str, Any]]:
    """从 TikTok HTML 页面中提取视频信息"""
    item = None

    # 尝试新格式：script 标签中的 JSON（videoDetail.itemInfo.itemStruct）
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    for s in scripts:
        if "playAddr" in s:
            json_match = re.search(r'\{.*"playAddr".*\}', s, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group(0))
                    item_struct = (data.get("videoDetail", {})
                                   .get("itemInfo", {})
                                   .get("itemStruct", {}))
                    if item_struct:
                        item = item_struct
                        break
                except Exception:
                    continue

    # 兼容旧格式：SIGI_STATE / __NEXT_DATA__
    if not item:
        m = re.search(r'<script\s+id="SIGI_STATE"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not m:
            m = re.search(r'window\.__NEXT_DATA__\s*=\s*(\{.*?\})\s*</script>', html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                item_module = data.get("ItemModule", {}) or data.get("props", {}).get("pageProps", {}).get("itemInfo", {})
                items = item_module.get("items", {}) if isinstance(item_module, dict) else {}
                if isinstance(items, dict):
                    item = list(items.values())[0] if items else None
                elif isinstance(items, list):
                    item = items[0] if items else None
            except Exception:
                pass

    return item
