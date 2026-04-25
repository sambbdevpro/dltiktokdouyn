from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config
from .downloader import download_audio_mp3, download_video, export_metadata
from .io_utils import ensure_dirs, load_urls


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dlmass", description="Bulk downloader for YouTube, TikTok, Douyin")
    parser.add_argument("--config", type=Path, default=Path("dlmass.config.json"), help="Path to config JSON")

    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("urls", nargs="*", help="Video/channel URLs")
    common.add_argument("--input-file", type=Path, default=None, help="File containing URLs")

    dl_video = sub.add_parser("download-video", parents=[common], help="Download videos")
    dl_video.add_argument("--audio-too", action="store_true", help="Also export mp3")

    dl_mp3 = sub.add_parser("download-mp3", parents=[common], help="Download mp3 only")

    exp = sub.add_parser("export-metadata", parents=[common], help="Export metadata placeholder")
    exp.add_argument("--output", type=Path, default=Path("output/metadata/urls.jsonl"))

    web = sub.add_parser("web", help="Run web UI")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=5001)
    web.add_argument("--debug", action="store_true")

    return parser


def run() -> None:
    parser = build_parser()
    args = parser.parse_args()

    cfg_path = args.config if args.config.exists() else None

    if args.command == "web":
        from .web import create_app

        app = create_app(cfg_path)
        app.run(host=args.host, port=args.port, debug=args.debug)
        return

    config = load_config(cfg_path)
    ensure_dirs([config.output_root, config.videos_dir, config.audio_dir, config.metadata_dir, config.archive_file.parent])

    urls = load_urls(args.urls, args.input_file)
    if not urls:
        raise SystemExit("No URLs provided. Use positional urls or --input-file")

    if args.command == "download-video":
        for url in urls:
            download_video(url, config)
            if args.audio_too:
                download_audio_mp3(url, config)
        return

    if args.command == "download-mp3":
        for url in urls:
            download_audio_mp3(url, config)
        return

    if args.command == "export-metadata":
        export_metadata(urls, config, args.output)
        return

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    run()
