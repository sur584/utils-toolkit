"""
Centralized configuration management for transcript module.

Loads settings from .env file and provides sensible defaults.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# This module's directory (backend/transcript/)
_MODULE_DIR: Path = Path(__file__).resolve().parent

# Project root is three levels above this file (backend/transcript/settings.py)
PROJECT_ROOT: Path = _MODULE_DIR.parent.parent

# Load transcript .env (if any)
_env_file = _MODULE_DIR / ".env"
if _env_file.exists():
    load_dotenv(_env_file)

# Model name to local path mapping
_MODEL_NAMES = {
    "tiny": "models--Systran--faster-whisper-tiny",
    "base": "models--Systran--faster-whisper-base",
    "small": "models--Systran--faster-whisper-small",
}
_MODEL_SNAPSHOTS = {
    "tiny": "latest",
    "base": "latest",
    "small": "1e6de4e4c7",
}
_DEFAULT_MODEL = "small"


def _resolve_model_path(model_name: str) -> Path:
    """Resolve model path within utils-toolkit project."""
    name = _MODEL_NAMES.get(model_name, _MODEL_NAMES[_DEFAULT_MODEL])
    snap = _MODEL_SNAPSHOTS.get(model_name, _MODEL_SNAPSHOTS[_DEFAULT_MODEL])
    path = PROJECT_ROOT / "models" / "hub" / name / "snapshots" / snap
    return path


@dataclass
class Settings:
    """Application settings, populated from .env and defaults."""

    # ASR
    asr_provider: str = "auto"
    local_asr_model_path: str = ""
    local_asr_device: str = "cuda"
    local_asr_compute_type: str = "float16"
    siliconflow_api_key: str = ""
    # Server
    host: str = "127.0.0.1"
    port: int = 8867
    # Concurrency
    max_concurrent_jobs: int = 3
    max_concurrent_jobs_local_asr: int = 1


_cached_settings: Settings | None = None


def _load_config_json() -> dict:
    """Read transcript-config.json and extract API key for local-mode fallback."""
    import json
    cfg_path = PROJECT_ROOT / "transcript-config.json"
    if cfg_path.exists():
        try:
            with open(cfg_path, encoding="utf-8") as f:
                data = json.load(f)
            result = {}
            for key, p in data.get("providers", {}).items():
                api_key = p.get("api_key", "").strip()
                if api_key and len(api_key) > 4 and ("mimo" in key.lower() or "siliconflow" in key.lower()):
                    result["siliconflow_api_key"] = api_key
            return result
        except Exception:
            pass
    return {}


def load_settings() -> Settings:
    """Load settings from environment variables and transcript-config.json.

    Returns a cached singleton Settings instance. Subsequent calls return
    the same object without re-reading the file.
    """
    global _cached_settings
    if _cached_settings is not None:
        return _cached_settings

    # Load config for API key fallback
    _cfg = _load_config_json()

    # Resolve model path: LOCAL_ASR_MODEL_PATH (explicit) > LOCAL_ASR_MODEL (name) > default
    local_asr_model_path = os.getenv("LOCAL_ASR_MODEL_PATH", "")
    if not local_asr_model_path:
        model_name = os.getenv("LOCAL_ASR_MODEL", _DEFAULT_MODEL).lower()
        local_asr_model_path = str(_resolve_model_path(model_name))
        logger.info("Using %s model: %s", model_name, local_asr_model_path)

    port_raw = os.getenv("PORT", "8867")

    # API keys: .env first, then config.json providers as fallback
    mimo_key = os.getenv("SILICONFLOW_API_KEY", "") or _cfg.get("siliconflow_api_key", "")

    _cached_settings = Settings(
        # ASR
        asr_provider=os.getenv("ASR_PROVIDER", "auto"),
        local_asr_model_path=local_asr_model_path,
        local_asr_device=os.getenv("LOCAL_ASR_DEVICE", "cuda"),
        local_asr_compute_type=os.getenv("LOCAL_ASR_COMPUTE_TYPE", "float16"),
        siliconflow_api_key=mimo_key,
        # Server
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(port_raw),
        # Concurrency
        max_concurrent_jobs=int(os.getenv("MAX_CONCURRENT_JOBS", "3")),
        max_concurrent_jobs_local_asr=int(
            os.getenv("MAX_CONCURRENT_JOBS_LOCAL_ASR", "1")
        ),
    )

    logger.info(
        "Settings loaded — provider=%s, host=%s:%s",
        _cached_settings.asr_provider,
        _cached_settings.host,
        _cached_settings.port,
    )
    return _cached_settings
