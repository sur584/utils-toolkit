"""
模型路由器 - 根据图片分类、系统负载、批量大小自动选择最佳模型
"""

import logging
import os

logger = logging.getLogger(__name__)


class ModelRouter:
    """智能模型选择"""

    # 基础路由规则
    ROUTING = {
        "product": "bria-rmbg",
        "portrait": "bria-rmbg",
        "pet": "isnet-general-use",
        "general": "isnet-general-use",
    }

    def select_model(
        self,
        classification: str,
        batch_size: int = 1,
        cpu_percent: float = None,
        explicit_model: str = None,
    ) -> str:
        """
        选择最佳模型

        Args:
            classification: 图片分类 (product/portrait/pet/general)
            batch_size: 批量处理的图片数量
            cpu_percent: 当前 CPU 使用率（0-100），None 时自动获取
            explicit_model: 用户显式指定的模型（优先级最高）

        Returns:
            模型名称
        """
        # 用户显式指定时直接返回
        if explicit_model and explicit_model != "auto":
            from .model_manager import ModelManager
            return ModelManager().resolve_model(explicit_model)

        # 获取 CPU 使用率
        if cpu_percent is None:
            cpu_percent = self._get_cpu_percent()

        # 负载降级规则（优先级从高到低）
        if batch_size > 80:
            logger.info(f"批量 {batch_size} 张 > 80，降级到 u2net")
            return "u2net"

        if batch_size > 40:
            logger.info(f"批量 {batch_size} 张 > 40，降级到 isnet-general-use")
            return "isnet-general-use"

        if cpu_percent > 90:
            logger.info(f"CPU {cpu_percent:.0f}% > 90%，降级到 isnet-general-use")
            return "isnet-general-use"

        # 基础路由
        model = self.ROUTING.get(classification, "isnet-general-use")
        return model

    def select_models_batch(
        self,
        classifications: list,
        batch_size: int,
    ) -> list:
        """
        批量选择模型（所有图片使用同一个模型，避免频繁切换）

        Returns:
            与 classifications 等长的模型名列表
        """
        model = self.select_model(
            classification=self._dominant_class(classifications),
            batch_size=batch_size,
        )
        return [model] * len(classifications)

    @staticmethod
    def _dominant_class(classifications: list) -> str:
        """批量中占比最多的分类"""
        if not classifications:
            return "general"
        from collections import Counter
        counter = Counter(classifications)
        return counter.most_common(1)[0][0]

    @staticmethod
    def _get_cpu_percent() -> float:
        """获取当前 CPU 使用率（非阻塞）"""
        try:
            import psutil
            return psutil.cpu_percent(interval=0)
        except ImportError:
            return 0.0
