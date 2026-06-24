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

        corner_mask = self._detect_corner_watermarks(img_array, sensitivity)
        corner_area = int(np.sum(corner_mask > 0))
        if 20 <= corner_area <= w * h * 0.025:
            return self._postprocess(corner_mask, w, h, {**p, "min_area": 20})

        tiled_mask = self._detect_tiled_watermarks(img_array, sensitivity)
        tiled_area = int(np.sum(tiled_mask > 0))
        if w * h * 0.005 <= tiled_area <= w * h * 0.28:
            return tiled_mask

        ocr_mask = self._detect_safe_ocr_watermark(img_array)
        ocr_area = int(np.sum(ocr_mask > 0))
        if w * h * 0.002 <= ocr_area <= w * h * 0.075:
            return self._postprocess(ocr_mask, w, h, {**p, "min_area": 20})

        return np.zeros((h, w), dtype=np.uint8)

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

    def _detect_safe_ocr_watermark(self, img_array: np.ndarray) -> np.ndarray:
        cv2 = self.cv2
        h, w = img_array.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        if self.ocr is False:
            return mask

        try:
            result = self.ocr(img_array)
            if not result or not result[0]:
                return mask
            for item in result[0]:
                bbox = item[0]
                if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
                    continue
                pts = np.array(bbox, dtype=np.int32)
                x, y, bw, bh = cv2.boundingRect(pts)
                area = bw * bh
                near_edge = x < w * 0.18 or x + bw > w * 0.82 or y < h * 0.18 or y + bh > h * 0.82
                small_text = area <= w * h * 0.03 and bw >= 8 and bh >= 8
                if near_edge and small_text:
                    cv2.fillPoly(mask, [pts], 255)
        except Exception as e:
            logger.warning(f"安全OCR检测失败: {e}")
            return np.zeros((h, w), dtype=np.uint8)

        return cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)), iterations=2)

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

    def _detect_tiled_watermarks(self, img_array: np.ndarray, sensitivity: str) -> np.ndarray:
        cv2 = self.cv2
        h, w = img_array.shape[:2]
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)

        local = cv2.GaussianBlur(gray, (0, 0), sigmaX=max(min(w, h) / 55, 9))
        diff = cv2.absdiff(gray, local)
        soft_text = cv2.inRange(hsv, np.array([0, 0, 70]), np.array([180, 80, 210]))
        _, subtle = cv2.threshold(diff, {"low": 16, "medium": 12, "high": 9}.get(sensitivity, 12), 255, cv2.THRESH_BINARY)
        candidate = cv2.bitwise_and(soft_text, subtle)

        edges = cv2.Canny(gray, 18, 70)
        candidate = cv2.bitwise_or(candidate, cv2.bitwise_and(edges, soft_text))
        candidate = cv2.morphologyEx(candidate, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)), iterations=1)

        grid_x, grid_y = 4, 5
        cells = []
        for gy in range(grid_y):
            row = []
            for gx in range(grid_x):
                x1 = gx * w // grid_x
                x2 = (gx + 1) * w // grid_x
                y1 = gy * h // grid_y
                y2 = (gy + 1) * h // grid_y
                ratio = int(np.sum(candidate[y1:y2, x1:x2] > 0)) / max((x2 - x1) * (y2 - y1), 1)
                row.append(ratio > 0.0008)
            cells.append(row)

        occupied = sum(1 for row in cells for hit in row if hit)
        adjacent = 0
        for gy in range(grid_y):
            for gx in range(grid_x):
                if not cells[gy][gx]:
                    continue
                if gx + 1 < grid_x and cells[gy][gx + 1]:
                    adjacent += 1
                if gy + 1 < grid_y and cells[gy + 1][gx]:
                    adjacent += 1

        coverage = int(np.sum(candidate > 0)) / max(w * h, 1)
        repeated = occupied >= 5 and adjacent >= 3
        if not repeated or not (0.002 <= coverage <= 0.16):
            return np.zeros((h, w), dtype=np.uint8)

        result = cv2.dilate(candidate, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=2)
        result_area = int(np.sum(result > 0)) / max(w * h, 1)
        if result_area > 0.18:
            return np.zeros((h, w), dtype=np.uint8)
        return result

    def _detect_corner_watermarks(self, img_array: np.ndarray, sensitivity: str) -> np.ndarray:
        cv2 = self.cv2
        h, w = img_array.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)

        roi_w = max(int(w * 0.28), 180)
        roi_h = max(int(h * 0.18), 120)
        margin = max(min(w, h) // 80, 8)
        rois = [
            (0, 0, min(roi_w, w), min(roi_h, h)),
            (max(w - roi_w, 0), 0, w, min(roi_h, h)),
            (0, max(h - roi_h, 0), min(roi_w, w), h),
            (max(w - roi_w, 0), max(h - roi_h, 0), w, h),
        ]
        min_area = {"low": 80, "medium": 45, "high": 25}.get(sensitivity, 45)
        max_area = max(int(w * h * 0.04), 2000)

        for x1, y1, x2, y2 in rois:
            roi_gray = gray[y1:y2, x1:x2]
            roi_hsv = hsv[y1:y2, x1:x2]
            if roi_gray.size == 0:
                continue

            bright = cv2.inRange(roi_hsv, np.array([0, 0, 145]), np.array([180, 95, 255]))
            local = cv2.adaptiveThreshold(
                roi_gray,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                31,
                -6,
            )
            candidate = cv2.bitwise_and(bright, local)
            candidate = cv2.morphologyEx(candidate, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)), iterations=1)
            candidate = cv2.dilate(candidate, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=1)

            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(candidate, connectivity=8)
            boxes = []
            for i in range(1, num_labels):
                area = stats[i, cv2.CC_STAT_AREA]
                bw = stats[i, cv2.CC_STAT_WIDTH]
                bh = stats[i, cv2.CC_STAT_HEIGHT]
                if min_area <= area <= max_area and bw >= 3 and bh >= 3:
                    x = stats[i, cv2.CC_STAT_LEFT]
                    y = stats[i, cv2.CC_STAT_TOP]
                    boxes.append((x, y, x + bw, y + bh))

            if not boxes:
                continue

            bx1 = max(min(b[0] for b in boxes) - margin, 0)
            by1 = max(min(b[1] for b in boxes) - margin, 0)
            bx2 = min(max(b[2] for b in boxes) + margin, x2 - x1)
            by2 = min(max(b[3] for b in boxes) + margin, y2 - y1)
            box_w = bx2 - bx1
            box_h = by2 - by1
            if box_w * box_h <= max_area and box_w >= 12 and box_h >= 8:
                mask[y1 + by1:y1 + by2, x1 + bx1:x1 + bx2] = 255

        bottom_right = self._detect_bottom_right_signature(img_array)
        return cv2.bitwise_or(mask, bottom_right)

    def _detect_bottom_right_signature(self, img_array: np.ndarray) -> np.ndarray:
        cv2 = self.cv2
        h, w = img_array.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

        x1 = int(w * 0.62)
        y1 = int(h * 0.74)
        roi_hsv = hsv[y1:h, x1:w]
        roi_gray = gray[y1:h, x1:w]
        if roi_hsv.size == 0:
            return mask

        bright = cv2.inRange(roi_hsv, np.array([0, 0, 125]), np.array([180, 140, 255]))
        dark = cv2.inRange(roi_hsv, np.array([0, 0, 0]), np.array([180, 160, 95]))
        local = cv2.GaussianBlur(roi_gray, (0, 0), sigmaX=max(min(w, h) / 120, 5))
        diff = cv2.absdiff(roi_gray, local)
        _, contrast = cv2.threshold(diff, 10, 255, cv2.THRESH_BINARY)
        edges = cv2.Canny(roi_gray, 24, 90)
        candidate = cv2.bitwise_or(cv2.bitwise_or(bright, dark), cv2.bitwise_or(contrast, edges))
        candidate = cv2.morphologyEx(candidate, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)), iterations=1)
        candidate = cv2.morphologyEx(candidate, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (7, 3)), iterations=2)

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(candidate, connectivity=8)
        boxes = []
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            bw = stats[i, cv2.CC_STAT_WIDTH]
            bh = stats[i, cv2.CC_STAT_HEIGHT]
            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP]
            abs_x2 = x1 + x + bw
            abs_y2 = y1 + y + bh
            in_signature_zone = abs_x2 > w * 0.76 and abs_y2 > h * 0.82
            text_like = 4 <= bh <= max(h * 0.08, 28) and 2 <= bw <= max(w * 0.24, 80)
            if in_signature_zone and text_like and 4 <= area <= w * h * 0.01:
                boxes.append((x, y, x + bw, y + bh))

        if not boxes:
            return mask

        pad_x = max(w // 45, 20)
        pad_y = max(h // 60, 14)
        bx1 = max(x1 + min(b[0] for b in boxes) - pad_x, 0)
        by1 = max(y1 + min(b[1] for b in boxes) - pad_y, 0)
        bx2 = min(x1 + max(b[2] for b in boxes) + pad_x, w)
        by2 = min(y1 + max(b[3] for b in boxes) + pad_y, h)
        box_area = (bx2 - bx1) * (by2 - by1)
        if box_area <= w * h * 0.035 and bx2 > w * 0.78 and by2 > h * 0.84:
            mask[by1:by2, bx1:bx2] = 255
        return mask

    def _is_bottom_right_mask(self, mask: np.ndarray) -> bool:
        cv2 = self.cv2
        h, w = mask.shape
        if int(np.sum(mask > 0)) <= 0:
            return False
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        xs = []
        ys = []
        xe = []
        ye = []
        for i in range(1, num_labels):
            if stats[i, cv2.CC_STAT_AREA] <= 0:
                continue
            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP]
            bw = stats[i, cv2.CC_STAT_WIDTH]
            bh = stats[i, cv2.CC_STAT_HEIGHT]
            xs.append(x)
            ys.append(y)
            xe.append(x + bw)
            ye.append(y + bh)
        if not xs:
            return False
        x1, y1, x2, y2 = min(xs), min(ys), max(xe), max(ye)
        area = (x2 - x1) * (y2 - y1)
        return x2 > w * 0.76 and y2 > h * 0.80 and area <= w * h * 0.055

    def _expand_bottom_right_mask(self, mask: np.ndarray) -> np.ndarray:
        cv2 = self.cv2
        h, w = mask.shape
        expanded = mask.copy()
        if not self._is_bottom_right_mask(mask):
            return expanded
        num_labels, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        for i in range(1, num_labels):
            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP]
            bw = stats[i, cv2.CC_STAT_WIDTH]
            bh = stats[i, cv2.CC_STAT_HEIGHT]
            corner_signature = x + bw > w * 0.76 and y + bh > h * 0.80 and bw * bh <= w * h * 0.045
            if corner_signature:
                pad_x = max(w // 80, 8)
                pad_y = max(h // 90, 6)
                expanded[max(y - pad_y, 0):min(y + bh + pad_y, h), max(x - pad_x, 0):min(x + bw + pad_x, w)] = 255
        return expanded

    def _prefill_edge_watermark(self, img_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
        cv2 = self.cv2
        prepared = img_bgr.copy()
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        h, w = mask.shape
        for i in range(1, num_labels):
            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP]
            bw = stats[i, cv2.CC_STAT_WIDTH]
            bh = stats[i, cv2.CC_STAT_HEIGHT]
            near_edge = x + bw > w * 0.70 and y + bh > h * 0.78
            if not near_edge or bw * bh > w * h * 0.06:
                continue

            sx1 = max(x - bw, 0)
            sx2 = max(x - 4, 0)
            sy1 = max(y, 0)
            sy2 = min(y + bh, h)
            if sx2 <= sx1 or sy2 <= sy1:
                sy1 = max(y - bh, 0)
                sy2 = max(y - 4, 0)
                sx1 = max(x, 0)
                sx2 = min(x + bw, w)
            if sx2 <= sx1 or sy2 <= sy1:
                continue

            patch = prepared[sy1:sy2, sx1:sx2]
            fill = cv2.resize(patch, (bw, bh), interpolation=cv2.INTER_LINEAR)
            prepared[y:y + bh, x:x + bw] = fill
        return prepared

    def _postprocess(self, mask: np.ndarray, w: int, h: int, params: dict) -> np.ndarray:
        """后处理：过滤噪点，保留合理大小区域"""
        cv2 = self.cv2

        # 连通域分析
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)

        result = np.zeros_like(mask)
        max_area = w * h * 0.15  # 最大不超过15%面积
        corner_margin = min(w, h) * 0.32

        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP]
            bw = stats[i, cv2.CC_STAT_WIDTH]
            bh = stats[i, cv2.CC_STAT_HEIGHT]
            in_corner = (x < corner_margin or x + bw > w - corner_margin) and (y < corner_margin or y + bh > h - corner_margin)
            min_area = 20 if in_corner else params["min_area"]
            if min_area <= area <= max_area:
                result[labels == i] = 255

        # 膨胀确保覆盖
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        result = cv2.dilate(result, kernel, iterations=2)
        result = cv2.morphologyEx(result, cv2.MORPH_CLOSE, kernel, iterations=1)

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
        final_mask = mask.copy()
        corner_only = self._is_bottom_right_mask(final_mask)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        work_mask = cv2.dilate(final_mask, kernel, iterations=2 if corner_only else 1)
        prepared = self._prefill_edge_watermark(img_bgr, work_mask)
        radius = max(5, min(16, int(round(min(image.size) / 220)))) if corner_only else max(4, min(12, int(round(min(image.size) / 280))))
        inpainted = cv2.inpaint(prepared, work_mask, inpaintRadius=radius, flags=flags)
        result = img_bgr.copy()
        result[final_mask > 0] = inpainted[final_mask > 0]

        result_rgb = cv2.cvtColor(result, cv2.COLOR_BGR2RGB)
        return Image.fromarray(result_rgb)

    def process_image_with_mask(
        self,
        image: Image.Image,
        sensitivity: str = "medium",
        method: str = "telea",
    ) -> Tuple[Image.Image, np.ndarray, dict]:
        image = image.convert("RGB")
        mask = self._expand_bottom_right_mask(self.detect_watermark(image, sensitivity))
        mask_area = int(np.sum(mask > 0))
        if mask_area <= 100:
            return image, mask, {"has_watermark": False, "mask_area": 0, "residual_area": 0, "iterations": 0}

        result = self.remove_watermark(image, mask, method)
        residual_area = 0
        iterations = 1
        bottom_right_only = self._is_bottom_right_mask(mask)
        max_mask_area = image.width * image.height * (0.055 if bottom_right_only else 0.18)
        for _ in range(3):
            residual_mask = self.detect_watermark(result, sensitivity)
            if bottom_right_only:
                corner_zone = np.zeros_like(residual_mask)
                corner_zone[int(image.height * 0.72):image.height, int(image.width * 0.60):image.width] = 255
                residual_mask = self.cv2.bitwise_and(residual_mask, corner_zone)
            residual_area = int(np.sum(residual_mask > 0))
            if residual_area <= 100:
                break
            combined_mask = self.cv2.bitwise_or(mask, residual_mask)
            combined_area = int(np.sum(combined_mask > 0))
            if combined_area > max_mask_area:
                break
            mask = self._expand_bottom_right_mask(combined_mask)
            mask_area = int(np.sum(mask > 0))
            result = self.remove_watermark(image, mask, method)
            iterations += 1

        return result, mask, {
            "has_watermark": True,
            "mask_area": mask_area,
            "residual_area": residual_area,
            "iterations": iterations,
        }

    def process_image(
        self,
        image_bytes: bytes,
        sensitivity: str = "medium",
        method: str = "telea",
    ) -> Tuple[bytes, dict]:
        start = time.time()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        original_size = image.size
        result, _, metadata = self.process_image_with_mask(image, sensitivity, method)

        buf = io.BytesIO()
        result.save(buf, format="PNG", quality=95)
        metadata = {
            **metadata,
            "original_size": f"{original_size[0]}x{original_size[1]}",
            "processing_time_ms": int((time.time() - start) * 1000),
        }
        return buf.getvalue(), metadata

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
