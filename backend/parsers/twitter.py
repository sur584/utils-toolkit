"""Twitter/X 解析器"""

import re
from typing import Dict, Any

from ._utils import _follow_redirects, _make_info, _empty_result, _ok
from urllib.parse import urlparse


DOMAINS = ["twitter.com", "x.com", "www.twitter.com", "www.x.com", "t.co"]


async def parse(url: str) -> Dict[str, Any]:
    url = url.rstrip("/")
    if "t.co" in urlparse(url).netloc:
        url = await _follow_redirects(url)

    m = re.search(r"/status/(\d+)", url)
    if not m:
        return _empty_result("无法提取推文 ID")
    tweet_id = m.group(1)

    embed_url = f"https://platform.twitter.com/embed/Tweet.html?id={tweet_id}"

    return _ok(_make_info(
        id=tweet_id, platform="twitter",
        title="Twitter/X 视频",
        video_url=embed_url,
        video_url_no_watermark=embed_url,
    ))
