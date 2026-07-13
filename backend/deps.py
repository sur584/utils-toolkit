"""
共享依赖 — 服务实例、历史记录函数、懒加载模块
"""

import json
import time
import uuid
import logging
from pathlib import Path
from typing import List

from fastapi import Request
from pydantic import BaseModel

from services.model_manager import ModelManager
from services.image_classifier import ImageClassifier
from services.model_router import ModelRouter
from services.image_optimizer import ImageOptimizer
from services.post_processor import PostProcessor
from services.task_queue import TaskQueue
from services.disk_cache import DiskCache

from config import MODELS_DIR, PROJECT_DIR, HISTORY_DIR

logger = logging.getLogger(__name__)

# ─── V3.0 服务层实例 ─────────────────────────────────
model_manager = ModelManager()
image_classifier = ImageClassifier(models_dir=str(MODELS_DIR))
model_router = ModelRouter()
image_optimizer = ImageOptimizer()
post_processor = PostProcessor()
task_queue = TaskQueue()
disk_cache = DiskCache(cache_dir=str(PROJECT_DIR / "cache"))

# ─── 数据模型 ─────────────────────────────────────────
class ParseRequest(BaseModel):
    url: str

class BatchParseRequest(BaseModel):
    urls: List[str]

class ParseProfileRequest(BaseModel):
    url: str
    limit: int = 20

# ─── 文字去除相关懒加载 ──────────────────────────────
_rapid_ocr = None
_lama = None
_cv2 = None

def _get_ocr():
    global _rapid_ocr
    if _rapid_ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _rapid_ocr = RapidOCR()
    return _rapid_ocr

def _get_lama():
    global _lama
    if _lama is None:
        from simple_lama_inpainting import SimpleLama
        _lama = SimpleLama()
    return _lama

def _get_cv2():
    global _cv2
    if _cv2 is None:
        import cv2
        _cv2 = cv2
    return _cv2

# ─── 历史记录（按 IP 隔离）─────────────────────────────
def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def _history_file(ip: str) -> Path:
    HISTORY_DIR.mkdir(exist_ok=True)
    safe_ip = ip.replace(".", "_").replace(":", "_")
    return HISTORY_DIR / f"history_{safe_ip}.json"

def _load_history(ip: str) -> list:
    f = _history_file(ip)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def _save_history(ip: str, history: list):
    f = _history_file(ip)
    f.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

def _add_to_history(video_info: dict, ip: str = "unknown"):
    history = _load_history(ip)
    record = {"id": str(uuid.uuid4())[:8], "parse_time": time.strftime("%Y-%m-%d %H:%M:%S"), **video_info}
    history.insert(0, record)
    _save_history(ip, history[:200])
