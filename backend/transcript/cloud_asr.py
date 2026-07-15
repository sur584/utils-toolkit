"""Unified cloud ASR client — dispatches to openai-compatible or whisper-api providers."""
import base64
import logging
import time

import httpx

logger = logging.getLogger(__name__)

# Minimal valid WAV: 1 second of silence at 16kHz mono 16-bit
_SILENT_WAV = (
    b"RIFF"          # ChunkID
    b"\x24\x00\x00\x00"  # ChunkSize = 36 + data size
    b"WAVE"          # Format
    b"fmt "          # Subchunk1ID
    b"\x10\x00\x00\x00"  # Subchunk1Size = 16 (PCM)
    b"\x01\x00"      # AudioFormat = 1 (PCM)
    b"\x01\x00"      # NumChannels = 1
    b"\x80\x3e\x00\x00"  # SampleRate = 16000
    b"\x00\x7d\x00\x00"  # ByteRate = 16000 * 1 * 16/8
    b"\x02\x00"      # BlockAlign = 1 * 16/8
    b"\x10\x00"      # BitsPerSample = 16
    b"data"          # Subchunk2ID
    b"\x00\x00\x00\x00"  # Subchunk2Size = 0 (no actual samples)
)

AUDIO_MIME_TYPES = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "flac": "audio/flac",
}


class CloudASRClient:
    """Unified cloud ASR client that dispatches to different provider types."""

    MAX_SIZE = 25 * 1024 * 1024  # 云端 ASR 保守上限

    def __init__(self, provider_config):
        from .cloud_config import ProviderConfig
        assert isinstance(provider_config, ProviderConfig)
        self.config = provider_config
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            timeout = 300.0 if self.config.type == "openai-compatible" else 60.0
            self._client = httpx.AsyncClient(timeout=timeout)
        return self._client

    async def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str = "mp3",
        language: str = "zh",
    ) -> str:
        if self.config.type == "openai-compatible":
            return await self._transcribe_openai_compatible(audio_bytes, audio_format, language)
        elif self.config.type == "whisper-api":
            return await self._transcribe_whisper_api(audio_bytes, audio_format, language)
        else:
            raise ValueError(f"Unknown provider type: {self.config.type}")

    async def test_connection(self) -> tuple[bool, str, float]:
        try:
            start = time.monotonic()
            await self.transcribe(_SILENT_WAV, audio_format="wav", language="zh")
            latency = (time.monotonic() - start) * 1000
            return True, "Provider reachable", round(latency, 1)
        except Exception as exc:
            logger.warning("Test connection failed for %s: %s", self.config.name, exc)
            return False, str(exc), 0.0

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _transcribe_openai_compatible(
        self, audio_bytes: bytes, audio_format: str, language: str,
    ) -> str:
        b64 = base64.b64encode(audio_bytes).decode()

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self.config.headers)

        body = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": b64,
                                "format": audio_format,
                            },
                        }
                    ],
                }
            ],
        }

        client = await self._get_client()
        try:
            resp = await client.post(self.config.base_url, headers=headers, json=body)
        except httpx.TimeoutException:
            raise RuntimeError("请求超时")
        except httpx.ConnectError:
            raise RuntimeError("无法连接到服务器")

        if resp.status_code == 401:
            raise RuntimeError("API Key 无效")
        if resp.status_code == 404:
            raise RuntimeError("模型不存在")
        if resp.status_code == 429:
            raise RuntimeError("请求频率超限，请稍后重试")
        if resp.status_code >= 400:
            snippet = resp.text[:200]
            raise RuntimeError(f"HTTP {resp.status_code}: {snippet}")

        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def _transcribe_whisper_api(
        self, audio_bytes: bytes, audio_format: str, language: str,
    ) -> str:
        mime = AUDIO_MIME_TYPES.get(audio_format, "audio/mpeg")

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
        }
        headers.update(self.config.headers)

        client = await self._get_client()
        try:
            resp = await client.post(
                self.config.base_url,
                headers=headers,
                data={"model": self.config.model, "language": language},
                files={"file": (f"audio.{audio_format}", audio_bytes, mime)},
            )
        except httpx.TimeoutException:
            raise RuntimeError("请求超时")
        except httpx.ConnectError:
            raise RuntimeError("无法连接到服务器")

        if resp.status_code == 401:
            raise RuntimeError("API Key 无效")
        if resp.status_code == 404:
            raise RuntimeError("模型不存在")
        if resp.status_code == 429:
            raise RuntimeError("请求频率超限，请稍后重试")
        if resp.status_code >= 400:
            snippet = resp.text[:200]
            raise RuntimeError(f"HTTP {resp.status_code}: {snippet}")

        try:
            data = resp.json()
            return data.get("text", "")
        except (ValueError, KeyError):
            return resp.text


def get_cloud_client(provider_key: str = "") -> CloudASRClient:
    """Create a CloudASRClient from transcript-config.json."""
    from .cloud_config import load_cloud_config

    config = load_cloud_config()
    key = provider_key or config.default_provider
    if key not in config.providers:
        raise RuntimeError(f"Provider '{key}' not found in transcript-config.json")
    return CloudASRClient(config.providers[key])
