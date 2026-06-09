"""
图片预处理器 - 根据模型动态调整图片尺寸和格式
"""

import io
import logging
from typing import Optional

from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)


class ImageOptimizer:
    """模型相关的图片预处理"""

    def __init__(self, model_manager=None):
        if model_manager is None:
            from .model_manager import ModelManager
            model_manager = ModelManager()
        self._model_manager = model_manager

    def preprocess(self, data: bytes, model_name: str) -> Image.Image:
        """
        预处理图片：解码、颜色模式归一化、模型相关尺寸限制

        Args:
            data: 原始图片字节
            model_name: 目标模型名（决定最大尺寸）

        Returns:
            处理后的 PIL Image（RGB 或 RGBA）

        Raises:
            ValueError: 文件格式错误、损坏或尺寸太小
        """
        try:
            img = Image.open(io.BytesIO(data))
            img.load()  # 强制解码，检测损坏文件
        except UnidentifiedImageError:
            raise ValueError(
                "无法识别此文件为图片。请确认文件是 JPG、PNG、WebP 或 BMP 格式"
            )
        except Exception as e:
            raise ValueError(f"图片文件损坏或无法读取：{str(e)[:100]}")

        # 颜色模式归一化
        img = self._normalize_mode(img)

        # 模型相关尺寸限制
        max_dim = self.get_max_dim(model_name)
        if max(img.size) > max_dim:
            ratio = max_dim / max(img.size)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
            logger.debug(f"图片缩放至 {new_size}（模型 {model_name} 最大 {max_dim}px）")

        # 最小尺寸检查
        if min(img.size) < 10:
            raise ValueError(
                f"图片尺寸太小（{img.width}x{img.height}），至少需要 10x10 像素"
            )

        return img

    def _normalize_mode(self, img: Image.Image) -> Image.Image:
        """统一颜色模式"""
        if img.mode in ("RGB", "RGBA"):
            return img

        orig_mode = img.mode
        try:
            if img.mode in ("P", "LA", "PA"):
                return img.convert("RGBA")
            else:
                return img.convert("RGB")
        except Exception:
            raise ValueError(
                f"不支持的颜色模式 {orig_mode}，请将图片转换为 RGB 或 RGBA 后重试"
            )

    def get_max_dim(self, model_name: str) -> int:
        cfg = self._model_manager.get_model_params(model_name)
        return cfg.get("max_dim", 2048)
