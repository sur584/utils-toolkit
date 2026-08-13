"""应用版本号单一来源。

版本号维护在仓库根目录的 version.json，前端首页、后端 API、OpenAPI 文档
均从此读取，避免在多处硬编码导致版本不一致。
"""
import json
from pathlib import Path

try:
    from config import PROJECT_DIR
except Exception:  # pragma: no cover - 仅用于独立运行兜底
    PROJECT_DIR = Path(__file__).resolve().parent.parent

_VERSION_FILE = PROJECT_DIR / "version.json"
_FALLBACK_VERSION = "1.0.3"
_FALLBACK_NAME = "小小工具箱"


def get_app_version() -> str:
    """读取 version.json 中的应用版本号；读取失败则返回兜底值。"""
    try:
        if _VERSION_FILE.exists():
            data = json.loads(_VERSION_FILE.read_text(encoding="utf-8"))
            version = str(data.get("version", "")).strip()
            if version:
                return version
    except Exception:
        pass
    return _FALLBACK_VERSION


def get_app_name() -> str:
    """读取 version.json 中的应用名称；读取失败则返回兜底值。"""
    try:
        if _VERSION_FILE.exists():
            data = json.loads(_VERSION_FILE.read_text(encoding="utf-8"))
            name = str(data.get("name", "")).strip()
            if name:
                return name
    except Exception:
        pass
    return _FALLBACK_NAME


# 模块加载时读取一次（版本变更需随发布重启服务，符合语义化版本发布语义）
APP_VERSION = get_app_version()
APP_NAME = get_app_name()
