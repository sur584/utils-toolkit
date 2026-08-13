"""
Local Whisper ASR client using faster-whisper with CUDA support.

Provides a LocalWhisperASR class that lazily loads a Whisper model
and performs transcription via faster-whisper, with automatic GPU/CPU fallback.
"""

import asyncio
import logging
import os
import sys
import tempfile

logger = logging.getLogger(__name__)


def _setup_nvidia_dll_path():
    """Add NVIDIA CUDA DLL directories to the search path on Windows.

    When nvidia-cublas-cu12 (etc.) are installed via pip, their DLLs live
    inside site-packages/nvidia/*/bin/.  ctranslate2 needs these on the
    DLL search path.  We prepend them to PATH and also pre-load cublas
    via ctypes so ctranslate2 finds it at inference time.
    """
    if sys.platform != "win32":
        return
    try:
        import importlib.util
        spec = importlib.util.find_spec("nvidia")
        if not spec:
            return
        nvidia_pkg = None
        if spec.submodule_search_locations:
            nvidia_pkg = list(spec.submodule_search_locations)[0]
        if not nvidia_pkg or not os.path.isdir(nvidia_pkg):
            return
        bin_dirs = []
        for entry in os.listdir(nvidia_pkg):
            bin_dir = os.path.join(nvidia_pkg, entry, "bin")
            if os.path.isdir(bin_dir):
                bin_dirs.append(bin_dir)
        if bin_dirs:
            os.environ["PATH"] = ";".join(bin_dirs) + ";" + os.environ.get("PATH", "")
            logger.info("Added NVIDIA DLL dirs to PATH: %s", bin_dirs)
            # Pre-load cublas DLL via ctypes so ctranslate2 can find it
            for d in bin_dirs:
                cublas = os.path.join(d, "cublas64_12.dll")
                if os.path.isfile(cublas):
                    try:
                        import ctypes
                        ctypes.CDLL(cublas)
                        logger.info("Pre-loaded cublas DLL: %s", cublas)
                    except Exception as ex:
                        logger.debug("Pre-load cublas failed: %s", ex)
    except Exception as e:
        logger.debug("Could not set up NVIDIA DLL paths: %s", e)


# Run once at import time
_setup_nvidia_dll_path()


def is_local_whisper_available() -> bool:
    """Check if faster-whisper is available (CPU or CUDA)."""
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


class LocalWhisperASR:
    """Local Whisper ASR using faster-whisper with lazy model loading and GPU fallback."""

    def __init__(self, model_path: str, device: str = "cuda", compute_type: str = "float16"):
        self._model_path = model_path
        self._device = device
        self._compute_type = compute_type
        self._model = None
        self._loaded_device = None

    def _load_model(self, force_cpu: bool = False):
        """Lazy-load the Whisper model, falling back to CPU int8 if CUDA fails."""
        from faster_whisper import WhisperModel

        device = "cpu" if force_cpu else self._device
        compute_type = "int8" if force_cpu else self._compute_type

        if device == "cuda":
            try:
                import ctranslate2
                if ctranslate2.get_cuda_device_count() == 0:
                    logger.warning("CUDA requested but no CUDA device found. Falling back to CPU.")
                    device = "cpu"
                    compute_type = "int8"
            except Exception:
                logger.warning("Cannot check CUDA availability. Falling back to CPU.")
                device = "cpu"
                compute_type = "int8"

        logger.info(
            "Loading faster-whisper model from '%s' (device=%s, compute_type=%s)",
            self._model_path, device, compute_type,
        )

        try:
            self._model = WhisperModel(
                self._model_path,
                device=device,
                compute_type=compute_type,
            )
            self._loaded_device = device
            logger.info("faster-whisper model loaded successfully on %s.", device)
        except Exception as e:
            if device == "cuda" and not force_cpu:
                logger.warning("CUDA model load failed (%s), retrying on CPU...", e)
                return self._load_model(force_cpu=True)
            raise RuntimeError(
                f"Failed to load faster-whisper model from '{self._model_path}': {e}"
            ) from e

    async def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str = "mp3",
        language: str = "zh",
    ) -> str:
        """Transcribe audio bytes to plain text (segments joined by spaces)."""
        segments = await self.transcribe_segments(audio_bytes, audio_format, language)
        return " ".join(s["text"] for s in segments if s["text"])

    async def transcribe_segments(
        self,
        audio_bytes: bytes,
        audio_format: str = "mp3",
        language: str = "zh",
    ) -> list[dict]:
        """Transcribe audio bytes to timestamped segments.

        Returns:
            A list of {"start": float, "end": float, "text": str} in seconds.
        """
        if self._model is None:
            self._load_model()

        # Write audio to a temp file — faster-whisper needs a file path.
        # 注意：faster-whisper 的 decode_audio 并不读取 audio_format，而是靠文件扩展名
        # 选择解封装器。当上游把「视频字节」按 .mp3 写入时，PyAV 会用 mp3 解封装器打开，
        # 导致 container.decode(audio=0) 找不到音频流而崩溃
        # (IndexError: tuple index out of range)。因此首轮按传入格式写入，失败时改用
        # 中性扩展名让 PyAV 按内容自动探测容器格式后重试。
        def _write_tmp(suffix: str) -> str:
            fd, path = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            with open(path, "wb") as fh:
                fh.write(audio_bytes)
            return path

        def _do_transcribe(path: str):
            segments, info = self._model.transcribe(
                path,
                language=language,
                vad_filter=True,
                vad_parameters=dict(
                    threshold=0.3,
                    min_speech_duration_ms=250,
                    min_silence_duration_ms=500,
                ),
            )
            result = []
            for segment in segments:
                text = segment.text.strip()
                if text:
                    result.append({
                        "start": float(segment.start),
                        "end": float(segment.end),
                        "text": text,
                    })
            return result, info

        tmp_path = None
        try:
            tmp_path = _write_tmp(f".{audio_format}")
            try:
                segments, info = await asyncio.to_thread(_do_transcribe, tmp_path)
            except Exception as first_err:
                err = str(first_err).lower()
                if any(k in err for k in (
                    "index out of range", "no stream", "invalid data",
                    "moov atom not found", "could not find", "no valid",
                )):
                    # 解码格式不匹配（如把视频字节当音频解包）——改用内容探测重试
                    logger.warning(
                        "音频首轮解码失败(%s)，改用内容自动探测格式重试", first_err
                    )
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                    tmp_path = _write_tmp(".bin")
                    try:
                        segments, info = await asyncio.to_thread(_do_transcribe, tmp_path)
                    except Exception as retry_err:
                        # 即便按内容探测仍无法解出音频流，说明文件本身无音轨/格式无法识别，
                        # 抛出清晰可执行的错误，避免上层收到晦涩的 IndexError。
                        raise RuntimeError(
                            "音频解码失败：文件不包含任何音轨（或格式无法识别），"
                            "无法进行语音识别。该视频可能为纯无声视频或下载到了无音轨变体。"
                        ) from retry_err
                elif self._loaded_device == "cuda" and "cublas" in err:
                    # CUDA 推理失败（缺少 cublas 等）——回退 CPU 重载重试
                    logger.warning("CUDA 推理失败(%s)，在 CPU 上重载模型重试", first_err)
                    self._load_model(force_cpu=True)
                    segments, info = await asyncio.to_thread(_do_transcribe, tmp_path)
                else:
                    raise

            logger.info(
                "Transcription completed: %d segments, detected language=%s",
                len(segments),
                getattr(info, "language", "unknown"),
            )
            return segments
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    logger.warning("Failed to remove temp file: %s", tmp_path)
