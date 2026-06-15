import base64
import logging
import time

import cv2
import numpy as np
from scipy import fft as scipy_fft
from scipy import signal
from scipy.stats import chi2

logger = logging.getLogger(__name__)


class WatermarkService:

    def detect_lsb(self, img: np.ndarray) -> dict:
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()
            chi_p, chi_stat = self._lsb_chi_square(gray)
            rs_ratio, regular_pos, singular_pos = self._lsb_rs_analysis(gray)

            chi_detected = chi_p < 0.05
            rs_detected = abs(rs_ratio - 1.0) > 0.15

            if chi_detected and rs_detected:
                confidence = min(95, int((1 - chi_p) * 60 + abs(rs_ratio - 1.0) * 200))
                detected = True
            elif chi_detected or rs_detected:
                confidence = min(60, int((1 - chi_p) * 30 + abs(rs_ratio - 1.0) * 100))
                detected = confidence > 30
            else:
                confidence = max(0, int((1 - chi_p) * 10 + abs(rs_ratio - 1.0) * 50))
                detected = False

            confidence = max(0, min(100, confidence))

            # technical_details
            technical_details = {}
            try:
                pixels = gray.flatten()
                total_pixels = len(pixels)
                count_even = int(np.sum(pixels % 2 == 0))
                count_odd = total_pixels - count_even
                if max(count_even, count_odd) > 0:
                    lsb_bias = 1.0 - min(count_even, count_odd) / max(count_even, count_odd)
                else:
                    lsb_bias = 0.0
                affected_ratio = count_even / total_pixels if total_pixels > 0 else 0.0
                bits_analyzed = 2
                estimated_kb = total_pixels * bits_analyzed / 8 / 1024
                technical_details = {
                    "bit_planes_analyzed": [1, 2],
                    "lsb_bias": round(lsb_bias, 4),
                    "affected_pixel_ratio": round(affected_ratio, 4),
                    "estimated_capacity_kb": round(estimated_kb, 2),
                    "chi_square_statistic": round(chi_stat, 2),
                    "rs_regular_blocks": regular_pos,
                    "rs_singular_blocks": singular_pos,
                }
            except Exception:
                technical_details = {}

            return {
                "detected": detected,
                "confidence": confidence,
                "description": "LSB隐写检测：卡方分析和RS分析均未发现明显异常" if not detected else "LSB隐写检测：发现像素最低位存在统计异常，可能嵌入了隐写信息",
                "chi_square_p": round(chi_p, 6),
                "rs_ratio": round(rs_ratio, 4),
                "technical_details": technical_details,
            }
        except Exception as e:
            logger.error(f"LSB detection failed: {e}")
            return {"detected": False, "confidence": 0, "description": f"检测出错: {str(e)[:100]}", "chi_square_p": 1.0, "rs_ratio": 1.0, "technical_details": {}}

    def detect_dct(self, img: np.ndarray) -> dict:
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()
            h, w = gray.shape
            h = h - h % 8
            w = w - w % 8
            gray = gray[:h, :w].astype(np.float64)

            all_coeffs = []
            dc_values = []
            ac_energies = []
            for i in range(0, h, 8):
                for j in range(0, w, 8):
                    block = gray[i:i+8, j:j+8]
                    dct_block = scipy_fft.dctn(block, type=2, norm='ortho')
                    flat = dct_block.flatten()
                    all_coeffs.append(flat)
                    dc_values.append(dct_block[0, 0])
                    ac_energy = np.sum(dct_block ** 2) - dct_block[0, 0] ** 2
                    ac_energies.append(ac_energy)

            coeffs = np.concatenate(all_coeffs)
            coeffs_int = np.round(coeffs).astype(np.int64)

            hist, _ = np.histogram(coeffs_int, bins=range(-256, 258))
            hist = hist.astype(np.float64)
            total = hist.sum()
            if total == 0:
                return {"detected": False, "confidence": 0, "description": "DCT频域分析：图像数据为空", "anomaly_score": 0.0, "technical_details": {}}

            zero_ratio = hist[256] / total if len(hist) > 256 else 0

            peak_count = 0
            for k in range(1, 20):
                idx_pos = 256 + k
                idx_neg = 256 - k
                idx_even = 256 + 2 * k
                if idx_pos < len(hist) and idx_neg < len(hist) and idx_even < len(hist):
                    pair_sum = hist[idx_pos] + hist[idx_neg]
                    even_val = hist[idx_even]
                    if even_val > 0 and pair_sum / even_val > 2.0:
                        peak_count += 1

            anomaly_score = float(zero_ratio * 0.3 + (peak_count / 19) * 0.7)
            detected = bool(anomaly_score > 0.15)
            confidence = max(0, min(100, int(anomaly_score * 100)))

            # technical_details
            technical_details = {}
            try:
                block_count = len(all_coeffs)
                ac_mean = float(np.mean(ac_energies)) if ac_energies else 0.0
                dc_mean = float(np.mean(dc_values)) if dc_values else 0.0
                ac_std = float(np.std(ac_energies)) if ac_energies else 0.0
                q_noise = ac_std / abs(dc_mean) if abs(dc_mean) > 1e-10 else 0.0
                technical_details = {
                    "block_count": block_count,
                    "zero_coeff_ratio": round(zero_ratio, 4),
                    "anomalous_frequency_count": peak_count,
                    "ac_energy_mean": round(ac_mean, 2),
                    "dc_mean": round(dc_mean, 2),
                    "quantization_noise_estimate": round(q_noise, 4),
                }
            except Exception:
                technical_details = {}

            return {
                "detected": detected,
                "confidence": confidence,
                "description": "DCT频域分析：量化系数分布正常，未发现频域水印特征" if not detected else "DCT频域分析：发现量化系数存在异常分布，可能存在频域水印",
                "anomaly_score": round(anomaly_score, 4),
                "technical_details": technical_details,
            }
        except Exception as e:
            logger.error(f"DCT detection failed: {e}")
            return {"detected": False, "confidence": 0, "description": f"检测出错: {str(e)[:100]}", "anomaly_score": 0.0, "technical_details": {}}

    def detect_dwt(self, img: np.ndarray) -> dict:
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()
            gray = gray.astype(np.float64)

            h, w = gray.shape
            h = h - h % 2
            w = w - w % 2
            gray = gray[:h, :w]

            lh, hl, hh = self._haar_dwt2(gray)

            detail_bands = [lh, hl, hh]
            svd_anomalies = []
            for band in detail_bands:
                U, S, Vt = np.linalg.svd(band, full_matrices=False)
                if len(S) > 1:
                    s_norm = S / (S.sum() + 1e-10)
                    entropy = -np.sum(s_norm * np.log2(s_norm + 1e-10))
                    max_entropy = np.log2(len(S))
                    ratio = entropy / max_entropy if max_entropy > 0 else 0
                    svd_anomalies.append(ratio)
                else:
                    svd_anomalies.append(0.0)

            svd_anomaly = np.mean(svd_anomalies) if svd_anomalies else 0.0

            high_freq_energy = sum(np.sum(b ** 2) for b in detail_bands)
            total_energy = np.sum(gray ** 2) + high_freq_energy
            energy_ratio = high_freq_energy / (total_energy + 1e-10)

            combined = float(svd_anomaly * 0.6 + energy_ratio * 0.4)
            detected = bool(combined > 0.55)
            confidence = max(0, min(100, int(combined * 100)))

            # technical_details
            technical_details = {}
            try:
                lh_energy = float(np.sum(lh ** 2))
                hl_energy = float(np.sum(hl ** 2))
                hh_energy = float(np.sum(hh ** 2))
                technical_details = {
                    "subband_energies": {
                        "LH": round(lh_energy, 4),
                        "HL": round(hl_energy, 4),
                        "HH": round(hh_energy, 4),
                    },
                    "svd_ratios": {
                        "LH": round(svd_anomalies[0], 4),
                        "HL": round(svd_anomalies[1], 4),
                        "HH": round(svd_anomalies[2], 4),
                    },
                    "high_freq_energy_ratio": round(float(energy_ratio), 4),
                    "image_dimensions": [h, w],
                }
            except Exception:
                technical_details = {}

            return {
                "detected": detected,
                "confidence": confidence,
                "description": "DWT小波分析：高频子带统计特征正常" if not detected else "DWT小波分析：高频子带存在异常能量分布，可能含有小波域水印",
                "svd_anomaly": round(svd_anomaly, 4),
                "technical_details": technical_details,
            }
        except Exception as e:
            logger.error(f"DWT detection failed: {e}")
            return {"detected": False, "confidence": 0, "description": f"检测出错: {str(e)[:100]}", "svd_anomaly": 0.0, "technical_details": {}}

    def detect_alpha(self, img: np.ndarray, has_alpha: bool) -> dict:
        try:
            if not has_alpha:
                return {"detected": False, "confidence": 0, "description": "Alpha通道检测：图像不含Alpha通道", "alpha_entropy": 0.0, "technical_details": {}}

            alpha = img[:, :, 3]
            hist, _ = np.histogram(alpha, bins=256, range=(0, 256))
            hist = hist.astype(np.float64)
            total = hist.sum()
            if total == 0:
                return {"detected": False, "confidence": 0, "description": "Alpha通道检测：Alpha通道为空", "alpha_entropy": 0.0, "technical_details": {}}

            prob = hist / total
            entropy = -np.sum(prob * np.log2(prob + 1e-10))

            unique_ratio = np.count_nonzero(hist) / 256.0

            non_extreme = np.sum((alpha > 0) & (alpha < 255))
            non_extreme_ratio = non_extreme / alpha.size

            alpha_detected = False
            alpha_confidence = 0

            if entropy > 4.0 and unique_ratio > 0.5:
                alpha_detected = True
                alpha_confidence = min(90, int(entropy * 10 + non_extreme_ratio * 30))
            elif entropy > 3.0 and non_extreme_ratio > 0.01:
                alpha_detected = True
                alpha_confidence = min(60, int(entropy * 8 + non_extreme_ratio * 20))
            else:
                alpha_confidence = max(0, int(entropy * 3))

            alpha_confidence = max(0, min(100, alpha_confidence))

            # technical_details
            technical_details = {}
            try:
                unique_count = int(np.count_nonzero(hist))
                alpha_data = alpha.astype(np.float64)
                alpha_mean = float(np.mean(alpha_data))
                alpha_std = float(np.std(alpha_data))
                if unique_count <= 3:
                    dist_desc = "binary (0/255)"
                elif unique_count > 100:
                    dist_desc = "continuous"
                else:
                    dist_desc = "discrete"
                technical_details = {
                    "unique_alpha_values": unique_count,
                    "non_trivial_pixel_count": int(non_extreme),
                    "non_trivial_pixel_ratio": round(float(non_extreme_ratio), 4),
                    "alpha_mean": round(alpha_mean, 2),
                    "alpha_std": round(alpha_std, 2),
                    "value_distribution": dist_desc,
                }
            except Exception:
                technical_details = {}

            return {
                "detected": alpha_detected,
                "confidence": alpha_confidence,
                "description": "Alpha通道检测：透明通道分布正常" if not alpha_detected else "Alpha通道检测：透明通道存在异常分布，可能通过Alpha通道嵌入信息",
                "alpha_entropy": round(entropy, 4),
                "technical_details": technical_details,
            }
        except Exception as e:
            logger.error(f"Alpha detection failed: {e}")
            return {"detected": False, "confidence": 0, "description": f"检测出错: {str(e)[:100]}", "alpha_entropy": 0.0, "technical_details": {}}

    def detect_visual(self, img: np.ndarray) -> dict:
        try:
            h, w = img.shape[:2]

            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float64)
            l_channel = lab[:, :, 0]

            enhanced_l = np.clip(l_channel * 3.5, 0, 255)
            clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
            cl_l = clahe.apply(enhanced_l.astype(np.uint8))

            lab[:, :, 0] = cl_l
            enhanced = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)

            channels = cv2.split(img)
            channel_names = ["B", "G", "R"]
            channel_previews = []
            for ch, name in zip(channels, channel_names):
                boosted = np.clip(ch.astype(np.float64) * 4.0, 0, 255).astype(np.uint8)
                clahe_ch = clahe.apply(boosted)
                channel_previews.append(clahe_ch)

            canvas_h = h * 2
            canvas_w = w * 2
            canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
            canvas[0:h, 0:w] = enhanced
            for idx, ch_preview in enumerate(channel_previews):
                color_map = np.zeros((h, w, 3), dtype=np.uint8)
                color_map[:, :, idx] = ch_preview
                row = idx // 2
                col = idx % 2 + 1
                if row == 0 and col == 2:
                    canvas[0:h, w:w*2] = color_map
                elif row == 1 and col == 1:
                    canvas[h:h*2, 0:w] = color_map
                elif row == 1 and col == 2:
                    canvas[h:h*2, w:w*2] = color_map

            scale = min(1.0, 800 / max(canvas_h, canvas_w))
            if scale < 1.0:
                new_size = (int(canvas_w * scale), int(canvas_h * scale))
                canvas = cv2.resize(canvas, new_size, interpolation=cv2.INTER_AREA)

            _, buf = cv2.imencode('.png', canvas)
            b64 = base64.b64encode(buf).decode('ascii')

            return {
                "detected": False,
                "confidence": 0,
                "description": "可视化攻击：已生成增强预览图，请人工检查是否存在隐藏图案",
                "enhanced_preview": b64,
            }
        except Exception as e:
            logger.error(f"Visual detection failed: {e}")
            return {"detected": False, "confidence": 0, "description": f"检测出错: {str(e)[:100]}", "enhanced_preview": ""}

    def detect_statistical(self, img: np.ndarray) -> dict:
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()

            hist, _ = np.histogram(gray, bins=256, range=(0, 256))
            hist = hist.astype(np.float64)
            total = hist.sum()
            if total == 0:
                return {"detected": False, "confidence": 0, "description": "统计分析：图像数据为空", "entropy": 0.0, "histogram_uniformity": 0.0, "technical_details": {}}

            prob = hist / total
            entropy = -np.sum(prob * np.log2(prob + 1e-10))

            expected = total / 256.0
            chi_stat = np.sum((hist - expected) ** 2 / (expected + 1e-10))
            uniformity = 1.0 - min(1.0, chi_stat / (total * 10))

            pair_diffs = []
            for k in range(128):
                idx_even = 2 * k
                idx_odd = 2 * k + 1
                if hist[idx_even] + hist[idx_odd] > 0:
                    diff = abs(hist[idx_even] - hist[idx_odd]) / (hist[idx_even] + hist[idx_odd] + 1e-10)
                    pair_diffs.append(diff)

            avg_pair_diff = np.mean(pair_diffs) if pair_diffs else 1.0

            stat_detected = False
            stat_confidence = 0

            if avg_pair_diff < 0.05 and entropy > 7.0:
                stat_detected = True
                stat_confidence = min(85, int((1 - avg_pair_diff) * 50 + entropy * 5))
            elif avg_pair_diff < 0.1 and entropy > 6.5:
                stat_confidence = min(50, int((1 - avg_pair_diff) * 30 + entropy * 3))

            stat_confidence = max(0, min(100, stat_confidence))

            # technical_details
            technical_details = {}
            try:
                unique_pixel_values = int(np.count_nonzero(hist))
                if avg_pair_diff < 0.05:
                    dist_desc = "uniform"
                elif avg_pair_diff < 0.2:
                    dist_desc = "normal"
                else:
                    dist_desc = "skewed"
                technical_details = {
                    "image_entropy": round(entropy, 4),
                    "max_possible_entropy": 8.0,
                    "entropy_utilization": round(entropy / 8.0, 4),
                    "histogram_chi_square": round(float(chi_stat), 2),
                    "pair_symmetry_index": round(float(avg_pair_diff), 4),
                    "unique_pixel_values": unique_pixel_values,
                    "pixel_distribution": dist_desc,
                }
            except Exception:
                technical_details = {}

            return {
                "detected": stat_detected,
                "confidence": stat_confidence,
                "description": "统计分析：像素分布正常" if not stat_detected else "统计分析：像素值对称性异常，偶数/奇数像素值分布过于均匀，可能存在LSB隐写",
                "entropy": round(entropy, 4),
                "histogram_uniformity": round(uniformity, 4),
                "technical_details": technical_details,
            }
        except Exception as e:
            logger.error(f"Statistical detection failed: {e}")
            return {"detected": False, "confidence": 0, "description": f"检测出错: {str(e)[:100]}", "entropy": 0.0, "histogram_uniformity": 0.0, "technical_details": {}}

    def detect_all(self, img_bytes: bytes) -> dict:
        start = time.time()

        try:
            img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
            if img is None:
                return {"has_watermark": False, "confidence": 0, "types": [], "details": {}, "visualization": "", "processing_time": round(time.time() - start, 3), "image_info": {}}
        except Exception as e:
            logger.error(f"Image decode failed: {e}")
            return {"has_watermark": False, "confidence": 0, "types": [], "details": {}, "visualization": "", "processing_time": round(time.time() - start, 3), "image_info": {}}

        h, w = img.shape[:2]
        has_alpha = len(img.shape) == 3 and img.shape[2] == 4
        channels = img.shape[2] if len(img.shape) == 3 else 1

        if has_alpha:
            bgr = img[:, :, :3]
        else:
            bgr = img if len(img.shape) == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

        results = {}
        methods = [
            ("lsb", lambda: self.detect_lsb(bgr)),
            ("dct", lambda: self.detect_dct(bgr)),
            ("dwt", lambda: self.detect_dwt(bgr)),
            ("alpha", lambda: self.detect_alpha(img, has_alpha)),
            ("visual", lambda: self.detect_visual(bgr)),
            ("statistical", lambda: self.detect_statistical(bgr)),
        ]

        for name, fn in methods:
            try:
                results[name] = fn()
            except Exception as e:
                logger.error(f"Detection method {name} failed: {e}")
                results[name] = {"detected": False, "confidence": 0, "description": f"检测出错: {str(e)[:100]}"}

        detected_types = [name for name, r in results.items() if r.get("detected")]

        if detected_types:
            confidences = [results[t]["confidence"] for t in detected_types]
            overall_confidence = min(100, int(np.mean(confidences) * 1.2))
        else:
            all_conf = [r.get("confidence", 0) for r in results.values()]
            overall_confidence = min(30, int(np.mean(all_conf)))

        visualization = self._generate_heatmap(bgr, results)

        return {
            "has_watermark": len(detected_types) > 0,
            "confidence": overall_confidence,
            "types": detected_types,
            "details": results,
            "visualization": visualization,
            "processing_time": round(time.time() - start, 3),
            "image_info": {
                "width": w,
                "height": h,
                "channels": channels,
                "has_alpha": has_alpha,
                "format": "BGRA" if has_alpha else "BGR",
                "total_pixels": h * w,
                "file_size_kb": round(len(img_bytes) / 1024, 2),
            },
        }

    def remove_lsb(self, img: np.ndarray, bits: int = 2) -> np.ndarray:
        mask = 0xFF << bits
        return (img.astype(np.uint16) & mask).astype(np.uint8)

    def remove_gaussian(self, img: np.ndarray, strength: float = 1.0) -> np.ndarray:
        ksize = max(3, int(3 + strength * 2))
        if ksize % 2 == 0:
            ksize += 1
        return cv2.GaussianBlur(img, (ksize, ksize), 0)

    def remove_jpeg(self, img: np.ndarray, quality: int = 50) -> np.ndarray:
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        _, buf = cv2.imencode('.jpg', img, encode_params)
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)

    def remove_bitplane(self, img: np.ndarray, planes: list = None) -> np.ndarray:
        if planes is None:
            planes = [0, 1]
        mask = 0xFF
        for p in planes:
            mask &= ~(1 << p)
        return (img.astype(np.uint16) & mask).astype(np.uint8)

    def remove_watermark(self, img_bytes: bytes, method: str = "combo", strength: int = 5) -> bytes:
        strength = max(1, min(10, strength))

        img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Cannot decode image")

        result = img.copy()

        if method == "lsb":
            bits = max(1, min(4, strength // 2 + 1))
            result = self.remove_lsb(result, bits=bits)

        elif method == "blur":
            s = strength / 5.0
            result = self.remove_gaussian(result, strength=s)

        elif method == "jpeg":
            quality = max(10, 100 - strength * 8)
            result = self.remove_jpeg(result, quality=quality)

        elif method == "bitplane":
            planes = list(range(0, max(1, strength // 2 + 1)))
            result = self.remove_bitplane(result, planes=planes)

        elif method == "combo":
            lsb_bits = max(1, min(3, strength // 3 + 1))
            result = self.remove_lsb(result, bits=lsb_bits)

            blur_s = strength / 8.0
            result = self.remove_gaussian(result, strength=blur_s)

            quality = max(20, 100 - strength * 6)
            result = self.remove_jpeg(result, quality=quality)

            if strength >= 5:
                planes = list(range(0, max(1, strength // 4 + 1)))
                result = self.remove_bitplane(result, planes=planes)

        else:
            raise ValueError(f"Unknown method: {method}")

        _, buf = cv2.imencode('.png', result)
        return buf.tobytes()

    def _lsb_chi_square(self, gray: np.ndarray) -> float:
        pixels = gray.flatten()
        observed = np.zeros(128, dtype=np.float64)
        expected = np.zeros(128, dtype=np.float64)

        for k in range(128):
            observed[k] = np.sum(pixels == 2 * k)
            expected[k] = np.sum(pixels == 2 * k + 1)

        mask = (observed + expected) > 0
        obs = observed[mask]
        exp = expected[mask]

        combined = obs + exp
        combined[combined == 0] = 1e-10

        chi_stat = np.sum((obs - combined / 2) ** 2 / (combined / 2))
        dof = max(1, len(obs) - 1)
        p_value = 1 - chi2.cdf(chi_stat, dof)

        return (p_value, float(chi_stat))

    def _lsb_rs_analysis(self, gray: np.ndarray) -> float:
        h, w = gray.shape
        block_h = h - h % 2
        block_w = w - w % 2
        gray = gray[:block_h, :block_w]

        regular_pos = 0
        singular_pos = 0
        regular_neg = 0
        singular_neg = 0

        for i in range(0, block_h, 2):
            for j in range(0, block_w, 2):
                block = gray[i:i+2, j:j+2].flatten().astype(np.int32)
                diff_orig = self._smoothness(block)

                flipped_pos = self._flip_lsb(block, positive=True)
                diff_pos = self._smoothness(flipped_pos)

                flipped_neg = self._flip_lsb(block, positive=False)
                diff_neg = self._smoothness(flipped_neg)

                if diff_pos > diff_orig:
                    regular_pos += 1
                elif diff_pos < diff_orig:
                    singular_pos += 1

                if diff_neg > diff_orig:
                    regular_neg += 1
                elif diff_neg < diff_orig:
                    singular_neg += 1

        total = regular_pos + singular_pos
        if total == 0:
            return (1.0, regular_pos, singular_pos)

        ratio = (regular_pos + regular_neg) / max(1, singular_pos + singular_neg)
        return (ratio, regular_pos, singular_pos)

    def _smoothness(self, block: np.ndarray) -> int:
        diff = 0
        for i in range(len(block) - 1):
            diff += abs(block[i + 1] - block[i])
        return diff

    def _flip_lsb(self, block: np.ndarray, positive: bool = True) -> np.ndarray:
        result = block.copy()
        for i in range(len(result)):
            lsb = result[i] & 1
            if positive:
                if lsb == 0:
                    result[i] = result[i] + 1 if result[i] < 255 else result[i]
                else:
                    result[i] = result[i] - 1
            else:
                if lsb == 0:
                    result[i] = result[i] - 1 if result[i] > 0 else result[i]
                else:
                    result[i] = result[i] + 1 if result[i] < 255 else result[i]
        return result

    def _haar_dwt2(self, data: np.ndarray):
        h, w = data.shape
        h = h - h % 2
        w = w - w % 2
        data = data[:h, :w]

        low_h = h // 2
        even_rows = data[0::2, :]
        odd_rows = data[1::2, :]
        low_pass_rows = (even_rows + odd_rows) / 2.0
        high_pass_rows = (even_rows - odd_rows) / 2.0

        low_w = w // 2
        ll = (low_pass_rows[:, 0::2] + low_pass_rows[:, 1::2]) / 2.0
        lh = (low_pass_rows[:, 0::2] - low_pass_rows[:, 1::2]) / 2.0
        hl = (high_pass_rows[:, 0::2] + high_pass_rows[:, 1::2]) / 2.0
        hh = (high_pass_rows[:, 0::2] - high_pass_rows[:, 1::2]) / 2.0

        return lh, hl, hh

    def _generate_heatmap(self, img: np.ndarray, results: dict) -> str:
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()
            h, w = gray.shape

            score_map = np.zeros((h, w), dtype=np.float64)

            block_size = 32
            for i in range(0, h - block_size + 1, block_size):
                for j in range(0, w - block_size + 1, block_size):
                    block = gray[i:i+block_size, j:j+block_size]
                    block_score = 0.0

                    if results.get("lsb", {}).get("detected"):
                        pair_diffs = []
                        for k in range(128):
                            e = np.sum(block == 2 * k)
                            o = np.sum(block == 2 * k + 1)
                            if e + o > 0:
                                pair_diffs.append(abs(e - o) / (e + o + 1e-10))
                        if pair_diffs:
                            block_score += (1 - np.mean(pair_diffs)) * 30

                    if results.get("statistical", {}).get("detected"):
                        hist, _ = np.histogram(block, bins=256, range=(0, 256))
                        prob = hist.astype(np.float64) / (block.size + 1e-10)
                        ent = -np.sum(prob * np.log2(prob + 1e-10))
                        block_score += ent * 3

                    if results.get("dct", {}).get("detected"):
                        block_f = block.astype(np.float64)
                        dct_b = scipy_fft.dctn(block_f, type=2, norm='ortho')
                        ac_energy = np.sum(dct_b ** 2) - dct_b[0, 0] ** 2
                        block_score += min(20, ac_energy / (block.size * 100))

                    score_map[i:i+block_size, j:j+block_size] = block_score

            if score_map.max() > 0:
                score_map = score_map / score_map.max() * 255
            score_map = score_map.astype(np.uint8)

            heatmap = cv2.applyColorMap(score_map, cv2.COLORMAP_JET)

            alpha = 0.5
            if len(img.shape) == 3:
                overlay = cv2.addWeighted(img, 1 - alpha, heatmap, alpha, 0)
            else:
                img_color = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                overlay = cv2.addWeighted(img_color, 1 - alpha, heatmap, alpha, 0)

            _, buf = cv2.imencode('.png', overlay)
            return base64.b64encode(buf).decode('ascii')
        except Exception as e:
            logger.error(f"Heatmap generation failed: {e}")
            return ""
