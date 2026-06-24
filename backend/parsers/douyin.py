"""抖音解析器"""

import re
import json
from urllib.parse import urlparse
from typing import Dict, Any

from ._utils import _headers, _fetch, _follow_redirects, _make_info, _empty_result, _ok


DOMAINS = ["v.douyin.com", "www.douyin.com", "www.iesdouyin.com", "m.douyin.com"]


async def parse(url: str) -> Dict[str, Any]:
    url = url.rstrip("/")
    parsed = urlparse(url)
    if "v.douyin.com" in parsed.netloc:
        url = await _follow_redirects(url)
        parsed = urlparse(url)
        # 检查是否重定向到了首页（短链接已失效）
        if parsed.netloc in ("www.douyin.com", "douyin.com") and parsed.path in ("", "/"):
            return _empty_result("短链接已失效或过期，请重新分享获取新链接")

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
        return _empty_result("无法提取视频 ID")

    page_url = f"https://www.iesdouyin.com/share/video/{video_id}/"
    html = await _fetch(page_url, headers=_headers(mobile=True), use_proxy=False)
    if not html:
        html = await _fetch(page_url, headers=_headers(mobile=True))
    if not html:
        return _empty_result("获取页面失败")

    marker = '"item_list":['
    start = html.find(marker)
    if start < 0:
        return _empty_result("页面解析失败，链接可能已失效")

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
    except Exception:
        return _empty_result("JSON 解析失败")

    item = items[0]
    author = item.get("author", {})
    video = item.get("video", {})
    stats = item.get("statistics", {})
    cover = video.get("cover", {})
    cover_url = cover.get("url_list", [""])[0] if isinstance(cover, dict) else ""
    play = video.get("play_addr", {})
    play_urls = play.get("url_list", []) if isinstance(play, dict) else []
    video_url = play_urls[0].replace("\\u002F", "/") if play_urls else ""
    avatar = author.get("avatar_thumb", {})
    avatar_url = avatar.get("url_list", [""])[0] if isinstance(avatar, dict) else ""

    info = _make_info(
        id=video_id, platform="douyin",
        title=item.get("desc", "") or "无标题",
        author=author.get("nickname", "未知作者"),
        author_avatar=avatar_url,
        cover=cover_url,
        duration=video.get("duration", 0) // 1000,
        video_url=video_url,
        video_url_no_watermark=video_url.replace("playwm", "play"),
        create_time=item.get("create_time", 0),
        digg_count=stats.get("digg_count", 0),
        comment_count=stats.get("comment_count", 0),
        share_count=stats.get("share_count", 0),
    )

    # 图文笔记：aweme_type=2 表示图片帖
    aweme_type = item.get("aweme_type", 0)
    images = item.get("images") or []
    is_image_post = aweme_type == 2 or (isinstance(images, list) and len(images) > 0)
    if is_image_post and images:
        image_list = []
        for img in images:
            url_list = img.get("download_url_list") or img.get("url_list") or []
            if url_list:
                img_url = url_list[0]
                if img_url:
                    image_list.append(img_url)
        if image_list:
            info["image_list"] = image_list
            info["note_type"] = "image"
            info["video_url"] = ""
            info["video_url_no_watermark"] = ""
    else:
        info["note_type"] = "video"

    return _ok(info)
