from __future__ import annotations

from pathlib import Path


def load_urls(urls: list[str], input_file: Path | None) -> list[str]:
    all_urls = [u.strip() for u in urls if u.strip()]
    if input_file:
        all_urls.extend(
            line.strip()
            for line in input_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    deduped = list(dict.fromkeys(all_urls))
    return deduped


def ensure_dirs(paths: list[Path]) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
