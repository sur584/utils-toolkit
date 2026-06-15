"""ASR 提供商 — 支持 local/cloud 两种模式

local 模式: faster-whisper 本地识别，失败回退到 MiMo
cloud 模式: 使用 transcript-config.json 中配置的云服务商
"""
import logging

from ..settings import load_settings
from ..cloud_config import load_cloud_config

logger = logging.getLogger(__name__)


def get_asr_client(provider: str = "auto"):
    """
    Return an ASR client based on current mode.

    - cloud mode: dispatch to CloudASRClient from transcript-config.json
    - local mode: use faster-whisper, fallback to MiMo
    """
    cloud_cfg = load_cloud_config()

    if cloud_cfg.mode == "cloud" and cloud_cfg.default_provider:
        # Cloud mode: use config.json providers
        from ..cloud_asr import get_cloud_client
        logger.info("ASR mode: cloud (provider=%s)", cloud_cfg.default_provider)
        return get_cloud_client(provider if provider != "auto" else "")

    # Local mode: faster-whisper with MiMo fallback
    return _get_local_asr(provider)


def _get_local_asr(provider: str = "auto"):
    """Local ASR with MiMo fallback."""
    from .local_whisper import LocalWhisperASR, is_local_whisper_available

    settings = load_settings()

    if provider == "auto":
        if is_local_whisper_available():
            logger.info("ASR auto-select: local Whisper (model=%s, device=%s)",
                        settings.local_asr_model_path, settings.local_asr_device)
            return LocalWhisperASR(
                model_path=settings.local_asr_model_path,
                device=settings.local_asr_device,
                compute_type=settings.local_asr_compute_type,
            )

        if settings.siliconflow_api_key:
            from .siliconflow import SiliconFlowASR
            logger.info("ASR auto-select: MiMo (model=mimo-v2.5-asr)")
            return SiliconFlowASR(api_key=settings.siliconflow_api_key)

        raise RuntimeError(
            "No ASR provider available. Install faster-whisper for local ASR, "
            "or configure a provider in transcript-config.json."
        )

    if provider == "local":
        if not is_local_whisper_available():
            raise RuntimeError(
                "Local Whisper ASR is not available. "
                "Install faster-whisper (pip install faster-whisper) and "
                "ensure a CUDA-capable GPU is present."
            )
        return LocalWhisperASR(
            model_path=settings.local_asr_model_path,
            device=settings.local_asr_device,
            compute_type=settings.local_asr_compute_type,
        )

    if provider == "mimo":
        from .siliconflow import SiliconFlowASR
        if not settings.siliconflow_api_key:
            raise RuntimeError("MiMo API key is not configured (SILICONFLOW_API_KEY).")
        return SiliconFlowASR(api_key=settings.siliconflow_api_key)

    raise RuntimeError(f"Unknown ASR provider: {provider!r}")
