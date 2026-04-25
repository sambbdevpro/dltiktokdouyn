from __future__ import annotations

import re
from dataclasses import dataclass


YOUTUBE_RE = re.compile(r"(?:youtube\.com|youtu\.be)", re.IGNORECASE)
TIKTOK_RE = re.compile(r"tiktok\.com", re.IGNORECASE)
DOUYIN_RE = re.compile(r"douyin\.com", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedUrl:
    url: str
    platform: str


def detect_platform(url: str) -> str:
    if YOUTUBE_RE.search(url):
        return "youtube"
    if TIKTOK_RE.search(url):
        return "tiktok"
    if DOUYIN_RE.search(url):
        return "douyin"
    raise ValueError(f"Unsupported URL: {url}")


def parse_url(url: str) -> ParsedUrl:
    return ParsedUrl(url=url.strip(), platform=detect_platform(url.strip()))
