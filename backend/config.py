"""
共享配置 — 路径常量、日志、环境变量
"""

import os
import logging
from pathlib import Path

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
