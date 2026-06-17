"""
共享配置 — 路径常量、日志、环境变量
"""

import os
import platform
import logging
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
# 优先级: .env 中的 HTTP_PROXY > 环境变量 > Windows 系统代理设置 > 直连
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
                    if not server.startswith("http://") and not server.startswith("https://"):
                        server = f"http://{server}"
                    return server
        except Exception:
            pass

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

# ─── 日志 ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE_DIR / "app.log", encoding="utf-8"),
    ],
)

# ─── 视频号解析 cookie ─────────────────────────────────
YUANBAO_COOKIE = os.environ.get("YUANBAO_COOKIE", "")
