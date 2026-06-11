"""微信视频号解析器"""

import os
import re
import json
import random
import time
import logging
import asyncio
from typing import Dict, Any, Optional
from urllib.parse import urlparse, parse_qs, quote

import httpx

from ._utils import _make_info, _empty_result, _ok

YUANBAO_COOKIE = os.environ.get("YUANBAO_COOKIE", "")


def update_cookie(new_cookie: str):
    """运行时更新 cookie（热更新，无需重启）"""
    global YUANBAO_COOKIE
    YUANBAO_COOKIE = new_cookie
    os.environ["YUANBAO_COOKIE"] = new_cookie
    logger.info("[视频号] Yuanbao cookie 已更新")

logger = logging.getLogger(__name__)

DOMAINS = ["channels.weixin.qq.com", "weixin.qq.com"]

_CHANNELS_PATTERNS = [
    r'channels\.weixin\.qq\.com/web/pages/feed/([a-f0-9]+)',
    r'channels\.weixin\.qq\.com/web/pages/feed\?feedId=([a-f0-9]+)',
    r'channels\.weixin\.qq\.com/finder-preview/pages/sph\?id=([a-zA-Z0-9]+)',
    r'feedId=([a-f0-9]+)',
]

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# Yuanbao API（主方案）
YUANBAO_API = 'https://yuanbao.tencent.com/api/weixin/get_parse_result'
# Cloudflare Worker API（备用方案）
WORKER_API = 'https://sph.litao.workers.dev/api/fetch_video_profile'
# get_feed_info API
FEED_INFO_API = 'https://channels.weixin.qq.com/finder-preview/api/feed/get_feed_info'


def _parse_count(s) -> int:
    if not s:
        return 0
    s = str(s).replace(',', '')
    if '万' in s:
        return int(float(s.replace('万', '')) * 10000)
    try:
        return int(s)
    except (ValueError, TypeError):
        return 0


def _generate_rid() -> str:
    ts_hex = hex(int(time.time()))[2:]
    rand_hex = ''.join([hex(random.randint(0, 15))[2:] for _ in range(8)])
    return f'{ts_hex}-{rand_hex}'


async def parse(url: str) -> Dict[str, Any]:
    """主解析入口"""
    if url.startswith("{") or url.startswith("["):
        return parse_video_info(url)
    elif "channels.weixin.qq.com" in url:
        return await _parse_url(url)
    elif "weixin.qq.com/sph/" in url:
        return await _parse_url(url)
    elif url.startswith("http") and ("mp4" in url or "m3u8" in url or "video" in url):
        return _ok(_make_info(
            id="wx_video", platform="wechat_channels", title="微信视频号",
            video_url=url, video_url_no_watermark=url,
        ))
    else:
        return _empty_result("请输入视频号分享链接")


async def _parse_url(url: str) -> Dict[str, Any]:
    """解析视频号链接：Yuanbao API → Worker API → get_feed_info（兜底）"""
    video_id = _extract_video_id(url)
    if not video_id:
        return _empty_result("无法从链接中提取视频ID")

    logger.info(f"[视频号] 解析 video_id: {video_id}")

    # 方案 1: Yuanbao API（需要 cookie）
    if YUANBAO_COOKIE:
        result = await _fetch_via_yuanbao(url)
        if result and result.get("success"):
            logger.info(f"[视频号] Yuanbao 解析成功")
            return result
        logger.warning(f"[视频号] Yuanbao 解析失败，尝试 Worker")

    # 方案 2: Worker API（备用）
    worker_task = asyncio.wait_for(_fetch_via_worker(url), timeout=12.0)
    try:
        worker_result = await worker_task
        if worker_result and worker_result.get("success"):
            logger.info(f"[视频号] Worker 解析成功")
            return worker_result
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning(f"[视频号] Worker 失败: {e}")

    # 方案 3: get_feed_info 短链接（仅元数据，无视频 URL）
    feed_data = await _get_feed_info_short(video_id)
    if feed_data:
        result = _build_result_from_feed(video_id, feed_data)
        if result["success"]:
            logger.info(f"[视频号] get_feed_info 元数据成功（无视频直链）")
            return result

    return _empty_result("解析失败。请确保 Yuanbao cookie 有效，或稍后重试")


async def _fetch_via_yuanbao(url: str) -> Optional[Dict[str, Any]]:
    """Yuanbao 两步解析：Step1 获取 token/eid → Step2 获取视频 URL"""
    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
            # Step 1: Yuanbao API → playable_url
            payload = {'type': 'video_channel_url', 'url': url, 'scene': 1}
            headers = {
                'accept': 'application/json, text/plain, */*',
                'content-type': 'application/json',
                'origin': 'https://yuanbao.tencent.com',
                'referer': 'https://yuanbao.tencent.com/chat/naQivTmsDa/cf4d0079-ed1b-4c55-a3f3-2ca1379727d1',
                'user-agent': UA,
                'cookie': YUANBAO_COOKIE,
            }

            resp1 = await client.post(YUANBAO_API, json=payload, headers=headers)
            if resp1.status_code != 200:
                logger.warning(f"[视频号] Yuanbao API 状态码: {resp1.status_code}")
                return None

            data1 = resp1.json()
            if data1.get('code') != 0:
                logger.warning(f"[视频号] Yuanbao API 错误: {data1.get('msg')}")
                return None

            parse_data = data1.get('data', {})
            playable_url = parse_data.get('playable_url', '')
            export_id_raw = parse_data.get('wx_export_id', '')

            if not playable_url and not export_id_raw:
                logger.warning("[视频号] Yuanbao 返回数据为空")
                return None

            # 从 playable_url 提取 token 和 eid
            general_token = ''
            export_id = ''
            if playable_url:
                parsed = urlparse(playable_url)
                params = parse_qs(parsed.query)
                general_token = params.get('token', [''])[0]
                export_id = params.get('eid', [''])[0]

            if not export_id:
                export_id = export_id_raw

            if not general_token or not export_id:
                logger.warning(f"[视频号] 无法提取 token/eid, playable_url: {playable_url[:100]}")
                return None

            # Step 2: get_feed_info with exportId + generalToken
            rid = _generate_rid()
            feed_payload = {'baseReq': {'generalToken': general_token}, 'exportId': export_id}
            referer = (
                f'https://channels.weixin.qq.com/finder-preview/pages/feed'
                f'?entry_card_type=48&comment_scene=39&appid=0'
                f'&token={quote(general_token)}&entry_scene=0&eid={quote(export_id)}'
            )
            feed_headers = {
                'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/json',
                'Origin': 'https://channels.weixin.qq.com',
                'Referer': referer,
                'User-Agent': UA,
            }

            api_url = f'{FEED_INFO_API}?_rid={rid}&_pageUrl=https%3A%2F%2Fchannels.weixin.qq.com%2Ffinder-preview%2Fpages%2Ffeed'
            resp2 = await client.post(api_url, json=feed_payload, headers=feed_headers)
            data2 = resp2.json()

            if data2.get('errCode') != 0:
                logger.warning(f"[视频号] get_feed_info 错误: {data2.get('errMsg')}")
                return None

            return _build_full_result(data2.get('data', {}), url)

    except Exception as e:
        logger.error(f"[视频号] Yuanbao 解析异常: {e}")
        return None


def _clean_video_url(video_url: str) -> str:
    """精简视频 URL，只保留 encfilekey 和 token（核心鉴权参数）"""
    if not video_url:
        return ''
    try:
        parsed = urlparse(video_url)
        encfilekey = parsed.query.split('encfilekey=')[1].split('&')[0] if 'encfilekey=' in parsed.query else ''
        token = parsed.query.split('token=')[1].split('&')[0] if 'token=' in parsed.query else ''
        if encfilekey and token:
            return f'{parsed.scheme}://{parsed.netloc}{parsed.path}?encfilekey={encfilekey}&token={token}'
    except Exception:
        pass
    return video_url


def _build_full_result(feed_data: dict, url: str) -> Dict[str, Any]:
    """从 get_feed_info 完整响应构建结果（含视频 URL）"""
    feed_info = feed_data.get('feedInfo', {})
    author_info = feed_data.get('authorInfo', {})

    if not feed_info:
        return _empty_result("API 返回数据为空")

    # 提取视频 URL（优先 h264）
    video_url = ''
    h264 = feed_info.get('h264VideoInfo', {})
    h265 = feed_info.get('h265VideoInfo', {})
    if h264 and h264.get('videoUrl'):
        video_url = h264['videoUrl']
    elif h265 and h265.get('videoUrl'):
        video_url = h265['videoUrl']
    elif feed_info.get('videoUrl'):
        video_url = feed_info['videoUrl']

    # 精简 URL：只保留核心鉴权参数
    video_url = _clean_video_url(video_url)

    title = feed_info.get('description', '') or feed_info.get('title', '') or '微信视频号'
    title = title.replace('\n', ' ').strip()
    if len(title) > 200:
        title = title[:200] + '...'

    author = author_info.get('nickname', '未知作者') if author_info else '未知作者'
    video_id = _extract_video_id(url) or 'wx_video'

    return _ok(_make_info(
        id=video_id,
        platform="wechat_channels",
        title=title,
        author=author,
        author_avatar=author_info.get('headImgUrl', '') if author_info else '',
        cover=feed_info.get('coverUrl', ''),
        duration=0,
        video_url=video_url,
        video_url_no_watermark=video_url,
        create_time=feed_info.get('createtime', 0),
        digg_count=_parse_count(feed_info.get('likeCountFmt', '0')),
        comment_count=_parse_count(feed_info.get('commentCountFmt', '0')),
        share_count=_parse_count(feed_info.get('forwardCountFmt', '0')),
    ))


def _extract_video_id(url: str) -> Optional[str]:
    """从 URL 中提取 video_id"""
    m = re.search(r'sph/([a-zA-Z0-9]+)', url)
    if m:
        return m.group(1)
    m = re.search(r'sph\?id=([a-zA-Z0-9]+)', url)
    if m:
        return m.group(1)
    for pattern in _CHANNELS_PATTERNS:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


async def _fetch_via_worker(url: str) -> Optional[Dict[str, Any]]:
    """通过 Worker API 获取视频直链和元数据（备用方案）"""
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            resp = await client.post(
                WORKER_API,
                json={'url': url},
                headers={'User-Agent': UA, 'Content-Type': 'application/json'},
            )
            if resp.status_code != 200:
                logger.warning(f"[视频号] Worker API 返回 {resp.status_code}")
                return None

            body = resp.json()
            if body.get('errCode') != 0:
                logger.warning(f"[视频号] Worker API 错误: {body.get('errMsg')}")
                return None

            data = body.get('data', {})
            feed_info = data.get('feedInfo', {})
            author_info = data.get('authorInfo', {})

            if not feed_info:
                return None

            video_url = ''
            h264 = feed_info.get('h264VideoInfo', {})
            h265 = feed_info.get('h265VideoInfo', {})
            if h264 and h264.get('videoUrl'):
                video_url = h264['videoUrl']
            elif h265 and h265.get('videoUrl'):
                video_url = h265['videoUrl']
            elif feed_info.get('videoUrl'):
                video_url = feed_info['videoUrl']

            title = feed_info.get('description', '') or '微信视频号'
            title = title.replace('\n', ' ').strip()
            if len(title) > 200:
                title = title[:200] + '...'

            author = author_info.get('nickname', '未知作者') if author_info else '未知作者'

            return _ok(_make_info(
                id=_extract_video_id(url) or 'wx_video',
                platform="wechat_channels",
                title=title,
                author=author,
                author_avatar=author_info.get('headImgUrl', '') if author_info else '',
                cover=feed_info.get('coverUrl', ''),
                duration=0,
                video_url=video_url,
                video_url_no_watermark=video_url,
                create_time=feed_info.get('createtime', 0),
                digg_count=_parse_count(feed_info.get('likeCountFmt', '0')),
                comment_count=_parse_count(feed_info.get('commentCountFmt', '0')),
                share_count=_parse_count(feed_info.get('forwardCountFmt', '0')),
            ))

    except Exception as e:
        logger.error(f"[视频号] Worker API 调用失败: {e}")
        return None


async def _get_feed_info_short(video_id: str) -> Optional[dict]:
    """调用 get_feed_info API 获取视频元数据（仅短链接模式，不含视频 URL）"""
    headers = {
        'User-Agent': UA,
        'Content-Type': 'application/json',
        'Referer': f'https://channels.weixin.qq.com/finder-preview/pages/sph?id={video_id}',
        'Origin': 'https://channels.weixin.qq.com',
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
            await client.get(
                f'https://channels.weixin.qq.com/finder-preview/pages/sph?id={video_id}',
                headers={'User-Agent': UA}
            )

            payload = {'baseReq': {'generalToken': ''}, 'shortUri': video_id}
            resp = await client.post(FEED_INFO_API, json=payload, headers=headers)
            data = resp.json()

            if data.get('errCode') == 0:
                return data.get('data', {})
            else:
                logger.warning(f"[视频号] get_feed_info 错误: {data.get('errMsg')}")
                return None

    except Exception as e:
        logger.error(f"[视频号] API 调用失败: {e}")
        return None


def _build_result_from_feed(video_id: str, feed_data: dict) -> Dict[str, Any]:
    """从 get_feed_info 短链接响应构建解析结果（仅元数据）"""
    feed_info = feed_data.get('feedInfo', {})
    author_info = feed_data.get('authorInfo', {})

    if not feed_info:
        return _empty_result("API 返回数据为空")

    title = feed_info.get('description', '') or feed_info.get('title', '') or '微信视频号'
    title = title.replace('\n', ' ').strip()
    author = author_info.get('nickname', '未知作者') if author_info else '未知作者'

    return _ok(_make_info(
        id=video_id,
        platform="wechat_channels",
        title=title,
        author=author,
        author_avatar=author_info.get('headImgUrl', '') if author_info else '',
        cover=feed_info.get('coverUrl', ''),
        duration=0,
        video_url="",
        video_url_no_watermark="",
        create_time=feed_info.get('createtime', 0),
        digg_count=_parse_count(feed_info.get('likeCountFmt', '0')),
        comment_count=_parse_count(feed_info.get('commentCountFmt', '0')),
        share_count=_parse_count(feed_info.get('forwardCountFmt', '0')),
    ))


def parse_video_info(json_str: str) -> Dict[str, Any]:
    """解析用户粘贴的视频信息 JSON"""
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        url_match = re.search(r'https?://[^\s"\'<>]*(?:mp4|m3u8|video)[^\s"\'<>]*', json_str, re.IGNORECASE)
        if url_match:
            return _ok(_make_info(
                id="wx_video", platform="wechat_channels", title="微信视频号",
                video_url=url_match.group(0), video_url_no_watermark=url_match.group(0),
            ))
        return _empty_result("无法解析，请粘贴视频号链接或视频直链")

    video_url = data.get("url", "") or data.get("videoUrl", "") or data.get("src", "")
    if not video_url:
        return _empty_result("未获取到视频地址")

    return _ok(_make_info(
        id=data.get("id", "wx_video"), platform="wechat_channels",
        title=data.get("title", "") or data.get("desc", "") or "微信视频号",
        author=data.get("nickname", "") or data.get("author", ""),
        cover=data.get("coverUrl", "") or data.get("cover", ""),
        video_url=video_url, video_url_no_watermark=video_url,
    ))
