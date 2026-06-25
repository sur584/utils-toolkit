"""
小小工具箱 - 后端服务
基于 FastAPI 提供多平台视频解析、下载、预览代理等 API
"""

import sys
import os
from contextlib import asynccontextmanager

# 添加 backend 目录到 sys.path 以便 import 同级模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.exception_handlers import http_exception_handler

from deps import model_manager, disk_cache
from routers import video, bg_remove, text_remove, watermark, watermark_removal, upscale, history, static

logger = logging.getLogger(__name__)

# 安全导入 transcript 模块（依赖缺失时优雅降级）
TRANSCRIPT_AVAILABLE = False
try:
    from routers import transcript
    TRANSCRIPT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"transcript 模块加载失败: {e} — 视频文案提取功能将不可用")
    logger.warning(f"可尝试手动修复: {sys.executable} -m pip install python-dotenv aiofiles faster-whisper")


@asynccontextmanager
async def lifespan(_app):
    # 启动时：清理缓存 + 启动后台清理
    try:
        disk_cache.cleanup()
        logger.info(f"启动缓存清理完成。当前状态: {disk_cache.stats()}")
    except Exception as e:
        logger.warning(f"缓存清理失败: {e}")
    disk_cache.start_background_cleanup()
    yield
    # 关闭时：停止后台清理
    disk_cache.stop_background_cleanup()


app = FastAPI(title="小小工具箱", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)


# ─── 静态资源缓存 + CORS 中间件 ────────────────────────
@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    # 始终确保返回响应，避免 ASGI "callable returned without starting response" 错误
    # 即使发生异常，也让 FastAPI 生成错误响应后再添加 CORS 头
    try:
        response = await call_next(request)
    except Exception as e:
        # 让 FastAPI 默认异常处理器处理异常并生成响应
        # 这里捕获异常是为了走到下面的代码，给错误响应也添加 CORS 头
        if isinstance(e, HTTPException):
            response = await http_exception_handler(request, e)
        else:
            # 对于非 HTTPException，转换为 500 错误响应
            logger.error(f"Uncaught exception processing request: {e}", exc_info=True)
            response = await http_exception_handler(request, HTTPException(status_code=500, detail=str(e)))

    path = request.url.path
    # 确保所有响应都有 CORS 头（StaticFiles 子应用可能绕过 CORSMiddleware）
    response.headers['Access-Control-Allow-Origin'] = '*'
    # 静态资源设置长缓存（CSS/JS/图片）
    if any(path.endswith(ext) for ext in ('.css', '.js', '.png', '.jpg', '.svg', '.ico', '.woff2', '.woff', '.ttf')):
        response.headers['Cache-Control'] = 'public, max-age=86400, immutable'
    elif path in ('/', '', '/tools/') or path.endswith('.html'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


# ─── 缓存统计（保留在 main 中，因为它属于全局状态） ────
@app.get("/api/cache/stats")
async def cache_stats():
    """返回缓存统计：磁盘占用、条目数、命中率"""
    return disk_cache.stats()


# ─── 注册路由 ─────────────────────────────────────────
app.include_router(video.router)
app.include_router(bg_remove.router)
app.include_router(text_remove.router)
app.include_router(watermark.router)
app.include_router(watermark_removal.router)
app.include_router(upscale.router)
app.include_router(history.router)
app.include_router(static.router)

# transcript 路由仅在依赖可用时注册
if TRANSCRIPT_AVAILABLE:
    try:
        app.include_router(transcript.router)
    except Exception as e:
        logger.warning(f"transcript 路由注册失败: {e} — 视频文案提取功能将不可用")

# ─── 静态文件挂载 & 404 处理 ──────────────────────────
# 必须在路由注册之后，以保证 API 路由优先匹配
static.mount_static(app)
static.register_404_handler(app)


if __name__ == "__main__":
    import uvicorn

    print("\n" + "=" * 50)
    print("  小小工具箱 v3.0")
    print("  支持：图片处理 | 视频解析下载 | AI 智能抠图")
    print("  本机访问: http://127.0.0.1:5001")
    print("  局域网:   http://0.0.0.0:5001 (同网络设备可访问)")

    # 预热默认模型
    try:
        from services.model_manager import ModelManager as _MM
        print(f"[...] 正在加载 AI 抠图模型 ({_MM.DEFAULT_MODEL})...")
        model_manager.preload_default()
        print("[OK] AI 模型加载完成")
    except Exception as e:
        print(f"[WARN] 模型预加载失败（首次使用时会自动下载）: {e}")

    print("=" * 50 + "\n")
    uvicorn.run("main:app", host="0.0.0.0", port=5001, log_level="info")
