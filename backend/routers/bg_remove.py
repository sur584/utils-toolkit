"""
背景去除 (抠图) 路由
"""

import io
import time
import asyncio
import logging
from typing import List

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse

from config import BG_REMOVER_DIR
from deps import (
    model_manager, image_classifier, model_router,
    image_optimizer, post_processor, task_queue, disk_cache,
    ModelManager, DiskCache,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/bg-remove/models")
async def bg_remove_models():
    """返回可用的抠图模型列表（V3.0 自动选择）"""
    return {
        "models": model_manager.list_models(),
        "default": ModelManager.DEFAULT_MODEL,
        "v3": True,
    }


@router.post("/api/bg-remove")
async def bg_remove(
    file: UploadFile = File(...),
    model: str = Form("auto"),
    quality: str = Form("fast"),  # 废弃，保留兼容
    format: str = Form("png"),
):
    """单张图片抠图（V3.0 智能路由）"""
    start_time = time.time()
    input_data = await file.read()
    if len(input_data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件大小不能超过 20MB")
    if len(input_data) == 0:
        raise HTTPException(status_code=400, detail="文件为空")

    # 1. 缓存检查
    cache_key = DiskCache.make_key(input_data, model)
    cached = disk_cache.get(cache_key)
    if cached:
        logger.info(f"缓存命中: {file.filename}")
        from urllib.parse import quote
        base_name = file.filename.rsplit('.', 1)[0] if file.filename else "image"
        ext = "webp" if format == "webp" else "png"
        filename = f"{base_name}_remove.{ext}"
        ascii_name = "".join(c if ord(c) < 128 else '_' for c in filename)
        encoded = quote(filename)
        media = "image/webp" if format == "webp" else "image/png"
        return StreamingResponse(
            io.BytesIO(cached),
            media_type=media,
            headers={
                "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}",
                "X-Cache-Hit": "true",
                "X-Processing-Time-Ms": str(int((time.time() - start_time) * 1000)),
            },
        )

    def _process():
        from rembg import remove

        # 2. 预处理（解码 + 颜色模式 + 尺寸限制）
        processed = image_optimizer.preprocess(input_data, "bria-rmbg")

        # 3. 图片分类
        classification = image_classifier.classify(processed)

        # 4. 模型路由
        selected_model = model_router.select_model(
            classification=classification,
            explicit_model=model,
        )

        # 5. 如果路由后的模型有更严格的尺寸限制，重新预处理
        max_dim = image_optimizer.get_max_dim(selected_model)
        if max(processed.size) > max_dim:
            processed = image_optimizer.preprocess(input_data, selected_model)

        # 6. 推理
        session = model_manager.get_session(selected_model)
        kwargs = dict(session=session)

        # Alpha matting
        alpha_params = post_processor.get_alpha_params(selected_model)
        if alpha_params.get("enabled"):
            kwargs["alpha_matting"] = True
            kwargs["alpha_matting_foreground_threshold"] = alpha_params["foreground_threshold"]
            kwargs["alpha_matting_background_threshold"] = alpha_params["background_threshold"]
            kwargs["alpha_matting_erode_size"] = alpha_params["erode_size"]

        result = remove(processed, **kwargs)

        # 7. 后处理（边缘优化）
        if hasattr(result, 'save'):
            result = post_processor.process(result, selected_model)
            buf = io.BytesIO()
            save_format = "WEBP" if format == "webp" else "PNG"
            result.save(buf, format=save_format, quality=90 if format == "webp" else None)
            output_data = buf.getvalue()
        else:
            output_data = result

        return output_data, classification, selected_model

    try:
        output_data, classification, selected_model = await asyncio.wait_for(
            asyncio.to_thread(_process), timeout=120
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="抠图处理超时（超过120秒）。建议缩小图片尺寸后重试")
    except MemoryError:
        raise HTTPException(status_code=500, detail="内存不足，图片太大无法处理。请将图片缩小到 2048px 以内后重试")
    except Exception as e:
        logger.error(f"抠图处理失败 {file.filename}: {e}", exc_info=True)
        err_msg = str(e)
        if "ONNX" in err_msg or "onnx" in err_msg:
            raise HTTPException(status_code=500, detail="AI 模型加载失败，请重启服务")
        raise HTTPException(status_code=500, detail=f"抠图处理失败：{err_msg[:200]}")

    # 8. 写入缓存
    disk_cache.put(cache_key, output_data, {
        "classification": classification,
        "model": selected_model,
    })

    elapsed_ms = int((time.time() - start_time) * 1000)
    logger.info(f"抠图完成: {file.filename} | 分类={classification} 模型={selected_model} 耗时={elapsed_ms}ms")

    from urllib.parse import quote
    base_name = file.filename.rsplit('.', 1)[0] if file.filename else "image"
    ext = "webp" if format == "webp" else "png"
    filename = f"{base_name}_remove.{ext}"
    ascii_name = "".join(c if ord(c) < 128 else '_' for c in filename)
    encoded = quote(filename)
    media = "image/webp" if format == "webp" else "image/png"
    return StreamingResponse(
        io.BytesIO(output_data),
        media_type=media,
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}",
            "X-Image-Classification": classification,
            "X-Model-Used": selected_model,
            "X-Cache-Hit": "false",
            "X-Processing-Time-Ms": str(elapsed_ms),
        },
    )


@router.post("/api/bg-remove-batch")
async def bg_remove_batch(
    files: List[UploadFile] = File(...),
    model: str = Form("auto"),
    quality: str = Form("fast"),  # 废弃，保留兼容
    format: str = Form("png"),
):
    """批量抠图（V3.0 并发处理）"""
    if len(files) > 100:
        raise HTTPException(status_code=400, detail="批量抠图最多支持 100 张图片")

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
            data = item["data"]

            # 预处理
            processed = image_optimizer.preprocess(data, "bria-rmbg")

            # 分类
            classification = image_classifier.classify(processed)

            # 路由
            selected_model = model_router.select_model(
                classification=classification,
                batch_size=len(valid_items),
                explicit_model=model,
            )

            # 尺寸限制
            max_dim = image_optimizer.get_max_dim(selected_model)
            if max(processed.size) > max_dim:
                processed = image_optimizer.preprocess(data, selected_model)

            # 推理
            from rembg import remove
            session = model_manager.get_session(selected_model)
            kwargs = dict(session=session)
            alpha_params = post_processor.get_alpha_params(selected_model)
            if alpha_params.get("enabled"):
                kwargs["alpha_matting"] = True
                kwargs["alpha_matting_foreground_threshold"] = alpha_params["foreground_threshold"]
                kwargs["alpha_matting_background_threshold"] = alpha_params["background_threshold"]
                kwargs["alpha_matting_erode_size"] = alpha_params["erode_size"]

            result = remove(processed, **kwargs)

            # 后处理
            if hasattr(result, 'save'):
                result = post_processor.process(result, selected_model)
                buf = io.BytesIO()
                save_format = "WEBP" if format == "webp" else "PNG"
                result.save(buf, format=save_format, quality=90 if format == "webp" else None)
                output_data = buf.getvalue()
            else:
                output_data = result

            # 保存结果
            base = item["filename"].rsplit('.', 1)[0] if item["filename"] else "image"
            ext = "webp" if format == "webp" else "png"
            out_name = f"{base}_remove.{ext}"
            out_path = BG_REMOVER_DIR / "output"
            out_path.mkdir(exist_ok=True)
            (out_path / out_name).write_bytes(output_data)

            # 写入缓存
            cache_key = DiskCache.make_key(data, selected_model)
            disk_cache.put(cache_key, output_data, {
                "classification": classification,
                "model": selected_model,
            })

            return idx, {
                "filename": out_name,
                "original_filename": item["filename"],
                "success": True,
                "classification": classification,
                "model": selected_model,
            }
        except Exception as e:
            logger.error(f"批量抠图失败 {item['filename']}: {e}", exc_info=True)
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


@router.post("/api/bg-remove-batch-stream")
async def bg_remove_batch_stream(
    files: List[UploadFile] = File(...),
    model: str = Form("auto"),
    format: str = Form("png"),
):
    """批量抠图 SSE 实时进度推送"""
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
        import json as _json
        yield f"data: {_json.dumps({'type': 'start', 'total': valid_count})}\n\n"

        for item in file_data:
            if item is None:
                continue
            try:
                data = item["data"]
                processed = image_optimizer.preprocess(data, "bria-rmbg")
                classification = image_classifier.classify(processed)
                selected_model = model_router.select_model(
                    classification=classification,
                    batch_size=valid_count,
                    explicit_model=model,
                )
                max_dim = image_optimizer.get_max_dim(selected_model)
                if max(processed.size) > max_dim:
                    processed = image_optimizer.preprocess(data, selected_model)

                from rembg import remove
                session = model_manager.get_session(selected_model)
                kwargs = dict(session=session)
                alpha_params = post_processor.get_alpha_params(selected_model)
                if alpha_params.get("enabled"):
                    kwargs["alpha_matting"] = True
                    kwargs["alpha_matting_foreground_threshold"] = alpha_params["foreground_threshold"]
                    kwargs["alpha_matting_background_threshold"] = alpha_params["background_threshold"]
                    kwargs["alpha_matting_erode_size"] = alpha_params["erode_size"]

                result = remove(processed, **kwargs)
                if hasattr(result, 'save'):
                    result = post_processor.process(result, selected_model)
                    buf = io.BytesIO()
                    result.save(buf, format="PNG")
                    output_data = buf.getvalue()
                else:
                    output_data = result

                base = item["filename"].rsplit('.', 1)[0]
                out_name = f"{base}_remove.png"
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


@router.get("/api/bg-remove/download/{filename}")
async def bg_remove_download(filename: str):
    """下载抠图结果"""
    out_path = BG_REMOVER_DIR / "output" / filename
    if not out_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    ext = filename.rsplit('.', 1)[-1] if '.' in filename else "png"
    media = "image/webp" if ext == "webp" else "image/png"
    return FileResponse(path=str(out_path), filename=filename, media_type=media)
