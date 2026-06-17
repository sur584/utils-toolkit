"""
视频解析 / 下载 / 代理 路由
"""

import asyncio
import logging

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from parsers import parse_link, batch_parse
from parsers._utils import _is_safe_url, _extract_url

from config import DOWNLOAD_DIR, HTTP_PROXY
from deps import (
    ParseRequest, BatchParseRequest,
    _get_client_ip, _add_to_history,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "3.0.0"}


@router.get("/api/platforms")
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


@router.post("/api/parse")
async def parse_video(req: ParseRequest, request: Request):
    """解析视频链接（自动识别平台）"""
    from urllib.parse import urlparse as _urlparse
    from parsers.wechat_channels import parse_video_info
    from parsers._utils import _ok, _make_info

    ip = _get_client_ip(request)
    raw = req.url.strip()
    logger.info(f"[解析] 收到请求: {raw[:80]}...")

    # 先尝试作为 JSON 解析（微信视频号等需要粘贴 JSON 数据）
    if raw.startswith("{") or raw.startswith("["):
        logger.info("[解析] 检测到 JSON 输入，尝试微信视频号解析")
        try:
            result = parse_video_info(raw)
            if result["success"] and result["data"]:
                _add_to_history(result["data"], ip)
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
            _add_to_history(result["data"], ip)
        return result

    parsed = _urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="仅支持 http/https 链接或视频信息 JSON")
    if not _is_safe_url(url):
        raise HTTPException(status_code=403, detail="不允许访问该地址")
    result = await parse_link(url)
    if result["success"] and result["data"]:
        _add_to_history(result["data"], ip)
    return result


@router.post("/api/batch-parse")
async def batch_parse_videos(req: BatchParseRequest, request: Request):
    """批量解析（最多 20 个）"""
    if len(req.urls) > 20:
        raise HTTPException(status_code=400, detail="批量解析最多支持 20 个链接")
    ip = _get_client_ip(request)
    # 从每行文本中提取 URL
    urls = [_extract_url(u.strip()) or u.strip() for u in req.urls]
    results = await batch_parse(urls)
    for r in results:
        if r["success"] and r["data"]:
            _add_to_history(r["data"], ip)
    return {"results": results}


@router.get("/api/proxy")
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


@router.get("/api/download")
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
        """检查文件是否为有效视频（而非加密/错误文件）"""
        if not p.exists() or p.stat().st_size < 10240:
            return False
        with open(p, "rb") as f:
            header = f.read(64)
        # 有效 MP4 签名
        if b"ftyp" in header[:20] or b"skip" in header[:20]:
            return True
        if b"ISOM" in header[:12] or b"isom" in header[:12]:
            return True
        # 无效：HTML 错误页面、JSON 错误等
        if header[:5] in (b'<!DOC', b'<html', b'<?xml', b'{"err', b'{\n  "'):
            return False
        return False

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
            # tt://@{username}/{video_id} 或 tt://{video_id}（旧格式）
            if vid.startswith("@"):
                page_url = f"https://www.tiktok.com/{vid}"
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
            if HTTP_PROXY and platform_name == "TikTok":
                ydl_opts["proxy"] = HTTP_PROXY
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
        logger.info(f"[下载] 微信视频号: url={actual_url[:100]}..., key={decrypt_key}")

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
                        from decrypt import decrypt_isaac
                        content = decrypt_isaac(content, int(decrypt_key))
                    except Exception as e:
                        logger.warning(f"视频解密失败: {e}")

                filepath.write_bytes(content)

                # 验证解密后的视频文件
                if not _is_valid_video(filepath):
                    filepath.unlink()
                    raise HTTPException(
                        status_code=500,
                        detail="视频解密后无法播放，可能解密密钥不正确或视频格式不支持"
                    )

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

        # 验证下载的视频文件
        if not _is_valid_video(filepath):
            filepath.unlink()
            raise HTTPException(
                status_code=500,
                detail="下载的文件不是有效视频，可能是加密视频或服务端返回了错误页面"
            )

        return FileResponse(path=str(filepath), filename=filename, media_type="video/mp4")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="下载超时")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")


# ─── Cookie 管理 ──────────────────────────────────────

class CookieUpdateRequest(BaseModel):
    cookie: str


@router.post("/api/wechat-cookie")
async def update_wechat_cookie(req: CookieUpdateRequest):
    """热更新视频号解析 cookie（无需重启服务）"""
    from parsers.wechat_channels import update_cookie
    if not req.cookie.strip():
        raise HTTPException(status_code=400, detail="cookie 不能为空")
    update_cookie(req.cookie.strip())
    return {"success": True, "message": "cookie 已更新"}


@router.get("/api/wechat-cookie/status")
async def cookie_status():
    """检查视频号 cookie 是否已配置"""
    from parsers.wechat_channels import YUANBAO_COOKIE
    return {"configured": bool(YUANBAO_COOKIE), "length": len(YUANBAO_COOKIE)}
