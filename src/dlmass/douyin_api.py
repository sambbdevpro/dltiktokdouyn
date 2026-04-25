from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from .config import AppConfig


class DouyinApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class DouyinMeta:
    video_id: str
    title: str
    uploader: str
    duration: int | None
    video_url: str


def _base_url(config: AppConfig) -> str:
    return config.douyin_api_base_url.rstrip("/") + "/"


def _headers(config: AppConfig) -> dict[str, str]:
    headers = {"accept": "application/json"}
    if config.user_agent:
        headers["User-Agent"] = config.user_agent
    if config.referer:
        headers["Referer"] = config.referer
    if config.douyin_api_token:
        headers["Authorization"] = f"Bearer {config.douyin_api_token}"
    return headers


def _request_json(config: AppConfig, path: str, query: dict[str, Any]) -> dict[str, Any]:
    url = urljoin(_base_url(config), path.lstrip("/"))
    full_url = f"{url}?{urlencode(query)}" if query else url
    req = Request(full_url, headers=_headers(config), method="GET")

    try:
        with urlopen(req, timeout=config.douyin_api_timeout_sec) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        error_body = ""
        if exc.fp is not None:
            error_body = exc.fp.read().decode("utf-8", errors="replace")
        raise DouyinApiError(
            f"Douyin API request failed: {full_url} | HTTP {exc.code} | {error_body or exc.reason}"
        ) from exc
    except Exception as exc:
        raise DouyinApiError(f"Douyin API request failed: {full_url} | {exc}") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise DouyinApiError(f"Douyin API invalid JSON: {full_url}") from exc

    if not isinstance(payload, dict):
        raise DouyinApiError(f"Douyin API invalid payload type: {full_url}")

    code = payload.get("code")
    if isinstance(code, int) and code != 200:
        raise DouyinApiError(f"Douyin API returned code={code}: {full_url}")

    return payload


def _extract_data(payload: dict[str, Any]) -> Any:
    if "data" in payload:
        return payload.get("data")

    detail = payload.get("detail")
    if isinstance(detail, dict):
        raise DouyinApiError(
            f"Douyin API detail error code={detail.get('code')}, router={detail.get('router')}, message={detail.get('message')}"
        )

    raise DouyinApiError("Douyin API response missing data")


def _first_str(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _nested(source: Any, *keys: str) -> Any:
    current = source
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _normalize_data(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise DouyinApiError("Douyin API data is not an object")
    aweme_detail = data.get("aweme_detail")
    if isinstance(aweme_detail, dict):
        merged = dict(data)
        merged.update(aweme_detail)
        return merged
    return data


def _pick_video_id(data: dict[str, Any], fallback_video_id: str | None = None) -> str | None:
    for value in (
        data.get("aweme_id"),
        data.get("video_id"),
        data.get("id"),
        _nested(data, "aweme_detail", "aweme_id"),
        _nested(data, "awemeInfo", "awemeId"),
        fallback_video_id,
    ):
        text = _first_str(value)
        if text:
            return text
    return None


def _pick_title(data: dict[str, Any], video_id: str) -> str:
    for value in (
        data.get("title"),
        data.get("desc"),
        data.get("video_title"),
        _nested(data, "aweme_detail", "desc"),
        _nested(data, "awemeInfo", "desc"),
    ):
        text = _first_str(value)
        if text:
            return text
    return f"Douyin video {video_id}"


def _pick_uploader(data: dict[str, Any]) -> str:
    for value in (
        data.get("nickname"),
        data.get("uploader"),
        data.get("author_name"),
        _nested(data, "aweme_detail", "author", "nickname"),
        _nested(data, "awemeInfo", "author", "nickname"),
    ):
        text = _first_str(value)
        if text:
            return text
    return "unknown"


def _pick_duration(data: dict[str, Any]) -> int | None:
    for value in (
        data.get("duration"),
        data.get("video_duration"),
        data.get("duration_sec"),
        _nested(data, "aweme_detail", "video", "duration"),
        _nested(data, "awemeInfo", "video", "duration"),
    ):
        if isinstance(value, (int, float)):
            number = int(value)
            return int(number / 1000) if number > 1000 else number
        if isinstance(value, str) and value.strip().isdigit():
            number = int(value.strip())
            return int(number / 1000) if number > 1000 else number
    return None


def _get_aweme_id(url: str, config: AppConfig) -> str:
    payload = _request_json(config, "/api/douyin/web/get_aweme_id", {"url": url})
    data = _extract_data(payload)

    if isinstance(data, str):
        text = data.strip()
        if text:
            return text

    if isinstance(data, dict):
        for value in (data.get("aweme_id"), data.get("id"), data.get("video_id")):
            text = _first_str(value)
            if text:
                return text

    raise DouyinApiError("Cannot resolve aweme_id from Douyin API")


def _fetch_one_video(aweme_id: str, config: AppConfig) -> Any:
    payload = _request_json(config, "/api/douyin/web/fetch_one_video", {"aweme_id": aweme_id})
    return _extract_data(payload)


def _get_sec_user_id(url: str, config: AppConfig) -> str:
    payload = _request_json(config, "/api/douyin/web/get_sec_user_id", {"url": url})
    data = _extract_data(payload)

    if isinstance(data, str):
        text = data.strip()
        if text:
            return text

    if isinstance(data, dict):
        for value in (data.get("sec_user_id"), data.get("id")):
            text = _first_str(value)
            if text:
                return text

    raise DouyinApiError("Cannot resolve sec_user_id from Douyin API")


def _fetch_user_post_videos(sec_user_id: str, max_cursor: int, count: int, config: AppConfig) -> dict[str, Any]:
    payload = _request_json(
        config,
        "/api/douyin/web/fetch_user_post_videos",
        {"sec_user_id": sec_user_id, "max_cursor": str(max_cursor), "count": str(count)},
    )
    data = _extract_data(payload)
    if not isinstance(data, dict):
        raise DouyinApiError("Douyin API returned invalid user posts payload")
    return data


def _hybrid_video_data(url: str, config: AppConfig) -> Any:
    payload = _request_json(config, "/api/hybrid/video_data", {"url": url, "minimal": "false"})
    return _extract_data(payload)


def build_metadata(url: str, config: AppConfig) -> DouyinMeta:
    try:
        hybrid_data = _hybrid_video_data(url, config)
        if isinstance(hybrid_data, dict):
            normalized = _normalize_data(hybrid_data)
            video_id = _pick_video_id(normalized)
            if video_id:
                return DouyinMeta(
                    video_id=video_id,
                    title=_pick_title(normalized, video_id),
                    uploader=_pick_uploader(normalized),
                    duration=_pick_duration(normalized),
                    video_url=f"https://www.douyin.com/video/{video_id}",
                )
    except DouyinApiError:
        pass

    aweme_id = _get_aweme_id(url, config)
    one_video_data = _fetch_one_video(aweme_id, config)

    if isinstance(one_video_data, dict):
        normalized = _normalize_data(one_video_data)
        video_id = _pick_video_id(normalized, fallback_video_id=aweme_id) or aweme_id
        return DouyinMeta(
            video_id=video_id,
            title=_pick_title(normalized, video_id),
            uploader=_pick_uploader(normalized),
            duration=_pick_duration(normalized),
            video_url=f"https://www.douyin.com/video/{video_id}",
        )

    return DouyinMeta(
        video_id=aweme_id,
        title=f"Douyin video {aweme_id}",
        uploader="unknown",
        duration=None,
        video_url=f"https://www.douyin.com/video/{aweme_id}",
    )


def build_user_videos_metadata(url: str, config: AppConfig) -> list[DouyinMeta]:
    sec_user_id = _get_sec_user_id(url, config)
    max_cursor = 0
    page_count = 0
    seen_cursors: set[int] = set()
    seen_video_ids: set[str] = set()
    items: list[DouyinMeta] = []

    while page_count < 200:
        page_count += 1
        page = _fetch_user_post_videos(sec_user_id, max_cursor=max_cursor, count=35, config=config)
        aweme_list = page.get("aweme_list")
        if not isinstance(aweme_list, list) or not aweme_list:
            break

        for entry in aweme_list:
            if not isinstance(entry, dict):
                continue
            normalized = _normalize_data(entry)
            video_id = _pick_video_id(normalized)
            if not video_id or video_id in seen_video_ids:
                continue
            seen_video_ids.add(video_id)
            items.append(
                DouyinMeta(
                    video_id=video_id,
                    title=_pick_title(normalized, video_id),
                    uploader=_pick_uploader(normalized),
                    duration=_pick_duration(normalized),
                    video_url=f"https://www.douyin.com/video/{video_id}",
                )
            )

        has_more_raw = page.get("has_more")
        has_more = bool(has_more_raw)
        if not has_more:
            break

        next_cursor_raw = page.get("max_cursor")
        if isinstance(next_cursor_raw, (int, float)):
            next_cursor = int(next_cursor_raw)
        elif isinstance(next_cursor_raw, str) and next_cursor_raw.strip().lstrip("-").isdigit():
            next_cursor = int(next_cursor_raw.strip())
        else:
            break

        if next_cursor in seen_cursors:
            break
        seen_cursors.add(next_cursor)
        max_cursor = next_cursor

    if not items:
        raise DouyinApiError("No videos found for Douyin user URL")

    return items


def _extract_download_url(data: Any) -> str | None:
    if isinstance(data, str):
        text = data.strip()
        if text.startswith("http"):
            return text
        return None

    if not isinstance(data, dict):
        return None

    for value in (
        _nested(data, "video_data", "nwm_video_url_HQ"),
        _nested(data, "video_data", "nwm_video_url"),
        _nested(data, "video_data", "wm_video_url"),
    ):
        text = _first_str(value)
        if text and text.startswith("http"):
            return text

    return None


def _download_direct(download_url: str, config: AppConfig) -> tuple[bytes, str | None]:
    req = Request(download_url, headers=_headers(config), method="GET")
    try:
        with urlopen(req, timeout=config.douyin_api_timeout_sec) as response:
            content = response.read()
            content_type = response.headers.get("Content-Type")
    except Exception as exc:
        raise DouyinApiError(f"Douyin direct download failed: {download_url} | {exc}") from exc

    if not content:
        raise DouyinApiError("Douyin direct download returned empty content")

    return content, content_type


def download_video_bytes(url: str, config: AppConfig) -> tuple[bytes, str | None]:
    query = {
        "url": url,
        "prefix": str(config.douyin_api_download_prefix).lower(),
        "with_watermark": str(config.douyin_api_with_watermark).lower(),
    }
    endpoint = urljoin(_base_url(config), "api/download")
    full_url = f"{endpoint}?{urlencode(query)}"
    req = Request(full_url, headers=_headers(config), method="GET")

    try:
        with urlopen(req, timeout=config.douyin_api_timeout_sec) as response:
            content = response.read()
            content_type = response.headers.get("Content-Type")
    except HTTPError as exc:
        error_body = ""
        if exc.fp is not None:
            error_body = exc.fp.read().decode("utf-8", errors="replace")
        raise DouyinApiError(
            f"Douyin download API failed: {full_url} | HTTP {exc.code} | {error_body or exc.reason}"
        ) from exc
    except Exception as exc:
        raise DouyinApiError(f"Douyin download API failed: {full_url} | {exc}") from exc

    if not content:
        raise DouyinApiError("Douyin download API returned empty content")

    content_type_lower = (content_type or "").lower()
    if "json" in content_type_lower:
        try:
            payload = json.loads(content.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise DouyinApiError("Douyin download API returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise DouyinApiError("Douyin download API JSON payload is invalid")

        data = _extract_data(payload)
        download_url = _extract_download_url(data)
        if not download_url:
            raise DouyinApiError("Douyin download API JSON does not contain downloadable URL")
        return _download_direct(download_url, config)

    return content, content_type
