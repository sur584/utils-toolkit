"""
图片高清化服务（超分辨率）
使用 OpenCV 的超分辨率算法实现图片放大
"""

import io
import logging
import time
from typing import Tuple
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)


class UpscaleService:
    """图片高清化服务"""

    def __init__(self):
        self._cv2 = None

    @property
    def cv2(self):
        if self._cv2 is None:
            import cv2
            self._cv2 = cv2
        return self._cv2

    def process_image(
        self,
        image_bytes: bytes,
        scale: int = 2,
    ) -> Tuple[bytes, dict]:
        """
        处理单张图片：放大并增强清晰度

        Args:
            image_bytes: 图片字节
            scale: 放大倍数 (2 或 4)

        Returns:
            (result_bytes, metadata)
        """
        start = time.time()
        cv2 = self.cv2

        # 解码图片
        image = Image.open(io.BytesIO(image_bytes))
        image = image.convert("RGB")

        original_w, original_h = image.size

        # 限制输入尺寸（避免内存溢出）
        max_input = 1024 if scale == 4 else 2048
        if max(image.size) > max_input:
            ratio = max_input / max(image.size)
            new_size = (int(image.width * ratio), int(image.height * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)

        # 转换为 OpenCV 格式
        img_array = np.array(image)
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        # 执行超分辨率放大
        result = self._upscale(img_bgr, scale)

        # 转回 RGB
        result_rgb = cv2.cvtColor(result, cv2.COLOR_BGR2RGB)
        result_image = Image.fromarray(result_rgb)

        # 编码输出
        buf = io.BytesIO()
        result_image.save(buf, format="PNG", quality=95)
        result_bytes = buf.getvalue()

        elapsed_ms = int((time.time() - start) * 1000)

        return result_bytes, {
            "scale": scale,
            "original_width": original_w,
            "original_height": original_h,
            "output_width": result_image.width,
            "output_height": result_image.height,
            "processing_time_ms": elapsed_ms,
        }

    def _upscale(self, img_bgr: np.ndarray, scale: int) -> np.ndarray:
        """
        使用 OpenCV 超分辨率算法放大图片

        Args:
            img_bgr: BGR 格式图片
            scale: 放大倍数

        Returns:
            放大后的图片
        """
        cv2 = self.cv2
        h, w = img_bgr.shape[:2]

        if scale == 4:
            # 4倍放大：分两次2倍放大，效果更好
            result = self._upscale_x2(img_bgr)
            result = self._upscale_x2(result)
        else:
            # 2倍放大
            result = self._upscale_x2(img_bgr)

        return result

    def _upscale_x2(self, img_bgr: np.ndarray) -> np.ndarray:
        """
        2倍超分辨率放大

        使用多步骤处理：
        1. 双三次插值放大
        2. 锐化增强
        3. 降噪处理
        """
        cv2 = self.cv2
        h, w = img_bgr.shape[:2]
        new_w, new_h = w * 2, h * 2

        # 步骤1：双三次插值放大
        upscaled = cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

        # 步骤2：Lanczos 锐化（增强细节）
        # 创建锐化核
        kernel = np.array([
            [0, -0.5, 0],
            [-0.5, 3, -0.5],
            [0, -0.5, 0]
        ], dtype=np.float32)
        sharpened = cv2.filter2D(upscaled, -1, kernel)

        # 混合原图和锐化图（避免过度锐化）
        alpha = 0.6
        result = cv2.addWeighted(sharpened, alpha, upscaled, 1 - alpha, 0)

        # 步骤3：轻微降噪（保留边缘）
        result = cv2.fastNlMeansDenoisingColored(
            result,
            None,
            h=3,
            hColor=3,
            templateWindowSize=7,
            searchWindowSize=21,
        )

        # 步骤4：对比度自适应增强
        lab = cv2.cvtColor(result, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)

        # CLAHE 对比度增强
        clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
        l = clahe.apply(l)

        lab = cv2.merge([l, a, b])
        result = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

        return result
