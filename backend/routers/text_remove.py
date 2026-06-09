"""
文字去除路由
"""

import io
import time
import asyncio
import logging

import numpy as np
from PIL import Image
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from deps import _get_ocr, _get_lama, _get_cv2

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/text-remove")
async def text_remove(
    file: UploadFile = File(...),
    method: str = Form("telea"),  # telea / ns (Navier-Stokes)
    dilate_size: int = Form(5),   # mask 膨胀大小
    dilate_iter: int = Form(2),   # 膨胀迭代次数
    expand: int = Form(3),        # 文字框外扩像素
    format: str = Form("png"),
):
    """智能去除图片中的文字：OCR 检测文字位置 + OpenCV 修复填充"""
    start_time = time.time()
    input_data = await file.read()
    if len(input_data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件大小不能超过 20MB")
    if len(input_data) == 0:
        raise HTTPException(status_code=400, detail="文件为空")

    def _process():
        cv2 = _get_cv2()

        # 解码图片，保留原始通道（RGBA 或 RGB）
        orig_img = Image.open(io.BytesIO(input_data))
        has_alpha = orig_img.mode == 'RGBA' or (orig_img.mode == 'P' and 'transparency' in orig_img.info)

        # 转为 RGBA 统一处理
        if has_alpha:
            img = orig_img.convert("RGBA")
            r, g, b, a = img.split()
            img_rgb = Image.merge("RGB", (r, g, b))
            alpha_channel = np.array(a)
        else:
            img = orig_img.convert("RGB")
            img_rgb = img
            alpha_channel = None

        img_np = np.array(img_rgb)
        h, w = img_np.shape[:2]

        # OCR 检测文字（RapidOCR）
        ocr = _get_ocr()
        result, _ = ocr(img_np)

        if not result:
            raise ValueError("未检测到文字，请确认图片中包含文字")

        # 提取文字框坐标（RapidOCR 返回 [box, text, confidence]）
        boxes = []
        for line in result:
            box = line[0]  # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            pts = np.array(box, dtype=np.int32)
            if pts.ndim == 2 and pts.shape[0] >= 3:
                # 计算外扩
                center = pts.mean(axis=0)
                expanded = []
                for pt in pts:
                    direction = pt - center
                    norm = np.linalg.norm(direction)
                    if norm > 0:
                        expanded.append(pt + direction / norm * expand)
                    else:
                        expanded.append(pt)
                boxes.append(np.array(expanded, dtype=np.int32))

        # 生成 mask
        mask = np.zeros((h, w), dtype=np.uint8)
        for box in boxes:
            cv2.fillPoly(mask, [box], 255)

        # 膨胀 mask，确保文字边缘完全覆盖
        kernel = np.ones((dilate_size, dilate_size), np.uint8)
        mask = cv2.dilate(mask, kernel, iterations=dilate_iter)

        # 如果有透明通道，将 mask 限制在不透明区域内（避免填充透明区域）
        if alpha_channel is not None:
            opaque_mask = (alpha_channel > 10).astype(np.uint8) * 255
            mask = cv2.bitwise_and(mask, opaque_mask)

        # 图像修复（LaMa 深度学习模型）
        pil_img = Image.fromarray(img_np)
        pil_mask = Image.fromarray(mask)
        lama = _get_lama()
        result_rgb = lama(pil_img, pil_mask)

        # 如果原图有透明通道，合成回去
        if alpha_channel is not None:
            result_np = np.array(result_rgb)
            # LaMa 可能微调尺寸，强制对齐
            if result_np.shape[0] != h or result_np.shape[1] != w:
                result_rgb = result_rgb.resize((w, h), Image.LANCZOS)
                result_np = np.array(result_rgb)
            alpha_resized = alpha_channel
            if alpha_resized.shape[0] != h or alpha_resized.shape[1] != w:
                alpha_resized = np.array(Image.fromarray(alpha_channel).resize((w, h), Image.LANCZOS))
            out_img = Image.fromarray(np.dstack([result_np, alpha_resized]))
        else:
            out_img = result_rgb

        # 编码输出
        buf = io.BytesIO()
        save_format = "WEBP" if format == "webp" else "PNG"
        out_img.save(buf, format=save_format, quality=90 if format == "webp" else None)
        return buf.getvalue(), len(boxes)

    try:
        output_data, text_count = await asyncio.wait_for(
            asyncio.to_thread(_process), timeout=120
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="文字去除处理超时，请缩小图片后重试")
    except Exception as e:
        logger.error(f"文字去除失败 {file.filename}: {e}", exc_info=True)
        err_msg = str(e)
        if "onnx" in err_msg.lower() or "ocr" in err_msg.lower():
            raise HTTPException(status_code=500, detail="OCR 模型加载失败，请重启服务")
        raise HTTPException(status_code=500, detail=f"文字去除失败：{err_msg[:200]}")

    elapsed_ms = int((time.time() - start_time) * 1000)
    logger.info(f"文字去除完成: {file.filename} | 检测到 {text_count} 处文字 | 耗时={elapsed_ms}ms")

    from urllib.parse import quote
    base_name = file.filename.rsplit('.', 1)[0] if file.filename else "image"
    ext = "webp" if format == "webp" else "png"
    filename = f"{base_name}_no_text.{ext}"
    ascii_name = "".join(c if ord(c) < 128 else '_' for c in filename)
    encoded = quote(filename)
    media = "image/webp" if format == "webp" else "image/png"
    return StreamingResponse(
        io.BytesIO(output_data),
        media_type=media,
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}",
            "X-Text-Count": str(text_count),
            "X-Processing-Time-Ms": str(elapsed_ms),
        },
    )
