"""
多平台视频解析模块 - 统一入口
支持：抖音、快手、B站、微博、小红书、TikTok、YouTube、Instagram、Twitter/X、西瓜视频、微信视频号
"""

import time
import random
import asyncio
import logging
from typing import Optional, Dict, Any, List

from ._utils import _extract_url

from . import douyin, bilibili, weibo, xiaohongshu, tiktok, youtube, instagram, twitter, xigua, wechat_channels

logger = logging.getLogger(__name__)

# ─── 平台路由 ────────────────────────────────────────
PLATFORM_MAP = {
    "douyin": (douyin.DOMAINS, douyin.parse),
    "bilibili": (bilibili.DOMAINS, bilibili.parse),
    "weibo": (weibo.DOMAINS, weibo.parse),
    "xiaohongshu": (xiaohongshu.DOMAINS, xiaohongshu.parse),
    "tiktok": (tiktok.DOMAINS, tiktok.parse),
    "youtube": (youtube.DOMAINS, youtube.parse),
    "instagram": (instagram.DOMAINS, instagram.parse),
    "twitter": (twitter.DOMAINS, twitter.parse),
    "xigua": (xigua.DOMAINS, xigua.parse),
    "wechat_channels": (wechat_channels.DOMAINS, wechat_channels.parse),
}


def detect_platform(url: str) -> Optional[str]:
    """根据 URL 自动检测平台"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    for platform, (domains, _) in PLATFORM_MAP.items():
        for d in domains:
            if d in netloc:
                return platform
    return None


# ─── 缓存 ────────────────────────────────────────────
_cache: Dict[str, tuple] = {}
CACHE_TTL = 600  # 10 minutes


def _get_cached(url: str) -> Optional[Dict[str, Any]]:
    if url in _cache:
        ts, result = _cache[url]
        if time.time() - ts < CACHE_TTL:
            return result
        del _cache[url]
    return None


def _set_cache(url: str, result: Dict[str, Any]):
    if result["success"]:
        _cache[url] = (time.time(), result)


# ─── 重试 ────────────────────────────────────────────
async def _parse_with_retry(url: str, platform: str, parser_func) -> Dict[str, Any]:
    """带单次重试的解析"""
    result = await parser_func(url)
    if not result["success"] and result.get("retry") is not False:
        logger.info(f"Parse failed for {platform}, retrying once...")
        await asyncio.sleep(1.0)
        result = await parser_func(url)
    return result


# ─── 统一入口 ────────────────────────────────────────
async def parse_link(url: str) -> Dict[str, Any]:
    """统一入口：自动检测平台并解析（带缓存和重试）"""
    raw_url = _extract_url(url)
    if raw_url:
        url = raw_url

    url = url.strip().rstrip("/")

    # 检查缓存
    cached = _get_cached(url)
    if cached:
        logger.info(f"[解析] 命中缓存: {url[:60]}")
        return cached

    platform = detect_platform(url)
    if platform:
        logger.info(f"[解析] 识别平台: {platform}")
        _, parser_func = PLATFORM_MAP[platform]
        result = await _parse_with_retry(url, platform, parser_func)
        if result.get("success"):
            logger.info(f"[解析] {platform} 解析成功")
        else:
            logger.warning(f"[解析] {platform} 解析失败: {result.get('message', 'unknown')}")
        _set_cache(url, result)
        return result

    logger.warning(f"[解析] 未识别的平台: {url[:60]}")

    return {"success": False, "message": "不支持的平台或无效链接", "data": None}


# ─── 批量解析（并行） ────────────────────────────────
async def batch_parse(urls: List[str]) -> List[Dict[str, Any]]:
    """批量解析 - 并发最多 3 个，带随机延迟防风控"""
    semaphore = asyncio.Semaphore(3)

    async def _parse_one(u: str) -> Dict[str, Any]:
        async with semaphore:
            result = await parse_link(u)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            return result

    tasks = [_parse_one(u.strip()) for u in urls if u.strip()]
    return await asyncio.gather(*tasks)
