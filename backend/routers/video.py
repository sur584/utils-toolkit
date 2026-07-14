"""
视频解析 / 下载 / 代理 路由
"""

import asyncio
import hashlib
import ipaddress
import logging
import threading

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from parsers import parse_link, batch_parse
from parsers._utils import _is_safe_url, _extract_url

from config import DOWNLOAD_DIR, get_active_proxy
from deps import (
    ParseRequest, BatchParseRequest, ParseProfileRequest,
    _get_client_ip, _add_to_history, ytdlp_semaphore,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class _DownloadCancelled(Exception):
    """客户端在下载途中断开连接（点击了取消）"""


async def _watch_disconnect(request: Request, event: threading.Event):
    """等待客户端断开连接（点击取消）。

    直接 await ASGI receive 通道，阻塞到 http.disconnect 到达为止——
    比 request.is_disconnected() 的零超时轮询可靠（后者在 uvicorn 下常检测不到断开）。
    """
    try:
        while True:
            message = await request._receive()
            if message.get("type") == "http.disconnect":
                event.set()
                logger.info("[下载] 检测到客户端断开，触发取消")
                return
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning(f"[下载] 断连监视异常: {e}")


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


@router.get("/api/tiktok-oembed")
async def tiktok_oembed(url: str = Query(...)):
    """通过后端获取 TikTok oEmbed 元数据，避免公共 CORS 代理不可用。"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if not _is_safe_url(url) or not (host == "tiktok.com" or host.endswith(".tiktok.com")):
        raise HTTPException(status_code=400, detail="仅支持 TikTok 链接")
    try:
        proxy = get_active_proxy()
        client_kwargs = dict(timeout=15, verify=False, follow_redirects=True)
        if proxy:
            client_kwargs["proxies"] = proxy
        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.get(
                "https://www.tiktok.com/oembed",
                params={"url": url},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"TikTok oEmbed 返回 {resp.status_code}")
        return resp.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TikTok oEmbed 请求失败: {type(e).__name__}")


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


@router.post("/api/parse-profile")
async def parse_profile_endpoint(req: ParseProfileRequest, request: Request):
    """博主主页批量解析：返回该账号的视频列表"""
    from parsers import parse_profile

    ip = _get_client_ip(request)
    raw = req.url.strip()
    url = _extract_url(raw) or raw
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="请输入有效的 http/https 主页链接")
    if not _is_safe_url(url):
        raise HTTPException(status_code=403, detail="不允许访问该地址")

    logger.info(f"[主页解析] 收到请求: {url[:80]}, limit={req.limit}, page={req.page}")
    result = await parse_profile(url, limit=req.limit, page=req.page)

    # 只写 1 条"主页快照"到历史，避免几百条视频淹没历史列表；翻页不重复写
    data = result.get("data") or {}
    videos = data.get("videos") or []
    if result.get("success") and videos and req.page == 1:
        first = videos[0]
        _add_to_history({
            **first,
            "title": f"[主页] {data.get('author', '')} · {data.get('total', 0)} 个视频",
        }, ip)
    return result


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
    request: Request,
    video_url: str = Query(..., description="视频直链"),
    title: str = Query("video", description="保存文件名"),
    referer: str = Query("https://www.douyin.com/", description="Referer"),
):
    """下载视频文件"""
    if not video_url:
        raise HTTPException(status_code=400, detail="视频 URL 不能为空")
    # yt-dlp 前缀（yt:// / tt:// / bl:// / tw://）跳过 URL 安全检查，因为它们不直接 fetch
    if not (video_url.startswith("yt://") or video_url.startswith("tt://") or video_url.startswith("bl://") or video_url.startswith("tw://")):
        if not _is_safe_url(video_url):
            raise HTTPException(status_code=403, detail="不允许访问该地址")

    def _sanitize_filename(value: str, max_length: int = 80) -> str:
        invalid_chars = '<>:"/\\|?*'
        safe = "".join(c for c in value if c not in invalid_chars and ord(c) >= 32)
        safe = " ".join(safe.split()).strip(" ._-")
        return (safe[:max_length].rstrip(" ._-") or "video")

    display_title = _sanitize_filename(title)
    storage_title = f"{display_title}-{hashlib.sha1(video_url.encode('utf-8')).hexdigest()[:10]}"

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

    # yt-dlp 下载（YouTube / TikTok / B站 / Twitter 等需要特殊处理的平台）
    if video_url.startswith("yt://") or video_url.startswith("tt://") or video_url.startswith("bl://") or video_url.startswith("tw://"):
        is_youtube = video_url.startswith("yt://")
        is_bilibili = video_url.startswith("bl://")
        is_twitter = video_url.startswith("tw://")
        vid = video_url[5:]  # skip "yt://" / "tt://" / "bl://" / "tw://"
        if is_youtube:
            page_url = f"https://www.youtube.com/watch?v={vid}"
            platform_name = "YouTube"
        elif is_bilibili:
            page_url = f"https://www.bilibili.com/video/{vid}"
            platform_name = "B站"
        elif is_twitter:
            if not vid.isdigit():
                raise HTTPException(status_code=400, detail="无效的 Twitter/X 视频 ID")
            page_url = f"https://x.com/i/status/{vid}"
            platform_name = "Twitter/X"
        else:
            # tt://@{username}/{video_id} 或 tt://{video_id}（旧格式）
            if vid.startswith("@"):
                page_url = f"https://www.tiktok.com/{vid}"
            else:
                page_url = f"https://www.tiktok.com/@/video/{vid}"
            platform_name = "TikTok"
        filepath = DOWNLOAD_DIR / f"{storage_title}.mp4"

        if _is_valid_video(filepath):
            return FileResponse(path=str(filepath), filename=f"{display_title}.mp4", media_type="video/mp4")

        if filepath.exists():
            filepath.unlink()

        # TikTok 无可用代理时快速失败，避免 20s 超时等待
        if platform_name == "TikTok" and not get_active_proxy():
            raise HTTPException(
                status_code=500,
                detail="TikTok 下载需要可访问 TikTok 的网络或代理，请配置代理地址后重试"
            )

        def _download_with_ytdlp():
            import yt_dlp

            def _progress_hook(d):
                if cancel_event.is_set():
                    logger.info(f"[下载] {platform_name} progress_hook 感知取消，中止 yt-dlp")
                    raise _DownloadCancelled()

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "outtmpl": str(filepath),
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "merge_output_format": "mp4",
                "nocheckcertificate": True,
                "progress_hooks": [_progress_hook],
                "retries": 3,
                "fragment_retries": 3,
                "extractor_retries": 2,
            }
            proxy = get_active_proxy()
            if proxy:
                ydl_opts["proxy"] = proxy
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([page_url])

        def _cleanup_partial():
            for f in DOWNLOAD_DIR.glob(f"{storage_title}.*"):
                try:
                    f.unlink()
                except OSError:
                    pass

        cancel_event = threading.Event()
        try:
            async with ytdlp_semaphore:
                watcher = asyncio.create_task(_watch_disconnect(request, cancel_event))
                try:
                    # 应用级重试：TikTok 等平台会概率性返回 403 反爬，重试即可成功。
                    # yt-dlp 原生 retries 覆盖不到 extract 阶段的 403，故在此补一层。
                    for attempt in range(3):
                        if cancel_event.is_set():
                            break
                        try:
                            await asyncio.to_thread(_download_with_ytdlp)
                            break
                        except _DownloadCancelled:
                            raise
                        except Exception as e:
                            if cancel_event.is_set():
                                raise
                            _cleanup_partial()  # 清理残留分片再重试
                            msg = str(e)
                            transient = any(k in msg for k in (
                                "403", "Forbidden", "Unable to download webpage",
                                "timed out", "Read timed out", "Connection",
                                "Temporary failure", "EOF", "500", "502", "503",
                            ))
                            if attempt < 2 and transient:
                                logger.warning(
                                    f"[下载] {platform_name} 第{attempt + 1}次失败({msg[:80]})，1.5s 后重试"
                                )
                                # 分片轮询而非固定 sleep，使重试等待期间也能即时响应取消
                                for _ in range(15):
                                    if cancel_event.is_set():
                                        break
                                    await asyncio.sleep(0.1)
                                continue
                            raise
                finally:
                    watcher.cancel()
            # 兜底：若 yt-dlp 吞掉了 hook 抛出的取消异常并正常返回，仍按取消处理
            if cancel_event.is_set():
                _cleanup_partial()
                logger.info(f"[下载] {platform_name} 已被客户端取消: {page_url}")
                raise HTTPException(status_code=499, detail="下载已取消")
            if not filepath.exists():
                for f in DOWNLOAD_DIR.glob(f"{storage_title}.*"):
                    filepath = f
                    break
            if not _is_valid_video(filepath):
                raise HTTPException(status_code=500, detail=f"{platform_name} 下载失败: 下载的文件不是有效视频")
            return FileResponse(path=str(filepath), filename=f"{display_title}.mp4", media_type="video/mp4")
        except _DownloadCancelled:
            _cleanup_partial()
            logger.info(f"[下载] {platform_name} 已被客户端取消: {page_url}")
            raise HTTPException(status_code=499, detail="下载已取消")
        except HTTPException:
            raise
        except Exception as e:
            # yt-dlp 可能把取消异常包装后再抛出，兜底判断
            if cancel_event.is_set():
                _cleanup_partial()
                logger.info(f"[下载] {platform_name} 已被客户端取消: {page_url}")
                raise HTTPException(status_code=499, detail="下载已取消")
            raise HTTPException(status_code=500, detail=f"{platform_name} 下载失败: {str(e)[:200]}")

    # 微信视频号加密视频下载（wx:// 前缀）
    if video_url.startswith("wx://"):
        # 格式: wx://video_url|decrypt_key
        parts = video_url[5:].split("|", 1)
        actual_url = parts[0]
        decrypt_key = parts[1] if len(parts) > 1 else None
        logger.info(f"[下载] 微信视频号: url={actual_url[:100]}..., key={decrypt_key}")

        filepath = DOWNLOAD_DIR / f"{storage_title}.mp4"

        if _is_valid_video(filepath):
            return FileResponse(path=str(filepath), filename=f"{display_title}.mp4", media_type="video/mp4")

        if filepath.exists():
            filepath.unlink()

        cancel_event = threading.Event()
        watcher = asyncio.create_task(_watch_disconnect(request, cancel_event))
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://channels.weixin.qq.com/",
            }
            async with httpx.AsyncClient(timeout=120, verify=False, follow_redirects=True) as client:
                async with client.stream("GET", actual_url, headers=headers) as resp:
                    if resp.status_code != 200:
                        raise HTTPException(status_code=502, detail=f"微信视频下载失败 (HTTP {resp.status_code})")

                    buf = bytearray()
                    async for chunk in resp.aiter_bytes(65536):
                        if cancel_event.is_set():
                            logger.info("[下载] 微信视频号 已被客户端取消")
                            raise HTTPException(status_code=499, detail="下载已取消")
                        buf.extend(chunk)
                    content = bytes(buf)

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

            return FileResponse(path=str(filepath), filename=f"{display_title}.mp4", media_type="video/mp4")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="下载超时")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"微信视频下载失败: {str(e)}")
        finally:
            watcher.cancel()

    filename = f"{display_title}.mp4"
    filepath = DOWNLOAD_DIR / f"{storage_title}.mp4"

    if filepath.exists() and filepath.stat().st_size > 0:
        return FileResponse(path=str(filepath), filename=filename, media_type="video/mp4")

    cancel_event = threading.Event()
    watcher = asyncio.create_task(_watch_disconnect(request, cancel_event))
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": referer,
        }
        async with httpx.AsyncClient(timeout=120, verify=False, follow_redirects=True) as client:
            async with client.stream("GET", video_url, headers=headers) as resp:
                if resp.status_code != 200:
                    raise HTTPException(status_code=502, detail=f"下载失败 (HTTP {resp.status_code})")
                with open(filepath, "wb") as f:
                    async for chunk in resp.aiter_bytes(65536):
                        if cancel_event.is_set():
                            f.close()
                            try:
                                filepath.unlink(missing_ok=True)
                            except OSError:
                                pass
                            logger.info(f"[下载] 已被客户端取消: {video_url[:100]}")
                            raise HTTPException(status_code=499, detail="下载已取消")
                        f.write(chunk)

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
    finally:
        watcher.cancel()


# ─── Cookie 管理 ──────────────────────────────────────

class ParseHtmlRequest(BaseModel):
    url: str
    html: str


@router.post("/api/parse-html")
async def parse_html_endpoint(req: ParseHtmlRequest, request: Request):
    """解析前端通过 CORS 代理获取的页面 HTML（用于服务端无法直连的平台）"""
    from parsers.tiktok import parse_html as tiktok_parse_html

    ip = _get_client_ip(request)
    html_len = len(req.html)
    logger.info(f"[解析-HTML] 收到前端中继 HTML ({html_len} bytes): {req.url[:80]}...")

    result = tiktok_parse_html(req.html, req.url)
    if result["success"] and result["data"]:
        logger.info(f"[解析-HTML] 中继解析成功: {result['data'].get('title', '')[:50]}")
        _add_to_history(result["data"], ip)
    else:
        logger.warning(f"[解析-HTML] 中继解析失败: {result.get('message', '')} (HTML {html_len} bytes)")
    return result


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


# ─── 代理配置 ──────────────────────────────────────

class ProxyConfigRequest(BaseModel):
    proxy: str


@router.post("/api/proxy-config")
async def set_proxy_config(req: ProxyConfigRequest):
    """设置客户端代理地址（热更新，无需重启服务）"""
    from config import set_client_proxy, get_active_proxy
    proxy = req.proxy.strip()
    if proxy and not proxy.startswith(("http://", "https://", "socks5://", "socks4://")):
        raise HTTPException(status_code=400, detail="代理格式无效，请使用 http://ip:port 或 socks5://ip:port")
    set_client_proxy(proxy)
    active = get_active_proxy()
    logger.info(f"[代理] 已更新: {proxy or '（清除）'}, 当前有效: {active or '（无）'}")
    return {"success": True, "proxy": proxy}


async def _test_client_proxy(proxy: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=4, verify=False, proxies=proxy) as client:
            resp = await client.get(
                "https://www.tiktok.com/oembed",
                params={"url": "https://www.tiktok.com/@tiktok/video/7106594312292453678"},
                headers={"User-Agent": "Mozilla/5.0"},
            )
        return resp.status_code in (200, 400, 404)
    except Exception:
        return False


@router.post("/api/proxy-config/auto-detect")
async def auto_detect_proxy_config(request: Request):
    """根据访问者 IP 探测常见代理端口并自动配置。"""
    from config import set_client_proxy, get_active_proxy

    client_ip = request.client.host if request.client else ""
    try:
        ip_obj = ipaddress.ip_address(client_ip)
    except Exception as e:
        logger.warning(f"[代理] IP 解析失败: {client_ip}, 错误: {e}")
        return {"success": False, "message": "无法识别客户端 IP", "client_ip": client_ip}

    # 处理 IPv6 映射的 IPv4 地址 (::ffff:a.b.c.d)
    check_ip = ip_obj
    if hasattr(ip_obj, 'ipv4_mapped') and ip_obj.ipv4_mapped:
        check_ip = ip_obj.ipv4_mapped
        logger.debug(f"[代理] 检测到 IPv6 映射地址，转换为 IPv4: {client_ip} -> {check_ip}")

    if not (check_ip.is_private or check_ip.is_loopback):
        return {"success": False, "message": "仅支持局域网或本机客户端自动检测", "client_ip": client_ip}

    ports = [7890, 7897, 7891, 7892, 7893, 7899, 10809, 10808, 1080, 1081, 8080, 3128, 8888, 1088]
    try:
        for port in ports:
            proxy = f"http://{check_ip}:{port}"
            if await _test_client_proxy(proxy):
                set_client_proxy(proxy)
                active = get_active_proxy()
                logger.info(f"[代理] 自动检测成功: {proxy}")
                return {"success": True, "proxy": proxy, "active": active, "client_ip": client_ip}
    except Exception as e:
        logger.error(f"[代理] 端口扫描过程出错: {e}", exc_info=True)
        return {"success": False, "message": f"代理检测过程出错: {str(e)}", "client_ip": client_ip}

    return {"success": False, "message": "未检测到可用客户端代理，请确认代理软件已开启局域网连接", "client_ip": client_ip}


@router.get("/api/logs/recent")
async def recent_logs(lines: int = Query(200, ge=1, le=1000)):
    """临时查看最近后端日志，便于局域网设备测试排查。"""
    from config import BASE_DIR
    log_file = BASE_DIR / "app.log"
    if not log_file.exists():
        return {"success": True, "lines": []}
    text = log_file.read_text(encoding="utf-8", errors="replace")
    return {"success": True, "lines": text.splitlines()[-lines:]}


@router.get("/api/proxy-config")
async def get_proxy_config():
    """查看当前代理配置状态"""
    from config import get_active_proxy, HTTP_PROXY, _CLIENT_PROXY
    return {
        "client_proxy": _CLIENT_PROXY,
        "auto_detected": bool(HTTP_PROXY),
        "active": get_active_proxy() or "",
    }
