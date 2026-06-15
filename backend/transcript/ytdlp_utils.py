"""yt-dlp 封装函数"""
import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def find_ytdlp() -> Optional[str]:
    """Find yt-dlp executable. Priority: bundled > system PATH."""
    # 1. Check bundled
    project_root = Path(__file__).parent.parent
    bundled = project_root / "component" / "yt-dlp.exe"
    if bundled.exists():
        return str(bundled)

    # 2. System PATH
    path = shutil.which("yt-dlp")
    if path:
        return path

    # 3. Common locations
    common = [
        Path(os.environ.get("PROGRAMFILES", "")) / "yt-dlp" / "yt-dlp.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "yt-dlp" / "yt-dlp.exe",
    ]
    for p in common:
        if p.exists():
            return str(p)

    return None


async def get_video_info(url: str, ytdlp_path: str, cookies_path: Optional[str] = None) -> dict:
    """Get video metadata via yt-dlp --dump-json."""
    cmd = [ytdlp_path, "--dump-json", "--no-download"]
    if cookies_path and Path(cookies_path).exists():
        cmd.extend(["--cookies", cookies_path])
    cmd.append(url)
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError("yt-dlp 获取视频信息超时")
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp error: {stderr.decode(errors='ignore')[:500]}")
    import json
    return json.loads(stdout.decode())


async def download_subtitles(url: str, output_dir: str, ytdlp_path: str, cookies_path: Optional[str] = None) -> Optional[Path]:
    """Download subtitles via yt-dlp. Returns path to found subtitle file, or None."""
    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")
    cmd = [
        ytdlp_path,
        "--write-subs", "--write-auto-subs",
        "--sub-lang", "zh-Hans,zh,en",
        "--skip-download",
        "-o", output_template,
    ]
    if cookies_path and Path(cookies_path).exists():
        cmd.extend(["--cookies", cookies_path])
    cmd.append(url)
    logger.info(f"yt-dlp subtitle cmd: {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError("yt-dlp 下载字幕超时")
    stderr_text = stderr.decode(errors='ignore')
    logger.info(f"yt-dlp subtitle stderr: {stderr_text[:500]}")
    # Don't check returncode - yt-dlp returns non-zero when no subs found
    # Search for subtitle files
    return _find_subtitle_file(Path(output_dir))


def _find_subtitle_file(directory: Path) -> Optional[Path]:
    """Search for subtitle files in priority order."""
    priority = ["zh-Hans", "ai-zh", "zh", "en"]
    files = list(directory.iterdir())

    # Priority by language tag
    for lang in priority:
        for f in files:
            if f.suffix == ".srt" and lang in f.stem:
                return f

    # Any .srt file
    for f in files:
        if f.suffix == ".srt":
            return f

    # .vtt files as last resort
    for f in files:
        if f.suffix == ".vtt":
            return f

    return None


async def download_audio(url: str, output_dir: str, ytdlp_path: str, cookies_path: Optional[str] = None) -> Optional[Path]:
    """Download audio-only via yt-dlp."""
    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")
    cmd = [
        ytdlp_path,
        "-x", "--audio-format", "mp3",
        "--audio-quality", "5",
        "-o", output_template,
    ]
    if cookies_path and Path(cookies_path).exists():
        cmd.extend(["--cookies", cookies_path])
    cmd.append(url)
    logger.info(f"yt-dlp audio cmd: {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError("yt-dlp 下载音频超时")
    if proc.returncode != 0:
        raise RuntimeError(f"音频下载失败: {stderr.decode(errors='ignore')[:500]}")

    # Find the downloaded audio file
    for f in Path(output_dir).iterdir():
        if f.suffix in (".mp3", ".m4a", ".opus", ".wav", ".ogg"):
            return f

    raise RuntimeError("音频下载失败: 未找到输出文件")
