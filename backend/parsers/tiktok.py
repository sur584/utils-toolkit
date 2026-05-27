"""TikTok 解析器"""

import re
import json
from typing import Dict, Any

from ._utils import _headers, _fetch, _follow_redirects, _make_info, _empty_result, _ok


DOMAINS = ["vm.tiktok.com", "www.tiktok.com", "tiktok.com"]


async def parse(url: str) -> Dict[str, Any]:
    url = url.rstrip("/")
    if "vm.tiktok.com" in url:
        url = await _follow_redirects(url)

    m = re.search(r"/video/(\d+)", url)
    if not m:
        return _empty_result("无法提取 TikTok 视频 ID")
    video_id = m.group(1)

    html = await _fetch(f"https://www.tiktok.com/@/video/{video_id}",
                        headers=_headers(referer="https://www.tiktok.com/", mobile=True))
    if not html:
        return _empty_result("获取 TikTok 页面失败")

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
        video_url=f"tt://{video_id}",
        video_url_no_watermark=play_addr,
        digg_count=stats.get("diggCount", 0) if isinstance(stats, dict) else 0,
        comment_count=stats.get("commentCount", 0) if isinstance(stats, dict) else 0,
        share_count=stats.get("shareCount", 0) if isinstance(stats, dict) else 0,
    ))
