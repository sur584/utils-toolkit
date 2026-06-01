"""
图片分类器 - 使用 MobileNetV3 ONNX 推理识别图片类型
分类结果：product / portrait / pet / general
"""

import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# ImageNet 1000 类到 4 分类的映射
# person 相关类（索引范围大致）
_PORTRAIT_CLASSES = set(range(0, 1))  # 0: tench (不用), 实际用下面的细分
# ImageNet person-related classes (common ones)
_PERSON_INDICES = {
    424,  # bow tie
    425,  # brassiere
    436,  # chain mail, ring mail
    466,  # cowboy boot
    467,  # cowboy hat
    502,  # academic gown
    504,  # bikini
    527,  # cowboy hat
    531,  # diaper
    554,  # fur coat
    572,  # gasmask
    573,  # gown
    592,  # hair slide
    593,  # hair spray
    602,  # holster
    614,  # jersey
    622,  # lab coat
    624,  # maillot
    625,  # maillot, tank suit
    652,  # military uniform
    659,  # miniskirt
    660,  # missile
    672,  # mortarboard
    681,  # neck brace
    682,  # necklace
    712,  # poncho
    733,  # purse
    738,  # rugby ball
    756,  # sandal
    775,  # ski mask
    779,  # sock
    800,  # suit
    816,  # sweatshirt
    821,  # tank
    833,  # thimble
    838,  # toilet tissue
    848,  # vestment
    852,  # wardrobe
    864,  # wig
    867,  # wooden spoon (不用)
    900,  # wallet
    907,  # Windsor tie
    909,  # wing
    921,  # bookcase (不用)
    928,  # ice cream (不用)
    931,  # bucket (不用)
    933,  # cheeseburger (不用)
    936,  # hotdog (不用)
    949,  # strawberry (不用)
    953,  # pineapple (不用)
    957,  # carbonara (不用)
    960,  # chocolate sauce (不用)
    983,  # trifle (不用)
}

# 真正的 person 类（ImageNet 没有直接的 "person" 类，但有一些人物相关的）
# 实际上 ImageNet 中 person 不是独立类，我们需要用其他方式
# 更好的做法：用类别的 WordNet 层级

# animal 类（ImageNet 中大约 0-397 是动物/鱼类/鸟类等）
_ANIMAL_INDICES = set(range(0, 398))  # 大部分动物在这个范围

# product/object 类 - 常见物品
_PRODUCT_INDICES = set(range(398, 1000))  # 非动物类


class ImageClassifier:
    """使用 MobileNetV3 ONNX 推理对图片进行分类"""

    MODEL_URL = "https://github.com/onnx/models/raw/main/validated/vision/classification/mobilenet/model/mobilenetv3-small-12.onnx"
    MODEL_FILENAME = "mobilenetv3_classifier.onnx"

    def __init__(self, models_dir: str = None):
        self._session = None
        self._models_dir = Path(models_dir) if models_dir else Path("models")
        self._model_path = self._models_dir / self.MODEL_FILENAME
        self._input_name = None
        self._loaded = False

    def _ensure_model(self):
        """确保模型文件存在，不存在则下载"""
        if self._model_path.exists():
            return

        logger.info(f"下载 MobileNetV3 分类模型到 {self._model_path}")
        self._models_dir.mkdir(parents=True, exist_ok=True)

        try:
            import urllib.request
            urllib.request.urlretrieve(self.MODEL_URL, str(self._model_path))
            logger.info("MobileNetV3 模型下载完成")
        except Exception as e:
            logger.error(f"MobileNetV3 模型下载失败: {e}")
            raise RuntimeError(f"分类模型下载失败: {e}")

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
        try:
            self._load()
            return self._classify_internal(img)
        except Exception as e:
            logger.warning(f"图片分类失败，默认 general: {e}")
            return "general"

    def classify_batch(self, images: list) -> list:
        """批量分类"""
        try:
            self._load()
            return [self._classify_internal(img) for img in images]
        except Exception as e:
            logger.warning(f"批量分类失败，默认 general: {e}")
            return ["general"] * len(images)

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
