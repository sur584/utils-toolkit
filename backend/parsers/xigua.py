"""西瓜视频解析器"""

import re
from typing import Dict, Any

import httpx

from ._utils import _headers, _make_info, _empty_result, _ok


DOMAINS = [".ixigua.com", "www.ixigua.com", "m.ixigua.com"]


async def parse(url: str) -> Dict[str, Any]:
    url = url.rstrip("/")
    m = re.search(r"/(\d{15,})", url)
    if not m:
        return _empty_result("无法提取西瓜视频 ID")
    vid = m.group(1)

    api = f"https://ib.365yg.com/api/news/feed/v88/?group_id={vid}&item_id={vid}"
    try:
        async with httpx.AsyncClient(timeout=15, verify=False) as c:
            r = await c.get(api, headers=_headers(referer="https://www.ixigua.com/"))
            data = r.json()
    except Exception:
        return _empty_result("西瓜视频 API 请求失败")

    item_list = data.get("data", [])
    if not item_list:
        return _empty_result("西瓜视频解析失败")

    item = item_list[0] if isinstance(item_list, list) else item_list
    video_url = item.get("video_url", "") or item.get("mp4_url", "")

    return _ok(_make_info(
        id=vid, platform="xigua",
        title=item.get("title", "") or "无标题",
        author=item.get("source", "未知作者"),
        cover=item.get("large_image_url", ""),
        video_url=video_url,
        video_url_no_watermark=video_url,
    ))
