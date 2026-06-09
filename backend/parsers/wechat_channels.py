"""微信视频号解析器"""

import json
import re
import logging
from typing import Dict, Any, Optional

import httpx

from ._utils import _make_info, _empty_result, _ok, _follow_redirects

logger = logging.getLogger(__name__)


DOMAINS = ["channels.weixin.qq.com", "weixin.qq.com"]

_CHANNELS_PATTERNS = [
    r'channels\.weixin\.qq\.com/web/pages/feed/([a-f0-9]+)',
    r'channels\.weixin\.qq\.com/web/pages/feed\?feedId=([a-f0-9]+)',
    r'channels\.weixin\.qq\.com/finder-preview/pages/sph\?id=([a-zA-Z0-9]+)',
    r'feedId=([a-f0-9]+)',
]


def _parse_count(s) -> int:
    """解析带万字/suffix 的计数字符串为整数"""
    if not s:
        return 0
    s = str(s).replace(',', '')
    if '万' in s:
        return int(float(s.replace('万', '')) * 10000)
    try:
        return int(s)
    except (ValueError, TypeError):
        return 0


def parse_video_info(json_str: str) -> Dict[str, Any]:
    """
    解析用户粘贴的视频信息

    支持多种输入格式：
    1. JSON 字符串
    2. 包含 URL 的文本
    3. 视频号链接
    """
    # 尝试解析 JSON
    try:
        data = json.loads(json_str)
        return _parse_json_data(data)
    except json.JSONDecodeError:
        pass

    # 尝试从文本中提取视频 URL
    url_match = re.search(
        r'https?://[^\s"\'<>]*(?:mp4|m3u8|video)[^\s"\'<>]*',
        json_str,
        re.IGNORECASE
    )
    if url_match:
        video_url = url_match.group(0)
        return _ok(_make_info(
            id="wx_video",
            platform="wechat_channels",
            title="微信视频号",
            author="未知作者",
            author_avatar="",
            cover="",
            duration=0,
            video_url=video_url,
            video_url_no_watermark=video_url,
            create_time=0,
            digg_count=0,
            comment_count=0,
            share_count=0,
        ))

    # 尝试提取视频号链接
    link_match = re.search(
        r'https?://channels\.weixin\.qq\.com/web/pages/feed/[a-f0-9]+',
        json_str
    )
    if link_match:
        return {
            "success": False,
            "message": "检测到视频号链接，但需要在微信中打开",
            "data": None,
        }

    return _empty_result("无法解析，请粘贴视频直链")


def _parse_json_data(data: dict) -> Dict[str, Any]:
    """解析 JSON 格式的视频信息"""
    video_id = data.get("id", "") or data.get("videoId", "")
    title = data.get("title", "") or data.get("desc", "") or "微信视频号"
    video_url = data.get("url", "") or data.get("videoUrl", "") or data.get("src", "")
    decrypt_key = data.get("key", "") or data.get("decryptKey", "") or data.get("videoEncKey", "")
    cover_url = data.get("coverUrl", "") or data.get("cover", "") or data.get("poster", "")
    duration = data.get("duration", 0)
    author = data.get("nickname", "") or data.get("author", "") or data.get("userName", "")

    if not video_url:
        return _empty_result("未获取到视频地址，请确保视频正在播放")

    # 加密视频使用 wx:// 前缀
    if decrypt_key:
        video_url_final = f"wx://{video_url}|{decrypt_key}"
    else:
        video_url_final = video_url

    return _ok(_make_info(
        id=video_id or "wx_video",
        platform="wechat_channels",
        title=title,
        author=author or "未知作者",
        author_avatar="",
        cover=cover_url,
        duration=int(duration) if duration else 0,
        video_url=video_url_final,
        video_url_no_watermark=video_url,
        create_time=0,
        digg_count=0,
        comment_count=0,
        share_count=0,
    ))


def get_usage_guide() -> str:
    """返回使用说明"""
    return """
【微信视频号说明】

微信视频号的视频仅限在微信 App 内播放，公开 API 不提供视频直链。
本工具可解析视频号的元数据（标题、作者、封面等），但无法直接下载视频。

如需保存视频，可使用手机录屏功能。
"""


async def parse(url: str) -> Dict[str, Any]:
    """主解析入口"""
    # 判断输入类型
    if url.startswith("{") or url.startswith("["):
        return parse_video_info(url)
    elif "channels.weixin.qq.com" in url:
        return await parse_channels_url(url)
    elif "weixin.qq.com/sph/" in url:
        return await parse_sph_url(url)
    elif url.startswith("http") and ("mp4" in url or "m3u8" in url or "video" in url):
        # 直接是视频 URL
        return _ok(_make_info(
            id="wx_video",
            platform="wechat_channels",
            title="微信视频号",
            author="未知作者",
            author_avatar="",
            cover="",
            duration=0,
            video_url=url,
            video_url_no_watermark=url,
            create_time=0,
            digg_count=0,
            comment_count=0,
            share_count=0,
        ))
    else:
        return {
            "success": False,
            "message": "请输入视频直链或使用抓包工具获取",
            "data": None,
            "guide": get_usage_guide(),
        }


def parse_url(url: str) -> Dict[str, Any]:
    """解析视频号链接"""
    video_id = None
    for pattern in _CHANNELS_PATTERNS:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            break

    if not video_id:
        return _empty_result("无法识别视频号链接")

    return {
        "success": False,
        "message": f"检测到视频号内容 (ID: {video_id})，但需要配合抓包工具获取视频直链",
        "data": None,
        "hint": get_usage_guide(),
    }


async def parse_channels_url(url: str) -> Dict[str, Any]:
    """异步解析 channels.weixin.qq.com 链接（获取元数据，视频直链不可用）"""
    video_id = None
    for pattern in _CHANNELS_PATTERNS:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            break

    if not video_id:
        return _empty_result("无法识别视频号链接")

    metadata = await fetch_video_metadata(video_id)

    if metadata:
        feed_info = metadata.get('feedInfo', {})
        author_info = metadata.get('authorInfo', {})

        # 微信视频号视频直链不可用，仅返回元数据
        return _ok(_make_info(
            id=video_id,
            platform="wechat_channels",
            title=feed_info.get('description', '微信视频号') if feed_info else '微信视频号',
            author=author_info.get('nickname', '未知作者') if author_info else '未知作者',
            author_avatar=author_info.get('headImgUrl', '') if author_info else '',
            cover=feed_info.get('coverUrl', '') if feed_info else '',
            duration=0,
            video_url="",
            video_url_no_watermark="",
            create_time=feed_info.get('createtime', 0) if feed_info else 0,
            digg_count=_parse_count(feed_info.get('likeCountFmt', '0')) if feed_info else 0,
            comment_count=_parse_count(feed_info.get('commentCountFmt', '0')) if feed_info else 0,
            share_count=_parse_count(feed_info.get('forwardCountFmt', '0')) if feed_info else 0,
        ))
    else:
        return {
            "success": False,
            "message": f"已识别为视频号链接 (ID: {video_id})，但获取元数据失败。请稍后重试或使用抓包工具",
            "data": None,
            "hint": get_usage_guide(),
        }


async def parse_sph_url(url: str) -> Dict[str, Any]:
    """
    解析视频号分享链接 (weixin.qq.com/sph/xxxxx)

    1. 跟踪重定向获取最终 URL
    2. 提取 video_id
    3. 调用内部 API 获取元数据
    4. 返回元数据（视频直链不可用）
    """
    try:
        # 1. 跟踪重定向获取最终 URL
        final_url = await _follow_redirects(url, timeout=10.0)
        logger.info(f"[视频号] 重定向后 URL: {final_url}")

        # 2. 提取 video_id
        video_id = None

        # 从 channels.weixin.qq.com/finder-preview/pages/sph?id=xxx 提取
        sph_match = re.search(r'sph\?id=([a-zA-Z0-9]+)', final_url)
        if sph_match:
            video_id = sph_match.group(1)

        # 从 weixin.qq.com/sph/xxx 提取
        if not video_id:
            sph_match = re.search(r'sph/([a-zA-Z0-9]+)', url)
            if sph_match:
                video_id = sph_match.group(1)

        if not video_id:
            return _empty_result("无法从链接中提取视频ID")

        logger.info(f"[视频号] 提取到 video_id: {video_id}")

        # 3. 调用 API 获取元数据
        metadata = await fetch_video_metadata(video_id)

        if metadata:
            feed_info = metadata.get('feedInfo', {})
            author_info = metadata.get('authorInfo', {})

            # 微信视频号视频直链不可用，仅返回元数据
            return _ok(_make_info(
                id=video_id,
                platform="wechat_channels",
                title=feed_info.get('description', '微信视频号'),
                author=author_info.get('nickname', '未知作者'),
                author_avatar=author_info.get('headImgUrl', ''),
                cover=feed_info.get('coverUrl', ''),
                duration=0,
                video_url="",
                video_url_no_watermark="",
                create_time=feed_info.get('createtime', 0),
                digg_count=_parse_count(feed_info.get('likeCountFmt', '0')),
                comment_count=_parse_count(feed_info.get('commentCountFmt', '0')),
                share_count=_parse_count(feed_info.get('forwardCountFmt', '0')),
            ))
        else:
            # API 调用失败，返回提示信息
            return {
                "success": False,
                "message": "已识别为视频号链接，但获取元数据失败。请稍后重试或使用抓包工具",
                "data": None,
                "hint": get_usage_guide(),
            }

    except Exception as e:
        logger.error(f"[视频号] 解析失败: {e}")
        return {
            "success": False,
            "message": f"处理分享链接失败: {str(e)}",
            "data": None,
            "hint": get_usage_guide(),
        }


async def fetch_video_metadata(video_id: str) -> Optional[Dict[str, Any]]:
    """
    调用微信内部 API 获取视频元数据

    注意：微信视频号的 get_feed_info API 不返回视频播放直链，
    视频 URL 仅在微信 App 内可用。此函数获取元数据（标题、作者、封面等）。
    """
    ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

    api_headers = {
        'User-Agent': ua,
        'Content-Type': 'application/json',
        'Referer': f'https://channels.weixin.qq.com/finder-preview/pages/sph?id={video_id}',
        'Origin': 'https://channels.weixin.qq.com',
    }

    result_data = {}

    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
            # 访问页面建立会话
            page_url = f'https://channels.weixin.qq.com/finder-preview/pages/sph?id={video_id}'
            await client.get(page_url, headers={'User-Agent': ua})

            # 调用 get_feed_info 获取元数据
            feed_api = 'https://channels.weixin.qq.com/finder-preview/api/feed/get_feed_info'
            feed_payload = {'baseReq': {'generalToken': ''}, 'shortUri': video_id}
            feed_resp = await client.post(feed_api, json=feed_payload, headers=api_headers)
            feed_data = feed_resp.json()

            if feed_data.get('errCode') == 0:
                logger.info(f"[视频号] get_feed_info 成功: {video_id}")
                result_data = feed_data.get('data', {})
            else:
                logger.warning(f"[视频号] get_feed_info 返回错误: {feed_data.get('errMsg')}")

    except Exception as e:
        logger.error(f"[视频号] API 调用失败: {e}")

    return result_data if result_data else None
