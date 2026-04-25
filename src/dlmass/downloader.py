from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import AppConfig
from .douyin_api import DouyinApiError, build_metadata, download_video_bytes
from .parsers import parse_url


def _run(cmd: list[str]) -> list[str]:
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        detail = stderr or stdout or str(exc)
        raise RuntimeError(detail) from exc

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    existing = [line for line in lines if Path(line).exists()]
    return existing


def _normalize_download_url(url: str) -> str:
    parsed = parse_url(url)
    if parsed.platform != "douyin":
        return url

    parsed_url = urlparse(url)
    qs = parse_qs(parsed_url.query)
    modal_id = (qs.get("modal_id") or [""])[0].strip()
    if modal_id:
        return f"https://www.douyin.com/video/{modal_id}"
    return url


def _is_cookie_db_copy_error(text: str) -> bool:
    lowered = text.lower()
    return "could not copy" in lowered and "cookie" in lowered and "database" in lowered


def _build_yt_dlp_cmd(config: AppConfig, platform: str, include_browser_cookies: bool = True) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--yes-playlist",
        "--ignore-errors",
        "--retries",
        str(config.retries),
        "--download-archive",
        str(config.archive_file),
        "--write-info-json",
        "--write-thumbnail",
        "--write-description",
        "--print",
        "after_move:filepath",
    ]
    if include_browser_cookies and config.cookies_from_browser:
        cmd.extend(["--cookies-from-browser", config.cookies_from_browser])
    if config.cookies_file and config.cookies_file.exists():
        cmd.extend(["--cookies", str(config.cookies_file)])
    if config.user_agent:
        cmd.extend(["--user-agent", config.user_agent])
    if config.referer:
        cmd.extend(["--referer", config.referer])
    if platform == "douyin" and config.extractor_args:
        cmd.extend(["--extractor-args", config.extractor_args])
    return cmd


def _run_with_cookie_fallback(config: AppConfig, platform: str, extra_args: list[str]) -> list[str]:
    cmd = _build_yt_dlp_cmd(config, platform, include_browser_cookies=True) + extra_args
    try:
        return _run(cmd)
    except RuntimeError as exc:
        detail = str(exc)
        if config.cookies_from_browser and _is_cookie_db_copy_error(detail):
            fallback_cmd = _build_yt_dlp_cmd(config, platform, include_browser_cookies=False) + extra_args
            return _run(fallback_cmd)
        raise


def _sanitize_file_name(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", name).strip()
    return cleaned or "video"


def _download_video_with_yt_dlp(url: str, config: AppConfig, platform: str) -> list[str]:
    download_url = _normalize_download_url(url)
    output_template = str(config.videos_dir / platform / "%(uploader)s" / "%(title)s [%(id)s].%(ext)s")
    extra_args = [
        "-f",
        "bestvideo*+bestaudio/best[ext=mp4]/best",
        "--merge-output-format",
        "mp4",
        "-o",
        output_template,
        download_url,
    ]
    return _run_with_cookie_fallback(config, platform, extra_args)


def _download_douyin_video_with_api(url: str, config: AppConfig) -> list[str]:
    meta = build_metadata(url, config)
    content, content_type = download_video_bytes(url, config)

    ext = "mp4"
    if isinstance(content_type, str) and "jpeg" in content_type.lower():
        ext = "jpg"

    uploader_dir = config.videos_dir / "douyin" / _sanitize_file_name(meta.uploader)
    uploader_dir.mkdir(parents=True, exist_ok=True)
    file_name = _sanitize_file_name(f"{meta.title} [{meta.video_id}].{ext}")
    file_path = uploader_dir / file_name
    file_path.write_bytes(content)
    return [str(file_path)]


def download_video(url: str, config: AppConfig) -> list[str]:
    parsed = parse_url(url)
    if parsed.platform != "douyin":
        return _download_video_with_yt_dlp(url, config, parsed.platform)

    if config.douyin_provider_mode == "yt_dlp":
        return _download_video_with_yt_dlp(url, config, parsed.platform)

    try:
        return _download_douyin_video_with_api(url, config)
    except DouyinApiError:
        if config.douyin_provider_mode == "api_with_fallback":
            return _download_video_with_yt_dlp(url, config, parsed.platform)
        raise


def download_audio_mp3(url: str, config: AppConfig) -> list[str]:
    parsed = parse_url(url)
    download_url = _normalize_download_url(url)
    output_template = str(config.audio_dir / parsed.platform / "%(uploader)s" / "%(title)s [%(id)s].%(ext)s")
    extra_args = [
        "-f",
        "bestaudio/best",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "--postprocessor-args",
        "ffmpeg:-af loudnorm=I=-16:LRA=11:TP=-1.5",
        "-o",
        output_template,
        download_url,
    ]
    return _run_with_cookie_fallback(config, parsed.platform, extra_args)


def download_provider(url: str, config: AppConfig, mode: str) -> tuple[list[str], str]:
    parsed = parse_url(url)
    if mode == "mp3":
        return download_audio_mp3(url, config), "yt_dlp"

    if parsed.platform != "douyin":
        return download_video(url, config), "yt_dlp"

    if config.douyin_provider_mode == "yt_dlp":
        return download_video(url, config), "yt_dlp"

    try:
        files = _download_douyin_video_with_api(url, config)
        return files, "douyin_api"
    except DouyinApiError:
        if config.douyin_provider_mode == "api_with_fallback":
            return _download_video_with_yt_dlp(url, config, parsed.platform), "yt_dlp_fallback"
        raise


def scan_provider_hint(url: str, config: AppConfig) -> str:
    parsed = parse_url(url)
    if parsed.platform != "douyin":
        return "yt_dlp"
    if config.douyin_provider_mode == "yt_dlp":
        return "yt_dlp"
    return "douyin_api"


def export_metadata(urls: list[str], config: AppConfig, output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    for url in urls:
        parsed = parse_url(url)
        entries.append({"url": parsed.url, "platform": parsed.platform})
    output_file.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in entries), encoding="utf-8")
