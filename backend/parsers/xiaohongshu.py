"""小红书解析器"""

import re
import json
from urllib.parse import urlparse
from typing import Dict, Any

from ._utils import DESKTOP_UA, _headers, _fetch, _follow_redirects, _make_info, _empty_result, _ok


DOMAINS = ["xiaohongshu.com", "xhslink.com", "www.xiaohongshu.com"]


async def parse(url: str) -> Dict[str, Any]:
    url = url.rstrip("/")
    parsed = urlparse(url)
    if "xhslink.com" in parsed.netloc:
        url = await _follow_redirects(url)

    m = re.search(r"/explore/(\w+)", url) or re.search(r"/discovery/item/(\w+)", url)
    if not m:
        parts = urlparse(url).path.strip("/").split("/")
        m_val = parts[-1] if len(parts) > 1 else None
    else:
        m_val = m.group(1)

    if not m_val:
        return _empty_result("无法提取小红书笔记 ID")

    headers = {
        "User-Agent": DESKTOP_UA,
        "Referer": "https://www.xiaohongshu.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    html = await _fetch(url, headers=headers)
    if not html:
        return _empty_result("获取小红书页面失败")

    m = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>', html, re.DOTALL)
    if not m:
        return _empty_result("页面解析失败")

    try:
        raw = m.group(1).replace("undefined", "null")
        state = json.loads(raw)
    except Exception:
        return _empty_result("JSON 解析失败")

    note_map = state.get("note", {}).get("noteDetailMap", {})
    if not note_map:
        return _empty_result("未找到笔记数据")

    note_data = note_map.get(m_val, {}).get("note", {})
    if not note_data:
        first_key = next(iter(note_map))
        note_data = note_map[first_key].get("note", {})

    if not note_data:
        return _empty_result("笔记数据为空")

    user = note_data.get("user", {})
    video = note_data.get("video", {})
    image_list = note_data.get("imageList", [])

    cover = ""
    if image_list:
        cover = image_list[0].get("urlDefault", "") or image_list[0].get("url", "")

    video_url = ""
    media = video.get("media", {})
    if isinstance(media, dict):
        stream = media.get("stream", {})
        for codec in ["h264", "h265", "av1"]:
            streams = stream.get(codec, [])
            if isinstance(streams, list) and streams:
                entry = streams[0]
                backups = entry.get("backupUrls", [])
                if backups:
                    video_url = backups[0]
                else:
                    video_url = entry.get("masterUrl", "")
                if video_url:
                    break

    is_video = bool(video_url)
    title = note_data.get("title", "") or note_data.get("desc", "") or "无标题"

    info = _make_info(
        id=m_val, platform="xiaohongshu",
        title=title,
        author=user.get("nickname", "未知作者"),
        author_avatar=user.get("avatar", ""),
        cover=cover,
        video_url=video_url,
        video_url_no_watermark=video_url,
    )

    if not is_video and image_list:
        info["image_list"] = [img.get("urlDefault", "") or img.get("url", "") for img in image_list if img.get("urlDefault") or img.get("url")]
        info["note_type"] = "image"
    else:
        info["note_type"] = "video" if is_video else "unknown"

    return _ok(info)
