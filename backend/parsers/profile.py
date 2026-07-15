"""博主主页批量解析 - 提取账号视频列表

分级策略：
  - TikTok / YouTube / B站：yt-dlp extract_flat 提取列表（TikTok/YouTube 需代理）
  - 抖音 / 小红书：抓主页首屏 SSR 数据，尽力而为（翻页需签名反爬，不支持）
"""

import re
import json
import math
import time
import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable
from urllib.parse import urlparse

from ._utils import _make_info, _empty_result, _ok, _fetch, _follow_redirects, DESKTOP_UA
from config import get_active_proxy
from deps import ytdlp_semaphore

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_LIMIT = 20
MAX_PROFILE_LIMIT = 100

# 抖音主页「一次抓全 + 内存缓存」参数
MAX_DOUYIN_FETCH = 300                                # 一次抓全的硬上限（防大号拖垮低配服务端）
_DOUYIN_LIST_CACHE: Dict[str, Dict[str, Any]] = {}   # sec_uid -> {raw, exceeded, author, had_cookie, ts}
_DOUYIN_CACHE_TTL = 600.0                             # 10 分钟；期内翻页/换每页数量复用，不重复抓
_DOUYIN_CACHE_MAX = 20                                # 有界，超出淘汰最旧，控内存
_douyin_fetch_lock = asyncio.Lock()                   # 防同号并发冷启动重复抓全

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
_SSR_PLATFORMS = ("xiaohongshu",)
# 官方 API 抓取的平台（需签名 + 登录 Cookie）
_API_PLATFORMS = ("douyin",)

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
    """归一化主页 URL 为 yt-dlp 最稳的形式"""
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


# ─── 首屏 SSR 分支（抖音 / 小红书，尽力而为）───────────
def _extract_json_after(text: str, marker: str) -> Optional[Any]:
    """从 marker 之后提取一个平衡括号的 JSON 对象/数组（跳过字符串字面量内的括号）"""
    start = text.find(marker)
    if start < 0:
        return None
    i = start + len(marker)
    while i < len(text) and text[i] not in "{[":
        i += 1
    if i >= len(text):
        return None
    open_ch = text[i]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    escaped = False
    for j in range(i, len(text)):
        c = text[j]
        if in_str:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                raw = text[i:j + 1]
                try:
                    return json.loads(raw)
                except Exception:
                    try:
                        return json.loads(raw.replace("undefined", "null"))
                    except Exception:
                        return None
    return None


def _deep_find_lists(obj: Any, key: str) -> List[Any]:
    """深度查找所有指定 key 的列表值"""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key and isinstance(v, list):
                found.append(v)
            found.extend(_deep_find_lists(v, key))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_deep_find_lists(item, key))
    return found


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


async def _parse_profile_xiaohongshu(url: str, limit: int) -> Dict[str, Any]:
    headers = {
        "User-Agent": DESKTOP_UA,
        "Referer": "https://www.xiaohongshu.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    html = await _fetch(url, headers=headers)
    if not html:
        return _empty_result("小红书主页抓取失败，建议粘贴单个视频链接")

    state = _extract_json_after(html, '__INITIAL_STATE__')
    if not isinstance(state, dict):
        return _empty_result("小红书主页首屏无数据（可能被风控），建议粘贴单个视频链接")

    user = state.get("user") or {}
    author = ""
    ui = user.get("userPageData") or {}
    if isinstance(ui, dict):
        author = (ui.get("basicInfo") or {}).get("nickname", "")

    videos: List[Dict[str, Any]] = []
    seen = set()
    # notes 通常是二维数组
    for notes in _deep_find_lists(user, "notes"):
        for group in notes:
            items = group if isinstance(group, list) else [group]
            for wrap in items:
                if not isinstance(wrap, dict):
                    continue
                note = wrap.get("noteCard") or wrap.get("note") or wrap
                nid = wrap.get("id") or note.get("noteId") or note.get("id") or ""
                if not nid or nid in seen:
                    continue
                seen.add(nid)
                cover = note.get("cover") or {}
                cover_url = ""
                if isinstance(cover, dict):
                    cover_url = cover.get("urlDefault") or cover.get("url") or ""
                videos.append(_make_info(
                    id=nid, platform="xiaohongshu",
                    title=(note.get("displayTitle") or note.get("title") or "无标题")[:200],
                    author=author or "未知作者",
                    cover=cover_url,
                    video_url=f"https://www.xiaohongshu.com/explore/{nid}",
                    video_url_no_watermark=f"https://www.xiaohongshu.com/explore/{nid}",
                    detail_url=f"https://www.xiaohongshu.com/explore/{nid}",
                    need_reparse=True,
                ))
                if len(videos) >= limit:
                    break
            if len(videos) >= limit:
                break
        if len(videos) >= limit:
            break

    if not videos:
        return _empty_result("小红书主页首屏无笔记（可能被风控），建议粘贴单个视频链接")

    return _ok({
        "platform": "xiaohongshu", "author": author or "未知作者",
        "profile_url": url, "total": len(videos), "videos": videos,
        "partial": True, "page": 1, "page_size": limit,
        "has_more": False, "total_count": len(videos), "total_pages": 1,
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

    # 小红书 仅首屏，不支持翻页（抖音走 API 支持翻页，不在此拦截）
    if platform in _SSR_PLATFORMS and page > 1:
        return _empty_result("小红书仅支持首屏，不支持翻页；如需更多请粘贴单个视频链接")

    normalized = _normalize_profile_url(url, platform)
    logger.info(f"[主页解析] platform={platform}, url={normalized}, limit={limit}, page={page}")

    if platform in _YTDLP_PLATFORMS:
        return await _parse_profile_ytdlp(normalized, platform, limit, page)
    if platform == "douyin":
        return await _parse_profile_douyin(normalized, limit, page, cookie)
    if platform == "xiaohongshu":
        return await _parse_profile_xiaohongshu(normalized, limit)
    return _empty_result("暂不支持该平台的主页批量解析")
