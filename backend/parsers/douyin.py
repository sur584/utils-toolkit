"""抖音解析器"""

import re
import json
import html as html_lib
from urllib.parse import urlparse, urlsplit, urlunsplit, parse_qsl, urlencode
from typing import Dict, Any, List, Tuple

from ._utils import _headers, _fetch, _follow_redirects, _make_info, _empty_result, _ok


DOMAINS = ["v.douyin.com", "www.douyin.com", "www.iesdouyin.com", "m.douyin.com"]


def _normalize_douyin_image_url(url: str) -> str:
    if not isinstance(url, str):
        return ""
    url = html_lib.unescape(url).replace("\\u002F", "/").strip()
    if not url.startswith(("http://", "https://")):
        return ""

    try:
        parts = urlsplit(url)
        query = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            lower_key = key.lower()
            lower_value = value.lower()
            if lower_key in ("watermark", "watermark_type") and lower_value not in ("0", "false"):
                value = "0"
            elif lower_key in ("wm", "wmark") and lower_value in ("1", "2", "3", "true"):
                value = "0"
            query.append((key, value))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    except Exception:
        return url


def _score_douyin_image_url(url: str, source: str = "") -> int:
    text = f"{source} {url}".lower()
    score = 0
    if source in ("origin_url", "original_url", "large_url"):
        score += 40
    elif source in ("display_url", "url_list"):
        score += 25
    elif source == "download_url_list":
        score -= 10

    for marker in ("origin", "original", "large", "tos-cn", "douyinpic", "image"):
        if marker in text:
            score += 5
    for marker in ("watermark", "wm=1", "wm=2", "wm=3", "_wm", "wmark", "new-water", "-water"):
        if marker in text:
            score -= 30
    return score


def _collect_douyin_image_urls(value: Any, source: str, results: List[Tuple[int, str]]) -> None:
    if isinstance(value, str):
        url = _normalize_douyin_image_url(value)
        if url:
            results.append((_score_douyin_image_url(url, source), url))
        return
    if isinstance(value, list):
        for item in value:
            _collect_douyin_image_urls(item, source, results)
        return
    if isinstance(value, dict):
        if "url_list" in value:
            _collect_douyin_image_urls(value.get("url_list"), source, results)
        elif "url" in value:
            _collect_douyin_image_urls(value.get("url"), source, results)


def _get_douyin_image_url(img: dict) -> str:
    if not isinstance(img, dict):
        return ""

    candidates: List[Tuple[int, str]] = []
    for field in ("origin_url", "original_url", "large_url", "display_url", "url"):
        _collect_douyin_image_urls(img.get(field), field, candidates)
    for field in ("url_list", "download_url_list"):
        _collect_douyin_image_urls(img.get(field), field, candidates)

    seen = set()
    unique_candidates = []
    for score, url in candidates:
        if url in seen:
            continue
        seen.add(url)
        unique_candidates.append((score, url))

    if not unique_candidates:
        return ""
    unique_candidates.sort(key=lambda item: item[0], reverse=True)
    return unique_candidates[0][1]


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
            img_url = _get_douyin_image_url(img)
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
