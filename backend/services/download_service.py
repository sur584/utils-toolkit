"""
下载服务 - 封装三种视频下载策略
从 main.py 中提取，统一 yt-dlp、微信加密视频、直接 HTTP 下载的逻辑。

策略:
1. yt-dlp: 处理 yt:// / tt:// / bl:// 前缀的特殊平台链接
2. WeChat: 处理 wx:// 前缀的微信视频号加密视频（ISAAC 流密码解密）
3. Direct: 直接 HTTP 下载普通视频链接
"""

import asyncio
import logging
from pathlib import Path

import httpx

from config import get_active_proxy

logger = logging.getLogger(__name__)


def is_valid_video(filepath: Path) -> bool:
    """
    检查文件是否为有效视频（而非加密文件、错误页面等）。

    Args:
        filepath: 视频文件路径

    Returns:
        True 如果文件存在、大小合理且包含有效的 MP4 签名
    """
    if not filepath.exists() or filepath.stat().st_size < 10240:
        return False
    with open(filepath, "rb") as f:
        header = f.read(64)
    # 有效 MP4 签名
    if b"ftyp" in header[:20] or b"skip" in header[:20]:
        return True
    if b"ISOM" in header[:12] or b"isom" in header[:12]:
        return True
    # 无效：HTML 错误页面、JSON 错误等
    if header[:5] in (b"<!DOC", b"<html", b"<?xml", b'{"err', b'{\n  "'):
        return False
    return False


def sanitize_filename(title: str, max_length: int = 80) -> str:
    """
    清理文件名，只保留安全字符。

    Args:
        title: 原始文件名

    Returns:
        清理后的文件名，仅包含字母数字、空格、下划线和连字符
    """
    invalid_chars = '<>:"/\\|?*'
    safe = "".join(c for c in title if c not in invalid_chars and ord(c) >= 32)
    safe = " ".join(safe.split()).strip(" ._-")
    return (safe[:max_length].rstrip(" ._-") or "video")


class DownloadService:
    """视频下载服务 - 根据 URL 前缀自动选择下载策略"""

    # yt-dlp 平台配置: (prefix, page_url_template, platform_display_name)
    _YT_DLP_PLATFORMS = {
        "yt://": ("https://www.youtube.com/watch?v={}", "YouTube"),
        "tt://": ("https://www.tiktok.com/@/video/{}", "TikTok"),
        "bl://": ("https://www.bilibili.com/video/{}", "B站"),
    }

    def __init__(self, downloads_dir: str):
        """
        Args:
            downloads_dir: 下载文件保存目录路径
        """
        self.downloads_dir = Path(downloads_dir)
        self.downloads_dir.mkdir(exist_ok=True)

    def detect_strategy(self, video_url: str) -> str:
        """
        根据 URL 前缀判断应使用的下载策略。

        Args:
            video_url: 视频 URL（可能包含协议前缀）

        Returns:
            'ytdlp' | 'wechat' | 'direct'
        """
        if video_url.startswith(("yt://", "tt://", "bl://")):
            return "ytdlp"
        if video_url.startswith("wx://"):
            return "wechat"
        return "direct"

    async def download_ytdlp(self, video_url: str, safe_title: str) -> str:
        """
        通过 yt-dlp 下载视频（YouTube / TikTok / B站）。

        Args:
            video_url: 带前缀的视频 URL（yt://ID / tt://ID / bl://ID）
            safe_title: 安全的文件名（已清理）

        Returns:
            下载后的文件路径字符串

        Raises:
            RuntimeError: 下载失败或文件无效
        """
        # 解析前缀和视频 ID
        platform_key = video_url[:5]  # "yt://" / "tt://" / "bl://"
        vid = video_url[5:]

        url_template, platform_name = self._YT_DLP_PLATFORMS[platform_key]
        # tt:// 支持 @username/video_id 和 video_id 两种格式
        if platform_key == "tt://" and vid.startswith("@"):
            page_url = f"https://www.tiktok.com/{vid}"
        else:
            page_url = url_template.format(vid)
        filepath = self.downloads_dir / f"{safe_title}.mp4"

        # TikTok 无客户端代理时快速失败，避免 20s 超时等待
        if platform_key == "tt://" and not get_active_proxy(client_only=True):
            raise RuntimeError(
                "TikTok 下载需要客户端代理，请在页面配置代理地址后重试"
            )

        # 如果已有有效文件，直接返回
        if is_valid_video(filepath):
            return str(filepath)

        # 清除可能存在的损坏文件
        if filepath.exists():
            filepath.unlink()

        def _download():
            import yt_dlp

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "outtmpl": str(filepath),
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "merge_output_format": "mp4",
                "nocheckcertificate": True,
            }
            if platform_key == "tt://":
                proxy = get_active_proxy(client_only=True)
            else:
                proxy = get_active_proxy()
            if proxy:
                ydl_opts["proxy"] = proxy
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([page_url])

        try:
            await asyncio.to_thread(_download)

            # yt-dlp 可能生成不同扩展名的文件
            if not filepath.exists():
                for f in self.downloads_dir.glob(f"{safe_title}.*"):
                    filepath = f
                    break

            if not is_valid_video(filepath):
                raise RuntimeError(
                    f"{platform_name} 下载失败: 下载的文件不是有效视频"
                )

            return str(filepath)
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"{platform_name} 下载失败: {str(e)[:200]}")

    async def download_wechat(self, video_url: str, safe_title: str) -> str:
        """
        下载并解密微信视频号视频。

        URL 格式: wx://video_url|decrypt_key
        使用 ISAAC 流密码进行解密。

        Args:
            video_url: wx:// 前缀的视频 URL
            safe_title: 安全的文件名

        Returns:
            下载后的文件路径字符串

        Raises:
            RuntimeError: 下载、解密失败或文件无效
        """
        # 解析 wx:// 格式: wx://video_url|decrypt_key
        parts = video_url[5:].split("|", 1)
        actual_url = parts[0]
        decrypt_key = parts[1] if len(parts) > 1 else None
        logger.info(
            f"[下载] 微信视频号: url={actual_url[:100]}..., key={decrypt_key}"
        )

        filepath = self.downloads_dir / f"{safe_title}.mp4"

        # 如果已有有效文件，直接返回
        if is_valid_video(filepath):
            return str(filepath)

        if filepath.exists():
            filepath.unlink()

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://channels.weixin.qq.com/",
            }
            async with httpx.AsyncClient(
                timeout=120, verify=False, follow_redirects=True
            ) as client:
                resp = await client.get(actual_url, headers=headers)
                if resp.status_code != 200:
                    raise RuntimeError(
                        f"微信视频下载失败 (HTTP {resp.status_code})"
                    )

                content = resp.content

                # 如果有解密密钥，使用 ISAAC 流密码解密
                if decrypt_key:
                    try:
                        from decrypt import decrypt_isaac

                        content = decrypt_isaac(content, int(decrypt_key))
                    except Exception as e:
                        logger.warning(f"视频解密失败: {e}")

                filepath.write_bytes(content)

                # 验证解密后的视频文件
                if not is_valid_video(filepath):
                    filepath.unlink()
                    raise RuntimeError(
                        "视频解密后无法播放，可能解密密钥不正确或视频格式不支持"
                    )

            return str(filepath)
        except httpx.TimeoutException:
            raise RuntimeError("下载超时")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"微信视频下载失败: {str(e)}")

    async def download_direct(
        self, video_url: str, safe_title: str, referer: str = None
    ) -> str:
        """
        直接 HTTP 下载视频文件。

        Args:
            video_url: 视频直链 URL
            safe_title: 安全的文件名
            referer: 请求的 Referer 头（默认使用通用 User-Agent）

        Returns:
            下载后的文件路径字符串

        Raises:
            RuntimeError: 下载失败或文件无效
        """
        filename = f"{safe_title}.mp4"
        filepath = self.downloads_dir / filename

        # 如果已有有效文件且大小大于 0，直接返回
        if filepath.exists() and filepath.stat().st_size > 0:
            return str(filepath)

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": referer or "https://www.douyin.com/",
            }
            async with httpx.AsyncClient(
                timeout=120, verify=False, follow_redirects=True
            ) as client:
                resp = await client.get(video_url, headers=headers)
                if resp.status_code != 200:
                    raise RuntimeError(f"下载失败 (HTTP {resp.status_code})")
                filepath.write_bytes(resp.content)

            # 验证下载的视频文件
            if not is_valid_video(filepath):
                filepath.unlink()
                raise RuntimeError(
                    "下载的文件不是有效视频，可能是加密视频或服务端返回了错误页面"
                )

            return str(filepath)
        except httpx.TimeoutException:
            raise RuntimeError("下载超时")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"下载失败: {str(e)}")

    async def download(
        self,
        video_url: str,
        title: str = "video",
        referer: str = "https://www.douyin.com/",
    ) -> tuple:
        """
        统一下载入口 - 自动检测策略并执行下载。

        Args:
            video_url: 视频 URL（支持 yt:// / tt:// / bl:// / wx:// / http(s)://）
            title: 文件标题（用于生成文件名）
            referer: HTTP Referer（仅 direct 策略使用）

        Returns:
            (filepath_str, filename_str, strategy_name)

        Raises:
            RuntimeError: 下载失败
        """
        safe_title = sanitize_filename(title)
        strategy = self.detect_strategy(video_url)

        if strategy == "ytdlp":
            filepath = await self.download_ytdlp(video_url, safe_title)
        elif strategy == "wechat":
            filepath = await self.download_wechat(video_url, safe_title)
        else:
            filepath = await self.download_direct(video_url, safe_title, referer)

        filename = f"{safe_title}.mp4"
        return filepath, filename, strategy
