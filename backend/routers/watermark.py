"""
暗水印检测/去除路由
"""

import io
import time
import asyncio
import logging
from typing import List
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from services.watermark_service import WatermarkService

logger = logging.getLogger(__name__)
router = APIRouter()
_svc = WatermarkService()

MAX_FILE_SIZE = 20 * 1024 * 1024


def _validate_file(data: bytes, filename: str):
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件大小不能超过 20MB")


def _build_download_headers(filename: str, suffix: str):
    base_name = filename.rsplit('.', 1)[0] if filename else "image"
    out_name = f"{base_name}_{suffix}.png"
    ascii_name = "".join(c if ord(c) < 128 else '_' for c in out_name)
    encoded = quote(out_name)
    return out_name, {
        "Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}',
    }


@router.post("/api/watermark/detect")
async def watermark_detect(file: UploadFile = File(...)):
    start_time = time.time()
    input_data = await file.read()
    _validate_file(input_data, file.filename)

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_svc.detect_all, input_data),
            timeout=60,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="水印检测超时（超过60秒），请缩小图片尺寸后重试")
    except MemoryError:
        raise HTTPException(status_code=500, detail="内存不足，图片太大无法处理")
    except Exception as e:
        logger.error(f"水印检测失败 {file.filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"水印检测失败：{str(e)[:200]}")

    elapsed_ms = int((time.time() - start_time) * 1000)
    logger.info(f"水印检测完成: {file.filename} | has_watermark={result.get('has_watermark')} 耗时={elapsed_ms}ms")

    return {
        **result,
        "processing_time": elapsed_ms,
    }


@router.post("/api/watermark/remove")
async def watermark_remove(
    file: UploadFile = File(...),
    method: str = Form("combo"),
    strength: int = Form(5),
):
    start_time = time.time()
    input_data = await file.read()
    _validate_file(input_data, file.filename)

    if method not in ("lsb", "blur", "jpeg", "bitplane", "combo"):
        raise HTTPException(status_code=400, detail=f"不支持的去除方法：{method}")
    if not (1 <= strength <= 10):
        raise HTTPException(status_code=400, detail="强度参数必须在 1-10 之间")

    try:
        output_data = await asyncio.wait_for(
            asyncio.to_thread(
                _svc.remove_watermark, input_data, method, strength
            ),
            timeout=120,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="水印去除超时（超过120秒），请缩小图片尺寸后重试")
    except MemoryError:
        raise HTTPException(status_code=500, detail="内存不足，图片太大无法处理")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"水印去除失败 {file.filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"水印去除失败：{str(e)[:200]}")

    elapsed_ms = int((time.time() - start_time) * 1000)
    logger.info(f"水印去除完成: {file.filename} | method={method} strength={strength} 耗时={elapsed_ms}ms")

    out_name, headers = _build_download_headers(file.filename, "watermark_removed")
    headers["X-Processing-Time-Ms"] = str(elapsed_ms)

    return StreamingResponse(
        io.BytesIO(output_data),
        media_type="image/png",
        headers=headers,
    )


@router.post("/api/watermark/batch-detect")
async def watermark_batch_detect(files: List[UploadFile] = File(...)):
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="批量检测最多支持 50 张图片")

    file_data = []
    for f in files:
        data = await f.read()
        if len(data) > MAX_FILE_SIZE:
            file_data.append({"filename": f.filename, "error": "文件超过 20MB"})
        elif len(data) == 0:
            file_data.append({"filename": f.filename, "error": "文件为空"})
        else:
            file_data.append({"filename": f.filename, "data": data})

    async def _detect_one(idx: int, item: dict):
        if "error" in item:
            return {"filename": item["filename"], "success": False, "error": item["error"]}
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_svc.detect_all, item["data"]),
                timeout=60,
            )
            return {"filename": item["filename"], "success": True, **result}
        except Exception as e:
            logger.error(f"批量水印检测失败 {item['filename']}: {e}", exc_info=True)
            return {"filename": item["filename"], "success": False, "error": str(e)[:200]}

    tasks = [_detect_one(i, item) for i, item in enumerate(file_data)]
    results = await asyncio.gather(*tasks)

    return {"results": results}
