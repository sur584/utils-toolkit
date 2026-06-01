"""
磁盘持久化 LRU 缓存 - 替代内存缓存，支持 TTL 和容量限制
"""

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DiskCache:
    """基于文件系统的 LRU 缓存，支持 TTL 自动过期"""

    def __init__(self, cache_dir: str = "cache", max_entries: int = 300, ttl_days: int = 7):
        self.cache_dir = Path(cache_dir)
        self.images_dir = self.cache_dir / "images"
        self.metadata_dir = self.cache_dir / "metadata"
        self.max_entries = max_entries
        self.ttl_seconds = ttl_days * 86400
        self._ensure_dirs()

    def _ensure_dirs(self):
        """创建缓存目录结构"""
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

    def _hash_key(self, key: str) -> str:
        """将 key 转为文件名安全的 hash"""
        return hashlib.sha256(key.encode()).hexdigest()[:32]

    def get(self, key: str) -> Optional[bytes]:
        """
        查找缓存。命中时更新访问时间并返回图片字节，未命中返回 None。
        """
        h = self._hash_key(key)
        img_path = self.images_dir / f"{h}.png"
        meta_path = self.metadata_dir / f"{h}.json"

        if not img_path.exists():
            return None

        # 检查 TTL
        try:
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                created = meta.get("created", 0)
                if time.time() - created > self.ttl_seconds:
                    self._remove(h)
                    return None
            else:
                # 无元数据，用文件修改时间
                mtime = img_path.stat().st_mtime
                if time.time() - mtime > self.ttl_seconds:
                    self._remove(h)
                    return None
        except Exception:
            pass

        # 更新访问时间
        self._update_access(h, key)

        try:
            return img_path.read_bytes()
        except Exception as e:
            logger.warning(f"缓存读取失败: {e}")
            return None

    def put(self, key: str, value: bytes, metadata: dict = None):
        """写入缓存，超过容量时淘汰最久未访问的条目"""
        h = self._hash_key(key)
        img_path = self.images_dir / f"{h}.png"

        try:
            img_path.write_bytes(value)
            self._update_access(h, key, metadata)
        except Exception as e:
            logger.warning(f"缓存写入失败: {e}")
            return

        # 容量检查
        self._evict_if_needed()

    def _update_access(self, h: str, key: str, extra: dict = None):
        """更新元数据文件"""
        meta_path = self.metadata_dir / f"{h}.json"
        meta = {
            "key": key,
            "access_time": time.time(),
            "created": time.time(),
        }
        if extra:
            meta.update(extra)
        # 如果已有元数据，保留 created 时间
        if meta_path.exists():
            try:
                old = json.loads(meta_path.read_text(encoding="utf-8"))
                meta["created"] = old.get("created", meta["created"])
            except Exception:
                pass
        try:
            meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _remove(self, h: str):
        """删除单个缓存条目"""
        try:
            img_path = self.images_dir / f"{h}.png"
            meta_path = self.metadata_dir / f"{h}.json"
            if img_path.exists():
                img_path.unlink()
            if meta_path.exists():
                meta_path.unlink()
        except Exception:
            pass

    def _evict_if_needed(self):
        """超过容量时淘汰最旧的条目"""
        try:
            metas = []
            for f in self.metadata_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    metas.append((f.stem, data.get("access_time", 0)))
                except Exception:
                    continue

            if len(metas) <= self.max_entries:
                return

            # 按访问时间排序，淘汰最旧的
            metas.sort(key=lambda x: x[1])
            to_remove = len(metas) - self.max_entries
            for h, _ in metas[:to_remove]:
                self._remove(h)
            logger.info(f"缓存淘汰 {to_remove} 个条目")
        except Exception as e:
            logger.warning(f"缓存淘汰失败: {e}")

    def cleanup(self):
        """启动时清理过期条目和损坏文件"""
        cleaned = 0
        now = time.time()

        # 清理过期
        for meta_path in self.metadata_dir.glob("*.json"):
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                created = data.get("created", 0)
                if now - created > self.ttl_seconds:
                    self._remove(meta_path.stem)
                    cleaned += 1
            except Exception:
                # 损坏的元数据也清理
                self._remove(meta_path.stem)
                cleaned += 1

        # 清理孤立图片（没有元数据的图片，超过 TTL）
        for img_path in self.images_dir.glob("*.png"):
            meta_path = self.metadata_dir / f"{img_path.stem}.json"
            if not meta_path.exists():
                mtime = img_path.stat().st_mtime
                if now - mtime > self.ttl_seconds:
                    img_path.unlink()
                    cleaned += 1

        if cleaned > 0:
            logger.info(f"缓存清理完成，移除 {cleaned} 个过期条目")

        # 初始化目录
        self._ensure_dirs()

    def stats(self) -> dict:
        """返回缓存统计信息"""
        image_count = len(list(self.images_dir.glob("*.png")))
        return {
            "entries": image_count,
            "max_entries": self.max_entries,
            "ttl_days": self.ttl_seconds // 86400,
            "cache_dir": str(self.cache_dir),
        }

    @staticmethod
    def make_key(data: bytes, model: str, param_version: str = "v1") -> str:
        """生成缓存 key：md5(图片数据) + 模型版本 + 参数版本"""
        h = hashlib.md5(data).hexdigest()
        return f"{h}_{model}_{param_version}"
