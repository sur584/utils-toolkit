"""
后处理器 - 边缘优化、高斯羽化、去白边
"""

import logging

import numpy as np
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)


class PostProcessor:
    """抠图结果的边缘优化"""

    def __init__(self, model_manager=None):
        if model_manager is None:
            from .model_manager import ModelManager
            model_manager = ModelManager()
        self._model_manager = model_manager

    def _build_alpha_params(self, model_name: str) -> dict:
        """从 ModelManager 的模型配置中提取 alpha matting 参数"""
        cfg = self._model_manager.get_model_params(model_name)
        if not cfg.get("alpha_matting"):
            return {"enabled": False}
        return {
            "enabled": True,
            "foreground_threshold": cfg.get("alpha_matting_foreground_threshold", 240),
            "background_threshold": cfg.get("alpha_matting_background_threshold", 10),
            "erode_size": cfg.get("alpha_matting_erode_size", 5),
        }

    def process(self, result: Image.Image, model_name: str) -> Image.Image:
        """
        完整后处理流水线

        Args:
            result: rembg 输出的 RGBA 图片
            model_name: 使用的模型名

        Returns:
            优化后的 RGBA 图片
        """
        if result.mode != "RGBA":
            return result

        # 提取 alpha 通道
        r, g, b, a = result.split()
        mask_array = np.array(a)

        # 1. 高斯羽化 - 平滑边缘
        a_smooth = a.filter(ImageFilter.GaussianBlur(radius=1.5))

        # 2. Alpha 优化（根据模型参数）
        params = self._build_alpha_params(model_name)
        if params.get("enabled"):
            a_smooth = self._optimize_alpha(a_smooth, params)

        # 3. 边缘收缩 - 去白边
        a_smooth = self._shrink_edges(a_smooth, pixels=1)

        # 合成结果
        result = Image.merge("RGBA", (r, g, b, a_smooth))
        return result

    def _optimize_alpha(self, alpha: Image.Image, params: dict) -> Image.Image:
        """优化 alpha 通道：增强前景/背景区分度"""
        fg_thresh = params.get("foreground_threshold", 240)
        bg_thresh = params.get("background_threshold", 10)

        arr = np.array(alpha, dtype=np.float32)

        # 前景区域加强（接近白色的 alpha 拉到 255）
        mask_fg = arr >= fg_thresh
        arr[mask_fg] = 255.0

        # 背景区域削弱（接近黑色的 alpha 拉到 0）
        mask_bg = arr <= bg_thresh
        arr[mask_bg] = 0.0

        # 中间区域做平滑过渡
        mask_mid = ~mask_fg & ~mask_bg
        if mask_mid.any():
            # 线性映射中间区域
            arr[mask_mid] = np.clip(
                (arr[mask_mid] - bg_thresh) / max(fg_thresh - bg_thresh, 1) * 255,
                0, 255
            )

        return Image.fromarray(arr.astype(np.uint8))

    def _shrink_edges(self, alpha: Image.Image, pixels: int = 1) -> Image.Image:
        """边缘收缩 - 减少白边/锯齿"""
        try:
            arr = np.array(alpha)
            # 简单的形态学侵蚀：每个像素取周围最小值
            from scipy.ndimage import minimum_filter
            eroded = minimum_filter(arr, size=pixels * 2 + 1)
            return Image.fromarray(eroded)
        except ImportError:
            # scipy 不可用时回退到 PIL 的 MinFilter
            return alpha.filter(ImageFilter.MinFilter(size=pixels * 2 + 1))

    def get_alpha_params(self, model_name: str) -> dict:
        """获取模型的 alpha matting 参数（供 rembg.remove 调用）"""
        return self._build_alpha_params(model_name)
