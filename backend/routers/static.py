"""
静态文件挂载与首页路由
"""

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from config import (
    BASE_DIR, PROJECT_DIR, VIDEO_TOOL_DIR, IMAGE_TOOL_DIR,
    BG_REMOVER_DIR, IMAGE_COMPOSITE_DIR, TEXT_REMOVER_DIR,
    WX_VIDEO_PARSER_DIR, LIBS_DIR, WATERMARK_TOOL_DIR,
    TRANSCRIPT_DIR,
)

router = APIRouter()


@router.get("/")
async def root():
    return RedirectResponse(url="/tools/")


@router.get("/tools/")
async def tools_home():
    index_file = PROJECT_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "小小工具箱 API 运行中", "docs": "/docs"}


def mount_static(app):
    """将所有静态文件目录挂载到 FastAPI app 上（必须在路由注册之后调用）"""

    # 挂载视频工具前端
    if VIDEO_TOOL_DIR.exists():
        app.mount("/tools/video-tool", StaticFiles(directory=str(VIDEO_TOOL_DIR), html=True), name="video-tool")

    # 挂载图片工具前端
    if IMAGE_TOOL_DIR.exists():
        app.mount("/tools/image-tool", StaticFiles(directory=str(IMAGE_TOOL_DIR), html=True), name="image-tool")

    # 挂载抠图工具前端
    if BG_REMOVER_DIR.exists():
        app.mount("/tools/bg-remover", StaticFiles(directory=str(BG_REMOVER_DIR), html=True), name="bg-remover")

    # 挂载溶图工具前端
    if IMAGE_COMPOSITE_DIR.exists():
        app.mount("/tools/image-composite", StaticFiles(directory=str(IMAGE_COMPOSITE_DIR), html=True), name="image-composite")

    # 挂载文字去除工具前端
    if TEXT_REMOVER_DIR.exists():
        app.mount("/tools/text-remover", StaticFiles(directory=str(TEXT_REMOVER_DIR), html=True), name="text-remover")

    # 挂载暗水印检测工具前端
    if WATERMARK_TOOL_DIR.exists():
        app.mount("/tools/watermark-tool", StaticFiles(directory=str(WATERMARK_TOOL_DIR), html=True), name="watermark-tool")

    # 挂载视频号解析工具前端
    if WX_VIDEO_PARSER_DIR.exists():
        app.mount("/tools/wx-video-parser", StaticFiles(directory=str(WX_VIDEO_PARSER_DIR), html=True), name="wx-video-parser")

    # 挂载文案提取工具前端
    if TRANSCRIPT_DIR.exists():
        app.mount("/tools/transcript", StaticFiles(directory=str(TRANSCRIPT_DIR), html=True), name="transcript")

    # 挂载公共库
    if LIBS_DIR.exists():
        app.mount("/tools/libs", StaticFiles(directory=str(LIBS_DIR)), name="libs")

    # 挂载 Vite 构建产物
    assets_dir = PROJECT_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")


def register_404_handler(app):
    """注册 404 错误处理（必须在静态文件挂载之后调用）"""

    @app.exception_handler(404)
    async def custom_404(request: Request, exc):
        four_oh_four = BASE_DIR / "static" / "404.html"
        if four_oh_four.exists():
            return HTMLResponse(content=four_oh_four.read_text(encoding="utf-8"), status_code=404)
        return HTMLResponse(content="<h1>404 Not Found</h1>", status_code=404)
