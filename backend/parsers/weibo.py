"""微博解析器"""

import re
from typing import Dict, Any

import httpx

from ._utils import _headers, _fetch, _make_info, _empty_result, _ok


DOMAINS = ["weibo.com", "m.weibo.cn", "video.weibo.com"]


async def parse(url: str) -> Dict[str, Any]:
    url = url.rstrip("/")
    m = re.search(r"/video/(\w+)", url) or re.search(r"video_id=(\w+)", url)
    if not m:
        html = await _fetch(url, headers=_headers(referer="https://weibo.com/", mobile=True))
        if html:
            m = re.search(r'"video_id"\s*:\s*"(\w+)"', html)
    if not m:
        return _empty_result("无法提取微博视频 ID")
    vid = m.group(1)

    api = f"https://m.weibo.cn/api/container/getIndex?containerid=231248{vid}"
    try:
        async with httpx.AsyncClient(timeout=15, verify=False) as c:
            r = await c.get(api, headers=_headers(referer="https://m.weibo.cn/", mobile=True))
            data = r.json()
    except Exception:
        return _empty_result("微博 API 请求失败")

    card = data.get("data", {}).get("card", {})
    info_data = card.get("mblog", {}) or card.get("card_info", {})
    page_info = info_data.get("page_info", {})
    media = page_info.get("urls", {}) or page_info.get("media_info", {})

    video_url = ""
    for key in ["mp4_720p_mp4", "mp4_hd_mp4", "mp4_ld_mp4", "stream_url_hd", "stream_url"]:
        if key in media:
            video_url = media[key]
            break

    return _ok(_make_info(
        id=vid, platform="weibo",
        title=info_data.get("text", "无标题")[:100],
        author=info_data.get("user", {}).get("screen_name", "未知作者"),
        cover=page_info.get("page_pic", {}).get("url", ""),
        duration=page_info.get("media_info", {}).get("duration", 0),
        video_url=video_url,
        video_url_no_watermark=video_url,
    ))
