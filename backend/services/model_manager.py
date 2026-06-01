"""
模型管理器 - 集中管理 rembg 模型的注册、加载、缓存和 Session 生命周期
"""

import os
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# 线程数配置
_NUM_THREADS = min(os.cpu_count() or 4, 8)
os.environ.setdefault("OMP_NUM_THREADS", str(_NUM_THREADS))


class ModelManager:
    """管理所有抠图模型的加载和 Session 缓存"""

    MODELS = {
        "bria-rmbg": {
            "label": "rmbg-2.0 最佳质量",
            "max_dim": 2048,
            "alpha_matting": True,
            "alpha_matting_foreground_threshold": 240,
            "alpha_matting_background_threshold": 10,
            "alpha_matting_erode_size": 5,
        },
        "isnet-general-use": {
            "label": "通用精准",
            "max_dim": 1536,
            "alpha_matting": True,
            "alpha_matting_foreground_threshold": 240,
            "alpha_matting_background_threshold": 10,
            "alpha_matting_erode_size": 5,
        },
        "u2net": {
            "label": "速度回退",
            "max_dim": 1024,
            "alpha_matting": False,
        },
    }

    DEFAULT_MODEL = "bria-rmbg"

    # 已弃用模型到新模型的映射
    DEPRECATED_MAP = {
        "u2netp": "bria-rmbg",
        "u2net_human_seg": "bria-rmbg",
        "silueta": "isnet-general-use",
    }

    def __init__(self):
        self._sessions: dict = {}
        self._locks: dict[str, threading.Lock] = {}
        self._default_lock = threading.Lock()

    def _get_lock(self, model_name: str) -> threading.Lock:
        """获取模型级别的锁（线程安全）"""
        if model_name not in self._locks:
            with self._default_lock:
                if model_name not in self._locks:
                    self._locks[model_name] = threading.Lock()
        return self._locks[model_name]

    def resolve_model(self, model_name: str) -> str:
        """解析模型名，处理弃用映射和无效名称"""
        if model_name in self.MODELS:
            return model_name
        if model_name in self.DEPRECATED_MAP:
            mapped = self.DEPRECATED_MAP[model_name]
            logger.warning(f"模型 '{model_name}' 已弃用，映射到 '{mapped}'")
            return mapped
        logger.warning(f"未知模型 '{model_name}'，使用默认 '{self.DEFAULT_MODEL}'")
        return self.DEFAULT_MODEL

    def get_session(self, model_name: str):
        """获取 rembg Session（懒加载 + 缓存）"""
        model_name = self.resolve_model(model_name)
        if model_name in self._sessions:
            return self._sessions[model_name]

        lock = self._get_lock(model_name)
        with lock:
            # double-check
            if model_name in self._sessions:
                return self._sessions[model_name]

            logger.info(f"加载模型: {model_name} ({self.MODELS[model_name]['label']})")
            try:
                from rembg import new_session
                from onnxruntime import SessionOptions, GraphOptimizationLevel, ExecutionMode

                opts = SessionOptions()
                opts.graph_optimization_level = GraphOptimizationLevel.ORT_ENABLE_ALL
                opts.execution_mode = ExecutionMode.ORT_PARALLEL
                opts.inter_op_num_threads = _NUM_THREADS
                opts.intra_op_num_threads = _NUM_THREADS

                session = new_session(model_name, opts)
                self._sessions[model_name] = session
                logger.info(f"模型 {model_name} 加载完成")
                return session
            except Exception as e:
                logger.error(f"模型 {model_name} 加载失败: {e}")
                raise

    def preload_default(self):
        """启动时预加载默认模型"""
        try:
            self.get_session(self.DEFAULT_MODEL)
            logger.info(f"默认模型 {self.DEFAULT_MODEL} 预加载完成")
        except Exception as e:
            logger.warning(f"默认模型预加载失败（首次使用时会自动下载）: {e}")

    def is_loaded(self, model_name: str) -> bool:
        return model_name in self._sessions

    def unload(self, model_name: str):
        """卸载指定模型释放内存"""
        if model_name in self._sessions:
            del self._sessions[model_name]
            logger.info(f"模型 {model_name} 已卸载")

    def get_model_info(self, model_name: str) -> dict:
        """获取模型配置信息"""
        model_name = self.resolve_model(model_name)
        info = self.MODELS.get(model_name, {}).copy()
        info["name"] = model_name
        info["loaded"] = self.is_loaded(model_name)
        return info

    def list_models(self) -> dict:
        """返回所有可用模型列表"""
        return {k: v["label"] for k, v in self.MODELS.items()}

    def get_model_params(self, model_name: str) -> dict:
        """获取模型的抠图参数"""
        model_name = self.resolve_model(model_name)
        return self.MODELS.get(model_name, {})
