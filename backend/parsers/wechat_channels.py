"""微信视频号解析器"""

import json
import re
import logging
from typing import Dict, Any, Optional

import httpx

from ._utils import _make_info, _empty_result, _ok, _follow_redirects

logger = logging.getLogger(__name__)


DOMAINS = ["channels.weixin.qq.com", "weixin.qq.com"]


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

    return _empty_result("无法解析，请粘贴视频直链或使用「抓包工具」获取")


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
【微信视频号视频下载方法】

方法一：使用抓包工具（推荐）
1. 下载抓包工具（如 Fiddler、Charles、mitmproxy）
2. 配置代理抓取微信流量
3. 播放视频，找到视频 URL
4. 复制 URL 粘贴到工具中

方法二：使用浏览器插件
1. 安装「猫抓」或「Stream」等浏览器插件
2. 在微信 PC 端打开视频号（使用系统浏览器打开）
3. 插件会自动捕获视频 URL
4. 复制 URL 粘贴到工具中

方法三：使用命令行工具
1. 安装 mitmproxy: pip install mitmproxy
2. 运行: mitmdump -s sniff_video.py
3. 配置微信使用代理
4. 播放视频，工具会自动捕获 URL
"""


async def parse(url: str) -> Dict[str, Any]:
    """主解析入口"""
    # 判断输入类型
    if url.startswith("{") or url.startswith("["):
        return parse_video_info(url)
    elif "channels.weixin.qq.com" in url:
        return parse_url(url)
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
    patterns = [
        r'channels\.weixin\.qq\.com/web/pages/feed/([a-f0-9]+)',
        r'channels\.weixin\.qq\.com/web/pages/feed\?feedId=([a-f0-9]+)',
        r'channels\.weixin\.qq\.com/finder-preview/pages/sph\?id=([a-zA-Z0-9]+)',
        r'feedId=([a-f0-9]+)',
    ]

    video_id = None
    for pattern in patterns:
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


async def parse_sph_url(url: str) -> Dict[str, Any]:
    """
    解析视频号分享链接 (weixin.qq.com/sph/xxxxx)

    1. 跟踪重定向获取最终 URL
    2. 提取 video_id
    3. 调用内部 API 获取元数据
    4. 返回元数据 + 使用说明
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

            # 解析点赞数等
            def parse_count(s):
                if not s:
                    return 0
                s = str(s).replace(',', '')
                if '万' in s:
                    return int(float(s.replace('万', '')) * 10000)
                try:
                    return int(s)
                except:
                    return 0

            # 返回元数据（不含视频直链）
            # video_url 为空，需要用户通过抓包获取后手动粘贴
            return _ok(_make_info(
                id=video_id,
                platform="wechat_channels",
                title=feed_info.get('description', '微信视频号'),
                author=author_info.get('nickname', '未知作者'),
                author_avatar=author_info.get('headImgUrl', ''),
                cover=feed_info.get('coverUrl', ''),
                duration=0,
                video_url="",  # 视频直链需要抓包获取
                video_url_no_watermark="",
                create_time=feed_info.get('createtime', 0),
                digg_count=parse_count(feed_info.get('likeCountFmt', '0')),
                comment_count=parse_count(feed_info.get('commentCountFmt', '0')),
                share_count=parse_count(feed_info.get('forwardCountFmt', '0')),
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

    API: /finder-preview/api/feed/get_feed_info
    """
    api_url = 'https://channels.weixin.qq.com/finder-preview/api/feed/get_feed_info'

    payload = {
        'baseReq': {'generalToken': ''},
        'shortUri': video_id
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Content-Type': 'application/json',
        'Referer': f'https://channels.weixin.qq.com/finder-preview/pages/sph?id={video_id}',
        'Origin': 'https://channels.weixin.qq.com',
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
            # 先访问页面建立会话
            page_url = f'https://channels.weixin.qq.com/finder-preview/pages/sph?id={video_id}'
            await client.get(page_url, headers={
                'User-Agent': headers['User-Agent'],
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            })

            # 调用 API
            resp = await client.post(api_url, json=payload, headers=headers)
            data = resp.json()

            if data.get('errCode') == 0:
                logger.info(f"[视频号] API 获取元数据成功: {video_id}")
                return data.get('data')
            else:
                logger.warning(f"[视频号] API 返回错误: {data.get('errMsg')}")
                return None

    except Exception as e:
        logger.error(f"[视频号] API 调用失败: {e}")
        return None
