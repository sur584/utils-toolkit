"""yt-dlp 封装函数"""
import asyncio
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _proxy_args() -> list[str]:
    """返回 yt-dlp 代理参数。海外平台（TikTok/YouTube 等）在国内需经代理访问。"""
    try:
        from config import get_active_proxy
        proxy = get_active_proxy()
    except Exception:
        proxy = ""
    return ["--proxy", proxy] if proxy else []


def resolve_cookie_cli_args() -> list[str]:
    """根据后端配置（YT_COOKIES_FILE / YT_COOKIES_FROM_BROWSER / Windows 默认 chrome）
    生成 yt-dlp CLI 的 Cookie 参数，规避 YouTube 的 bot 校验。

    返回 [] 表示不加 Cookie（可能触发 "Sign in to confirm you're not a bot"）。
    """
    try:
        from ytdlp_cookies import get_ytdlp_cookie_opts
    except Exception:
        return []
    opts = get_ytdlp_cookie_opts()
    if not opts:
        return []
    if "cookiefile" in opts:
        return ["--cookies", opts["cookiefile"]]
    if "cookiesfrombrowser" in opts:
        browser = opts["cookiesfrombrowser"][0][0]
        return ["--cookies-from-browser", browser]
    return []


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


async def get_video_info(url: str, ytdlp_path: str, cookie_args: Optional[list] = None) -> dict:
    """Get video metadata via yt-dlp --dump-json."""
    cmd = [ytdlp_path, "--dump-json", "--no-download"]
    if cookie_args:
        cmd.extend(cookie_args)
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


async def download_subtitles(url: str, output_dir: str, ytdlp_path: str,
                             cookie_args: Optional[list] = None, lang: str = "") -> Optional[Path]:
    """Download subtitles via yt-dlp. Returns path to found subtitle file, or None.

    lang: 优先下载的字幕语言标签（如 en / zh-Hans / ja）。为空时回退到 zh-Hans,zh,en。
    """
    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")
    # 字幕语言优先级：用户指定的语言排在最前，再回退到中文/英文
    sub_langs = "zh-Hans,zh,en"
    if lang:
        sub_langs = f"{lang},zh-Hans,zh,en"
    cmd = [
        ytdlp_path,
        "--write-subs", "--write-auto-subs",
        "--sub-lang", sub_langs,
        "--skip-download",
        "-o", output_template,
    ]
    if cookie_args:
        cmd.extend(cookie_args)
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
    return _find_subtitle_file(Path(output_dir), preferred=lang)


def _find_subtitle_file(directory: Path, preferred: str = "") -> Optional[Path]:
    """Search for subtitle files in priority order. preferred: 优先语言标签（如 en/zh-Hans/ja）。"""
    priority = []
    if preferred:
        priority.append(preferred)
    priority += ["zh-Hans", "ai-zh", "zh", "en"]
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


async def download_audio(url: str, output_dir: str, ytdlp_path: str, cookie_args: Optional[list] = None) -> Optional[Path]:
    """Download audio-only via yt-dlp."""
    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")
    cmd = [
        ytdlp_path,
        "-x", "--audio-format", "mp3",
        "--audio-quality", "5",
        "-o", output_template,
    ]
    if cookie_args:
        cmd.extend(cookie_args)
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


async def list_subtitles(url: str, ytdlp_path: str, cookies_path: Optional[str] = None) -> dict:
    """运行 yt-dlp --list-subs，解析出可用字幕语言。

    Returns: {"manual": [语言代码...], "auto": [语言代码...]}
    """
    cmd = [ytdlp_path, "--list-subs", "--no-download", "--skip-download"]
    if cookies_path and Path(cookies_path).exists():
        cmd.extend(["--cookies", cookies_path])
    cmd.append(url)
    logger.info(f"yt-dlp list-subs cmd: {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError("yt-dlp 列举字幕超时")
    out = stdout.decode(errors="ignore")
    err = stderr.decode(errors="ignore")
    if proc.returncode != 0 and not out:
        raise RuntimeError(f"yt-dlp 列举字幕失败: {err[:500]}")
    return _parse_subs_list(out)


def _parse_subs_list(text: str) -> dict:
    """解析 yt-dlp --list-subs 的输出，区分人工字幕与自动生成字幕。"""
    result = {"manual": [], "auto": []}
    auto_marker = "Available automatic captions"
    manual_text = text
    auto_text = ""
    auto_start = text.find(auto_marker)
    if auto_start != -1:
        manual_text = text[:auto_start]
        auto_text = text[auto_start:]
    code_re = re.compile(r"^([A-Za-z][A-Za-z-]*)\s+(\S+)", re.MULTILINE)

    def _grab(section: str) -> list:
        codes = []
        for m in code_re.finditer(section):
            code = m.group(1)
            if code.lower() in ("language", "available"):  # 跳过表头行
                continue
            if code not in codes:
                codes.append(code)
        return codes

    result["manual"] = _grab(manual_text)
    result["auto"] = _grab(auto_text)
    return result
