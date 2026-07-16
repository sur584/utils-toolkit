"""
共享配置 — 路径常量、日志、环境变量
"""

import os
import platform
import logging
import socket
from pathlib import Path

# 加载 .env 文件
_env_file = Path(__file__).resolve().parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# ─── 全局 HTTP 代理自动检测 ──────────────────────────
# 优先级: .env 中的 HTTP_PROXY > 环境变量 > Windows 系统代理设置 > 常见本机代理端口 > 直连
def _normalize_proxy_server(server: str) -> str:
    server = server.strip()
    if not server:
        return ""
    if ";" in server:
        parts = {}
        for item in server.split(";"):
            if "=" in item:
                key, value = item.split("=", 1)
                parts[key.strip().lower()] = value.strip()
        server = parts.get("https") or parts.get("http") or parts.get("socks") or ""
    if server and not server.startswith(("http://", "https://", "socks5://", "socks4://")):
        server = f"http://{server}"
    return server


def _local_port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def _detect_proxy() -> str:
    # 1. 环境变量（.env 已写入 os.environ）
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        val = os.environ.get(key, "").strip()
        if val:
            return val

    # 2. Windows 系统代理设置
    if platform.system() == "Windows":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            ) as key:
                enabled = winreg.QueryValueEx(key, "ProxyEnable")[0]
                server = winreg.QueryValueEx(key, "ProxyServer")[0]
                if enabled and server:
                    proxy = _normalize_proxy_server(server)
                    if proxy:
                        return proxy
        except Exception:
            pass

    for port in (7897, 7890, 7891, 7892, 7893, 7899, 10809, 10808, 1080, 1081):
        if _local_port_open(port):
            return f"http://127.0.0.1:{port}"

    return ""

HTTP_PROXY = _detect_proxy()

# ─── 运行时代理配置（通过前端设置，覆盖自动检测）────────
# 用于客户端设备有代理但服务端无代理的场景
# 格式: http://192.168.1.18:7890
_CLIENT_PROXY: str = ""  # 运行时由 API 热更新


def get_active_proxy(client_only: bool = False) -> str:
    """返回当前有效的代理地址
    Args:
        client_only: 仅返回客户端手动配置的代理（跳过自动检测）。
            用于 TikTok 等被国内代理 geo-block 的平台。
    """
    if client_only:
        return _CLIENT_PROXY
    return _CLIENT_PROXY or HTTP_PROXY


def set_client_proxy(proxy: str) -> None:
    """设置客户端代理地址（热更新，无需重启服务）"""
    global _CLIENT_PROXY
    _CLIENT_PROXY = proxy.strip()

# ─── 路径常量 ─────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
HISTORY_DIR = BASE_DIR / "history_data"
VIDEO_TOOL_DIR = PROJECT_DIR / "tools" / "video-tool"
IMAGE_TOOL_DIR = PROJECT_DIR / "tools" / "image-tool"
BG_REMOVER_DIR = PROJECT_DIR / "tools" / "bg-remover"
IMAGE_COMPOSITE_DIR = PROJECT_DIR / "tools" / "image-composite"
TEXT_REMOVER_DIR = PROJECT_DIR / "tools" / "text-remover"
WATERMARK_TOOL_DIR = PROJECT_DIR / "tools" / "watermark-tool"
WX_VIDEO_PARSER_DIR = PROJECT_DIR / "tools" / "wx-video-parser"
TRANSCRIPT_DIR = PROJECT_DIR / "tools" / "transcript"
MODELS_DIR = PROJECT_DIR / "models"
LIBS_DIR = PROJECT_DIR / "tools" / "libs"

DOWNLOAD_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)

# 让 rembg 把模型存到项目内的 models 目录
os.environ["U2NET_HOME"] = str(MODELS_DIR)

# ─── 下载缓存清理 ─────────────────────────────────────
# downloads/ 是「下载到服务端磁盘再回传」的缓存目录，只增不减。
# 启动时 + 定时删除超过 DOWNLOAD_MAX_AGE_HOURS 的旧文件，保留短期「秒回」缓存。
DOWNLOAD_MAX_AGE_HOURS = 6.0


def cleanup_download_dir(max_age_hours: float = DOWNLOAD_MAX_AGE_HOURS) -> int:
    """删除 DOWNLOAD_DIR 中修改时间超过 max_age_hours 的文件，返回删除数量。"""
    import time
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    try:
        entries = list(DOWNLOAD_DIR.iterdir())
    except OSError:
        return 0
    for f in entries:
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            pass
    return removed


# ─── 日志 ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE_DIR / "app.log", encoding="utf-8"),
    ],
)
# httpx 默认 INFO 会打印完整请求 URL（含 xsec_token 等临时鉴权 query），降到 WARNING 防泄露
logging.getLogger("httpx").setLevel(logging.WARNING)

# ─── 视频号解析 cookie ─────────────────────────────────
YUANBAO_COOKIE = os.environ.get("YUANBAO_COOKIE", "")
