"""
可见水印智能去除路由
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

_service = None
WATERMARK_REMOVAL_CACHE_VERSION = "v10"


def _get_service():
    global _service
    if _service is None:
        from services.watermark_removal_service import WatermarkRemovalService
        _service = WatermarkRemovalService()
    return _service


@router.post("/api/watermark-removal")
async def watermark_removal(
    file: UploadFile = File(...),
    sensitivity: str = Form("medium"),
    method: str = Form("telea"),
):
    """单张图片智能去水印"""
    start_time = time.time()
    input_data = await file.read()

    if len(input_data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件大小不能超过 20MB")
    if len(input_data) == 0:
        raise HTTPException(status_code=400, detail="文件为空")

    # 缓存检查
    cache_key = DiskCache.make_key(input_data, f"wmrm_{sensitivity}_{method}", WATERMARK_REMOVAL_CACHE_VERSION)
    cached = disk_cache.get(cache_key)
    if cached:
        base_name = file.filename.rsplit(".", 1)[0] if file.filename else "image"
        filename = f"{base_name}_nowm.png"
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
        svc = _get_service()
        return svc.process_image(input_data, sensitivity, method)

    try:
        output_data, metadata = await asyncio.wait_for(
            asyncio.to_thread(_process), timeout=120
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="处理超时（超过120秒）")
    except MemoryError:
        raise HTTPException(status_code=500, detail="内存不足")
    except Exception as e:
        logger.error(f"去水印失败 {file.filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"处理失败：{str(e)[:200]}")

    disk_cache.put(cache_key, output_data, metadata)

    elapsed_ms = int((time.time() - start_time) * 1000)
    logger.info(f"去水印完成: {file.filename} | has_wm={metadata.get('has_watermark')} 耗时={elapsed_ms}ms")

    base_name = file.filename.rsplit(".", 1)[0] if file.filename else "image"
    filename = f"{base_name}_nowm.png"
    ascii_name = "".join(c if ord(c) < 128 else "_" for c in filename)
    encoded = quote(filename)

    return StreamingResponse(
        io.BytesIO(output_data),
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}',
            "X-Has-Watermark": str(metadata.get("has_watermark", False)).lower(),
            "X-Mask-Area": str(metadata.get("mask_area", 0)),
            "X-Cache-Hit": "false",
            "X-Processing-Time-Ms": str(elapsed_ms),
        },
    )


@router.post("/api/watermark-removal-batch")
async def watermark_removal_batch(
    files: List[UploadFile] = File(...),
    sensitivity: str = Form("medium"),
    method: str = Form("telea"),
):
    """批量智能去水印"""
    if len(files) > 100:
        raise HTTPException(status_code=400, detail="批量处理最多支持 100 张图片")

    file_data = []
    for f in files:
        data = await f.read()
        if len(data) > 20 * 1024 * 1024:
            file_data.append({"filename": f.filename, "error": "文件超过 20MB"})
        elif len(data) == 0:
            file_data.append({"filename": f.filename, "error": "文件为空"})
        else:
            file_data.append({"filename": f.filename, "data": data})

    valid_items = [(i, item) for i, item in enumerate(file_data) if "data" in item]
    results = [None] * len(file_data)

    for i, item in enumerate(file_data):
        if "error" in item:
            results[i] = {"filename": item["filename"], "success": False, "error": item["error"]}

    def process_one(task):
        idx, item = task
        try:
            svc = _get_service()
            output_data, metadata = svc.process_image(item["data"], sensitivity, method)

            base = item["filename"].rsplit(".", 1)[0] if item["filename"] else "image"
            out_name = f"{base}_nowm.png"
            out_path = BG_REMOVER_DIR / "output"
            out_path.mkdir(exist_ok=True)
            (out_path / out_name).write_bytes(output_data)

            cache_key = DiskCache.make_key(item["data"], f"wmrm_{sensitivity}_{method}", WATERMARK_REMOVAL_CACHE_VERSION)
            disk_cache.put(cache_key, output_data, metadata)

            return idx, {
                "filename": out_name,
                "original_filename": item["filename"],
                "success": True,
                **metadata,
            }
        except Exception as e:
            logger.error(f"批量去水印失败 {item['filename']}: {e}", exc_info=True)
            return idx, {"filename": item["filename"], "success": False, "error": str(e)[:200]}

    batch_results = await task_queue.process_batch(
        tasks=valid_items,
        process_fn=process_one,
    )

    for idx, result in batch_results:
        results[idx] = result

    return {"results": [r for r in results if r is not None]}


@router.post("/api/watermark-removal-batch-stream")
async def watermark_removal_batch_stream(
    files: List[UploadFile] = File(...),
    sensitivity: str = Form("medium"),
    method: str = Form("telea"),
):
    """批量去水印 SSE 实时进度推送"""
    import json as _json

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

        svc = _get_service()

        for item in file_data:
            if item is None:
                continue
            try:
                output_data, metadata = svc.process_image(item["data"], sensitivity, method)

                base = item["filename"].rsplit(".", 1)[0]
                out_name = f"{base}_nowm.png"
                out_path = BG_REMOVER_DIR / "output"
                out_path.mkdir(exist_ok=True)
                (out_path / out_name).write_bytes(output_data)

                completed[0] += 1
                elapsed = time.time() - start_time
                speed = round(elapsed / completed[0], 1)
                yield f"data: {_json.dumps({'type': 'progress', 'completed': completed[0], 'total': valid_count, 'filename': out_name, 'has_watermark': metadata.get('has_watermark', False), 'speed': speed})}\n\n"
            except Exception as e:
                completed[0] += 1
                yield f"data: {_json.dumps({'type': 'error', 'filename': item['filename'], 'error': str(e)[:200]})}\n\n"

        yield f"data: {_json.dumps({'type': 'done', 'total': valid_count, 'elapsed': round(time.time() - start_time, 1)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
