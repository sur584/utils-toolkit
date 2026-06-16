"""
图片高清化路由（超分辨率）
"""

import io
import time
import asyncio
import logging
from typing import List
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from config import BG_REMOVER_DIR
from deps import task_queue, disk_cache, DiskCache

logger = logging.getLogger(__name__)
router = APIRouter()

# 懒加载高清化服务
_upscale_service = None


def _get_upscale_service():
    global _upscale_service
    if _upscale_service is None:
        from services.upscale_service import UpscaleService
        _upscale_service = UpscaleService()
    return _upscale_service


@router.post("/api/upscale")
async def upscale(
    file: UploadFile = File(...),
    scale: int = Form(2),
):
    """单张图片高清化"""
    start_time = time.time()
    input_data = await file.read()

    if len(input_data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件大小不能超过 20MB")
    if len(input_data) == 0:
        raise HTTPException(status_code=400, detail="文件为空")

    if scale not in [2, 4]:
        raise HTTPException(status_code=400, detail="放大倍数仅支持 2 或 4")

    # 缓存检查
    cache_key = DiskCache.make_key(input_data, f"upscale_{scale}x")
    cached = disk_cache.get(cache_key)
    if cached:
        logger.info(f"缓存命中: {file.filename}")
        base_name = file.filename.rsplit(".", 1)[0] if file.filename else "image"
        filename = f"{base_name}_{scale}x.png"
        ascii_name = "".join(c if ord(c) < 128 else "_" for c in filename)
        encoded = quote(filename)
        return StreamingResponse(
            io.BytesIO(cached),
            media_type="image/png",
            headers={
                "Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}',
                "X-Cache-Hit": "true",
                "X-Processing-Time-Ms": str(int((time.time() - start_time) * 1000)),
            },
        )

    def _process():
        service = _get_upscale_service()
        return service.process_image(input_data, scale)

    try:
        output_data, metadata = await asyncio.wait_for(
            asyncio.to_thread(_process), timeout=180
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="处理超时（超过180秒）。建议缩小图片尺寸后重试")
    except MemoryError:
        raise HTTPException(status_code=500, detail="内存不足，图片太大无法处理")
    except Exception as e:
        logger.error(f"高清化处理失败 {file.filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"处理失败：{str(e)[:200]}")

    # 写入缓存
    disk_cache.put(cache_key, output_data, metadata)

    elapsed_ms = int((time.time() - start_time) * 1000)
    logger.info(f"高清化完成: {file.filename} | {scale}x 耗时={elapsed_ms}ms")

    base_name = file.filename.rsplit(".", 1)[0] if file.filename else "image"
    filename = f"{base_name}_{scale}x.png"
    ascii_name = "".join(c if ord(c) < 128 else "_" for c in filename)
    encoded = quote(filename)

    return StreamingResponse(
        io.BytesIO(output_data),
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}',
            "X-Scale": str(scale),
            "X-Original-Size": f"{metadata.get('original_width', 0)}x{metadata.get('original_height', 0)}",
            "X-Output-Size": f"{metadata.get('output_width', 0)}x{metadata.get('output_height', 0)}",
            "X-Cache-Hit": "false",
            "X-Processing-Time-Ms": str(elapsed_ms),
        },
    )


@router.post("/api/upscale-batch")
async def upscale_batch(
    files: List[UploadFile] = File(...),
    scale: int = Form(2),
):
    """批量高清化"""
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="批量处理最多支持 50 张图片")

    if scale not in [2, 4]:
        raise HTTPException(status_code=400, detail="放大倍数仅支持 2 或 4")

    # 读取所有文件数据
    file_data = []
    for f in files:
        data = await f.read()
        if len(data) > 20 * 1024 * 1024:
            file_data.append({"filename": f.filename, "error": "文件超过 20MB"})
        elif len(data) == 0:
            file_data.append({"filename": f.filename, "error": "文件为空"})
        else:
            file_data.append({"filename": f.filename, "data": data})

    # 分离有效和无效文件
    valid_items = [(i, item) for i, item in enumerate(file_data) if "data" in item]
    results = [None] * len(file_data)

    # 标记无效文件
    for i, item in enumerate(file_data):
        if "error" in item:
            results[i] = {"filename": item["filename"], "success": False, "error": item["error"]}

    # 构建任务列表
    def process_one(task):
        idx, item = task
        try:
            service = _get_upscale_service()
            output_data, metadata = service.process_image(item["data"], scale)

            base = item["filename"].rsplit(".", 1)[0] if item["filename"] else "image"
            out_name = f"{base}_{scale}x.png"
            out_path = BG_REMOVER_DIR / "output"
            out_path.mkdir(exist_ok=True)
            (out_path / out_name).write_bytes(output_data)

            # 写入缓存
            cache_key = DiskCache.make_key(item["data"], f"upscale_{scale}x")
            disk_cache.put(cache_key, output_data, metadata)

            return idx, {
                "filename": out_name,
                "original_filename": item["filename"],
                "success": True,
                **metadata,
            }
        except Exception as e:
            logger.error(f"批量高清化失败 {item['filename']}: {e}", exc_info=True)
            return idx, {"filename": item["filename"], "success": False, "error": str(e)[:200]}

    # 并发处理
    batch_results = await task_queue.process_batch(
        tasks=valid_items,
        process_fn=process_one,
    )

    # 合并结果
    for idx, result in batch_results:
        results[idx] = result

    return {"results": [r for r in results if r is not None]}


@router.post("/api/upscale-batch-stream")
async def upscale_batch_stream(
    files: List[UploadFile] = File(...),
    scale: int = Form(2),
):
    """批量高清化 SSE 实时进度推送"""
    import json as _json

    # 读取所有文件
    file_data = []
    for f in files:
        data = await f.read()
        if len(data) > 20 * 1024 * 1024 or len(data) == 0:
            file_data.append(None)
        else:
            file_data.append({"filename": f.filename, "data": data})

    valid_count = sum(1 for d in file_data if d is not None)
    completed = [0]
    start_time = time.time()

    async def event_stream():
        yield f"data: {_json.dumps({'type': 'start', 'total': valid_count})}\n\n"

        service = _get_upscale_service()

        for item in file_data:
            if item is None:
                continue
            try:
                output_data, metadata = service.process_image(item["data"], scale)

                base = item["filename"].rsplit(".", 1)[0]
                out_name = f"{base}_{scale}x.png"
                out_path = BG_REMOVER_DIR / "output"
                out_path.mkdir(exist_ok=True)
                (out_path / out_name).write_bytes(output_data)

                completed[0] += 1
                elapsed = time.time() - start_time
                speed = round(elapsed / completed[0], 1)
                yield f"data: {_json.dumps({'type': 'progress', 'completed': completed[0], 'total': valid_count, 'filename': out_name, 'speed': speed})}\n\n"
            except Exception as e:
                completed[0] += 1
                yield f"data: {_json.dumps({'type': 'error', 'filename': item['filename'], 'error': str(e)[:200]})}\n\n"

        yield f"data: {_json.dumps({'type': 'done', 'total': valid_count, 'elapsed': round(time.time() - start_time, 1)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
