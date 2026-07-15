"""核心文案提取流水线"""
import asyncio
import html
import logging
import re
import shutil
from pathlib import Path
from typing import Callable, Optional

from opencc import OpenCC

from .settings import load_settings
from .ytdlp_utils import find_ytdlp, get_video_info, download_subtitles, download_audio
from .platforms import detect_platform
from .platforms.douyin import resolve_url as resolve_douyin_url, fetch_video_info, download_video_audio
from .asr import get_asr_client
from .temp_manager import temp_workspace
from .cache.store import get as cache_get, put as cache_put, cleanup as cache_cleanup

logger = logging.getLogger(__name__)

_cc = OpenCC('t2s')


def _to_simplified(text: str) -> str:
    """繁体中文转简体中文"""
    return _cc.convert(text)


async def extract_transcript(
    url: str,
    method: str = "auto",
    asr_model: str = "auto",
    language: str = "zh",
    api_key: str = "",
    progress_callback: Optional[Callable] = None,
) -> dict:
    """
    Main extraction pipeline.
    Returns: {"method_used": str, "transcript": str, "title": str, "platform": str, ...}
    """
    async def progress(step: str, pct: int, msg: str):
        if progress_callback:
            await progress_callback(step, pct, msg)

    # Load centralized settings
    settings = load_settings()

    # Step 1: Platform detection and URL normalization
    await progress("parsing", 10, "正在解析链接...")
    platform = detect_platform(url)

    # Resolve redirect URLs (e.g. Douyin share links) before cache lookup
    if platform == "douyin":
        url = await resolve_douyin_url(url)

    # Check cache first (after URL resolution so keys match)
    cached = cache_get(url)
    if cached:
        logger.info("Cache hit for URL: %s", url[:80])
        return cached

    # Cleanup expired entries
    cache_cleanup()

    if platform == "douyin":
        # 抖音：直接抓取，不需要 yt-dlp 和 cookies
        result = await _extract_douyin(url, method, language, settings, progress)
        cache_put(url, result)
        return result

    if platform == "wechat_channels":
        # 微信视频号：复用视频下载功能的解析器拿直链，再走 ASR（yt-dlp 不支持）
        result = await _extract_wechat(url, method, language, settings, progress)
        cache_put(url, result)
        return result

    # 其他平台：使用 yt-dlp
    result = await _extract_ytdlp(url, platform, method, language, settings, progress)
    cache_put(url, result)
    return result


async def _extract_douyin(url: str, method: str, language: str, settings, progress_cb) -> dict:
    """抖音专用提取流程 - 直接抓取，不需要 cookies"""
    async def progress(step, pct, msg):
        if progress_cb:
            await progress_cb(step, pct, msg)

    # 获取视频信息
    await progress("parsing", 15, "正在解析抖音链接...")
    info = await fetch_video_info(url)
    title = info["title"][:100]
    author = info["author"]
    video_url = info["video_url"]

    logger.info(f"抖音视频: {title} by {author}, video_url={video_url[:80]}...")

    # 抖音通常没有平台字幕，直接进入 ASR 流程
    transcript = None
    segments = None
    method_used = "subtitle"

    # 尝试字幕（抖音一般没有，但保留兼容性）
    # 跳过，直接进入 ASR

    # ASR 流程
    if not transcript and method in ("auto", "asr_only"):
        await progress("asr", 30, "正在下载视频...")
        async with temp_workspace() as tmp:
            # 下载视频
            video_path = await download_video_audio(video_url, str(tmp / "video"))

            await progress("asr", 55, "正在提取音频...")

            # 用 ffmpeg 提取音频（如果有）
            audio_path = await _extract_audio(video_path, str(tmp / "audio"))

            await progress("asr", 65, "正在上传音频...")

            audio_bytes = Path(audio_path).read_bytes()
            _limit = _asr_size_limit(settings)
            if _limit is not None and len(audio_bytes) > _limit:
                raise RuntimeError(f"音频文件过大 ({len(audio_bytes) // 1024 // 1024}MB)，超过当前引擎 {_limit // 1024 // 1024}MB 限制")

            await progress("asr", 70, "正在进行语音识别...")
            transcript, segments = await _transcribe_with_fallback(audio_bytes, language, settings, progress_cb)
            method_used = "asr"

    if not transcript:
        raise RuntimeError("未能提取到文案内容")

    transcript = _to_simplified(transcript)
    segments = _finalize_segments(segments, transcript, info.get("duration", 0))
    await progress("done", 100, "提取完成")

    return {
        "method_used": method_used,
        "transcript": transcript,
        "srt": segments_to_srt(segments),
        "title": title,
        "platform": "douyin",
        "author": author,
        "cover": info.get("cover", ""),
        "video_url": info.get("video_url", ""),
        "duration": info.get("duration", 0),
        "char_count": len(transcript),
    }


async def _extract_wechat(url: str, method: str, language: str, settings, progress_cb) -> dict:
    """微信视频号提取流程 - 复用视频下载解析器拿直链，无平台字幕，直接 ASR"""
    async def progress(step, pct, msg):
        if progress_cb:
            await progress_cb(step, pct, msg)

    # 复用「视频下载」功能已有的视频号解析器（带缓存/重试/多方案兜底）
    await progress("parsing", 15, "正在解析视频号链接...")
    from parsers import parse_link

    parsed = await parse_link(url)
    if not parsed.get("success"):
        raise RuntimeError(parsed.get("message") or "视频号解析失败")

    data = parsed.get("data") or {}
    video_url = data.get("video_url", "")
    if not video_url:
        raise RuntimeError("视频号解析未获取到视频直链，请在「视频下载」页配置 Yuanbao cookie 后重试")

    title = (data.get("title") or "微信视频号")[:100]
    author = data.get("author", "未知作者")

    logger.info(f"视频号: {title} by {author}, video_url={video_url[:80]}...")

    if method == "subtitle_only":
        raise RuntimeError("视频号暂无平台字幕，请使用自动或语音识别模式")

    transcript = None
    segments = None
    method_used = "asr"

    if method in ("auto", "asr_only"):
        await progress("asr", 30, "正在下载视频...")
        async with temp_workspace() as tmp:
            # 复用下载服务（自动选策略 + MP4 有效性校验）
            from services.download_service import DownloadService

            svc = DownloadService(str(tmp))
            video_path, _, _ = await svc.download(
                video_url, title=title, referer="https://channels.weixin.qq.com/"
            )

            await progress("asr", 55, "正在提取音频...")
            audio_path = await _extract_audio(video_path, str(tmp / "audio"))

            await progress("asr", 65, "正在上传音频...")
            audio_bytes = Path(audio_path).read_bytes()
            _limit = _asr_size_limit(settings)
            if _limit is not None and len(audio_bytes) > _limit:
                raise RuntimeError(f"音频文件过大 ({len(audio_bytes) // 1024 // 1024}MB)，超过当前引擎 {_limit // 1024 // 1024}MB 限制")

            await progress("asr", 70, "正在进行语音识别...")
            transcript, segments = await _transcribe_with_fallback(audio_bytes, language, settings, progress_cb)

    if not transcript:
        raise RuntimeError("未能提取到文案内容")

    transcript = _to_simplified(transcript)
    segments = _finalize_segments(segments, transcript, data.get("duration", 0))
    await progress("done", 100, "提取完成")

    return {
        "method_used": method_used,
        "transcript": transcript,
        "srt": segments_to_srt(segments),
        "title": title,
        "platform": "wechat_channels",
        "author": author,
        "cover": data.get("cover", ""),
        "video_url": video_url,
        "duration": data.get("duration", 0),
        "char_count": len(transcript),
    }


async def _extract_audio(video_path: str, output_prefix: str) -> str:
    """从视频中提取音频。输出 MP3 格式（体积小 4x，上传更快）。"""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        audio_path = output_prefix + ".mp3"
        cmd = [
            ffmpeg, "-i", video_path,
            "-vn", "-ar", "16000", "-ac", "1",
            "-f", "mp3", "-b:a", "64k", "-threads", "0",
            "-y", audio_path
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        if proc.returncode == 0 and Path(audio_path).exists():
            return audio_path
        logger.warning("ffmpeg MP3 提取失败，尝试 WAV 格式")
        audio_path = output_prefix + ".wav"
        cmd = [
            ffmpeg, "-i", video_path,
            "-vn", "-ar", "16000", "-ac", "1",
            "-y", audio_path
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        if proc.returncode == 0 and Path(audio_path).exists():
            return audio_path
        logger.warning("ffmpeg 提取音频失败，将直接使用视频文件")

    return video_path


def _finalize_segments(segments: Optional[list[dict]], transcript: str, duration: float) -> list[dict]:
    """统一收尾：真实 segments 转简体；无真实 segments 时按文本+时长合成近似时间轴。"""
    if segments:
        return [{**s, "text": _to_simplified(s["text"])} for s in segments]
    return synthesize_segments(transcript, duration)


async def _transcribe_client(client, audio_bytes, language):
    """调用单个 ASR 客户端，优先取带时间戳的 segments。

    Returns: (text, segments | None)。仅本地 Whisper 提供 transcribe_segments，
    其余（MiMo/云端 chat-completion）只返回纯文本，segments 为 None。
    """
    if hasattr(client, "transcribe_segments"):
        segments = await client.transcribe_segments(audio_bytes, audio_format="mp3", language=language)
        text = " ".join(s["text"] for s in segments if s["text"])
        return text, segments
    text = await client.transcribe(audio_bytes, audio_format="mp3", language=language)
    return text, None


async def _transcribe_with_fallback(audio_bytes, language, settings, progress_cb):
    """ASR 识别，失败时自动回退到 MiMo。

    Returns: (text, segments | None)。
    """
    from .asr import get_asr_client
    client = get_asr_client(settings.asr_provider)
    try:
        return await _transcribe_client(client, audio_bytes, language)
    except RuntimeError as e:
        if settings.asr_provider != "mimo":
            logger.warning(f"ASR {settings.asr_provider} 失败: {e}，回退到 MiMo")
            if progress_cb:
                await progress_cb("asr", 72, "主引擎失败，切换备选引擎...")
            fallback_client = get_asr_client("mimo")
            return await _transcribe_client(fallback_client, audio_bytes, language)
        raise


_FALLBACK_SIZE_LIMIT = 25 * 1024 * 1024  # 无法确定引擎时的保守上限


def _asr_size_limit(settings) -> Optional[int]:
    """当前 ASR 引擎的音频大小上限（字节）；None 表示无限制（本地 Whisper）。"""
    try:
        from .asr import get_asr_client
        client = get_asr_client(settings.asr_provider)
        return getattr(client, "MAX_SIZE", None)
    except Exception:
        return _FALLBACK_SIZE_LIMIT


async def _compress_audio_adaptive(
    src_path: str, output_prefix: str,
    size_limit: Optional[int] = None, progress_cb=None,
) -> str:
    """转 16kHz 单声道 mp3；有上限时自适应降码率直到不超过上限。"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return src_path

    audio_path = output_prefix + ".mp3"

    async def _run(bitrate: int) -> bool:
        cmd = [
            ffmpeg, "-i", src_path,
            "-vn", "-ar", "16000", "-ac", "1",
            "-f", "mp3", "-b:a", f"{bitrate}k", "-threads", "0",
            "-y", audio_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=300)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return False
        return proc.returncode == 0 and Path(audio_path).exists()

    if size_limit is None:
        if await _run(48):
            return audio_path
        return src_path

    for bitrate in (48, 32, 24, 16, 12):
        if not await _run(bitrate):
            continue
        if Path(audio_path).stat().st_size <= size_limit:
            return audio_path
    return audio_path if Path(audio_path).exists() else src_path


async def extract_transcript_from_file(
    file_path: str, filename: str,
    language: str = "zh", progress_callback: Optional[Callable] = None,
) -> dict:
    """本地上传文件提取流程：转码压缩 → 大小校验 → ASR → 转简体。"""
    async def progress(step, pct, msg):
        if progress_callback:
            await progress_callback(step, pct, msg)

    settings = load_settings()
    title = Path(filename).stem[:100] or "本地文件"
    size_limit = _asr_size_limit(settings)

    await progress("upload", 15, "文件已接收...")
    async with temp_workspace() as tmp:
        await progress("transcode", 30, "正在转码压缩音频...")
        audio_path = await _compress_audio_adaptive(
            file_path, str(tmp / "audio"), size_limit, progress_callback
        )

        audio_bytes = Path(audio_path).read_bytes()
        if size_limit is not None and len(audio_bytes) > size_limit:
            raise RuntimeError(
                f"音频文件过大 ({len(audio_bytes) // 1024 // 1024}MB)，"
                f"超过当前引擎 {size_limit // 1024 // 1024}MB 限制"
            )

        await progress("asr", 70, "正在进行语音识别...")
        transcript, segments = await _transcribe_with_fallback(
            audio_bytes, language, settings, progress_callback
        )

    if not transcript:
        raise RuntimeError("未能提取到文案内容")

    transcript = _to_simplified(transcript)
    segments = _finalize_segments(segments, transcript, 0)
    await progress("done", 100, "提取完成")

    return {
        "method_used": "asr",
        "transcript": transcript,
        "srt": segments_to_srt(segments),
        "title": title,
        "platform": "local",
        "author": "本地文件",
        "cover": "",
        "video_url": "",
        "duration": 0,
        "char_count": len(transcript),
    }


async def _extract_ytdlp(url: str, platform: Optional[str], method: str,
                         language: str, settings, progress_cb) -> dict:
    """其他平台的 yt-dlp 提取流程"""
    async def progress(step, pct, msg):
        if progress_cb:
            await progress_cb(step, pct, msg)

    ytdlp = find_ytdlp()
    if not ytdlp:
        raise RuntimeError("未找到 yt-dlp，请将其放置在 component/ 目录下或添加到系统 PATH")

    # Step 2: 获取视频信息
    await progress("parsing", 15, "正在获取视频信息...")
    title = "未知标题"
    author = "未知作者"
    info = {}
    try:
        info = await get_video_info(url, ytdlp)
        title = info.get("title", "未知标题")[:100]
        author = info.get("uploader", "未知作者")
    except Exception as e:
        logger.warning(f"获取视频信息失败: {e}")

    # Step 3: 尝试字幕提取
    transcript = None
    segments = None
    method_used = "subtitle"

    if method in ("auto", "subtitle_only"):
        await progress("subtitles", 25, "正在尝试获取平台字幕...")
        async with temp_workspace() as tmp:
            try:
                sub_file = await download_subtitles(url, str(tmp), ytdlp)
                if sub_file:
                    await progress("subtitles", 40, "正在解析字幕文件...")
                    content = sub_file.read_text(encoding="utf-8-sig")
                    if sub_file.suffix == ".srt":
                        segments = parse_srt_segments(content)
                    elif sub_file.suffix == ".vtt":
                        segments = parse_vtt_segments(content)
                    if segments:
                        transcript = segments_to_text(segments)
            except Exception as e:
                logger.warning(f"字幕提取失败: {e}")

    # Step 4: ASR 兜底
    if not transcript and method in ("auto", "asr_only"):
        await progress("asr", 55, "正在下载音频...")
        async with temp_workspace() as tmp:
            audio_file = await download_audio(url, str(tmp), ytdlp)
            await progress("asr", 65, "正在上传音频...")

            audio_bytes = audio_file.read_bytes()
            _limit = _asr_size_limit(settings)
            if _limit is not None and len(audio_bytes) > _limit:
                raise RuntimeError(f"音频文件过大 ({len(audio_bytes) // 1024 // 1024}MB)，超过当前引擎 {_limit // 1024 // 1024}MB 限制")

            await progress("asr", 70, "正在进行语音识别...")
            transcript, segments = await _transcribe_with_fallback(audio_bytes, language, settings, progress_cb)
            method_used = "asr"

    if not transcript:
        raise RuntimeError("未能提取到文案内容")

    transcript = _to_simplified(transcript)
    segments = _finalize_segments(segments, transcript, info.get("duration", 0))
    await progress("done", 100, "提取完成")

    return {
        "method_used": method_used,
        "transcript": transcript,
        "srt": segments_to_srt(segments),
        "title": title,
        "platform": platform or "unknown",
        "author": author,
        "cover": info.get("thumbnail", ""),
        "video_url": info.get("webpage_url", ""),
        "duration": info.get("duration", 0),
        "char_count": len(transcript),
    }


def _srt_time_to_seconds(ts: str) -> float:
    """将 SRT/VTT 时间戳 (HH:MM:SS,mmm 或 HH:MM:SS.mmm) 转为秒。"""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
        elif len(parts) == 2:
            h, m, s = "0", parts[0], parts[1]
        else:
            return 0.0
        return int(h) * 3600 + int(m) * 60 + float(s)
    except ValueError:
        return 0.0


def _clean_line(line: str) -> str:
    """去除字幕行内的标签、HTML 实体并规整空白。"""
    line = re.sub(r"<[^>]+>", "", line)
    line = html.unescape(line)
    return re.sub(r"\s+", " ", line).strip()


_TIME_RANGE_RE = re.compile(
    r"(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*"
    r"(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}[.,]\d{1,3})"
)


def parse_srt_segments(content: str) -> list[dict]:
    """解析 SRT，保留时间轴，返回 [{start, end, text}]。"""
    content = content.lstrip("﻿")
    segments = []
    for block in re.split(r"\n\s*\n", content.strip()):
        block_lines = block.strip().split("\n")
        if len(block_lines) < 2:
            continue
        m = None
        text_start = 0
        for idx, bl in enumerate(block_lines[:2]):
            m = _TIME_RANGE_RE.search(bl)
            if m:
                text_start = idx + 1
                break
        if not m:
            continue
        text = _clean_line(" ".join(block_lines[text_start:]))
        if not text:
            continue
        if segments and segments[-1]["text"] == text:
            continue
        segments.append({
            "start": _srt_time_to_seconds(m.group(1)),
            "end": _srt_time_to_seconds(m.group(2)),
            "text": text,
        })
    return segments


def parse_vtt_segments(content: str) -> list[dict]:
    """解析 WebVTT，保留时间轴，返回 [{start, end, text}]。"""
    content = content.lstrip("﻿")
    content = re.sub(r"^WEBVTT.*?\n\n", "", content, flags=re.DOTALL)
    segments = []
    for block in re.split(r"\n\s*\n", content.strip()):
        block_lines = block.strip().split("\n")
        m = None
        text_lines = []
        for bl in block_lines:
            if m is None:
                # 时间轴之前的行（cue 序号 / cue 标识符）一律忽略
                m = _TIME_RANGE_RE.search(bl)
                continue
            text_lines.append(bl)
        if not m:
            continue
        text = _clean_line(" ".join(text_lines))
        if not text:
            continue
        if segments and segments[-1]["text"] == text:
            continue
        segments.append({
            "start": _srt_time_to_seconds(m.group(1)),
            "end": _srt_time_to_seconds(m.group(2)),
            "text": text,
        })
    return segments


def segments_to_text(segments: list[dict]) -> str:
    """把 segments 拼成纯文本（空格分隔）。"""
    return " ".join(s["text"] for s in segments if s.get("text"))


# 中文口语约 5 字/秒，用于无时长信息时估算时间轴
_CHARS_PER_SECOND = 5.0


def synthesize_segments(text: str, duration: float) -> list[dict]:
    """无真实时间戳时，按标点切句、按字符占比在 [0, duration] 上分配，合成近似时间轴。"""
    text = (text or "").strip()
    if not text:
        return []

    # 按句末标点切分，保留标点
    pieces = re.split(r"(?<=[。！？；.!?;\n])", text)
    chunks = [p.strip() for p in pieces if p.strip()]
    if not chunks:
        chunks = [text]

    total_chars = sum(len(c) for c in chunks)
    if not duration or duration <= 0:
        duration = max(total_chars / _CHARS_PER_SECOND, 1.0)

    segments = []
    cursor = 0.0
    for chunk in chunks:
        span = duration * (len(chunk) / total_chars) if total_chars else duration
        start = cursor
        end = min(cursor + span, duration)
        segments.append({"start": start, "end": end, "text": chunk})
        cursor = end
    if segments:
        segments[-1]["end"] = duration
    return segments


def _format_srt_time(seconds: float) -> str:
    """秒 -> SRT 时间戳 HH:MM:SS,mmm。"""
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def segments_to_srt(segments: list[dict]) -> str:
    """把 segments 格式化为标准 SRT 文本。"""
    blocks = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        idx = len(blocks) + 1
        blocks.append(
            f"{idx}\n{_format_srt_time(seg['start'])} --> {_format_srt_time(seg['end'])}\n{text}"
        )
    return "\n\n".join(blocks)
