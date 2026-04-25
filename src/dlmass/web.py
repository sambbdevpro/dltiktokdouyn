from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from flask import Flask, jsonify, request, render_template_string

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
    <button class=\"ok\" onclick=\"downloadSelected('video')\">Download video đã chọn</button>
    <button class=\"ok\" onclick=\"downloadSelected('mp3')\">Download MP3 đã chọn</button>
  </div>

  <div class=\"panel\">
    <h3>Trạng thái</h3>
    <div id=\"status\" class=\"status\">Sẵn sàng.</div>
  </div>

  <div class=\"panel\">
    <h3>Downloaded files</h3>
    <div id=\"downloadSummary\" class=\"muted\">Chưa có file nào.</div>
    <table id=\"downloadedFiles\"></table>
  </div>

<script>
let rows = [];
let downloadedFiles = [];

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
  ['', 'Platform', 'Title', 'Uploader', 'Duration(s)'].forEach(text => {
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

    tr.appendChild(tdCheck);
    tr.appendChild(tdPlatform);
    tr.appendChild(tdTitle);
    tr.appendChild(tdUploader);
    tr.appendChild(tdDuration);
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
    setStatus('Đang tải ' + urls.length + ' mục dưới dạng ' + mode + '...');
    const res = await fetch('/api/download', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mode, urls})
    });
    const data = await res.json();
    if (!res.ok) {
      setStatus('Lỗi download: ' + (data.error || 'unknown'));
      return;
    }
    const newFiles = Array.isArray(data.files) ? data.files : [];
    for (const p of newFiles) {
      if (downloadedFiles.indexOf(p) === -1) {
        downloadedFiles.push(p);
      }
    }
    renderDownloadedFiles(downloadedFiles);
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

        if mode not in {"video", "mp3"}:
            return jsonify({"error": "mode must be 'video' or 'mp3'"}), 400
        if not isinstance(urls, list) or not urls:
            return jsonify({"error": "urls must be a non-empty list"}), 400

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

        return jsonify(
            {
                "success_count": success_count,
                "failed_count": len(failed),
                "failed": failed,
                "files": dedup_files,
                "provider_used": dedup_providers,
            }
        )

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
