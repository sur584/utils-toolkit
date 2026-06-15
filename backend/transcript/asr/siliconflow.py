"""MiMo ASR 客户端 - 支持小米 MiMo 平台"""
import base64
import logging
import os

import httpx

from ..cloud_asr import AUDIO_MIME_TYPES

logger = logging.getLogger(__name__)


class SiliconFlowASR:
    """ASR client for audio transcription (OpenAI-compatible API)."""

    DEFAULT_API_URL = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "mimo-v2.5-asr"):
        self.api_key = api_key
        self.model = model
        self.api_url = os.getenv("ASR_API_URL", self.DEFAULT_API_URL)

    async def transcribe(self, audio_bytes: bytes, audio_format: str = "mp3", language: str = "zh") -> str:
        audio_b64 = base64.b64encode(audio_bytes).decode()

        # MiMo 要求 input_audio.data 使用 data URL 格式
        mime = AUDIO_MIME_TYPES.get(audio_format, "audio/mpeg")
        data_url = f"data:{mime};base64,{audio_b64}"

        try:
            return await self._call_api(data_url, audio_format)
        except Exception as e:
            logger.error(f"ASR API 调用失败: {e}")
            raise RuntimeError(f"ASR API 调用失败: {e}")

    async def _call_api(self, data_url: str, audio_format: str) -> str:
        """Call OpenAI-compatible API with data URL audio input."""
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                self.api_url,
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_audio",
                                    "input_audio": {
                                        "data": data_url,
                                        "format": audio_format,
                                    },
                                }
                            ],
                        }
                    ],
                },
            )

            if resp.status_code == 401:
                raise RuntimeError("API Key 无效，请检查配置")

            if resp.status_code == 404:
                raise RuntimeError(f"模型 '{self.model}' 不存在，请检查模型名称")

            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
