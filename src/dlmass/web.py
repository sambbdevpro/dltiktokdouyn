from __future__ import annotations

import secrets
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from flask import Flask, jsonify, request, render_template_string, send_file

from .config import load_config
from .downloader import download_provider
from .io_utils import ensure_dirs
from .scanner import scan_urls


INDEX_HTML = """
<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>DLMass UI</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; background: #0b1220; color: #f1f5f9; }
    textarea { width: 100%; min-height: 100px; padding: 10px; background: #111827; color: #f8fafc; border: 1px solid #334155; border-radius: 8px; }
    button { margin-right: 8px; margin-top: 10px; padding: 8px 12px; border-radius: 8px; border: none; cursor: pointer; }
    .primary { background: #2563eb; color: white; }
    .ok { background: #16a34a; color: white; }
    .panel { margin-top: 16px; padding: 16px; border: 1px solid #334155; border-radius: 10px; background: #111827; }
    table { width: 100%; border-collapse: collapse; margin-top: 8px; }
    th, td { text-align: left; border-bottom: 1px solid #334155; padding: 8px; }
    .muted { color: #94a3b8; }
    .status { white-space: pre-wrap; background: #0f172a; padding: 10px; border-radius: 8px; }
  </style>
</head>
<body>
  <h1>DLMass Downloader</h1>
  <p class=\"muted\">Dán link video hoặc link kênh YouTube/TikTok/Douyin, mỗi dòng 1 link.</p>
  <textarea id=\"urls\" placeholder=\"https://www.youtube.com/@channel\"></textarea><br />
  <button class=\"primary\" onclick=\"scanUrls()\">Quét video</button>
  <button onclick=\"toggleAll(true)\">Chọn tất cả</button>
  <button onclick=\"toggleAll(false)\">Bỏ chọn</button>

  <div class=\"panel\">
    <h3>Kết quả quét</h3>
    <div id=\"summary\" class=\"muted\">Chưa có dữ liệu.</div>
    <table id=\"results\"></table>
    <div style=\"margin-top: 10px;\">
      <span class=\"muted\">Nơi lưu file:</span>
      <label style=\"margin-left: 8px;\"><input type=\"radio\" name=\"delivery\" value=\"server\" checked /> Lưu trên server</label>
      <label style=\"margin-left: 8px;\"><input type=\"radio\" name=\"delivery\" value=\"client\" /> Tải về máy này</label>
    </div>
    <button class=\"ok\" onclick=\"downloadSelected('video')\">Download video đã chọn</button>
    <button class=\"ok\" onclick=\"downloadSelected('mp3')\">Download MP3 đã chọn</button>
  </div>

  <div class=\"panel\">
    <h3>Trạng thái</h3>
    <div id=\"status\" class=\"status\">Sẵn sàng.</div>
  </div>

  <div class=\"panel\" id=\"downloadedFilesPanel\">
    <h3>Downloaded files</h3>
    <div id=\"downloadSummary\" class=\"muted\">Chưa có file nào.</div>
    <table id=\"downloadedFiles\"></table>
  </div>

<script>
let rows = [];
let downloadedFiles = [];

function currentDelivery() {
  const selected = document.querySelector('input[name="delivery"]:checked');
  return selected ? selected.value : 'server';
}

function triggerClientDownloads(items) {
  if (!Array.isArray(items) || items.length === 0) {
    return;
  }
  for (const item of items) {
    const url = item && item.url ? String(item.url) : '';
    if (!url) {
      continue;
    }
    const a = document.createElement('a');
    a.href = url;
    if (item.name) {
      a.download = String(item.name);
    }
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }
}

function toggleDownloadedPanel(show) {
  const panel = document.getElementById('downloadedFilesPanel');
  if (!panel) {
    return;
  }
  panel.style.display = show ? 'block' : 'none';
}

async function openFileLocation(filePath) {
  try {
    const res = await fetch('/api/open-location', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({file_path: filePath})
    });
    const data = await res.json();
    if (!res.ok) {
      setStatus('Không mở được vị trí file: ' + (data.error || 'unknown'));
      return;
    }
    setStatus('Đã mở vị trí file.');
  } catch (err) {
    const errMsg = (err && err.message) ? err.message : String(err);
    setStatus('Lỗi mở vị trí file: ' + errMsg);
  }
}

function renderDownloadedFiles(items) {
  const table = document.getElementById('downloadedFiles');
  const summary = document.getElementById('downloadSummary');
  table.innerHTML = '';

  if (!items || items.length === 0) {
    summary.innerText = 'Chưa có file nào.';
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.innerText = 'Chưa có file tải xong để mở vị trí.';
    tr.appendChild(td);
    table.appendChild(tr);
    return;
  }

  summary.innerText = 'Có ' + items.length + ' file đã tải.';

  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  ['File', 'Action'].forEach(text => {
    const th = document.createElement('th');
    th.innerText = text;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);

  const tbody = document.createElement('tbody');
  for (const filePath of items) {
    const tr = document.createElement('tr');

    const tdPath = document.createElement('td');
    tdPath.innerText = String(filePath || '');

    const tdAction = document.createElement('td');
    const btn = document.createElement('button');
    btn.className = 'primary';
    btn.innerText = 'Open file location';
    btn.onclick = function() { openFileLocation(filePath); };
    tdAction.appendChild(btn);

    tr.appendChild(tdPath);
    tr.appendChild(tdAction);
    tbody.appendChild(tr);
  }

  table.appendChild(thead);
  table.appendChild(tbody);
}

function selectedUrls() {
  const checks = document.querySelectorAll('input[name="pick"]:checked');
  return Array.from(checks).map(c => c.value);
}

function toggleAll(checked) {
  document.querySelectorAll('input[name="pick"]').forEach(cb => cb.checked = checked);
}

async function scanUrls() {
  try {
    const raw = document.getElementById('urls').value;
    const urls = raw.split('\\n').map(x => x.trim()).filter(Boolean);
    if (urls.length === 0) {
      setStatus('Vui lòng nhập ít nhất 1 URL.');
      return;
    }
    setStatus('Đang quét...');
    const res = await fetch('/api/scan', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({urls})
    });
    const data = await res.json();
    if (!res.ok) {
      setStatus('Lỗi quét: ' + (data.error || 'unknown'));
      return;
    }
    rows = data.items;
    renderTable(rows);
    document.getElementById('summary').innerText = 'Tìm thấy ' + rows.length + ' video.';
    setStatus('Quét xong. Chọn video rồi bấm download.');
  } catch (err) {
    const errMsg = (err && err.message) ? err.message : String(err);
    setStatus('Lỗi quét (network/runtime): ' + errMsg);
  }
}

function renderTable(items) {
  const table = document.getElementById('results');
  table.innerHTML = '';

  if (items.length === 0) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.innerText = 'Không có video.';
    tr.appendChild(td);
    table.appendChild(tr);
    return;
  }

  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  ['', 'Platform', 'Title', 'Uploader', 'Duration(s)', 'Video Link'].forEach(text => {
    const th = document.createElement('th');
    th.innerText = text;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);

  const tbody = document.createElement('tbody');
  for (const item of items) {
    const tr = document.createElement('tr');

    const tdCheck = document.createElement('td');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.name = 'pick';
    cb.value = String(item.video_url || '');
    cb.checked = true;
    tdCheck.appendChild(cb);

    const tdPlatform = document.createElement('td');
    tdPlatform.innerText = String(item.platform || '');

    const tdTitle = document.createElement('td');
    tdTitle.innerText = String(item.title || '');

    const tdUploader = document.createElement('td');
    tdUploader.innerText = String(item.uploader || '');

    const tdDuration = document.createElement('td');
    tdDuration.innerText = (item.duration === null || item.duration === undefined) ? '' : String(item.duration);

    const tdVideoLink = document.createElement('td');
    const videoUrl = String(item.video_url || '');
    if (videoUrl) {
      const a = document.createElement('a');
      a.href = videoUrl;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.innerText = 'Open link';
      tdVideoLink.appendChild(a);
    } else {
      tdVideoLink.innerText = '';
    }

    tr.appendChild(tdCheck);
    tr.appendChild(tdPlatform);
    tr.appendChild(tdTitle);
    tr.appendChild(tdUploader);
    tr.appendChild(tdDuration);
    tr.appendChild(tdVideoLink);
    tbody.appendChild(tr);
  }

  table.appendChild(thead);
  table.appendChild(tbody);
}

async function downloadSelected(mode) {
  try {
    const urls = selectedUrls();
    if (urls.length === 0) {
      setStatus('Chưa chọn video nào.');
      return;
    }
    const delivery = currentDelivery();
    setStatus('Đang tải ' + urls.length + ' mục dưới dạng ' + mode + '...');
    const res = await fetch('/api/download', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mode, urls, delivery})
    });
    const data = await res.json();
    if (!res.ok) {
      setStatus('Lỗi download: ' + (data.error || 'unknown'));
      return;
    }

    if (delivery === 'client') {
      toggleDownloadedPanel(false);
      const downloadItems = Array.isArray(data.download_items) ? data.download_items : [];
      triggerClientDownloads(downloadItems);
    } else {
      toggleDownloadedPanel(true);
      const newFiles = Array.isArray(data.files) ? data.files : [];
      for (const p of newFiles) {
        if (downloadedFiles.indexOf(p) === -1) {
          downloadedFiles.push(p);
        }
      }
      renderDownloadedFiles(downloadedFiles);
    }

    if (Array.isArray(data.failed) && data.failed.length > 0) {
      const firstErr = data.failed[0].error || 'unknown';
      setStatus('Hoàn tất. Thành công: ' + data.success_count + ', lỗi: ' + data.failed_count + '. Lỗi đầu tiên: ' + firstErr);
    } else {
      setStatus('Hoàn tất. Thành công: ' + data.success_count + ', lỗi: ' + data.failed_count);
    }
  } catch (err) {
    const errMsg = (err && err.message) ? err.message : String(err);
    setStatus('Lỗi download (network/runtime): ' + errMsg);
  }
}

function setStatus(text) {
  document.getElementById('status').innerText = text;
}
</script>
</body>
</html>
"""


def create_app(config_path: Path | None = None) -> Flask:
    app = Flask(__name__)
    cfg = load_config(config_path if config_path and config_path.exists() else None)
    ensure_dirs([cfg.output_root, cfg.videos_dir, cfg.audio_dir, cfg.metadata_dir, cfg.archive_file.parent])

    download_links: dict[str, dict[str, object]] = {}
    download_token_ttl_sec = 600
    web_bundle_dir = (cfg.output_root / "tmp_web").expanduser().resolve()
    ensure_dirs([web_bundle_dir])

    def cleanup_expired_links() -> None:
        now = int(time.time())
        expired_tokens = [token for token, info in download_links.items() if int(info.get("expires_at", 0)) <= now]
        for token in expired_tokens:
            info = download_links.pop(token, None)
            if not isinstance(info, dict):
                continue
            if bool(info.get("temporary")):
                tmp_path = Path(str(info.get("path", ""))).expanduser().resolve()
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except Exception:
                        pass

    def issue_download_link(path: Path, *, temporary: bool = False) -> dict[str, object]:
        cleanup_expired_links()
        token = secrets.token_urlsafe(24)
        expires_at = int(time.time()) + download_token_ttl_sec
        absolute_path = path.expanduser().resolve()
        download_links[token] = {
            "path": str(absolute_path),
            "name": absolute_path.name,
            "expires_at": expires_at,
            "temporary": temporary,
        }
        path = absolute_path
        return {
            "name": path.name,
            "url": f"/api/download-file?token={token}",
            "content_type": "application/zip" if path.suffix.lower() == ".zip" else "application/octet-stream",
            "expires_in_sec": download_token_ttl_sec,
        }

    def build_zip_bundle(paths: list[Path]) -> Path:
        bundle_name = f"dlmass_{int(time.time())}_{secrets.token_hex(4)}.zip"
        bundle_path = web_bundle_dir / bundle_name
        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for src in paths:
                zf.write(src, arcname=src.name)
        return bundle_path

    def normalize_existing_paths(raw_paths: list[str]) -> list[Path]:
        normalized: list[Path] = []
        for item in raw_paths:
            p = Path(item).expanduser().resolve()
            if p.exists() and p.is_file():
                normalized.append(p)
        return normalized

    cleanup_expired_links()

    @app.get("/api/download-file")
    def api_download_file():
        cleanup_expired_links()
        token = request.args.get("token", "").strip()
        if not token:
            return jsonify({"error": "token is required"}), 400

        info = download_links.get(token)
        if not isinstance(info, dict):
            return jsonify({"error": "invalid or expired token"}), 404

        expires_at = int(info.get("expires_at", 0))
        if expires_at <= int(time.time()):
            download_links.pop(token, None)
            return jsonify({"error": "invalid or expired token"}), 404

        target = Path(str(info.get("path", "")))
        if not target.exists() or not target.is_file():
            download_links.pop(token, None)
            return jsonify({"error": "file does not exist"}), 404

        target = target.expanduser().resolve()
        return send_file(target, as_attachment=True, download_name=str(info.get("name", target.name)))

    @app.get("/")
    def index():
        return render_template_string(INDEX_HTML)

    @app.post("/api/scan")
    def api_scan():
        payload = request.get_json(silent=True) or {}
        urls = payload.get("urls")
        if not isinstance(urls, list) or not urls:
            return jsonify({"error": "urls must be a non-empty list"}), 400

        try:
            clean_urls = [str(u).strip() for u in urls if str(u).strip()]
            items = scan_urls(clean_urls, cfg)
            return jsonify({"items": items})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.post("/api/download")
    def api_download():
        payload = request.get_json(silent=True) or {}
        mode = payload.get("mode")
        urls = payload.get("urls")
        delivery = payload.get("delivery", "server")

        if mode not in {"video", "mp3"}:
            return jsonify({"error": "mode must be 'video' or 'mp3'"}), 400
        if not isinstance(urls, list) or not urls:
            return jsonify({"error": "urls must be a non-empty list"}), 400
        if delivery not in {"server", "client"}:
            return jsonify({"error": "delivery must be 'server' or 'client'"}), 400

        success_count = 0
        failed: list[dict] = []
        files: list[str] = []
        providers: list[str] = []

        for url in [str(u).strip() for u in urls if str(u).strip()]:
            try:
                new_files, provider_used = download_provider(url, cfg, mode)
                files.extend(new_files)
                providers.append(provider_used)
                success_count += 1
            except Exception as exc:
                failed.append({"url": url, "error": str(exc)})

        dedup_files = list(dict.fromkeys(files))
        dedup_providers = list(dict.fromkeys(providers))

        response_payload = {
            "success_count": success_count,
            "failed_count": len(failed),
            "failed": failed,
            "provider_used": dedup_providers,
            "delivery": delivery,
        }

        if delivery == "server":
            response_payload["files"] = dedup_files
            return jsonify(response_payload)

        existing_paths = normalize_existing_paths(dedup_files)
        download_items: list[dict[str, object]] = []

        if len(existing_paths) == 1:
            download_items.append(issue_download_link(existing_paths[0], temporary=False))
        elif len(existing_paths) > 1:
            bundle_path = build_zip_bundle(existing_paths)
            download_items.append(issue_download_link(bundle_path, temporary=True))

        response_payload["download_items"] = download_items
        return jsonify(response_payload)

    @app.post("/api/open-location")
    def api_open_location():
        payload = request.get_json(silent=True) or {}
        file_path_raw = payload.get("file_path")
        if not isinstance(file_path_raw, str) or not file_path_raw.strip():
            return jsonify({"error": "file_path must be a non-empty string"}), 400

        target = Path(file_path_raw).expanduser().resolve()
        if not target.exists():
            return jsonify({"error": "file does not exist"}), 404

        try:
            subprocess.Popen(["explorer", "/select,", str(target)])
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    return app
