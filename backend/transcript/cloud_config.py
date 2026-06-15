"""Cloud provider configuration — JSON-based config for cloud ASR providers."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class ProviderConfig:
    name: str
    type: str  # "openai-compatible" or "whisper-api"
    api_key: str
    base_url: str
    model: str
    headers: dict = field(default_factory=dict)


@dataclass
class CloudConfig:
    mode: str  # "local" or "cloud"
    default_provider: str
    providers: dict  # str -> ProviderConfig
    cookies_path: str = ""


_config: CloudConfig | None = None
_config_mtime: float = 0.0
_config_path = PROJECT_ROOT / "transcript-config.json"


def _parse_config(raw: dict) -> CloudConfig:
    """Parse and validate raw config dict into CloudConfig."""
    mode = raw.get("mode", "local")
    if mode not in ("local", "cloud"):
        mode = "local"

    default_provider = raw.get("default_provider", "")
    providers_raw = raw.get("providers", {})

    providers: dict[str, ProviderConfig] = {}
    valid_types = {"openai-compatible", "whisper-api"}
    for key, p in providers_raw.items():
        missing = [
            f for f in ("name", "type", "api_key", "base_url", "model")
            if f not in p
        ]
        if missing:
            continue
        if p["type"] not in valid_types:
            continue
        providers[key] = ProviderConfig(
            name=p["name"],
            type=p["type"],
            api_key=p["api_key"],
            base_url=p["base_url"],
            model=p["model"],
            headers=p.get("headers", {}),
        )

    return CloudConfig(
        mode=mode,
        default_provider=default_provider,
        providers=providers,
        cookies_path=raw.get("cookies_path", ""),
    )


def load_cloud_config(force_reload: bool = False) -> CloudConfig:
    """Load config from transcript-config.json with mtime-based auto-reload."""
    global _config, _config_mtime
    if not _config_path.exists():
        # Return default config if file doesn't exist
        return CloudConfig(mode="local", default_provider="", providers={})
    current_mtime = _config_path.stat().st_mtime
    if _config is not None and not force_reload and current_mtime == _config_mtime:
        return _config
    raw = json.loads(_config_path.read_text(encoding="utf-8"))
    _config = _parse_config(raw)
    _config_mtime = current_mtime
    return _config


def save_cloud_config(config: CloudConfig) -> None:
    """Serialize CloudConfig back to transcript-config.json and reload."""
    raw = {
        "mode": config.mode,
        "default_provider": config.default_provider,
        "providers": {},
        "cookies_path": config.cookies_path,
    }
    for key, p in config.providers.items():
        raw["providers"][key] = {
            "name": p.name,
            "type": p.type,
            "api_key": p.api_key,
            "base_url": p.base_url,
            "model": p.model,
            "headers": p.headers,
        }
    _config_path.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    load_cloud_config(force_reload=True)


def mask_key(key: str) -> str:
    """Mask an API key for display purposes."""
    if len(key) <= 8:
        return "***"
    return key[:3] + "***" + key[-3:]
