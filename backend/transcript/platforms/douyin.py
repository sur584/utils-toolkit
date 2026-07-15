"""抖音视频解析 - 复用 download video 项目的方式，不需要 cookies"""
import json
import logging
import re
from typing import Dict, Any
from urllib.parse import urlparse

import httpx

from ._utils import _headers, _follow_redirects, _fetch

logger = logging.getLogger(__name__)

# 复用主解析器的官方 detail API（a_bogus 签名 + ttwid，匿名取数），避免重复实现签名逻辑
try:
    from parsers.douyin import _fetch_aweme_detail as _dy_fetch_detail
except Exception:  # pragma: no cover - 导入失败时降级为仅用分享页兜底
    _dy_fetch_detail = None


async def resolve_url(url: str) -> str:
    """Resolve Douyin short links to canonical URL."""
    url = url.rstrip("/")
    parsed = urlparse(url)
    if "v.douyin.com" in parsed.netloc:
        url = await _follow_redirects(url)
        parsed = urlparse(url)
        if parsed.netloc in ("www.douyin.com", "douyin.com") and parsed.path in ("", "/"):
            raise ValueError("短链接已失效或过期，请重新分享获取新链接")
    return url


async def fetch_video_info(url: str) -> Dict[str, Any]:
    """
    从抖音页面抓取视频信息（复用 download video 项目的解析方式）。
    不需要 cookies，直接从 iesdouyin.com 获取。
    返回: {"title", "author", "video_url", "desc", "duration"}
    """
    # 提取 video_id
    parsed = urlparse(url)
    video_id = None
    for pat in [r"/video/(\d+)", r"/note/(\d+)", r"modal_id=(\d+)", r"aweme_id=(\d+)"]:
        m = re.search(pat, url)
        if m:
            video_id = m.group(1)
            break
    if not video_id:
        parts = parsed.path.strip("/").split("/")
        if parts and parts[-1].isdigit():
            video_id = parts[-1]
    if not video_id:
        raise ValueError("无法提取视频 ID")

    # 抖音已下线分享页内嵌的 item_list JSON（share 页现返回空壳）。优先走官方 detail API
    # （复用 parsers.douyin 的 a_bogus 签名 + ttwid，匿名即可），失败再回退旧分享页兜底。
    item = None
    if _dy_fetch_detail is not None:
        try:
            item = await _dy_fetch_detail(video_id)
        except Exception as e:
            logger.warning(f"[抖音转录] detail API 异常: {type(e).__name__}: {e}")
            item = None

    if item is None:
        page_urls = [
            f"https://www.douyin.com/share/video/{video_id}/",
            f"https://www.iesdouyin.com/share/video/{video_id}/",
        ]
        html = None
        for page_url in page_urls:
            html = await _fetch(page_url, headers=_headers(mobile=True), use_proxy=False)
            if not html:
                html = await _fetch(page_url, headers=_headers(mobile=True))
            if html and '"item_list":[' in html:
                break
        if not html or '"item_list":[' not in html:
            raise RuntimeError("解析失败：抖音接口未返回数据（可稍后重试，或 a_bogus 签名/风控问题）")

        marker = '"item_list":['
        start = html.find(marker)
        bracket_start = html.index("[", start)
        depth = 0
        end = bracket_start
        for i in range(bracket_start, len(html)):
            if html[i] == "[":
                depth += 1
            elif html[i] == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        try:
            items = json.loads(html[bracket_start:end])
        except Exception as e:
            raise RuntimeError(f"JSON 解析失败: {e}")
        item = items[0] if items else None
        if item is None:
            raise RuntimeError("解析失败：抖音接口未返回数据")

    author = item.get("author", {})
    video = item.get("video", {})

    # 获取视频下载地址（优先选最低码率，减少下载时间）
    video_url = ""
    bit_rates = video.get("bit_rate", [])
    if bit_rates and isinstance(bit_rates, list):
        try:
            lowest = min(bit_rates, key=lambda b: b.get("bit_rate", float("inf")))
            play = lowest.get("play_addr", {})
            play_urls = play.get("url_list", []) if isinstance(play, dict) else []
            if play_urls:
                video_url = play_urls[0].replace("\\u002F", "/")
        except (ValueError, TypeError):
            pass

    # 回退到原始 play_addr
    if not video_url:
        play = video.get("play_addr", {})
        play_urls = play.get("url_list", []) if isinstance(play, dict) else []
        video_url = play_urls[0].replace("\\u002F", "/") if play_urls else ""

    # 无水印版本
    video_url_no_wm = video_url.replace("playwm", "play") if video_url else ""

    # 封面图
    cover = ""
    origin_cover = video.get("origin_cover", {})
    if isinstance(origin_cover, dict):
        cover_urls = origin_cover.get("url_list", [])
        if cover_urls:
            cover = cover_urls[0]
    if not cover:
        cover_obj = video.get("cover", {})
        if isinstance(cover_obj, dict):
            cover_urls = cover_obj.get("url_list", [])
            if cover_urls:
                cover = cover_urls[0]

    return {
        "video_id": video_id,
        "title": item.get("desc", "") or "无标题",
        "author": author.get("nickname", "未知作者"),
        "video_url": video_url_no_wm or video_url,
        "cover": cover,
        "desc": item.get("desc", ""),
        "duration": video.get("duration", 0) // 1000,
    }


async def download_video_audio(video_url: str, output_path: str) -> str:
    """
    直接下载视频文件（不通过 yt-dlp）。
    返回保存的文件路径。
    """
    if not video_url:
        raise RuntimeError("视频地址为空")

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(video_url, headers=_headers())
        resp.raise_for_status()

        # 根据 content-type 决定扩展名
        ct = resp.headers.get("content-type", "")
        if "mp4" in ct or "video" in ct:
            ext = ".mp4"
        else:
            ext = ".mp4"  # 默认

        save_path = output_path + ext
        with open(save_path, "wb") as f:
            f.write(resp.content)

        return save_path
