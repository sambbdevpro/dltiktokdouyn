from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, asdict
from urllib.parse import parse_qs, urlparse

from .config import AppConfig
from .douyin_api import DouyinApiError, build_metadata, build_user_videos_metadata
from .parsers import parse_url


@dataclass(frozen=True)
class VideoItem:
    platform: str
    source_url: str
    video_url: str
    video_id: str
    title: str
    uploader: str
    duration: int | None


def _resolve_video_url(platform: str, source_url: str, entry: dict) -> str:
    webpage = entry.get("webpage_url") or entry.get("original_url")
    if webpage:
        return str(webpage)

    entry_url = entry.get("url")
    if isinstance(entry_url, str) and entry_url.startswith("http"):
        return entry_url

    video_id = str(entry.get("id") or "").strip()
    if platform == "youtube" and video_id:
        return f"https://www.youtube.com/watch?v={video_id}"

    return source_url


def _candidate_urls(url: str, platform: str) -> list[str]:
    candidates = [url]
    if platform != "douyin":
        return candidates

    parsed_url = urlparse(url)
    qs = parse_qs(parsed_url.query)
    modal_id = (qs.get("modal_id") or [""])[0].strip()
    if modal_id:
        candidates.insert(0, f"https://www.douyin.com/video/{modal_id}")
    return list(dict.fromkeys(candidates))


def _is_cookie_db_copy_error(text: str) -> bool:
    lowered = text.lower()
    return "could not copy" in lowered and "cookie" in lowered and "database" in lowered


def _apply_config_options(
    cmd: list[str], config: AppConfig | None, platform: str, include_browser_cookies: bool = True
) -> None:
    if not config:
        return
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


def _scan_with_yt_dlp(url: str, flat_playlist: bool, platform: str, config: AppConfig | None) -> dict:
    def build_cmd(include_browser_cookies: bool) -> list[str]:
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--dump-single-json",
            "--skip-download",
            "--ignore-errors",
        ]
        _apply_config_options(cmd, config, platform, include_browser_cookies=include_browser_cookies)
        if flat_playlist:
            cmd.append("--flat-playlist")
        cmd.append(url)
        return cmd

    try:
        result = subprocess.run(build_cmd(True), check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = f"{exc.stderr or ''}\n{exc.stdout or ''}".strip()
        if config and config.cookies_from_browser and _is_cookie_db_copy_error(detail):
            result = subprocess.run(build_cmd(False), check=True, capture_output=True, text=True)
        else:
            raise

    return json.loads(result.stdout)


def _extract_modal_id(url: str) -> str:
    parsed_url = urlparse(url)
    qs = parse_qs(parsed_url.query)
    return (qs.get("modal_id") or [""])[0].strip()


def _is_douyin_user_url(url: str) -> bool:
    parsed_url = urlparse(url)
    host = parsed_url.netloc.lower()
    if "douyin.com" not in host:
        return False
    path = parsed_url.path.strip("/").lower()
    return path.startswith("user/")


def _scan_single_url(url: str, config: AppConfig | None) -> list[VideoItem]:
    parsed = parse_url(url)

    if parsed.platform == "douyin" and config and config.douyin_provider_mode in {"api", "api_with_fallback"}:
        try:
            if _is_douyin_user_url(url) and not _extract_modal_id(url):
                metas = build_user_videos_metadata(url, config)
                return [
                    VideoItem(
                        platform="douyin",
                        source_url=url,
                        video_url=meta.video_url,
                        video_id=meta.video_id,
                        title=meta.title,
                        uploader=meta.uploader,
                        duration=meta.duration,
                    )
                    for meta in metas
                ]

            meta = build_metadata(url, config)
            return [
                VideoItem(
                    platform="douyin",
                    source_url=url,
                    video_url=meta.video_url,
                    video_id=meta.video_id,
                    title=meta.title,
                    uploader=meta.uploader,
                    duration=meta.duration,
                )
            ]
        except DouyinApiError:
            if config.douyin_provider_mode == "api":
                raise

    payload: dict | None = None
    errors: list[str] = []
    for candidate in _candidate_urls(url, parsed.platform):
        for flat_playlist in (True, False):
            try:
                payload = _scan_with_yt_dlp(candidate, flat_playlist, parsed.platform, config)
                break
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or "").strip()
                errors.append(f"{candidate} | flat={flat_playlist}: {stderr or str(exc)}")
            except json.JSONDecodeError as exc:
                errors.append(f"{candidate} | flat={flat_playlist}: invalid JSON: {exc}")
        if payload is not None:
            break

    if payload is None:
        if parsed.platform == "douyin":
            modal_id = _extract_modal_id(url)
            if modal_id:
                fallback_url = f"https://www.douyin.com/video/{modal_id}"
                return [
                    VideoItem(
                        platform="douyin",
                        source_url=url,
                        video_url=fallback_url,
                        video_id=modal_id,
                        title=f"Douyin video {modal_id}",
                        uploader="unknown",
                        duration=None,
                    )
                ]
        detail = "\n".join(errors[-3:]) if errors else "unknown scan error"
        raise RuntimeError(f"Không quét được URL {url}. Chi tiết: {detail}")

    entries = payload.get("entries")
    if isinstance(entries, list) and entries:
        items: list[VideoItem] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            video_id = str(entry.get("id") or "").strip()
            title = str(entry.get("title") or "Untitled")
            uploader = str(entry.get("uploader") or entry.get("channel") or "unknown")
            duration_raw = entry.get("duration")
            duration = int(duration_raw) if isinstance(duration_raw, (int, float)) else None
            video_url = _resolve_video_url(parsed.platform, url, entry)
            items.append(
                VideoItem(
                    platform=parsed.platform,
                    source_url=url,
                    video_url=video_url,
                    video_id=video_id,
                    title=title,
                    uploader=uploader,
                    duration=duration,
                )
            )
        return items

    video_id = str(payload.get("id") or "").strip()
    title = str(payload.get("title") or "Untitled")
    uploader = str(payload.get("uploader") or payload.get("channel") or "unknown")
    duration_raw = payload.get("duration")
    duration = int(duration_raw) if isinstance(duration_raw, (int, float)) else None
    video_url = _resolve_video_url(parsed.platform, url, payload)
    return [
        VideoItem(
            platform=parsed.platform,
            source_url=url,
            video_url=video_url,
            video_id=video_id,
            title=title,
            uploader=uploader,
            duration=duration,
        )
    ]


def scan_urls(urls: list[str], config: AppConfig | None = None) -> list[dict]:
    unique_urls = list(dict.fromkeys(urls))
    all_items: list[VideoItem] = []
    for url in unique_urls:
        all_items.extend(_scan_single_url(url, config))

    deduped: dict[tuple[str, str], VideoItem] = {}
    for item in all_items:
        key = (item.platform, item.video_id or item.video_url)
        deduped[key] = item

    return [asdict(item) for item in deduped.values()]
