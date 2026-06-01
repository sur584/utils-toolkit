"""
小小工具箱 - 后端服务
基于 FastAPI 提供多平台视频解析、下载、预览代理等 API
"""

import sys
import os

# 添加 backend 目录到 sys.path 以便 import parsers
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json
import io
import time
import uuid
import logging
import asyncio
from pathlib import Path
from typing import List

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from parsers import parse_link, batch_parse
from parsers._utils import _is_safe_url, _extract_url

from services.model_manager import ModelManager
from services.image_classifier import ImageClassifier
from services.model_router import ModelRouter
from services.image_optimizer import ImageOptimizer
from services.post_processor import PostProcessor
from services.task_queue import TaskQueue
from services.disk_cache import DiskCache

# ─── 配置 ─────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
HISTORY_FILE = BASE_DIR / "history.json"
VIDEO_TOOL_DIR = PROJECT_DIR / "tools" / "video-tool"
IMAGE_TOOL_DIR = PROJECT_DIR / "tools" / "image-tool"
BG_REMOVER_DIR = PROJECT_DIR / "tools" / "bg-remover"
IMAGE_COMPOSITE_DIR = PROJECT_DIR / "tools" / "image-composite"
MODELS_DIR = PROJECT_DIR / "models"
LIBS_DIR = PROJECT_DIR / "tools" / "libs"

DOWNLOAD_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)

# 让 rembg 把模型存到项目内的 models 目录
os.environ["U2NET_HOME"] = str(MODELS_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE_DIR / "app.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ─── V3.0 服务层初始化 ─────────────────────────────────
model_manager = ModelManager()
image_classifier = ImageClassifier(models_dir=str(MODELS_DIR))
model_router = ModelRouter()
image_optimizer = ImageOptimizer()
post_processor = PostProcessor()
task_queue = TaskQueue()
disk_cache = DiskCache(cache_dir=str(PROJECT_DIR / "cache"))

# ─── FastAPI 应用 ─────────────────────────────────────
app = FastAPI(title="小小工具箱", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)


# ─── 静态资源缓存中间件 ───────────────────────────────
@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    # 静态资源设置长缓存（CSS/JS/图片）
    if any(path.endswith(ext) for ext in ('.css', '.js', '.png', '.jpg', '.svg', '.ico', '.woff2', '.woff', '.ttf')):
        response.headers['Cache-Control'] = 'public, max-age=86400, immutable'
    elif path in ('/', '', '/tools/') or path.endswith('.html'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


# ─── 数据模型 ─────────────────────────────────────────
class ParseRequest(BaseModel):
    url: str

class BatchParseRequest(BaseModel):
    urls: List[str]


# ─── 历史记录 ─────────────────────────────────────────
def _load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def _save_history(history: list):
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

def _add_to_history(video_info: dict):
    history = _load_history()
    record = {"id": str(uuid.uuid4())[:8], "parse_time": time.strftime("%Y-%m-%d %H:%M:%S"), **video_info}
    history.insert(0, record)
    _save_history(history[:200])


# ─── API 路由 ─────────────────────────────────────────
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "3.0.0"}


@app.get("/api/platforms")
async def supported_platforms():
    """返回支持的平台列表"""
    return {"platforms": [
        {"id": "douyin", "name": "抖音", "domains": ["douyin.com", "iesdouyin.com"]},
        {"id": "bilibili", "name": "B站", "domains": ["bilibili.com", "b23.tv"]},
        {"id": "weibo", "name": "微博", "domains": ["weibo.com", "weibo.cn"]},
        {"id": "xiaohongshu", "name": "小红书", "domains": ["xiaohongshu.com", "xhslink.com"]},
        {"id": "tiktok", "name": "TikTok", "domains": ["tiktok.com"]},
        {"id": "youtube", "name": "YouTube", "domains": ["youtube.com", "youtu.be"]},
        {"id": "instagram", "name": "Instagram", "domains": ["instagram.com"]},
        {"id": "twitter", "name": "Twitter/X", "domains": ["twitter.com", "x.com", "t.co"]},
        {"id": "xigua", "name": "西瓜视频", "domains": ["ixigua.com"]},
        {"id": "wechat_channels", "name": "微信视频号", "domains": ["channels.weixin.qq.com"]},
    ]}


@app.post("/api/parse")
async def parse_video(req: ParseRequest):
    """解析视频链接（自动识别平台）"""
    from urllib.parse import urlparse as _urlparse
    from parsers.wechat_channels import parse_video_info
    from parsers._utils import _ok, _make_info

    raw = req.url.strip()
    logger.info(f"[解析] 收到请求: {raw[:80]}...")

    # 先尝试作为 JSON 解析（微信视频号等需要粘贴 JSON 数据）
    if raw.startswith("{") or raw.startswith("["):
        logger.info("[解析] 检测到 JSON 输入，尝试微信视频号解析")
        try:
            result = parse_video_info(raw)
            if result["success"] and result["data"]:
                _add_to_history(result["data"])
            return result
        except Exception:
            pass

    # 尝试提取 URL
    extracted = _extract_url(raw)
    url = extracted or raw
    if extracted and extracted != raw.strip():
        logger.info(f"[解析] 从文本中提取到链接: {extracted[:80]}")

    # 检查是否是视频直链（mp4/m3u8 等）
    if url.startswith("http") and (".mp4" in url or "m3u8" in url):
        result = _ok(_make_info(
            id="direct_video",
            platform="direct",
            title="直接链接",
            video_url=url,
            video_url_no_watermark=url,
        ))
        if result["success"] and result["data"]:
            _add_to_history(result["data"])
        return result

    parsed = _urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="仅支持 http/https 链接或视频信息 JSON")
    if not _is_safe_url(url):
        raise HTTPException(status_code=403, detail="不允许访问该地址")
    result = await parse_link(url)
    if result["success"] and result["data"]:
        _add_to_history(result["data"])
    return result


@app.post("/api/batch-parse")
async def batch_parse_videos(req: BatchParseRequest):
    """批量解析（最多 20 个）"""
    if len(req.urls) > 20:
        raise HTTPException(status_code=400, detail="批量解析最多支持 20 个链接")
    # 从每行文本中提取 URL
    urls = [_extract_url(u.strip()) or u.strip() for u in req.urls]
    results = await batch_parse(urls)
    for r in results:
        if r["success"] and r["data"]:
            _add_to_history(r["data"])
    return {"results": results}


@app.get("/api/proxy")
async def proxy_video(video_url: str = Query(...), referer: str = Query("https://www.douyin.com/")):
    """
    视频代理：解决浏览器跨域和 Referer 限制
    前端通过此接口加载视频进行在线预览
    """
    if not video_url:
        raise HTTPException(status_code=400, detail="URL 不能为空")
    if not _is_safe_url(video_url):
        raise HTTPException(status_code=403, detail="不允许访问该地址")

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": referer,
        }
        # 先获取完整内容再返回（避免流式传输的 chunked encoding 问题）
        async with httpx.AsyncClient(timeout=60, verify=False, follow_redirects=True) as client:
            resp = await client.get(video_url, headers=headers)

            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"上游返回 {resp.status_code}")

            content_type = resp.headers.get("content-type", "video/mp4")
            content = resp.content

        return StreamingResponse(
            iter([content]),
            media_type=content_type,
            headers={"Accept-Ranges": "bytes", "Content-Length": str(len(content))},
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="代理请求超时")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"代理失败: {str(e)}")


@app.get("/api/download")
async def download_video(
    video_url: str = Query(..., description="视频直链"),
    title: str = Query("video", description="保存文件名"),
    referer: str = Query("https://www.douyin.com/", description="Referer"),
):
    """下载视频文件"""
    if not video_url:
        raise HTTPException(status_code=400, detail="视频 URL 不能为空")
    # yt-dlp 前缀（yt:// / tt:// / bl://）跳过 URL 安全检查，因为它们不直接 fetch
    if not (video_url.startswith("yt://") or video_url.startswith("tt://") or video_url.startswith("bl://")):
        if not _is_safe_url(video_url):
            raise HTTPException(status_code=403, detail="不允许访问该地址")

    safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip() or "video"

    def _is_valid_video(p):
        """检查文件是否为有效视频（而非 HTML 错误页面）"""
        if not p.exists() or p.stat().st_size < 1024:
            return False
        with open(p, "rb") as f:
            header = f.read(16)
        return b"ftyp" in header or b"skip" in header

    # yt-dlp 下载（YouTube / TikTok / B站 等需要特殊处理的平台）
    if video_url.startswith("yt://") or video_url.startswith("tt://") or video_url.startswith("bl://"):
        is_youtube = video_url.startswith("yt://")
        is_bilibili = video_url.startswith("bl://")
        vid = video_url[5:]  # skip "yt://" / "tt://" / "bl://"
        if is_youtube:
            page_url = f"https://www.youtube.com/watch?v={vid}"
            platform_name = "YouTube"
        elif is_bilibili:
            page_url = f"https://www.bilibili.com/video/{vid}"
            platform_name = "B站"
        else:
            page_url = f"https://www.tiktok.com/@/video/{vid}"
            platform_name = "TikTok"
        filepath = DOWNLOAD_DIR / f"{safe_title}.mp4"

        if _is_valid_video(filepath):
            return FileResponse(path=str(filepath), filename=f"{safe_title}.mp4", media_type="video/mp4")

        if filepath.exists():
            filepath.unlink()

        def _download_with_ytdlp():
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "outtmpl": str(filepath),
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "merge_output_format": "mp4",
                "nocheckcertificate": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([page_url])

        try:
            await asyncio.to_thread(_download_with_ytdlp)
            if not filepath.exists():
                for f in DOWNLOAD_DIR.glob(f"{safe_title}.*"):
                    filepath = f
                    break
            if not _is_valid_video(filepath):
                raise HTTPException(status_code=500, detail=f"{platform_name} 下载失败: 下载的文件不是有效视频")
            return FileResponse(path=str(filepath), filename=f"{safe_title}.mp4", media_type="video/mp4")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"{platform_name} 下载失败: {str(e)[:200]}")

    # 微信视频号加密视频下载（wx:// 前缀）
    if video_url.startswith("wx://"):
        # 格式: wx://video_url|decrypt_key
        parts = video_url[5:].split("|", 1)
        actual_url = parts[0]
        decrypt_key = parts[1] if len(parts) > 1 else None

        filepath = DOWNLOAD_DIR / f"{safe_title}.mp4"

        if _is_valid_video(filepath):
            return FileResponse(path=str(filepath), filename=f"{safe_title}.mp4", media_type="video/mp4")

        if filepath.exists():
            filepath.unlink()

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://channels.weixin.qq.com/",
            }
            async with httpx.AsyncClient(timeout=120, verify=False, follow_redirects=True) as client:
                resp = await client.get(actual_url, headers=headers)
                if resp.status_code != 200:
                    raise HTTPException(status_code=502, detail=f"微信视频下载失败 (HTTP {resp.status_code})")

                content = resp.content

                # 如果有解密密钥，需要解密（ISAAC 流密码）
                if decrypt_key:
                    try:
                        from .decrypt import decrypt_isaac
                        content = decrypt_isaac(content, int(decrypt_key))
                    except Exception as e:
                        logger.warning(f"视频解密失败: {e}")

                filepath.write_bytes(content)

            return FileResponse(path=str(filepath), filename=f"{safe_title}.mp4", media_type="video/mp4")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="下载超时")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"微信视频下载失败: {str(e)}")

    filename = f"{safe_title}.mp4"
    filepath = DOWNLOAD_DIR / filename

    if filepath.exists() and filepath.stat().st_size > 0:
        return FileResponse(path=str(filepath), filename=filename, media_type="video/mp4")

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": referer,
        }
        async with httpx.AsyncClient(timeout=120, verify=False, follow_redirects=True) as client:
            resp = await client.get(video_url, headers=headers)
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"下载失败 (HTTP {resp.status_code})")
            filepath.write_bytes(resp.content)

        return FileResponse(path=str(filepath), filename=filename, media_type="video/mp4")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="下载超时")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")


@app.get("/api/history")
async def get_history(limit: int = Query(50, ge=1, le=200)):
    return {"history": _load_history()[:limit]}


@app.delete("/api/history")
async def clear_history():
    _save_history([])
    return {"message": "历史记录已清空"}


@app.delete("/api/history/{record_id}")
async def delete_history_record(record_id: str):
    history = [h for h in _load_history() if h.get("id") != record_id]
    _save_history(history)
    return {"message": "已删除"}


@app.get("/api/bg-remove/models")
async def bg_remove_models():
    """返回可用的抠图模型列表（V3.0 自动选择）"""
    return {
        "models": model_manager.list_models(),
        "default": ModelManager.DEFAULT_MODEL,
        "v3": True,
    }


# ─── V3.0 抠图 API ────────────────────────────────────

@app.post("/api/bg-remove")
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

    # 1. 缓存检查（先用 auto 模型分类结果做 key）
    #    由于分类需要先解码图片，缓存 key 暂用 md5+model
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


@app.post("/api/bg-remove-batch")
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


@app.post("/api/bg-remove-batch-stream")
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


@app.get("/api/bg-remove/download/{filename}")
async def bg_remove_download(filename: str):
    """下载抠图结果"""
    out_path = BG_REMOVER_DIR / "output" / filename
    if not out_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    ext = filename.rsplit('.', 1)[-1] if '.' in filename else "png"
    media = "image/webp" if ext == "webp" else "image/png"
    return FileResponse(path=str(out_path), filename=filename, media_type=media)


# ─── 根路由：跳转到 /tools/ ─────────────────────────────
@app.get("/")
async def root():
    return RedirectResponse(url="/tools/")


# ─── 工具箱首页 ────────────────────────────────────
@app.get("/tools/")
async def tools_home():
    index_file = PROJECT_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "小小工具箱 API 运行中", "docs": "/docs"}


# ─── 挂载视频工具前端 ────────────────────────────────────
if VIDEO_TOOL_DIR.exists():
    app.mount("/tools/video-tool", StaticFiles(directory=str(VIDEO_TOOL_DIR), html=True), name="video-tool")

# ─── 挂载图片工具前端 ────────────────────────────────────
if IMAGE_TOOL_DIR.exists():
    app.mount("/tools/image-tool", StaticFiles(directory=str(IMAGE_TOOL_DIR), html=True), name="image-tool")

# ─── 挂载抠图工具前端 ────────────────────────────────────
if BG_REMOVER_DIR.exists():
    app.mount("/tools/bg-remover", StaticFiles(directory=str(BG_REMOVER_DIR), html=True), name="bg-remover")

# ─── 挂载溶图工具前端 ────────────────────────────────────
if IMAGE_COMPOSITE_DIR.exists():
    app.mount("/tools/image-composite", StaticFiles(directory=str(IMAGE_COMPOSITE_DIR), html=True), name="image-composite")

# ─── 挂载公共库 ────────────────────────────────────
if LIBS_DIR.exists():
    app.mount("/tools/libs", StaticFiles(directory=str(LIBS_DIR)), name="libs")


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  小小工具箱 v3.0")
    print("  支持：图片处理 | 视频解析下载 | AI 智能抠图")
    print("  本机访问: http://127.0.0.1:5001")
    print("  局域网:   http://0.0.0.0:5001 (同网络设备可访问)")

    # 清理过期缓存
    try:
        disk_cache.cleanup()
    except Exception as e:
        logger.warning(f"缓存清理失败: {e}")

    # 预热默认模型
    try:
        print(f"[...] 正在加载 AI 抠图模型 ({ModelManager.DEFAULT_MODEL})...")
        model_manager.preload_default()
        print("[OK] AI 模型加载完成")
    except Exception as e:
        print(f"[WARN] 模型预加载失败（首次使用时会自动下载）: {e}")

    print("=" * 50 + "\n")
    uvicorn.run("main:app", host="0.0.0.0", port=5001, log_level="info")
