"""博主主页批量解析 - 提取账号视频列表

分级策略：
  - TikTok / YouTube / B站：yt-dlp extract_flat 提取列表（TikTok/YouTube 需代理）
  - 抖音 / 小红书：调官方接口（a_bogus / x-s 签名 + 登录 Cookie），游标抓全后按页切片
"""

import re
import math
import time
import asyncio
import logging
import secrets
from typing import Dict, Any, List, Optional, Callable, Tuple
from urllib.parse import urlparse, urlsplit, parse_qs, quote

import httpx

from ._utils import _make_info, _empty_result, _ok, _follow_redirects
from config import get_active_proxy
from deps import ytdlp_semaphore
from . import xhs_sign

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_LIMIT = 20
MAX_PROFILE_LIMIT = 100

# 抖音主页「一次抓全 + 内存缓存」参数
MAX_DOUYIN_FETCH = 300                                # 一次抓全的硬上限（防大号拖垮低配服务端）
_DOUYIN_LIST_CACHE: Dict[str, Dict[str, Any]] = {}   # sec_uid -> {raw, exceeded, author, had_cookie, ts}
_DOUYIN_CACHE_TTL = 600.0                             # 10 分钟；期内翻页/换每页数量复用，不重复抓
_DOUYIN_CACHE_MAX = 20                                # 有界，超出淘汰最旧，控内存
_douyin_fetch_lock = asyncio.Lock()                   # 防同号并发冷启动重复抓全

# 小红书主页「一次抓全 + 内存缓存」参数（结构对齐抖音）
MAX_XHS_FETCH = 300
_XHS_LIST_CACHE: Dict[str, Dict[str, Any]] = {}      # user_id -> {raw, exceeded, author, had_cookie, ts}
_XHS_CACHE_TTL = 600.0
_XHS_CACHE_MAX = 20
_xhs_fetch_lock = asyncio.Lock()

_XHS_HOST = "https://edith.xiaohongshu.com"
_XHS_USER_POSTED = "/api/sns/web/v1/user_posted"

# 单视频 URL 特征（用于排除"这是单视频而非主页"的误判）
_SINGLE_VIDEO_PATTERNS = {
    "tiktok": re.compile(r"/video/\d+"),
    "youtube": re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/|/embed/|/watch)"),
    "bilibili": re.compile(r"/video/BV[\w]{10}"),
    "douyin": re.compile(r"/(?:video|note)/\d+"),
    "xiaohongshu": re.compile(r"/(?:explore|discovery/item)/\w+"),
}

# 主页 URL 特征（按平台）
_PROFILE_PATTERNS = {
    "tiktok": [re.compile(r"tiktok\.com/@[\w.-]+/?(?:\?|$)")],
    "youtube": [
        re.compile(r"youtube\.com/@[\w.-]+(?:/(?:videos|shorts|live|streams|featured))?/?(?:\?|$)"),
        re.compile(r"youtube\.com/(?:c|channel|user)/[\w.-]+(?:/(?:videos|shorts|live))?/?(?:\?|$)"),
    ],
    "bilibili": [re.compile(r"space\.bilibili\.com/\d+(?:/\w+)?/?(?:\?|$)")],
    "douyin": [re.compile(r"(?:ies)?douyin\.com/(?:share/)?user/[\w.=-]+")],
    "xiaohongshu": [re.compile(r"xiaohongshu\.com/user/profile/\w+")],
}

# yt-dlp 引擎覆盖的平台
_YTDLP_PLATFORMS = ("tiktok", "youtube", "bilibili")
# 首屏 SSR 抓取的平台（尽力而为）
_SSR_PLATFORMS = ()
# 官方 API 抓取的平台（需签名 + 登录 Cookie）
_API_PLATFORMS = ("douyin", "xiaohongshu")

_PLATFORM_HEADERS = {
    "tiktok": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.tiktok.com/",
    },
    "youtube": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    },
    "bilibili": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.bilibili.com/",
    },
}


# ─── URL 检测 ────────────────────────────────────────
def detect_profile_url(url: str) -> Optional[str]:
    """检测 URL 是否为受支持的主页链接，返回平台名；否则 None"""
    from . import detect_platform
    raw = url.strip().rstrip("/")
    platform = detect_platform(raw)
    if not platform or platform not in _PROFILE_PATTERNS:
        return None
    # 先排除单视频 URL（如 tiktok.com/@user/video/123）
    sp = _SINGLE_VIDEO_PATTERNS.get(platform)
    if sp and sp.search(raw):
        return None
    for pat in _PROFILE_PATTERNS[platform]:
        if pat.search(raw):
            return platform
    return None


def _normalize_profile_url(url: str, platform: str) -> str:
    """归一化主页 URL 为各引擎最稳的形式。

    注意：小红书必须保留 query——xsec_token/xsec_source 是 user_posted 接口
    鉴权与签名的必需参数，不能像其他平台那样 strip。
    """
    if platform == "xiaohongshu":
        return url.strip()  # 保留完整 query
    url = url.split("?")[0].rstrip("/")
    if platform == "youtube":
        path = urlparse(url).path.rstrip("/")
        last_seg = path.rsplit("/", 1)[-1] if path else ""
        if last_seg not in ("videos", "shorts", "live", "streams", "featured"):
            url = url + "/videos"
    elif platform == "bilibili":
        if not url.endswith("/video"):
            url = url + "/video"
    elif platform == "douyin":
        # 短链展开后可能是 iesdouyin.com/share/user/{sec_uid}，统一成标准主页 URL
        m = re.search(r"/user/([\w.=-]+)", urlparse(url).path)
        if m:
            url = f"https://www.douyin.com/user/{m.group(1)}"
    return url


# ─── entry 转换 ──────────────────────────────────────
def _pick_thumbnail(thumbnails: Optional[List[Dict]]) -> str:
    if not thumbnails:
        return ""
    best = max(thumbnails, key=lambda t: t.get("preference", -10) or -10)
    return best.get("url", "")


def _convert_tiktok_entry(e: Dict, author_hint: str) -> Optional[Dict[str, Any]]:
    url = e.get("url") or ""
    m = re.search(r"/@([\w.-]+)/video/(\d+)", url)
    if not m:
        return None
    user, vid = m.group(1), m.group(2)
    title = (e.get("title") or e.get("description") or "无标题").strip()
    return _make_info(
        id=vid, platform="tiktok",
        title=title[:200],
        author=e.get("uploader") or user or author_hint,
        cover=_pick_thumbnail(e.get("thumbnails")),
        duration=int(e.get("duration") or 0),
        video_url=f"tt://@{user}/video/{vid}",
        video_url_no_watermark=f"tt://@{user}/video/{vid}",
        digg_count=e.get("like_count") or 0,
        comment_count=e.get("comment_count") or 0,
        share_count=e.get("repost_count") or 0,
    )


def _convert_youtube_entry(e: Dict, author_hint: str) -> Optional[Dict[str, Any]]:
    url = e.get("url") or ""
    m = re.search(r"(?:v=|/shorts/|/live/)([\w-]{11})", url) or re.search(r"([\w-]{11})", url)
    if not m:
        return None
    vid = m.group(1)
    cover = _pick_thumbnail(e.get("thumbnails")) or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    return _make_info(
        id=vid, platform="youtube",
        title=(e.get("title") or "无标题").strip()[:200],
        author=author_hint or "未知作者",
        cover=cover,
        duration=int(e.get("duration") or 0),
        video_url=f"yt://{vid}",
        video_url_no_watermark=f"yt://{vid}",
    )


def _convert_bilibili_entry(e: Dict, author_hint: str) -> Optional[Dict[str, Any]]:
    url = e.get("url") or ""
    m = re.search(r"(BV[\w]{10})", url)
    if not m:
        return None
    bvid = m.group(1)
    return _make_info(
        id=bvid, platform="bilibili",
        title=(e.get("title") or "无标题").strip()[:200],
        author=e.get("uploader") or author_hint or "未知作者",
        cover=e.get("thumbnail") or _pick_thumbnail(e.get("thumbnails")),
        duration=int(e.get("duration") or 0),
        video_url=f"bl://{bvid}",
        video_url_no_watermark=f"bl://{bvid}",
    )


_CONVERTERS: Dict[str, Callable] = {
    "tiktok": _convert_tiktok_entry,
    "youtube": _convert_youtube_entry,
    "bilibili": _convert_bilibili_entry,
}


# ─── yt-dlp 分支 ─────────────────────────────────────
async def _parse_profile_ytdlp(url: str, platform: str, limit: int, page: int = 1) -> Dict[str, Any]:
    proxy = get_active_proxy()
    if platform in ("tiktok", "youtube") and not proxy:
        return _empty_result(f"{platform} 主页解析需要可访问外网的代理，请先在上方配置代理")

    start = (page - 1) * limit + 1
    end = page * limit

    def _extract():
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "extract_flat": "in_playlist",
            "playliststart": start,
            "playlistend": end,
            "socket_timeout": 20 if proxy else 8,
            "http_headers": _PLATFORM_HEADERS.get(platform, {}),
        }
        if proxy:
            ydl_opts["proxy"] = proxy
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        async with ytdlp_semaphore:
            info = await asyncio.to_thread(_extract)
    except Exception as e:
        err = str(e)[:200]
        logger.warning(f"[主页解析] yt-dlp 失败 {platform}: {err}")
        hint = ""
        if "412" in err and platform == "bilibili":
            hint = "（B站风控拦截，可稍后再试或改用单视频链接）"
        elif "Unsupported URL" in err:
            hint = "（请粘贴博主主页链接，而非视频/合集链接）"
        return _empty_result(f"主页解析失败: {err}{hint}")

    if not info:
        return _empty_result("解析结果为空")

    entries = info.get("entries") or []

    # YouTube 兜底：返回的是 tab 索引（url=None）而非视频，追加 /videos 重试
    if platform == "youtube" and entries:
        first = entries[0]
        if first and first.get("url") is None and not url.endswith("/videos"):
            logger.info("[主页解析] YouTube 返回 tab 索引，追加 /videos 重试")
            return await _parse_profile_ytdlp(url + "/videos", platform, limit, page)

    author_hint = info.get("title") or info.get("uploader") or ""
    if platform == "youtube" and author_hint:
        author_hint = re.sub(r"\s+-\s+(Videos|Shorts|Live|Streams|Featured)$", "", author_hint).strip()

    converter = _CONVERTERS[platform]
    videos: List[Dict[str, Any]] = []
    seen = set()
    for e in entries:
        if not e:
            continue
        try:
            item = converter(e, author_hint)
        except Exception as ex:
            logger.warning(f"[主页解析] entry 转换失败: {ex}")
            continue
        if not item or item["id"] in seen:
            continue
        seen.add(item["id"])
        videos.append(item)
        if len(videos) >= limit:
            break

    if not videos:
        if page > 1:
            return _empty_result("已经是最后一页，没有更多视频了")
        return _empty_result("未解析到任何视频，可能该账号无视频或被风控")

    # 翻页信息：拿满一页则推断还有下一页；playlist_count 可用时算总页数
    has_more = len(videos) >= limit
    total_count = info.get("playlist_count")
    total_pages = math.ceil(total_count / limit) if isinstance(total_count, int) and total_count > 0 else None

    return _ok({
        "platform": platform,
        "author": author_hint or "未知作者",
        "profile_url": url,
        "total": len(videos),
        "videos": videos,
        "page": page,
        "page_size": limit,
        "has_more": has_more,
        "total_count": total_count,
        "total_pages": total_pages,
    })


# ─── 官方 API 分支（抖音 / 小红书，游标抓全 + 缓存 + 切片）───────────
async def _get_douyin_full_list(sec_uid: str, cookie: str) -> Dict[str, Any]:
    """一次性抓全抖音博主投稿列表（上限 MAX_DOUYIN_FETCH），带 per-sec_uid 内存缓存。

    抖音接口是游标（max_cursor/has_more）分页，且每批返回条数由服务端决定（会递减）。
    此处循环推进游标累积至抓完或触顶，按 aweme_id 去重，供上层按页码切片——
    从而保证每页条数一致、总数可知。返回 {"raw", "exceeded", "author", "ts"}。
    匿名（无 Cookie）通常只能拿首批（~32 条），游标推进返回空即停。
    """
    from .douyin import fetch_user_post_list

    has_cookie = bool(cookie)

    def _usable(e: Dict[str, Any]) -> bool:
        # 未过期，且不能用「匿名残缺缓存」应付「带 Cookie 的请求」
        # （匿名仅首屏 ~32 条，带 Cookie 需重抓才能拿全）
        if time.time() - e["ts"] >= _DOUYIN_CACHE_TTL:
            return False
        if has_cookie and not e.get("had_cookie"):
            return False
        return True

    ent = _DOUYIN_LIST_CACHE.get(sec_uid)
    if ent and _usable(ent):
        return ent

    async with _douyin_fetch_lock:
        # 拿锁后二次检查：并发同号时可能已被前一个请求抓好
        ent = _DOUYIN_LIST_CACHE.get(sec_uid)
        if ent and _usable(ent):
            return ent

        collected: List[Dict[str, Any]] = []
        seen: set = set()
        cursor = 0
        has_more = True
        exceeded = False
        author = ""

        while has_more and len(collected) < MAX_DOUYIN_FETCH:
            aweme_list, next_cursor, has_more = await fetch_user_post_list(
                sec_uid, max_cursor=cursor, count=50, cookie=cookie
            )
            if not aweme_list:
                break
            for it in aweme_list:
                if not isinstance(it, dict):
                    continue
                vid = str(it.get("aweme_id") or "")
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                collected.append(it)
                if not author:
                    author = (it.get("author") or {}).get("nickname", "")
            cursor = next_cursor
            if len(collected) >= MAX_DOUYIN_FETCH:
                exceeded = has_more  # 触顶但抖音仍有更多 → 标记超上限
                break
            if has_more:
                await asyncio.sleep(0.4)  # 防风控轻微延时

        ent = {"raw": collected, "exceeded": exceeded, "author": author,
               "had_cookie": has_cookie, "ts": time.time()}
        # 写缓存前控内存：超出上限淘汰最旧一条
        if sec_uid not in _DOUYIN_LIST_CACHE and len(_DOUYIN_LIST_CACHE) >= _DOUYIN_CACHE_MAX:
            oldest = min(_DOUYIN_LIST_CACHE, key=lambda k: _DOUYIN_LIST_CACHE[k]["ts"])
            _DOUYIN_LIST_CACHE.pop(oldest, None)
        _DOUYIN_LIST_CACHE[sec_uid] = ent
        return ent


async def _parse_profile_douyin(url: str, limit: int, page: int = 1, cookie: str = "") -> Dict[str, Any]:
    """抖音博主主页：一次抓全（≤300）后按页码切片，保证每页条数一致、总数可知。

    需 a_bogus 签名 + 用户登录 Cookie（匿名仅首屏 ~32 条）。抓全结果按 sec_uid 缓存，
    翻页/换每页数量在 TTL 内复用，不重复抓。实际下载仍复用最稳的 iesdouyin 单视频路径
    （need_reparse=True，下载时前端回填）。
    """
    from .douyin import extract_sec_uid

    sec_uid = extract_sec_uid(url)
    if not sec_uid:
        return _empty_result("无法从链接中提取用户 sec_uid，请确认是抖音主页链接")

    try:
        ent = await _get_douyin_full_list(sec_uid, cookie)
    except RuntimeError as e:
        msg = str(e)
        if page > 1 and not cookie:
            return _empty_result("抖音匿名仅能获取第一页，翻页请在上方展开并粘贴登录 Cookie")
        if "登录" in msg or "a_bogus" in msg or "空数据" in msg:
            return _empty_result("抖音接口未返回数据：登录 Cookie 可能失效，请重新从浏览器粘贴 Cookie")
        if "风控" in msg:
            return _empty_result("可能被抖音风控拦截，请稍后再试")
        return _empty_result(f"抖音主页解析失败：{msg}")
    except Exception as e:
        logger.warning(f"[抖音主页] 请求异常: {type(e).__name__}: {e}")
        return _empty_result("抖音主页请求异常，请稍后再试")

    raw = ent["raw"]
    author = ent["author"]
    if not raw:
        return _empty_result("未获取到作品：该账号可能无公开作品/为私密账号，或登录 Cookie 已失效")

    page_size = limit
    total = len(raw)
    total_pages = max(1, math.ceil(total / page_size))
    start = (page - 1) * page_size
    window = raw[start:start + page_size]  # 精确切片 → 每页条数一致（末页可不足）

    if not window:
        # 请求页超出范围：匿名多为「首屏之外需登录」，其余为「没有更多」
        if page > 1 and not cookie:
            return _empty_result("抖音匿名仅能获取第一页，翻页请在上方展开并粘贴登录 Cookie")
        return _empty_result("该页没有作品了")

    videos: List[Dict[str, Any]] = []
    for item in window:
        vid = str(item.get("aweme_id") or "")
        if not vid:
            continue
        video = item.get("video") or {}
        cover = video.get("cover") or video.get("origin_cover") or {}
        cover_url = ""
        if isinstance(cover, dict):
            ul = cover.get("url_list") or []
            cover_url = ul[0] if ul else ""
        stats = item.get("statistics") or {}
        videos.append(_make_info(
            id=vid, platform="douyin",
            title=(item.get("desc") or "无标题")[:200],
            author=author or "未知作者",
            cover=cover_url,
            duration=(video.get("duration") or 0) // 1000,
            video_url=f"https://www.douyin.com/video/{vid}",
            video_url_no_watermark=f"https://www.douyin.com/video/{vid}",
            detail_url=f"https://www.douyin.com/video/{vid}",
            need_reparse=True,
            create_time=item.get("create_time", 0),
            digg_count=stats.get("digg_count", 0),
            comment_count=stats.get("comment_count", 0),
            share_count=stats.get("share_count", 0),
        ))

    return _ok({
        "platform": "douyin", "author": author or "未知作者",
        "profile_url": url, "total": len(videos), "videos": videos,
        "page": page, "page_size": page_size,
        "total_count": total, "total_pages": total_pages,
        "has_more": page < total_pages,       # 从缓存判断，可靠
        "exceeded_cap": ent["exceeded"],      # 超 300 → 前端提示
        "anonymous": not bool(cookie),        # 未登录 → 前端提示登录可获取全部
    })


def extract_xhs_user_id(url: str) -> Tuple[str, str, str]:
    """从小红书主页 URL 提取 (user_id, xsec_token, xsec_source)。

    URL 形如 /user/profile/<user_id>?xsec_token=...&xsec_source=pc_note
    xsec_token / xsec_source 是 user_posted 接口鉴权必需，缺 source 缺省 pc_feed。
    """
    parts = urlsplit(url)
    m = re.search(r"/user/profile/([0-9a-fA-F]+)", parts.path)
    user_id = m.group(1) if m else ""
    q = parse_qs(parts.query)
    xsec_token = (q.get("xsec_token") or [""])[0]
    xsec_source = (q.get("xsec_source") or [""])[0] or "pc_feed"
    return user_id, xsec_token, xsec_source


def _extract_a1(cookie: str) -> str:
    """从 cookie 串解析 a1 字段值（签名必需）。"""
    m = re.search(r"(?:^|;)\s*a1=([^;]+)", cookie or "")
    return m.group(1).strip() if m else ""


def _xhs_headers(cookie: str, sign_ret: Dict[str, str]) -> Dict[str, str]:
    """组装 user_posted 请求头（签名头 + 追踪头 + 模板头 + Cookie）。"""
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://www.xiaohongshu.com",
        "Referer": "https://www.xiaohongshu.com/",
        "x-s": sign_ret.get("xs", ""),
        "x-t": sign_ret.get("xt", ""),
        "x-s-common": sign_ret.get("xs_common", ""),
        "x-b3-traceid": secrets.token_hex(8),
        "x-xray-traceid": secrets.token_hex(16),
        "Cookie": cookie,
    }


async def _fetch_xhs_user_posted(
    user_id: str, cursor: str, cookie: str, a1: str,
    xsec_token: str, xsec_source: str,
) -> Tuple[List[Dict[str, Any]], str, bool]:
    """拉取一批 user_posted，返回 (notes, next_cursor, has_more)。

    签名入参 api 必须是拼好 query 的完整路径。接口 HTTP 200 但 success=false
    表示登录失效/风控/token 过期 → 抛 RuntimeError(msg) 由上层转可读提示。
    """
    query = (
        f"num=30&cursor={quote(cursor, safe='')}&user_id={user_id}"
        f"&image_formats=jpg,webp,avif&xsec_token={quote(xsec_token, safe='')}&xsec_source={xsec_source}"
    )
    api = f"{_XHS_USER_POSTED}?{query}"

    sign_ret = await xhs_sign.sign(api, a1, "", "GET")
    headers = _xhs_headers(cookie, sign_ret)

    async with httpx.AsyncClient(timeout=15.0, verify=False, trust_env=False) as client:
        r = await client.get(_XHS_HOST + api, headers=headers)

    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    try:
        body = r.json()
    except Exception:
        raise RuntimeError("响应非 JSON（可能被风控拦截）")

    if not body.get("success", False):
        msg = body.get("msg") or f"code={body.get('code')}"
        raise RuntimeError(msg)

    data = body.get("data") or {}
    notes = data.get("notes") or []
    next_cursor = data.get("cursor") or ""
    has_more = bool(data.get("has_more"))
    return notes, next_cursor, has_more


async def _get_xhs_full_list(
    user_id: str, cookie: str, a1: str, xsec_token: str, xsec_source: str,
) -> Dict[str, Any]:
    """一次性抓全小红书博主笔记（上限 MAX_XHS_FETCH），带 per-user_id 内存缓存。

    游标（cursor/has_more）分页，按 note_id 去重累积至抓完或触顶，供上层按页切片。
    结构与 _get_douyin_full_list 一致：返回 {"raw","exceeded","author","had_cookie","ts"}。
    """
    has_cookie = bool(cookie)

    def _usable(e: Dict[str, Any]) -> bool:
        if time.time() - e["ts"] >= _XHS_CACHE_TTL:
            return False
        if has_cookie and not e.get("had_cookie"):
            return False
        return True

    ent = _XHS_LIST_CACHE.get(user_id)
    if ent and _usable(ent):
        return ent

    async with _xhs_fetch_lock:
        ent = _XHS_LIST_CACHE.get(user_id)
        if ent and _usable(ent):
            return ent

        collected: List[Dict[str, Any]] = []
        seen: set = set()
        cursor = ""
        has_more = True
        exceeded = False
        author = ""

        while has_more and len(collected) < MAX_XHS_FETCH:
            notes, next_cursor, has_more = await _fetch_xhs_user_posted(
                user_id, cursor, cookie, a1, xsec_token, xsec_source
            )
            if not notes:
                break
            for it in notes:
                if not isinstance(it, dict):
                    continue
                nid = str(it.get("note_id") or "")
                if not nid or nid in seen:
                    continue
                seen.add(nid)
                collected.append(it)
                if not author:
                    author = (it.get("user") or {}).get("nickname", "")
            cursor = next_cursor
            if len(collected) >= MAX_XHS_FETCH:
                exceeded = has_more
                break
            if has_more:
                await asyncio.sleep(0.4)

        ent = {"raw": collected, "exceeded": exceeded, "author": author,
               "had_cookie": has_cookie, "ts": time.time()}
        if user_id not in _XHS_LIST_CACHE and len(_XHS_LIST_CACHE) >= _XHS_CACHE_MAX:
            oldest = min(_XHS_LIST_CACHE, key=lambda k: _XHS_LIST_CACHE[k]["ts"])
            _XHS_LIST_CACHE.pop(oldest, None)
        _XHS_LIST_CACHE[user_id] = ent
        return ent


async def _parse_profile_xiaohongshu(url: str, limit: int, page: int = 1, cookie: str = "") -> Dict[str, Any]:
    """小红书博主主页：真实 user_posted 接口 + 登录 Cookie + 游标抓全（≤300）后按页切片。

    小红书强制要求 Cookie（anonymous 恒 False）：签名需 cookie 里的 a1，接口需登录态。
    抓全结果按 user_id 缓存，翻页/换每页数量在 TTL 内复用。下载沿用单视频路径
    （need_reparse=True，前端回填）。
    """
    user_id, xsec_token, xsec_source = extract_xhs_user_id(url)
    if not user_id:
        return _empty_result("无法从链接提取小红书用户 ID，请确认是主页链接")
    if not cookie:
        return _empty_result("小红书主页解析需要登录 Cookie，请在下方展开并粘贴")
    a1 = _extract_a1(cookie)
    if not a1:
        return _empty_result("Cookie 缺少 a1 字段，请重新从浏览器复制完整登录 Cookie")

    try:
        ent = await _get_xhs_full_list(user_id, cookie, a1, xsec_token, xsec_source)
    except RuntimeError as e:
        msg = str(e)
        if "签名" in msg or "node" in msg:
            return _empty_result(f"小红书签名失败：{msg}")
        return _empty_result(f"小红书接口失败：{msg}（Cookie 可能失效或 xsec_token 过期，请重新从浏览器复制主页链接）")
    except Exception as e:
        logger.warning(f"[小红书主页] 请求异常: {type(e).__name__}: {e}")
        return _empty_result("小红书主页请求异常，请稍后再试")

    raw = ent["raw"]
    author = ent["author"]
    if not raw:
        return _empty_result("未获取到作品（可能 Cookie 失效或 xsec_token 过期，请重新从浏览器复制主页链接）")

    page_size = limit
    total = len(raw)
    total_pages = max(1, math.ceil(total / page_size))
    start = (page - 1) * page_size
    window = raw[start:start + page_size]
    if not window:
        return _empty_result("该页没有作品了")

    videos: List[Dict[str, Any]] = []
    for it in window:
        nid = str(it.get("note_id") or "")
        if not nid:
            continue
        cover = it.get("cover") or {}
        cover_url = ""
        if isinstance(cover, dict):
            cover_url = cover.get("url_default") or cover.get("url") or ""
        note_token = it.get("xsec_token") or xsec_token
        detail = f"https://www.xiaohongshu.com/explore/{nid}?xsec_token={note_token}"
        videos.append(_make_info(
            id=nid, platform="xiaohongshu",
            title=(it.get("display_title") or "无标题")[:200],
            author=(it.get("user") or {}).get("nickname", "") or author or "未知作者",
            cover=cover_url,
            video_url=detail,
            video_url_no_watermark=detail,
            detail_url=detail,
            need_reparse=True,
        ))

    return _ok({
        "platform": "xiaohongshu", "author": author or "未知作者",
        "profile_url": url, "total": len(videos), "videos": videos,
        "page": page, "page_size": page_size,
        "total_count": total, "total_pages": total_pages,
        "has_more": page < total_pages,
        "exceeded_cap": ent["exceeded"],
        "anonymous": False,
    })


# ─── 统一入口 ────────────────────────────────────────
_SHORT_LINK_HOSTS = ("v.douyin.com", "vm.tiktok.com", "vt.tiktok.com", "b23.tv", "xhslink.com", "youtu.be")


async def parse_profile(url: str, limit: int = DEFAULT_PROFILE_LIMIT, page: int = 1, cookie: str = "") -> Dict[str, Any]:
    """解析博主主页，返回视频列表（yt-dlp/抖音 API 支持分页；抖音需登录 Cookie）"""
    url = url.strip()
    limit = min(max(limit, 1), MAX_PROFILE_LIMIT)
    page = max(page, 1)

    from . import detect_platform

    # 短链先展开（v.douyin.com / vm.tiktok.com / b23.tv 等多为单视频分享链）
    host = urlparse(url).netloc.lower()
    if any(h in host for h in _SHORT_LINK_HOSTS):
        try:
            expanded = await _follow_redirects(url)
            if expanded:
                url = expanded
        except Exception as e:
            logger.warning(f"[主页解析] 短链展开失败: {str(e)[:100]}")

    platform = detect_platform(url)
    if not platform or platform not in (_YTDLP_PLATFORMS + _SSR_PLATFORMS + _API_PLATFORMS):
        return _empty_result(f"当前不支持该平台的主页批量解析：{platform or '未知平台'}")

    sp = _SINGLE_VIDEO_PATTERNS.get(platform)
    if sp and sp.search(url.rstrip("/")):
        return _empty_result("该链接是单视频链接，请使用「链接解析」功能")

    # 严格校验必须是主页 URL（排除合集/搜索/关于等子页面）
    if detect_profile_url(url) != platform:
        return _empty_result("请粘贴博主主页链接（不支持合集 / 搜索 / 子页面）")

    normalized = _normalize_profile_url(url, platform)
    # 小红书 URL 带 xsec_token（临时鉴权凭证），日志只记 path 不记 query
    log_url = normalized.split("?", 1)[0] if platform == "xiaohongshu" else normalized
    logger.info(f"[主页解析] platform={platform}, url={log_url}, limit={limit}, page={page}")

    if platform in _YTDLP_PLATFORMS:
        return await _parse_profile_ytdlp(normalized, platform, limit, page)
    if platform == "douyin":
        return await _parse_profile_douyin(normalized, limit, page, cookie)
    if platform == "xiaohongshu":
        return await _parse_profile_xiaohongshu(normalized, limit, page, cookie)
    return _empty_result("暂不支持该平台的主页批量解析")
