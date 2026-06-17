"""TikTok 解析器"""

import re
import json
import asyncio
import logging
from typing import Dict, Any, Optional

import httpx

from ._utils import _follow_redirects, _make_info, _empty_result, _ok
from config import HTTP_PROXY

logger = logging.getLogger(__name__)

_PROXY = HTTP_PROXY

DOMAINS = ["vm.tiktok.com", "www.tiktok.com", "tiktok.com"]

# TikTok 专用浏览器头 — 使用英语环境绕过地区重定向
_DESKTOP_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
_MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"


def _tt_headers(mobile: bool = False, lang: str = "en") -> Dict[str, str]:
    """TikTok 专用请求头 — 英语语言+模拟 cookie 绕过 geo 重定向"""
    return {
        "User-Agent": _MOBILE_UA if mobile else _DESKTOP_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9" if lang == "en" else "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.tiktok.com/",
        "Cookie": "tt_webid=1; tt_csrf_token=1; tt_chain_token=1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }


async def _tt_fetch(url: str, mobile: bool = True) -> Optional[str]:
    """TikTok 专用 fetch — 不跟随重定向，检测 geo 跳转"""
    try:
        client_kwargs = dict(timeout=20, verify=False, follow_redirects=False)
        if _PROXY:
            client_kwargs["proxies"] = _PROXY
        async with httpx.AsyncClient(**client_kwargs) as c:
            r = await c.get(url, headers=_tt_headers(mobile=mobile))
            if r.status_code == 200:
                # 检查是否被重定向到地区页面
                if "/hk/" in str(r.url) or "/about" in str(r.url):
                    logger.warning(f"TikTok 地区重定向: {r.url}")
                    return None
                return r.text
            if r.status_code == 302:
                loc = r.headers.get("location", "")
                logger.warning(f"TikTok 302 重定向: {loc}")
                return None
    except Exception as e:
        logger.warning(f"TikTok fetch 失败: {type(e).__name__}: {e}")
    return None


async def _parse_via_ytdlp(video_id: str, username: str) -> Optional[Dict[str, Any]]:
    """使用 yt-dlp 兜底解析 TikTok 视频信息"""
    page_url = f"https://www.tiktok.com/{username}/video/{video_id}"

    def _extract():
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "socket_timeout": 30,
            "http_headers": _tt_headers(mobile=False, lang="en"),
        }
        if _PROXY:
            ydl_opts["proxy"] = _PROXY
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

    # yt-dlp 失败时，降级到 HTML 页面抓取（英语头 + 不跟随重定向）
    if not item:
        logger.info("yt-dlp 解析失败，尝试 HTML 页面抓取...")
        html = await _tt_fetch(f"https://www.tiktok.com/{username}/video/{video_id}", mobile=True)
        if not html:
            # 换桌面头再试一次
            html = await _tt_fetch(f"https://www.tiktok.com/{username}/video/{video_id}", mobile=False)
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
