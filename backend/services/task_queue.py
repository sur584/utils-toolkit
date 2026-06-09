"""
任务队列 - 并发批量处理，支持进度追踪
"""

import asyncio
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# 并发线程数
_MAX_WORKERS = min((os.cpu_count() or 4) // 2, 6)


class TaskQueue:
    """并发批量处理队列"""

    def __init__(self, max_workers: int = None):
        self.max_workers = max_workers or _MAX_WORKERS
        self._executor: Optional[ThreadPoolExecutor] = None
        self._progress: dict = {}  # batch_id -> progress dict

    def _get_executor(self) -> ThreadPoolExecutor:
        if self._executor is None or self._executor._shutdown:
            self._executor = ThreadPoolExecutor(
                max_workers=self.max_workers,
                thread_name_prefix="bg-remover",
            )
        return self._executor

    async def process_batch(
        self,
        tasks: list,
        process_fn: Callable,
        batch_id: str = None,
    ) -> list:
        """
        并发处理一批任务

        Args:
            tasks: 任务列表（每项传给 process_fn）
            process_fn: 处理函数，接受单个 task，返回 result dict
            batch_id: 批次 ID（用于进度追踪）

        Returns:
            结果列表
        """
        batch_id = batch_id or str(uuid.uuid4())[:8]
        total = len(tasks)
        self._progress[batch_id] = {
            "total": total,
            "completed": 0,
            "failed": 0,
            "start_time": time.time(),
            "speed": 0,
        }

        results = [None] * total
        executor = self._get_executor()
        loop = asyncio.get_running_loop()

        async def run_one(idx, task):
            try:
                result = await loop.run_in_executor(executor, process_fn, task)
                results[idx] = result
                prog = self._progress[batch_id]
                prog["completed"] += 1
                if not result.get("success", True):
                    prog["failed"] += 1
                elapsed = time.time() - prog["start_time"]
                done = prog["completed"]
                prog["speed"] = round(elapsed / done, 1) if done > 0 else 0
            except Exception as e:
                results[idx] = {"success": False, "error": str(e)}
                self._progress[batch_id]["failed"] += 1
                self._progress[batch_id]["completed"] += 1

        # 并发执行
        await asyncio.gather(*[run_one(i, t) for i, t in enumerate(tasks)])

        # 清理进度
        progress = self._progress.pop(batch_id, {})
        logger.info(
            f"批次 {batch_id} 完成: {progress.get('completed', 0)}/{total}, "
            f"失败 {progress.get('failed', 0)}, "
            f"耗时 {time.time() - progress.get('start_time', time.time()):.1f}s"
        )

        return results

    def get_progress(self, batch_id: str) -> dict:
        """获取批次进度"""
        prog = self._progress.get(batch_id)
        if not prog:
            return None
        elapsed = time.time() - prog["start_time"]
        completed = prog["completed"]
        total = prog["total"]
        remaining = total - completed
        speed = prog["speed"]

        return {
            "batch_id": batch_id,
            "total": total,
            "completed": completed,
            "failed": prog["failed"],
            "speed": f"{speed}s/img",
            "eta": int(remaining * speed) if speed > 0 and remaining > 0 else 0,
            "elapsed": round(elapsed, 1),
        }

    def shutdown(self):
        if self._executor and not self._executor._shutdown:
            self._executor.shutdown(wait=False)
