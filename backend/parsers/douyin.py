"""抖音解析器"""

import re
import json
import time
import random
import string
import asyncio
import logging
import html as html_lib
from urllib.parse import urlparse, urlsplit, urlunsplit, parse_qsl, urlencode
from typing import Dict, Any, List, Tuple, Optional

import httpx

from ._utils import _headers, _fetch, _follow_redirects, _make_info, _empty_result, _ok, DESKTOP_UA
from ._abogus import get_a_bogus

logger = logging.getLogger(__name__)


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

    # 抖音分享页：iesdouyin.com 旧域名已失效（返回空壳页、不再内嵌 item_list），
    # 优先改用 www.douyin.com 分享页；能拿到 item_list 就用，否则回退旧域名兜底。
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


# ══════════════════════════════════════════════════════════════════════════
# 博主主页视频列表 API
#
# ⚠ 重要维护提示：
#   抖音 Web 主页接口 aweme/v1/web/aweme/post/ 有两道反爬：
#   ① a_bogus 签名（见 _abogus.py，会随抖音前端版本更新失效）；
#   ② 强制登录（anonymous 请求返回 200/0 字节，响应头 x-whale-throughput-abort-data
#      解码为 {"name":"强制登录"}）。因此**必须由用户从浏览器粘贴登录后的 Cookie**
#      （含 sessionid_ss / passport_csrf_token 等），仅靠签名无法拿到数据。
#   失效表现：body 为空 / aweme_list 为空 / status_code!=0。
#   届时：从 f2 等开源项目同步更新 _abogus.py，或提示用户重新粘贴 Cookie。
# ══════════════════════════════════════════════════════════════════════════

_POST_LIST_API = "https://www.douyin.com/aweme/v1/web/aweme/post/"

# ttwid 内存缓存（TTL 1h），避免每次请求都打 register 接口
_ttwid_cache: Dict[str, Any] = {"value": "", "ts": 0.0}
_ttwid_lock = asyncio.Lock()  # 防并发冷启动惊群，多请求只打一次 register
_TTWID_TTL = 3600.0


def _generate_ms_token(length: int = 107) -> str:
    """生成随机 msToken 兜底串（[A-Za-z0-9_-]）"""
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(random.choice(alphabet) for _ in range(length))


async def _get_ttwid(force_refresh: bool = False) -> str:
    """从 ttwid.bytedance.com register 接口获取 ttwid（带内存缓存 + 并发锁）。
    普通首页 GET 不下发 ttwid，只有 register 接口会。拿不到返回空串（不阻断）。
    """
    now = time.time()
    if not force_refresh and _ttwid_cache["value"] and (now - _ttwid_cache["ts"] < _TTWID_TTL):
        return _ttwid_cache["value"]

    async with _ttwid_lock:
        # 拿到锁后二次检查：并发场景下可能已被前一个请求刷新
        now = time.time()
        if not force_refresh and _ttwid_cache["value"] and (now - _ttwid_cache["ts"] < _TTWID_TTL):
            return _ttwid_cache["value"]

        payload = {
            "region": "cn", "aid": 1768, "needFid": False,
            "service": "www.ixigua.com",
            "migrate_info": {"ticket": "", "source": "node"},
            "cbUrlProtocol": "https", "union": True,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=False, trust_env=False) as c:
                r = await c.post(
                    "https://ttwid.bytedance.com/ttwid/union/register/",
                    json=payload,
                    headers={"User-Agent": DESKTOP_UA, "Content-Type": "application/json"},
                )
                set_cookie = r.headers.get("set-cookie", "")
                m = re.search(r"ttwid=([^;]+)", set_cookie)
                if m:
                    _ttwid_cache["value"] = m.group(1)
                    _ttwid_cache["ts"] = now
                    return _ttwid_cache["value"]
        except Exception as e:
            logger.warning(f"[抖音] 获取 ttwid 失败: {type(e).__name__}: {e}")
        return _ttwid_cache["value"]


def _merge_cookie(user_cookie: str, ttwid: str, ms_token: str) -> str:
    """把用户粘贴的登录 Cookie 与 ttwid/msToken 合并成完整 Cookie 头。
    用户 Cookie 中已有的字段优先保留，缺失的用兜底值补齐。
    """
    jar: Dict[str, str] = {}
    if user_cookie:
        # 用户常从 DevTools 整段复制，可能带 "Cookie:" 前缀，去掉避免污染首字段
        user_cookie = re.sub(r"^\s*cookie:\s*", "", user_cookie, flags=re.I)
        for pair in user_cookie.split(";"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                jar[k.strip()] = v.strip()
    if ttwid and "ttwid" not in jar:
        jar["ttwid"] = ttwid
    if "msToken" not in jar:
        jar["msToken"] = ms_token
    return "; ".join(f"{k}={v}" for k, v in jar.items())


async def fetch_user_post_list(
    sec_uid: str, max_cursor: int = 0, count: int = 20, cookie: str = ""
) -> Tuple[List[Dict], int, bool]:
    """调用抖音官方 Web API 拉取博主投稿列表。
    返回 (aweme_list, next_max_cursor, has_more)。
    body 为空 → 刷新 ttwid 重试 1 次；仍空则 raise（签名/登录疑失效）。
    """
    ms_token = _generate_ms_token()

    async def _once(force_refresh: bool) -> Optional[httpx.Response]:
        ttwid = await _get_ttwid(force_refresh=force_refresh)
        params = {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "sec_user_id": sec_uid,
            "max_cursor": str(max_cursor),
            "count": str(count),
            "cookie_enabled": "true",
            "platform": "PC",
            "downlink": "10",
            "effective_type": "4g",
            "round_trip_time": "50",
            "msToken": ms_token,
        }
        query = urlencode(params)
        a_bogus = get_a_bogus(query, DESKTOP_UA)
        params["a_bogus"] = a_bogus
        cookie_header = _merge_cookie(cookie, ttwid, ms_token)
        headers = {
            "User-Agent": DESKTOP_UA,
            "Referer": f"https://www.douyin.com/user/{sec_uid}",
            "Accept": "application/json, text/plain, */*",
            "Cookie": cookie_header,
        }
        # trust_env=False：抖音国内直连，禁走代理，否则被判异常流量
        async with httpx.AsyncClient(timeout=15.0, verify=False, trust_env=False) as c:
            return await c.get(_POST_LIST_API, params=params, headers=headers)

    r = await _once(force_refresh=False)
    if r is None or not r.content or len(r.content) < 50:
        logger.warning("[抖音] 主页 API 首次返回空，刷新 ttwid 重试")
        r = await _once(force_refresh=True)
    if r is None or not r.content or len(r.content) < 50:
        raise RuntimeError("抖音接口返回空数据（登录 Cookie 失效或 a_bogus 签名失效）")

    try:
        data = r.json()
    except Exception:
        raise RuntimeError("抖音接口响应非 JSON（可能被风控或需要重新登录）")

    status_code = data.get("status_code", 0)
    if status_code != 0:
        raise RuntimeError(f"抖音接口风控拦截 (status_code={status_code})")

    aweme_list = data.get("aweme_list") or []
    next_cursor = int(data.get("max_cursor") or 0)
    has_more = bool(data.get("has_more"))
    return aweme_list, next_cursor, has_more


def extract_sec_uid(url: str) -> Optional[str]:
    """从已展开的抖音主页 URL 中提取 sec_uid。
    兼容 /user/{sec_uid} 路径 与 query 中的 sec_uid=... 。
    """
    try:
        parts = urlsplit(url)
    except Exception:
        return None
    m = re.search(r"/user/([A-Za-z0-9_\-=]+)", parts.path)
    if m:
        return m.group(1)
    for k, v in parse_qsl(parts.query):
        if k == "sec_uid" and v:
            return v
    return None
