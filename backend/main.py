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
import hashlib
import logging
import asyncio
from pathlib import Path
from typing import List
from collections import OrderedDict

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

# ─── 全局 rembg session（按模型缓存，避免每次请求重新加载）──
_bg_sessions = {}
BG_MODELS = {
    "u2netp": "极速（推荐）",
    "u2net": "标准",
    "isnet-general-use": "通用精准（产品/物体推荐）",
    "u2net_human_seg": "人像优化",
    "silueta": "边缘更精细",
}
BG_DEFAULT_MODEL = "u2netp"

def _get_bg_session(model_name: str = None):
    model_name = model_name or BG_DEFAULT_MODEL
    if model_name not in BG_MODELS:
        model_name = BG_DEFAULT_MODEL
    if model_name not in _bg_sessions:
        import os as _os
        _os.environ.setdefault("OMP_NUM_THREADS", str(min(_os.cpu_count() or 4, 8)))
        from rembg import new_session
        from onnxruntime import SessionOptions, GraphOptimizationLevel, ExecutionMode
        nthreads = min(_os.cpu_count() or 4, 8)
        opts = SessionOptions()
        opts.graph_optimization_level = GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.execution_mode = ExecutionMode.ORT_PARALLEL
        opts.inter_op_num_threads = nthreads
        opts.intra_op_num_threads = nthreads
        logger.info(f"加载 rembg 模型: {model_name}")
        _bg_sessions[model_name] = new_session(model_name, opts)
        logger.info(f"模型 {model_name} 加载完成")
    return _bg_sessions[model_name]

# ─── 结果缓存（相同图片+模型+质量 → 秒返回）──
_bg_cache = OrderedDict()
_BG_CACHE_MAX = 50

def _cache_key(data: bytes, model: str, quality: str) -> str:
    h = hashlib.md5(data).hexdigest()
    return f"{h}_{model}_{quality}"

def _cache_get(key: str):
    if key in _bg_cache:
        _bg_cache.move_to_end(key)
        return _bg_cache[key]
    return None

def _cache_set(key: str, value: bytes):
    _bg_cache[key] = value
    _bg_cache.move_to_end(key)
    while len(_bg_cache) > _BG_CACHE_MAX:
        _bg_cache.popitem(last=False)

# ─── FastAPI 应用 ─────────────────────────────────────
app = FastAPI(title="小小工具箱", version="2.0.0")

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
    return {"status": "ok", "version": "2.0.0"}


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
    """返回可用的抠图模型列表"""
    return {"models": BG_MODELS, "default": BG_DEFAULT_MODEL}


# ─── 抠图 API ─────────────────────────────────────────
def _preprocess_image(data: bytes, fast: bool = False) -> "Image.Image":
    """预处理图片：统一颜色模式、限制尺寸，返回 PIL Image（避免重复编码）"""
    from PIL import Image, UnidentifiedImageError
    try:
        img = Image.open(io.BytesIO(data))
        img.load()  # 强制解码，检测损坏文件
    except UnidentifiedImageError:
        raise ValueError("无法识别此文件为图片。请确认文件是 JPG、PNG、WebP 或 BMP 格式，而非其他类型文件")
    except Exception as e:
        raise ValueError(f"图片文件损坏或无法读取，请尝试重新导出图片：{str(e)[:100]}")

    orig_mode = img.mode
    # 统一颜色模式（rembg 不支持 CMYK/P/L 等模式）
    if img.mode not in ('RGB', 'RGBA'):
        try:
            img = img.convert('RGBA' if img.mode in ('P', 'LA', 'PA') else 'RGB')
        except Exception:
            raise ValueError(f"不支持的颜色模式 {orig_mode}，请将图片转换为 RGB 或 RGBA 模式后重试")

    # 限制最大尺寸：fast 模式用更小的尺寸
    max_dim = 2048 if fast else 4096
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    if min(img.size) < 10:
        raise ValueError(f"图片尺寸太小（{img.width}x{img.height}），至少需要 10x10 像素")

    return img


@app.post("/api/bg-remove")
async def bg_remove(file: UploadFile = File(...), model: str = Form(BG_DEFAULT_MODEL), quality: str = Form("fast")):
    """单张图片抠图（移除背景）quality: fast=速度优先, high=质量优先"""
    input_data = await file.read()
    if len(input_data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件大小不能超过 20MB")
    if len(input_data) == 0:
        raise HTTPException(status_code=400, detail="文件为空")

    fast_mode = quality != "high"

    # 检查缓存
    ck = _cache_key(input_data, model, quality)
    cached = _cache_get(ck)
    if cached:
        logger.info(f"命中缓存: {file.filename}")
        from urllib.parse import quote
        base_name = file.filename.rsplit('.', 1)[0] if file.filename else "image"
        filename = f"nobg_{base_name}.png"
        ascii_name = "".join(c if ord(c) < 128 else '_' for c in filename)
        encoded = quote(filename)
        return StreamingResponse(
            io.BytesIO(cached),
            media_type="image/png",
            headers={"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"},
        )

    def _process():
        from rembg import remove
        processed = _preprocess_image(input_data, fast=fast_mode)
        kwargs = dict(
            session=_get_bg_session(model),
            alpha_matting=not fast_mode,
        )
        if not fast_mode:
            kwargs["alpha_matting_foreground_threshold"] = 240
            kwargs["alpha_matting_background_threshold"] = 10
            kwargs["alpha_matting_erode_size"] = 10
        result = remove(processed, **kwargs)
        # rembg 输入 PIL Image 时返回 PIL Image，需要转为 bytes
        if hasattr(result, 'save'):
            buf = io.BytesIO()
            result.save(buf, format='PNG')
            return buf.getvalue()
        return result

    try:
        output_data = await asyncio.wait_for(asyncio.to_thread(_process), timeout=120)
    except ValueError as e:
        # 来自 _preprocess_image 的友好错误信息
        raise HTTPException(status_code=400, detail=str(e))
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="抠图处理超时（超过120秒）。建议：1）切换到「速度优先」模式；2）缩小图片尺寸；3）选择 u2netp 极速模型")
    except MemoryError:
        raise HTTPException(status_code=500, detail="内存不足，图片太大无法处理。请将图片缩小到 2048px 以内后重试")
    except Exception as e:
        logger.error(f"抠图处理失败 {file.filename}: {e}", exc_info=True)
        err_msg = str(e)
        if "ONNX" in err_msg or "onnx" in err_msg:
            raise HTTPException(status_code=500, detail="AI 模型加载失败，请尝试切换其他模型或重启服务")
        if "CUDA" in err_msg or "cuda" in err_msg:
            raise HTTPException(status_code=500, detail="GPU 加速不可用，请切换到 CPU 模型（如 u2netp）")
        raise HTTPException(status_code=500, detail=f"抠图处理失败：{err_msg[:200]}")

    # 存入缓存
    _cache_set(ck, output_data)

    from urllib.parse import quote
    base_name = file.filename.rsplit('.', 1)[0] if file.filename else "image"
    filename = f"nobg_{base_name}.png"
    ascii_name = "".join(c if ord(c) < 128 else '_' for c in filename)
    encoded = quote(filename)
    return StreamingResponse(
        io.BytesIO(output_data),
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"},
    )


@app.post("/api/bg-remove-batch")
async def bg_remove_batch(files: List[UploadFile] = File(...), model: str = Form(BG_DEFAULT_MODEL), quality: str = Form("fast")):
    """批量抠图（顺序处理，返回下载路径列表）"""
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="批量抠图最多支持 50 张图片")

    fast_mode = quality != "high"
    results = []
    for f in files:
        input_data = await f.read()
        if len(input_data) > 20 * 1024 * 1024:
            results.append({"filename": f.filename, "success": False, "error": "文件超过 20MB"})
            continue

        def _process(data=input_data):
            from rembg import remove
            processed = _preprocess_image(data, fast=fast_mode)
            kwargs = dict(
                session=_get_bg_session(model),
                alpha_matting=not fast_mode,
            )
            if not fast_mode:
                kwargs["alpha_matting_foreground_threshold"] = 240
                kwargs["alpha_matting_background_threshold"] = 10
                kwargs["alpha_matting_erode_size"] = 10
            return remove(processed, **kwargs)

        try:
            output_data = await asyncio.wait_for(asyncio.to_thread(_process), timeout=120)
            base = f.filename.rsplit('.', 1)[0] if f.filename else "image"
            out_name = f"nobg_{base}.png"
            out_path = BG_REMOVER_DIR / "output"
            out_path.mkdir(exist_ok=True)
            (out_path / out_name).write_bytes(output_data)
            results.append({"filename": out_name, "success": True})
        except asyncio.TimeoutError:
            results.append({"filename": f.filename, "success": False, "error": "处理超时（超过120秒）"})
        except Exception as e:
            logger.error(f"批量抠图失败 {f.filename}: {e}", exc_info=True)
            results.append({"filename": f.filename, "success": False, "error": str(e)[:200]})

    return {"results": results}


@app.get("/api/bg-remove/download/{filename}")
async def bg_remove_download(filename: str):
    """下载抠图结果"""
    out_path = BG_REMOVER_DIR / "output" / filename
    if not out_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path=str(out_path), filename=filename, media_type="image/png")


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
    print("  小小工具箱 v2.0")
    print("  支持：图片处理 | 视频解析下载（抖音/B站/小红书/TikTok/YouTube 等）")
    print("  本机访问: http://127.0.0.1:5001")
    print("  局域网:   http://0.0.0.0:5001 (同网络设备可访问)")

    # 预热 rembg 默认模型，避免首次请求卡顿
    try:
        print(f"[...] 正在加载 AI 抠图模型 ({BG_DEFAULT_MODEL})...")
        _get_bg_session()
        print("[OK] AI 模型加载完成")
    except Exception as e:
        print(f"[WARN] 模型预加载失败（首次使用时会自动下载）: {e}")

    print("=" * 50 + "\n")
    uvicorn.run("main:app", host="0.0.0.0", port=5001, log_level="info")
