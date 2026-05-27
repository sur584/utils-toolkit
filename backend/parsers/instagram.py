"""Instagram 解析器"""

import re
from typing import Dict, Any

from ._utils import _make_info, _empty_result, _ok


DOMAINS = ["instagram.com", "www.instagram.com", "instagr.am"]


async def parse(url: str) -> Dict[str, Any]:
    url = url.rstrip("/")
    m = re.search(r"/reel/(\w+)", url) or re.search(r"/p/(\w+)", url) or re.search(r"/tv/(\w+)", url)
    if not m:
        return _empty_result("无法提取 Instagram 帖子 ID")
    post_id = m.group(1)

    embed_url = f"https://www.instagram.com/reel/{post_id}/embed/"

    return _ok(_make_info(
        id=post_id, platform="instagram",
        title="Instagram Reels",
        video_url=embed_url,
        video_url_no_watermark=embed_url,
    ))
