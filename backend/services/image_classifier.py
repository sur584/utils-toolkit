"""
图片分类器 - 使用 MobileNetV3 ONNX 推理识别图片类型
分类结果：product / portrait / pet / general

P0 (2026-08-05): 原 onnx/models GitHub 路径已 404（v3 文件被移除），
                 MODEL_URL 改为 MODEL_URLS 列表，按顺序 fallback 下载，
                 首选 HuggingFace onnx-community 镜像。
P1 (2026-08-05): 加进程内下载锁 + 双重检查 + 5 分钟失败冷却，
                 并使用 .downloading 临时文件防止半成品被误读。
P2 (2026-08-05): 连续失败 3 次后全局禁用分类器，静默返回 general，
                 避免批量任务中每个请求都刷错误日志。
"""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class ImageClassifier:
    """使用 MobileNetV3 ONNX 推理对图片进行分类"""

    # P0: 多源 fallback，按顺序尝试，第一个成功即使用。
    # 原 GitHub onnx/models 路径已 404（该仓库 mobilenet 目录下 v3 文件被移除，
    # 目前只剩 mobilenetv2-*）。首选 HuggingFace onnx-community 转换的 timm
    # MobileNetV3-Small-100（ImageNet-1k，1000 类，预处理与原模型一致）。
    MODEL_URLS = [
        "https://huggingface.co/onnx-community/mobilenetv3_small_100.lamb_in1k/resolve/main/onnx/model.onnx",
        # 历史路径，保留作为最后 fallback；已确认 404，实际不会命中。
        "https://github.com/onnx/models/raw/main/validated/vision/classification/mobilenet/model/mobilenetv3-small-12.onnx",
    ]
    MODEL_FILENAME = "mobilenetv3_classifier.onnx"

    # P1: 下载失败后冷却时间（秒），冷却期内直接放弃下载，让上层降级 general。
    _RETRY_INTERVAL = 300

    # P2: 连续失败达到该阈值后全局禁用分类器（不再尝试加载/推理）。
    _DISABLE_THRESHOLD = 3

    def __init__(self, models_dir: str = None):
        self._session = None
        self._models_dir = Path(models_dir) if models_dir else Path("models")
        self._model_path = self._models_dir / self.MODEL_FILENAME
        self._input_name = None
        self._loaded = False

        # P1: 下载流程的进程内互斥锁 + 失败冷却时间戳。
        self._download_lock = threading.Lock()
        self._last_failure_time: float = 0.0

        # P2: 连续失败计数与全局禁用开关；用独立轻量锁保护计数，
        # 避免与下载锁竞争导致推理请求被串行化。
        self._state_lock = threading.Lock()
        self._failure_count: int = 0
        self._disabled: bool = False

    def _ensure_model(self):
        """确保模型文件存在，不存在则按 MODEL_URLS 顺序下载（线程安全 + 失败冷却）"""
        # P1: 双重检查 - 锁外快路径，避免每次都抢锁。
        if self._model_path.exists():
            return

        with self._download_lock:
            # P1: 进入锁后再次检查，可能其他线程已经下载完成。
            if self._model_path.exists():
                return

            # P1: 冷却期内直接失败，避免批量任务中每个请求都重复打网络。
            now = time.time()
            if self._last_failure_time and now - self._last_failure_time < self._RETRY_INTERVAL:
                remaining = int(self._RETRY_INTERVAL - (now - self._last_failure_time))
                raise RuntimeError(
                    f"分类模型近期下载失败，{remaining}s 内不再重试（已降级 general）"
                )

            self._models_dir.mkdir(parents=True, exist_ok=True)
            # P1: 用 .downloading 后缀防止半成品被其他线程/进程当成有效文件读取。
            tmp_path = self._model_path.with_suffix(".downloading")

            last_error: Optional[Exception] = None
            for idx, url in enumerate(self.MODEL_URLS):
                try:
                    logger.info(f"下载 MobileNetV3 分类模型 [{idx + 1}/{len(self.MODEL_URLS)}]: {url}")
                    if tmp_path.exists():
                        tmp_path.unlink()
                    import urllib.request
                    urllib.request.urlretrieve(url, str(tmp_path))
                    # P1: 原子替换，落盘成功后其他线程才能看到完整文件。
                    os.replace(tmp_path, self._model_path)
                    logger.info("MobileNetV3 模型下载完成")
                    # P2: 下载成功，重置失败计数。
                    self._last_failure_time = 0.0
                    self._failure_count = 0
                    return
                except Exception as e:
                    last_error = e
                    logger.warning(f"模型源 [{idx + 1}] 下载失败: {url} -> {e}")
                    if tmp_path.exists():
                        try:
                            tmp_path.unlink()
                        except OSError:
                            pass
                    continue

            # P1: 所有源都失败，记录冷却起点，让后续请求快速失败。
            self._last_failure_time = time.time()
            raise RuntimeError(f"分类模型全部下载源均失败: {last_error}")

    def _load(self):
        """加载 ONNX 模型"""
        if self._loaded:
            return

        self._ensure_model()

        try:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            opts.intra_op_num_threads = min(os.cpu_count() or 4, 4)

            self._session = ort.InferenceSession(
                str(self._model_path),
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            self._input_name = self._session.get_inputs()[0].name
            self._loaded = True
            logger.info("MobileNetV3 分类模型加载完成")
        except Exception as e:
            logger.error(f"MobileNetV3 模型加载失败: {e}")
            raise

    def classify(self, img: Image.Image) -> str:
        """
        分类单张图片

        Args:
            img: PIL Image（任意模式）

        Returns:
            "product" | "portrait" | "pet" | "general"
        """
        # P2: 已禁用时静默降级，不再刷日志。
        if self._disabled:
            return "general"
        try:
            self._load()
            result = self._classify_internal(img)
            # P2: 推理成功，重置连续失败计数。
            with self._state_lock:
                self._failure_count = 0
            return result
        except Exception as e:
            self._record_failure(e, context="单张分类")
            return "general"

    def classify_batch(self, images: list) -> list:
        """批量分类"""
        # P2: 已禁用时静默降级，保持返回长度与输入一致。
        if self._disabled:
            return ["general"] * len(images)
        try:
            self._load()
            results = [self._classify_internal(img) for img in images]
            # P2: 推理成功，重置连续失败计数。
            with self._state_lock:
                self._failure_count = 0
            return results
        except Exception as e:
            self._record_failure(e, context="批量分类")
            return ["general"] * len(images)

    def _record_failure(self, error: Exception, context: str = "分类"):
        """
        P2: 记录一次分类失败，连续失败达到阈值则全局禁用分类器。
        禁用前打印 warning 告知用户；禁用后 classify/classify_batch 入口会
        静默降级，不再输出日志噪音。
        """
        with self._state_lock:
            if self._disabled:
                return
            self._failure_count += 1
            count = self._failure_count
            should_disable = count >= self._DISABLE_THRESHOLD

        if should_disable:
            self._disabled = True
            logger.warning(
                f"图片分类器连续失败 {count} 次，已全局禁用，后续请求将静默降级为 general。"
                f"最后一次错误({context}): {error}"
            )
        else:
            logger.warning(
                f"{context}失败，默认 general（连续失败 {count}/{self._DISABLE_THRESHOLD}）: {error}"
            )

    def _classify_internal(self, img: Image.Image) -> str:
        """内部分类逻辑"""
        # 预处理：resize 到 224x224，归一化
        input_tensor = self._preprocess(img)

        # 推理
        outputs = self._session.run(None, {self._input_name: input_tensor})
        logits = outputs[0][0]  # shape: (1000,)

        # softmax
        probs = self._softmax(logits)

        # 映射到 4 分类
        return self._map_to_category(probs)

    def _preprocess(self, img: Image.Image) -> np.ndarray:
        """预处理图片为 MobileNetV3 输入格式"""
        # 转 RGB
        if img.mode != "RGB":
            img = img.convert("RGB")

        # resize 到 224x224
        img = img.resize((224, 224), Image.BILINEAR)

        # 转 numpy，归一化到 [0, 1]
        arr = np.array(img, dtype=np.float32) / 255.0

        # ImageNet 标准化
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        arr = (arr - mean) / std

        # HWC -> NCHW
        arr = np.transpose(arr, (2, 0, 1))
        arr = np.expand_dims(arr, axis=0)
        return arr

    @staticmethod
    def _softmax(x):
        e = np.exp(x - np.max(x))
        return e / e.sum()

    @staticmethod
    def _map_to_category(probs: np.ndarray) -> str:
        """将 ImageNet 1000 类概率映射到 4 个业务分类"""
        top_class = int(np.argmax(probs))
        top_prob = float(probs[top_class])

        # 置信度太低时归为 general
        if top_prob < 0.1:
            return "general"

        # person 类：ImageNet 中的 person 相关类
        # class 0 是 goldfish，person 相关类比较分散
        # 使用 top-5 类别综合判断
        top5 = np.argsort(probs)[-5:]

        # 检查是否有动物类（ImageNet 0-397 大部分是动物）
        animal_score = sum(float(probs[i]) for i in range(min(398, len(probs))))

        # 检查是否有 person 相关类
        person_classes = {424, 502, 504, 531, 554, 573, 602, 614, 624, 625,
                          652, 659, 672, 681, 682, 712, 756, 775, 779, 800,
                          816, 821, 848, 864, 900, 907}
        person_score = sum(float(probs[i]) for i in person_classes if i < len(probs))

        # 判断逻辑
        if person_score > 0.3:
            return "portrait"
        elif animal_score > 0.4:
            return "pet"
        else:
            # 非动物、非人物 → 检查是否是白色背景的产品图
            # 这个判断比较粗糙，但在没有额外模型的情况下足够
            return "product" if top_prob > 0.3 else "general"
