"""集中构建 yt-dlp 的 Cookie 选项，规避 YouTube / TikTok 的 bot 校验。

YouTube 自 2023 年起对未登录请求频繁弹出 "Sign in to confirm you're not a bot"，
yt-dlp 必须在请求时携带登录态 Cookie 才能稳定解析/下载。本模块统一两种零/低配置方案：

  1. YT_COOKIES_FILE        —— Netscape cookies.txt 的绝对路径（用户用浏览器插件导出）。
                              优先级最高，适合把 Cookie 文件放在服务器上长期复用。
  2. YT_COOKIES_FROM_BROWSER —— 浏览器名（chrome/edge/firefox/brave/opera/...），
                              直接读取本机浏览器的 Cookie 数据库，无需手动导出。
                              - 未显式设置时，Windows 默认尝试 chrome（前提是服务与
                                浏览器运行在同一 Windows 账号、且该账号已登录 YouTube）。
                              - 设为 none / off / 0 / false / no 可强制关闭。

返回空 dict 表示不附加 Cookie（此时 YouTube 大概率触发 bot 校验）。
"""

import os
import platform
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def get_ytdlp_cookie_opts() -> Dict[str, Any]:
    """返回 yt-dlp 的 Cookie 相关 ydl_opts 片段（可能为空 dict）。"""
    # 1. 显式 cookie 文件（Netscape 格式）最高优先级
    cookie_file = os.environ.get("YT_COOKIES_FILE", "").strip()
    if cookie_file:
        if os.path.isfile(cookie_file):
            logger.info(f"[YT-Cookie] 使用 cookie 文件: {cookie_file}")
            return {"cookiefile": cookie_file}
        logger.warning(f"[YT-Cookie] YT_COOKIES_FILE 指向的文件不存在，已忽略: {cookie_file}")

    # 2. 从本机浏览器提取（含 Windows 默认 chrome）
    browser = os.environ.get("YT_COOKIES_FROM_BROWSER", "").strip().lower()
    if browser == "":
        # 未显式设置时，Windows 默认尝试本机 chrome（零配置，需服务与浏览器同账号）
        if platform.system() == "Windows":
            browser = "chrome"
    if browser in ("none", "off", "false", "0", "disabled", "no"):
        return {}
    if browser:
        logger.info(f"[YT-Cookie] 从本机浏览器提取 Cookie: {browser}")
        # 注意：通过 Python 库 API（YoutubeDL(ydl_opts)）传入时，cookiesfrombrowser
        # 必须是「浏览器名 / profile / keyring / container」4 元组（或单元素列表 ["chrome"]），
        # 不能写成 [("chrome",)]（会被 yt-dlp 当作浏览器名字符串而报 unsupported browser）。
        return {"cookiesfrombrowser": (browser, None, None, None)}

    return {}


# 备用播放器客户端：tv / tv_embedded / ios / android 等无需登录即可绕过大多数
# "Sign in to confirm you're not a bot" 校验（web 客户端最容易被拦）。yt-dlp 会按顺序
# 尝试，任一可用即返回。与 Cookie 叠加使用，进一步提升成功率。
YOUTUBE_PLAYER_CLIENTS = ["tv", "tv_embedded", "ios", "android", "web"]


def get_youtube_extractor_args() -> Dict[str, Any]:
    """返回规避 YouTube bot 校验的 extractor_args（切换播放器客户端，无需登录）。"""
    return {"extractor_args": {"youtube": {"player_client": YOUTUBE_PLAYER_CLIENTS}}}


def is_cookie_related_error(msg: str) -> bool:
    """判断异常是否由 Cookie 提取失败引起，用于重试时降级为「无 Cookie」再试。"""
    m = (msg or "").lower()
    keys = (
        "cookie", "cookies", "browser", "decrypt", "could not find",
        "unsupported browser", "unknown browser", "local state", "keyring",
        "nss", "sqlite", "no such file", "permission",
    )
    return any(k in m for k in keys)
