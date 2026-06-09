"""
磁盘持久化 LRU 缓存 - 支持 TTL、磁盘大小限制、双阈值淘汰、后台清理
"""

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """缓存配置 - 所有可调参数集中管理"""
    cache_dir: str = "cache"
    max_entries: int = 300
    ttl_days: int = 7
    max_disk_mb: int = 500
    soft_threshold: float = 0.80
    hard_threshold: float = 0.95
    cleanup_interval_minutes: int = 10

    soft_limit_bytes: int = field(init=False)
    hard_limit_bytes: int = field(init=False)
    max_disk_bytes: int = field(init=False)

    def __post_init__(self):
        self.max_disk_bytes = self.max_disk_mb * 1024 * 1024
        self.soft_limit_bytes = int(self.max_disk_bytes * self.soft_threshold)
        self.hard_limit_bytes = int(self.max_disk_bytes * self.hard_threshold)


class DiskCache:
    """基于文件系统的 LRU 缓存，支持 TTL、磁盘大小限制、后台清理"""

    def __init__(self, cache_dir: str = "cache", max_entries: int = 300,
                 ttl_days: int = 7, config: Optional[CacheConfig] = None):
        if config is None:
            config = CacheConfig(cache_dir=cache_dir, max_entries=max_entries, ttl_days=ttl_days)
        self.config = config
        self.cache_dir = Path(config.cache_dir)
        self.images_dir = self.cache_dir / "images"
        self.metadata_dir = self.cache_dir / "metadata"
        self.ttl_seconds = config.ttl_days * 86400
        self._lock = threading.Lock()
        self._cleanup_timer: Optional[threading.Timer] = None
        self._stats = {"hits": 0, "misses": 0}
        self._running = False
        self._ensure_dirs()

    def _ensure_dirs(self):
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

    def _hash_key(self, key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()[:32]

    def _dir_size_bytes(self) -> int:
        total = 0
        try:
            for f in self.images_dir.glob("*.png"):
                total += f.stat().st_size
        except Exception:
            pass
        return total

    def get(self, key: str) -> Optional[bytes]:
        h = self._hash_key(key)
        img_path = self.images_dir / f"{h}.png"
        meta_path = self.metadata_dir / f"{h}.json"

        if not img_path.exists():
            with self._lock:
                self._stats["misses"] += 1
            return None

        # TTL 检查
        try:
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                created = meta.get("created", 0)
                if time.time() - created > self.ttl_seconds:
                    self._remove(h)
                    with self._lock:
                        self._stats["misses"] += 1
                    return None
            else:
                mtime = img_path.stat().st_mtime
                if time.time() - mtime > self.ttl_seconds:
                    self._remove(h)
                    with self._lock:
                        self._stats["misses"] += 1
                    return None
        except Exception:
            pass

        # 更新访问时间
        with self._lock:
            self._update_access(h, key)

        try:
            data = img_path.read_bytes()
            with self._lock:
                self._stats["hits"] += 1
            return data
        except Exception as e:
            logger.warning(f"缓存读取失败: {e}")
            with self._lock:
                self._stats["misses"] += 1
            return None

    def put(self, key: str, value: bytes, metadata: dict = None):
        h = self._hash_key(key)
        img_path = self.images_dir / f"{h}.png"

        try:
            img_path.write_bytes(value)
            with self._lock:
                self._update_access(h, key, metadata)
        except Exception as e:
            logger.warning(f"缓存写入失败: {e}")
            return

        self._evict_if_needed()

    def _update_access(self, h: str, key: str, extra: dict = None):
        meta_path = self.metadata_dir / f"{h}.json"
        meta = {
            "key": key,
            "access_time": time.time(),
            "created": time.time(),
        }
        if extra:
            meta.update(extra)
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
        try:
            entries = []
            for meta_file in self.metadata_dir.glob("*.json"):
                try:
                    data = json.loads(meta_file.read_text(encoding="utf-8"))
                    h = meta_file.stem
                    img_path = self.images_dir / f"{h}.png"
                    size = img_path.stat().st_size if img_path.exists() else 0
                    entries.append((h, data.get("access_time", 0), size))
                except Exception:
                    continue

            if not entries:
                return

            # 条目数限制
            if len(entries) > self.config.max_entries:
                entries.sort(key=lambda x: x[1])
                to_remove_count = len(entries) - self.config.max_entries
                for h, _, _ in entries[:to_remove_count]:
                    self._remove(h)
                entries = entries[to_remove_count:]
                logger.info(f"缓存淘汰 {to_remove_count} 个条目（条目数超限）")

            # 磁盘大小限制
            disk_usage = self._dir_size_bytes()
            if disk_usage <= self.config.soft_limit_bytes:
                return

            if disk_usage > self.config.hard_limit_bytes:
                target_bytes = self.config.soft_limit_bytes
            else:
                target_bytes = int(self.config.max_disk_bytes * 0.70)

            entries.sort(key=lambda x: x[1])
            bytes_to_free = disk_usage - target_bytes
            freed = 0
            evicted = 0
            for h, _, size in entries:
                if freed >= bytes_to_free:
                    break
                self._remove(h)
                freed += size
                evicted += 1

            if evicted > 0:
                logger.info(
                    f"磁盘清理：淘汰 {evicted} 个条目（{freed / 1024 / 1024:.1f}MB），"
                    f"磁盘占用 {disk_usage / 1024 / 1024:.1f}MB -> 目标 {target_bytes / 1024 / 1024:.1f}MB"
                )
        except Exception as e:
            logger.warning(f"缓存淘汰失败: {e}")

    def cleanup(self):
        cleaned = 0
        now = time.time()

        for meta_path in self.metadata_dir.glob("*.json"):
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                created = data.get("created", 0)
                if now - created > self.ttl_seconds:
                    self._remove(meta_path.stem)
                    cleaned += 1
            except Exception:
                self._remove(meta_path.stem)
                cleaned += 1

        for img_path in self.images_dir.glob("*.png"):
            meta_path = self.metadata_dir / f"{img_path.stem}.json"
            if not meta_path.exists():
                mtime = img_path.stat().st_mtime
                if now - mtime > self.ttl_seconds:
                    img_path.unlink()
                    cleaned += 1

        self._evict_if_needed()

        if cleaned > 0:
            logger.info(f"缓存清理完成，移除 {cleaned} 个过期条目")
        self._ensure_dirs()

    def stats(self) -> dict:
        image_count = len(list(self.images_dir.glob("*.png")))
        disk_bytes = self._dir_size_bytes()
        total_requests = self._stats["hits"] + self._stats["misses"]
        return {
            "entries": image_count,
            "max_entries": self.config.max_entries,
            "disk_mb": round(disk_bytes / 1024 / 1024, 2),
            "max_disk_mb": self.config.max_disk_mb,
            "disk_usage_percent": round(disk_bytes / self.config.max_disk_bytes * 100, 1) if self.config.max_disk_bytes > 0 else 0,
            "soft_limit_mb": round(self.config.soft_limit_bytes / 1024 / 1024, 1),
            "hard_limit_mb": round(self.config.hard_limit_bytes / 1024 / 1024, 1),
            "ttl_days": self.config.ttl_days,
            "cache_dir": str(self.cache_dir),
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate": round(self._stats["hits"] / total_requests * 100, 1) if total_requests > 0 else 0,
            "background_cleanup_running": self._running,
            "cleanup_interval_minutes": self.config.cleanup_interval_minutes,
        }

    def start_background_cleanup(self):
        if self._running:
            return
        self._running = True
        self._schedule_cleanup()
        logger.info(f"后台缓存清理已启动（间隔: {self.config.cleanup_interval_minutes} 分钟）")

    def _schedule_cleanup(self):
        if not self._running:
            return
        interval = self.config.cleanup_interval_minutes * 60
        self._cleanup_timer = threading.Timer(interval, self._background_cleanup_tick)
        self._cleanup_timer.daemon = True
        self._cleanup_timer.start()

    def _background_cleanup_tick(self):
        if not self._running:
            return
        try:
            self.cleanup()
        except Exception as e:
            logger.warning(f"后台清理异常: {e}")
        finally:
            self._schedule_cleanup()

    def stop_background_cleanup(self):
        self._running = False
        if self._cleanup_timer:
            self._cleanup_timer.cancel()
            self._cleanup_timer = None

    @staticmethod
    def make_key(data: bytes, model: str, param_version: str = "v1") -> str:
        h = hashlib.md5(data).hexdigest()
        return f"{h}_{model}_{param_version}"
