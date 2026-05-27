"""YouTube 解析器 - 使用 yt-dlp 获取视频信息，下载时用 yt-dlp + ffmpeg 合并音视频"""

import re
from typing import Dict, Any

import yt_dlp

from ._utils import _make_info, _empty_result, _ok


DOMAINS = ["youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"]


async def parse(url: str) -> Dict[str, Any]:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([\w-]{11})", url)
    if not m:
        return _empty_result("无法提取 YouTube 视频 ID")
    vid = m.group(1)

    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "nocheckcertificate": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
    except Exception as e:
        return _empty_result(f"YouTube 解析失败: {str(e)[:100]}")

    if not info:
        return _empty_result("YouTube 解析失败")

    title = info.get("title", "无标题")
    author = info.get("uploader", "未知作者")
    thumbnail = info.get("thumbnail", "")
    duration = info.get("duration", 0)

    # 使用特殊前缀标记 YouTube 链接，下载时用 yt-dlp 处理
    video_url = f"yt://{vid}"

    return _ok(_make_info(
        id=vid, platform="youtube",
        title=title,
        author=author,
        cover=thumbnail,
        duration=duration,
        video_url=video_url,
        video_url_no_watermark=video_url,
    ))
