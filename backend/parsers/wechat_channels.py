"""微信视频号解析器"""

import json
import re
from typing import Dict, Any

from ._utils import _make_info, _empty_result, _ok


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
        "message": "视频号链接需要配合抓包工具使用",
        "data": None,
        "hint": get_usage_guide(),
    }
