"""共享工具函数和常量"""

import re
import ipaddress
import logging
from typing import Optional, Dict
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
DESKTOP_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _headers(referer: str = "https://www.douyin.com/", mobile: bool = False) -> Dict[str, str]:
    return {
        "User-Agent": MOBILE_UA if mobile else DESKTOP_UA,
        "Referer": referer,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }



async def _follow_redirects(url: str, timeout: float = 10.0) -> str:
    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as c:
        r = await c.get(url, headers=_headers())
        count = 0
        while r.is_redirect and count < 10:
            loc = r.headers.get("location", "")
            if not loc:
                break
            if loc.startswith("/"):
                p = urlparse(str(r.url))
                loc = f"{p.scheme}://{p.netloc}{loc}"
            r = await c.get(loc, headers=_headers())
            count += 1
        return str(r.url)


async def _fetch(
    url: str,
    headers: Dict = None,
    timeout: float = 15.0,
    follow: bool = True,
    use_proxy: bool = True,
) -> Optional[str]:
    try:
        client_kwargs = dict(timeout=timeout, follow_redirects=follow)
        if not use_proxy:
            client_kwargs["trust_env"] = False
        async with httpx.AsyncClient(**client_kwargs) as c:
            r = await c.get(url, headers=headers or _headers())
            if r.status_code == 200:
                return r.text
    except Exception as e:
        logger.warning(f"Fetch {url} failed: {e}")
    return None


def _extract_url(text: str) -> Optional[str]:
    """从任意文本中提取 URL"""
    m = re.search(r"https?://[^\s<>\"'\)]+", text)
    return m.group(0) if m else None


def _is_safe_url(url: str) -> bool:
    """检查 URL 是否安全：仅允许 http/https，禁止访问内网地址"""
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    # 禁止访问内网/本地地址
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    except ValueError:
        # hostname 不是 IP，检查常见内网域名
        blocked = ("localhost", "127.0.0.1", "0.0.0.0", "metadata.google.internal")
        if hostname.lower() in blocked:
            return False
        # 检查 .local 等内网域名
        if hostname.endswith(".local") or hostname.endswith(".internal"):
            return False

    return True
