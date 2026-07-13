from urllib.parse import urlparse
from typing import Optional

DOUYIN_DOMAINS = ["v.douyin.com", "www.douyin.com", "www.iesdouyin.com", "m.douyin.com"]
WECHAT_DOMAINS = ["channels.weixin.qq.com", "weixin.qq.com"]

PLATFORM_DOMAINS = {
    "douyin": DOUYIN_DOMAINS,
    "wechat_channels": WECHAT_DOMAINS,
}


def detect_platform(url: str) -> Optional[str]:
    """Detect platform from URL domain."""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    for platform, domains in PLATFORM_DOMAINS.items():
        for d in domains:
            if d in netloc:
                return platform
    return None
