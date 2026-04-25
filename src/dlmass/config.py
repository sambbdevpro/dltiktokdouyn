from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    output_root: Path
    videos_dir: Path
    audio_dir: Path
    metadata_dir: Path
    archive_file: Path
    retries: int
    cookies_from_browser: str | None
    cookies_file: Path | None
    user_agent: str | None
    referer: str | None
    extractor_args: str | None
    douyin_provider_mode: str
    douyin_api_base_url: str
    douyin_api_timeout_sec: int
    douyin_api_token: str | None
    douyin_api_download_prefix: bool
    douyin_api_with_watermark: bool


DEFAULT_CONFIG = {
    "output_root": "output",
    "videos_dir": "output/videos",
    "audio_dir": "output/audio",
    "metadata_dir": "output/metadata",
    "archive_file": "output/download_archive.txt",
    "retries": 2,
    "cookies_from_browser": None,
    "cookies_file": None,
    "user_agent": None,
    "referer": None,
    "extractor_args": None,
    "douyin_provider_mode": "api_with_fallback",
    "douyin_api_base_url": "https://apidl.kycaz.com",
    "douyin_api_timeout_sec": 15,
    "douyin_api_token": None,
    "douyin_api_download_prefix": True,
    "douyin_api_with_watermark": False,
}


def _to_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def load_config(config_path: Path | None) -> AppConfig:
    data = dict(DEFAULT_CONFIG)
    if config_path and config_path.exists():
        user_cfg = json.loads(config_path.read_text(encoding="utf-8"))
        data.update(user_cfg)

    output_root = Path(data["output_root"])
    videos_dir = Path(data["videos_dir"])
    audio_dir = Path(data["audio_dir"])
    metadata_dir = Path(data["metadata_dir"])
    archive_file = Path(data["archive_file"])

    cookies_file_raw = _to_optional_str(data.get("cookies_file"))
    cookies_file = Path(cookies_file_raw) if cookies_file_raw else None

    mode = _to_optional_str(data.get("douyin_provider_mode")) or "api_with_fallback"
    if mode not in {"yt_dlp", "api", "api_with_fallback"}:
        mode = "api_with_fallback"

    return AppConfig(
        output_root=output_root,
        videos_dir=videos_dir,
        audio_dir=audio_dir,
        metadata_dir=metadata_dir,
        archive_file=archive_file,
        retries=int(data["retries"]),
        cookies_from_browser=_to_optional_str(data.get("cookies_from_browser")),
        cookies_file=cookies_file,
        user_agent=_to_optional_str(data.get("user_agent")),
        referer=_to_optional_str(data.get("referer")),
        extractor_args=_to_optional_str(data.get("extractor_args")),
        douyin_provider_mode=mode,
        douyin_api_base_url=_to_optional_str(data.get("douyin_api_base_url")) or "https://apidl.kycaz.com",
        douyin_api_timeout_sec=int(data.get("douyin_api_timeout_sec", 15)),
        douyin_api_token=_to_optional_str(data.get("douyin_api_token")),
        douyin_api_download_prefix=_to_bool(data.get("douyin_api_download_prefix"), True),
        douyin_api_with_watermark=_to_bool(data.get("douyin_api_with_watermark"), False),
    )
