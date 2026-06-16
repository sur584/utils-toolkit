"""
可见水印检测与去除服务
自动检测图片上的文字/Logo水印，使用 Inpainting 技术修复
"""

import io
import logging
import time
from typing import Tuple, Optional
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)


class WatermarkRemovalService:
    """可见水印智能检测与去除服务"""

    def __init__(self):
        self._ocr = None
        self._cv2 = None

    @property
    def cv2(self):
        if self._cv2 is None:
            import cv2
            self._cv2 = cv2
        return self._cv2

    @property
    def ocr(self):
        if self._ocr is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                self._ocr = RapidOCR()
            except ImportError:
                logger.warning("rapidocr 未安装，文字检测功能不可用")
                self._ocr = False
        return self._ocr

    def detect_watermark(
        self,
        image: Image.Image,
        sensitivity: str = "medium",
    ) -> np.ndarray:
        """
        自动检测可见水印区域，返回二值 mask

        Args:
            image: PIL Image
            sensitivity: 检测灵敏度 ('low', 'medium', 'high')

        Returns:
            numpy array mask (255=水印区域, 0=背景)
        """
        cv2 = self.cv2
        img_array = np.array(image.convert("RGB"))
        h, w = img_array.shape[:2]

        # 灵敏度参数
        params = {
            "low": {"edge_low": 50, "edge_high": 150, "morph_size": 7, "min_area": 800},
            "medium": {"edge_low": 30, "edge_high": 100, "morph_size": 5, "min_area": 400},
            "high": {"edge_low": 20, "edge_high": 80, "morph_size": 3, "min_area": 200},
        }
        p = params.get(sensitivity, params["medium"])

        # 多种检测方法
        masks = []

        # 1. 边缘检测 + 形态学
        edge_mask = self._detect_by_edge(img_array, p)
        masks.append(edge_mask)

        # 2. OCR 文字检测
        ocr_mask = self._detect_by_ocr(img_array)
        if ocr_mask is not None:
            masks.append(ocr_mask)

        # 3. 亮度/对比度异常检测
        bright_mask = self._detect_by_brightness(img_array)
        masks.append(bright_mask)

        # 4. 颜色异常检测（半透明水印常见白色/灰色）
        color_mask = self._detect_by_color(img_array)
        masks.append(color_mask)

        # 合并所有检测结果
        combined = np.zeros((h, w), dtype=np.uint8)
        for m in masks:
            combined = cv2.bitwise_or(combined, m)

        # 后处理
        result = self._postprocess(combined, w, h, p)

        return result

    def _detect_by_edge(self, img_array: np.ndarray, params: dict) -> np.ndarray:
        """边缘检测找水印轮廓"""
        cv2 = self.cv2
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

        # Canny 边缘检测
        edges = cv2.Canny(gray, params["edge_low"], params["edge_high"])

        # 形态学闭操作连接边缘
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (params["morph_size"], params["morph_size"])
        )
        edges = cv2.dilate(edges, kernel, iterations=2)
        edges = cv2.erode(edges, kernel, iterations=1)

        return edges

    def _detect_by_ocr(self, img_array: np.ndarray) -> Optional[np.ndarray]:
        """OCR 检测文字水印"""
        cv2 = self.cv2
        if self.ocr is False:
            return None

        h, w = img_array.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)

        try:
            result = self.ocr(img_array)
            if result and result[0]:
                for item in result[0]:
                    bbox = item[0]
                    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                        pts = np.array(bbox, dtype=np.int32)
                        cv2.fillPoly(mask, [pts], 255)

                # 膨胀扩展
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
                mask = cv2.dilate(mask, kernel, iterations=3)

                return mask
        except Exception as e:
            logger.warning(f"OCR检测失败: {e}")

        return None

    def _detect_by_brightness(self, img_array: np.ndarray) -> np.ndarray:
        """检测亮度异常区域（水印通常较亮或较暗）"""
        cv2 = self.cv2
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape

        # 计算局部亮度均值
        blur = cv2.GaussianBlur(gray, (51, 51), 0)

        # 找亮度异常区域（与局部均值差异大）
        diff = cv2.absdiff(gray, blur)

        # 自适应阈值
        _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)

        # 形态学处理
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

        return thresh

    def _detect_by_color(self, img_array: np.ndarray) -> np.ndarray:
        """检测半透明水印常见颜色（白色、灰色、黑色文字）"""
        cv2 = self.cv2
        h, w = img_array.shape[:2]

        # 转换到 HSV
        hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)

        # 检测高亮度低饱和度区域（白色/灰色水印）
        # H: any, S: low, V: high
        lower_white = np.array([0, 0, 200])
        upper_white = np.array([180, 30, 255])
        white_mask = cv2.inRange(hsv, lower_white, upper_white)

        # 检测低亮度区域（黑色文字水印）
        lower_black = np.array([0, 0, 0])
        upper_black = np.array([180, 255, 50])
        black_mask = cv2.inRange(hsv, lower_black, upper_black)

        # 合并
        combined = cv2.bitwise_or(white_mask, black_mask)

        # 只保留边缘附近的区域（水印通常在边缘或角落）
        # 创建边缘区域 mask
        edge_zone = np.zeros((h, w), dtype=np.uint8)
        margin = min(h, w) // 4
        edge_zone[:margin, :] = 255  # 上
        edge_zone[-margin:, :] = 255  # 下
        edge_zone[:, :margin] = 255  # 左
        edge_zone[:, -margin:] = 255  # 右

        # 中心区域也保留（有些水印在中间）
        center_margin = min(h, w) // 6
        center_zone = np.zeros((h, w), dtype=np.uint8)
        cy, cx = h // 2, w // 2
        center_zone[cy-center_margin:cy+center_margin, cx-center_margin:cx+center_margin] = 255

        valid_zone = cv2.bitwise_or(edge_zone, center_zone)
        result = cv2.bitwise_and(combined, valid_zone)

        # 形态学处理
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        result = cv2.morphologyEx(result, cv2.MORPH_CLOSE, kernel, iterations=2)

        return result

    def _postprocess(self, mask: np.ndarray, w: int, h: int, params: dict) -> np.ndarray:
        """后处理：过滤噪点，保留合理大小区域"""
        cv2 = self.cv2

        # 连通域分析
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)

        result = np.zeros_like(mask)
        max_area = w * h * 0.15  # 最大不超过15%面积

        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if params["min_area"] <= area <= max_area:
                result[labels == i] = 255

        # 膨胀确保覆盖
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        result = cv2.dilate(result, kernel, iterations=2)

        return result

    def remove_watermark(
        self,
        image: Image.Image,
        mask: np.ndarray,
        method: str = "telea",
    ) -> Image.Image:
        """
        使用 Inpainting 去除水印

        Args:
            image: 原图
            mask: 水印区域 mask
            method: 'telea' 或 'ns'

        Returns:
            去水印后的图片
        """
        cv2 = self.cv2
        img_array = np.array(image.convert("RGB"))
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        flags = cv2.INPAINT_NS if method == "ns" else cv2.INPAINT_TELEA
        result = cv2.inpaint(img_bgr, mask, inpaintRadius=3, flags=flags)

        result_rgb = cv2.cvtColor(result, cv2.COLOR_BGR2RGB)
        return Image.fromarray(result_rgb)

    def process_image(
        self,
        image_bytes: bytes,
        sensitivity: str = "medium",
        method: str = "telea",
    ) -> Tuple[bytes, dict]:
        """
        处理单张图片：检测水印 → 去除水印

        Returns:
            (result_bytes, metadata)
        """
        start = time.time()

        image = Image.open(io.BytesIO(image_bytes))
        image = image.convert("RGB")
        original_size = image.size

        # 限制尺寸
        max_dim = 2048
        if max(image.size) > max_dim:
            ratio = max_dim / max(image.size)
            new_size = (int(image.width * ratio), int(image.height * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)

        # 检测水印
        mask = self.detect_watermark(image, sensitivity)
        mask_area = int(np.sum(mask > 0))
        has_watermark = mask_area > 100

        if not has_watermark:
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            return buf.getvalue(), {
                "has_watermark": False,
                "mask_area": 0,
                "processing_time_ms": int((time.time() - start) * 1000),
            }

        # 去除水印
        result = self.remove_watermark(image, mask, method)

        buf = io.BytesIO()
        result.save(buf, format="PNG", quality=95)

        return buf.getvalue(), {
            "has_watermark": True,
            "mask_area": mask_area,
            "original_size": f"{original_size[0]}x{original_size[1]}",
            "processing_time_ms": int((time.time() - start) * 1000),
        }

    def process_batch(
        self,
        items: list,
        sensitivity: str = "medium",
        method: str = "telea",
    ) -> list:
        """批量处理"""
        results = []
        for idx, filename, image_bytes in items:
            try:
                output_data, metadata = self.process_image(image_bytes, sensitivity, method)
                base = filename.rsplit(".", 1)[0] if filename else "image"
                results.append((
                    idx,
                    {
                        "filename": f"{base}_nowm.png",
                        "original_filename": filename,
                        "success": True,
                        **metadata,
                    },
                ))
            except Exception as e:
                logger.error(f"批量去水印失败 {filename}: {e}", exc_info=True)
                results.append((
                    idx,
                    {"filename": filename, "success": False, "error": str(e)[:200]},
                ))
        return results
