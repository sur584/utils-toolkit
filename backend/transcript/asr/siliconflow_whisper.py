"""SiliconFlow Whisper ASR 客户端 - 国内快速语音识别"""
import logging

import httpx

from ..cloud_asr import AUDIO_MIME_TYPES

logger = logging.getLogger(__name__)


class SiliconFlowWhisperASR:
    """ASR client using SiliconFlow Whisper API (OpenAI-compatible)."""

    API_URL = "https://api.siliconflow.cn/v1/audio/transcriptions"

    def __init__(self, api_key: str, model: str = "FunAudioLLM/SenseVoiceSmall"):
        self.api_key = api_key
        self.model = model

    async def transcribe(self, audio_bytes: bytes, audio_format: str = "mp3", language: str = "zh") -> str:
        try:
            return await self._call_api(audio_bytes, audio_format)
        except Exception as e:
            logger.error(f"SiliconFlow ASR 调用失败: {e}")
            raise RuntimeError(f"SiliconFlow ASR 调用失败: {e}")

    async def _call_api(self, audio_bytes: bytes, audio_format: str) -> str:
        mime = AUDIO_MIME_TYPES.get(audio_format, "audio/mpeg")

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                self.API_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                data={
                    "model": self.model,
                    "language": "zh",
                },
                files={
                    "file": (f"audio.{audio_format}", audio_bytes, mime)
                },
            )

            if resp.status_code == 401:
                raise RuntimeError("SiliconFlow API Key 无效，请检查配置")
            if resp.status_code == 404:
                raise RuntimeError(f"模型 '{self.model}' 不存在，请检查模型名称")
            if resp.status_code == 429:
                raise RuntimeError("SiliconFlow API 请求过于频繁，请稍后重试")

            resp.raise_for_status()
            data = resp.json()
            return data.get("text", "")
