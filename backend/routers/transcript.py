"""
视频文案提取路由（transcript）
从 video-transcript 项目迁移而来的 API 路由
"""

import asyncio
import logging
import os
import shutil
import tempfile
import time
import uuid
from typing import Dict

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from transcript.settings import load_settings
from transcript.cloud_config import load_cloud_config, save_cloud_config, mask_key
from transcript.pipeline import extract_transcript, extract_transcript_from_file
from transcript.platforms._utils import _is_safe_url, _extract_url
from transcript.asr.local_whisper import is_local_whisper_available
from transcript.cloud_asr import get_cloud_client
from transcript.ytdlp_utils import find_ytdlp

logger = logging.getLogger(__name__)

router = APIRouter()

# ─── Settings ─────────────────────────────────────
settings = load_settings()

# ─── Job Store ────────────────────────────────────
_jobs: Dict[str, dict] = {}
JOB_TTL = 1800  # 30 minutes
MAX_JOBS = 100
ALLOWED_UPLOAD_EXT = {
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".flv", ".m4v", ".ts", ".wmv",
    ".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac", ".wma", ".opus",
}
MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500MB
UPLOAD_CHUNK = 1024 * 1024           # 1MB
_semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)


class TranscriptRequest(BaseModel):
    url: str
    method: str = "auto"        # "auto" | "subtitle_only" | "asr_only"
    asr_model: str = "auto"     # "auto" | specific model id
    language: str = "zh"


class ConfigUpdateRequest(BaseModel):
    mode: str = "local"         # "local" | "cloud"
    default_provider: str = ""
    providers: dict = {}
    cookies_path: str = ""


class ProviderTestRequest(BaseModel):
    provider_key: str


def _make_response(success: bool, message: str, data=None):
    return {"success": success, "message": message, "data": data}


def _cleanup_jobs():
    """Remove expired jobs."""
    now = time.time()
    expired = [jid for jid, j in _jobs.items() if now - j["created_at"] > JOB_TTL]
    for jid in expired:
        del _jobs[jid]


# ─── Routes ───────────────────────────────────────

@router.get("/api/transcript/config")
async def get_config():
    # Cloud config
    cloud_cfg = load_cloud_config()

    # 判断当前实际使用的 ASR
    local_asr_available = is_local_whisper_available()
    if cloud_cfg.mode == "cloud" and cloud_cfg.default_provider:
        active_provider = cloud_cfg.default_provider
        active_mode = "cloud"
    else:
        active_mode = "local"
        if settings.asr_provider == "auto":
            if local_asr_available:
                active_provider = "local"
            elif settings.siliconflow_api_key:
                active_provider = "mimo"
            else:
                active_provider = "none"
        else:
            active_provider = settings.asr_provider

    # Extract model name from path
    local_asr_model = ""
    if settings.local_asr_model_path:
        from pathlib import Path
        model_path = Path(settings.local_asr_model_path)
        for part in model_path.parts:
            if "faster-whisper-" in part:
                local_asr_model = part.split("faster-whisper-")[-1]
                break
        if not local_asr_model:
            local_asr_model = model_path.name

    # Cloud providers (masked keys)
    cloud_providers = {}
    for key, p in cloud_cfg.providers.items():
        cloud_providers[key] = {
            "name": p.name,
            "type": p.type,
            "configured": bool(p.api_key),
            "model": p.model,
            "base_url": p.base_url,
            "api_key": p.api_key,
            "headers": p.headers,
        }

    return _make_response(True, "ok", {
        "mode": active_mode,
        "asr_provider": settings.asr_provider,
        "asr_active": active_provider,
        "local_asr_available": local_asr_available,
        "local_asr_model": local_asr_model,
        "local_asr_device": settings.local_asr_device,
        "mimo_configured": bool(settings.siliconflow_api_key),
        "ytdlp_found": find_ytdlp() is not None,
        "default_provider": cloud_cfg.default_provider,
        "providers": cloud_providers,
        "supported_platforms": [
            {"key": "douyin", "name": "抖音"},
            {"key": "wechat_channels", "name": "微信视频号"},
            {"key": "bilibili", "name": "B站"},
            {"key": "youtube", "name": "YouTube"},
            {"key": "tiktok", "name": "TikTok"},
            {"key": "xiaohongshu", "name": "小红书"},
            {"key": "weibo", "name": "微博"},
            {"key": "instagram", "name": "Instagram"},
            {"key": "twitter", "name": "Twitter"},
        ],
    })


@router.put("/api/transcript/config")
async def update_config(req: ConfigUpdateRequest):
    try:
        config = load_cloud_config()

        # Validate mode
        if req.mode not in ("local", "cloud"):
            return _make_response(False, "mode 必须是 'local' 或 'cloud'")

        config.mode = req.mode
        config.cookies_path = req.cookies_path

        if req.mode == "cloud":
            if not req.providers:
                return _make_response(False, "云模式下至少需要一个 provider")
            if req.default_provider not in req.providers:
                return _make_response(
                    False,
                    f"default_provider '{req.default_provider}' 不在 providers 中",
                )

            valid_types = {"openai-compatible", "whisper-api"}
            from transcript.cloud_config import ProviderConfig
            new_providers = {}
            for key, p in req.providers.items():
                missing = [f for f in ("name", "type", "api_key", "base_url", "model") if f not in p]
                if missing:
                    return _make_response(False, f"Provider '{key}' 缺少必填字段: {missing}")
                if p["type"] not in valid_types:
                    return _make_response(False, f"Provider '{key}' type 无效: '{p['type']}'")
                new_providers[key] = ProviderConfig(
                    name=p["name"], type=p["type"], api_key=p["api_key"],
                    base_url=p["base_url"], model=p["model"],
                    headers=p.get("headers", {}),
                )
            config.providers = new_providers
            config.default_provider = req.default_provider

        save_cloud_config(config)
        return _make_response(True, "配置已保存")
    except Exception as e:
        logger.error(f"Config update failed: {e}", exc_info=True)
        return _make_response(False, str(e))


@router.post("/api/transcript/config/test")
async def test_provider(req: ProviderTestRequest):
    try:
        client = get_cloud_client(req.provider_key)
        success, message, latency = await client.test_connection()
        await client.close()
        return {"success": success, "message": message, "data": {"latency_ms": round(latency, 1)}}
    except Exception as e:
        logger.error(f"Provider test failed: {e}", exc_info=True)
        return _make_response(False, str(e))


@router.post("/api/transcript")
async def submit_transcript(req: TranscriptRequest):
    _cleanup_jobs()

    if len(_jobs) >= MAX_JOBS:
        raise HTTPException(status_code=429, detail=_make_response(False, "任务队列已满，请稍后再试"))

    if not req.url.strip():
        raise HTTPException(status_code=400, detail=_make_response(False, "请输入有效的视频链接"))

    # Extract URL from text (user might paste text containing a URL)
    url = _extract_url(req.url) or req.url.strip()

    # Validate URL safety (SSRF protection)
    if not _is_safe_url(url):
        raise HTTPException(status_code=400, detail=_make_response(False, "不安全的链接，请输入有效的公开视频链接"))

    # Update the request URL with the extracted/validated URL
    req.url = url

    job_id = uuid.uuid4().hex[:8]
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "processing",
        "step": "parsing",
        "progress": 0,
        "message": "任务已提交",
        "result": None,
        "created_at": time.time(),
    }

    asyncio.create_task(_run_job(job_id, req))

    return _make_response(True, "任务已提交", {
        "job_id": job_id,
        "status": "processing",
    })


@router.get("/api/transcript/{job_id}")
async def poll_transcript(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=_make_response(False, "任务不存在或已过期"))

    job = _jobs[job_id]

    if job["status"] == "completed":
        result = {**job["result"], "status": "completed"}
        return _make_response(True, "提取成功", result)
    elif job["status"] == "failed":
        return _make_response(False, job["message"], {"job_id": job_id, "status": "failed"})
    else:
        return _make_response(True, "处理中", {
            "job_id": job_id,
            "status": "processing",
            "step": job["step"],
            "progress": job["progress"],
            "message": job["message"],
        })


async def _run_job(job_id: str, req: TranscriptRequest):
    """Background task to run the transcript extraction."""
    async with _semaphore:
        job = _jobs[job_id]
        try:
            async def progress_cb(step, pct, msg):
                job["step"] = step
                job["progress"] = pct
                job["message"] = msg
                logger.info(f"Job {job_id} progress: {pct}% - {msg}")

            logger.info(f"Job {job_id} starting extraction for: {req.url[:60]}")
            result = await extract_transcript(
                url=req.url,
                method=req.method,
                asr_model=req.asr_model,
                language=req.language,
                api_key=settings.siliconflow_api_key,
                progress_callback=progress_cb,
            )

            job["status"] = "completed"
            job["result"] = result
            job["message"] = "提取成功"
            logger.info(f"Job {job_id} completed successfully")

        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)
            job["status"] = "failed"
            job["message"] = "提取失败，请稍后重试"


@router.post("/api/transcript/upload")
async def upload_transcript(file: UploadFile = File(...), language: str = Form("zh")):
    _cleanup_jobs()
    if len(_jobs) >= MAX_JOBS:
        raise HTTPException(status_code=429, detail=_make_response(False, "任务队列已满，请稍后再试"))

    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXT:
        raise HTTPException(status_code=400, detail=_make_response(False, f"不支持的文件类型: {ext or '未知'}"))

    tmp_dir = tempfile.mkdtemp(prefix="transcript_upload_")
    file_path = os.path.join(tmp_dir, filename)
    total = 0
    try:
        with open(file_path, "wb") as f:
            while True:
                chunk = await file.read(UPLOAD_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_SIZE:
                    f.close()
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    raise HTTPException(status_code=413, detail=_make_response(False, "文件过大，最大支持 500MB"))
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.error(f"文件上传失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=_make_response(False, "文件保存失败"))
    finally:
        await file.close()

    if total == 0:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=_make_response(False, "文件为空"))

    job_id = uuid.uuid4().hex[:8]
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "processing",
        "step": "upload",
        "progress": 0,
        "message": "文件已上传，正在处理",
        "result": None,
        "created_at": time.time(),
    }

    asyncio.create_task(_run_upload_job(job_id, file_path, filename, language, tmp_dir))

    return _make_response(True, "文件已上传", {"job_id": job_id, "status": "processing"})


async def _run_upload_job(job_id: str, file_path: str, filename: str, language: str, tmp_dir: str):
    """后台任务：本地上传文件的文案提取。"""
    async with _semaphore:
        job = _jobs[job_id]
        try:
            async def progress_cb(step, pct, msg):
                job["step"] = step
                job["progress"] = pct
                job["message"] = msg
                logger.info(f"Upload job {job_id} progress: {pct}% - {msg}")

            logger.info(f"Upload job {job_id} starting for file: {filename}")
            result = await extract_transcript_from_file(
                file_path=file_path,
                filename=filename,
                language=language,
                progress_callback=progress_cb,
            )
            job["status"] = "completed"
            job["result"] = result
            job["message"] = "提取成功"
            logger.info(f"Upload job {job_id} completed")
        except Exception as e:
            logger.error(f"Upload job {job_id} failed: {e}", exc_info=True)
            job["status"] = "failed"
            job["message"] = "提取失败，请稍后重试"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/api/extract")
async def extract_direct(req: TranscriptRequest):
    """同步接口：直接返回提取结果，适合程序化调用"""
    url = _extract_url(req.url) or req.url.strip()
    if not _is_safe_url(url):
        raise HTTPException(status_code=400, detail=_make_response(False, "不安全的链接"))

    async with _semaphore:
        try:
            result = await asyncio.wait_for(
                extract_transcript(
                    url=url,
                    method=req.method,
                    asr_model=req.asr_model,
                    language=req.language,
                    api_key=settings.siliconflow_api_key,
                ),
                timeout=300.0,
            )
            return _make_response(True, "提取成功", result)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=408, detail=_make_response(False, "处理超时，请稍后重试"))
        except Exception as e:
            logger.error(f"Direct extract failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=_make_response(False, str(e)))


# ─── Video Proxy ─────────────────────────────────
@router.get("/api/transcript/proxy")
async def proxy_video(video_url: str = "", referer: str = "https://www.douyin.com/"):
    """视频代理：解决浏览器跨域和 Referer 限制"""
    if not video_url:
        raise HTTPException(status_code=400, detail="缺少 video_url 参数")

    from transcript.platforms._utils import _headers, _is_safe_url
    import httpx
    from fastapi.responses import StreamingResponse

    # SSRF 防护：校验目标 URL 安全性
    if not _is_safe_url(video_url):
        raise HTTPException(status_code=400, detail="不安全的 video_url")

    # Referer 白名单校验，防止伪造 Referer 访问内部服务
    _allowed_referer_domains = (
        "douyin.com", "tiktok.com", "youtube.com",
        "douyinvod.com", "googlevideo.com", "ytimg.com",
        "tiktokcdn.com", "bytedance.com",
    )
    try:
        from urllib.parse import urlparse
        referer_host = urlparse(referer).hostname or ""
        if not any(referer_host.endswith(d) for d in _allowed_referer_domains):
            referer = "https://www.douyin.com/"
    except Exception:
        referer = "https://www.douyin.com/"

    headers = _headers(referer=referer)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            req = client.build_request("GET", video_url, headers=headers)
            resp = await client.send(req, stream=True)
            content_type = resp.headers.get("content-type", "video/mp4")

            async def stream_chunks():
                try:
                    async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                        yield chunk
                finally:
                    resp.close()

            content_length = resp.headers.get("content-length")
            extra_headers = {}
            if content_length:
                extra_headers["Content-Length"] = content_length
            return StreamingResponse(stream_chunks(), media_type=content_type, headers=extra_headers)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Proxy failed: {e}")
        raise HTTPException(status_code=502, detail="代理请求失败")
