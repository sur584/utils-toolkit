"""
小小工具箱 - 后端服务
基于 FastAPI 提供多平台视频解析、下载、预览代理等 API
"""

import sys
import os

# 添加 backend 目录到 sys.path 以便 import parsers
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json
import time
import uuid
import logging
import asyncio
from pathlib import Path
from typing import List

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yt_dlp

from parsers import parse_link, batch_parse
from parsers._utils import _is_safe_url, _extract_url

# ─── 配置 ─────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
HISTORY_FILE = BASE_DIR / "history.json"
VIDEO_TOOL_DIR = PROJECT_DIR / "tools" / "video-tool"
IMAGE_TOOL_DIR = PROJECT_DIR / "tools" / "image-tool"

DOWNLOAD_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger(__name__)

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


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  小小工具箱 v2.0")
    print("  支持：图片处理 | 视频解析下载（抖音/B站/小红书/TikTok/YouTube 等）")
    print("  打开浏览器访问: http://127.0.0.1:5001")
    print("=" * 50 + "\n")
    uvicorn.run("main:app", host="127.0.0.1", port=5001, log_level="info")
