#!/usr/bin/env python3
"""Serve the neuron annotation workbench with local autosave.

Usage:
    python3 tools/serve_neuron_workbench.py
    python3 tools/serve_neuron_workbench.py --root-dir Outputs/NeuronReview

Then open:
    http://127.0.0.1:8765/
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP_DIR = PROJECT_ROOT / "Outputs/NeuronReview/calcium_video_2/app"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.architecture_runs import as_run_manifest


class WorkbenchHandler(BaseHTTPRequestHandler):
    app_dir: Path
    root_dir: Path | None = None

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _send(self, status: int, body: bytes, content_type: str, *, include_body: bool = True) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def _safe_path(self) -> Path | None:
        parsed = urlparse(self.path)
        rel = unquote(parsed.path).lstrip("/")
        if not rel:
            rel = "index.html"
        root = (self.root_dir or self.app_dir).resolve()
        candidate = (root / rel).resolve()
        if candidate == root or root not in candidate.parents:
            return None
        return candidate

    def _safe_put_path(self, parsed_path: str) -> Path | None:
        rel = unquote(parsed_path).lstrip("/")
        if self.root_dir is None:
            if rel not in {"annotations.json", "architecture_runs.json"}:
                return None
            return (self.app_dir / rel).resolve()
        parts = Path(rel).parts
        if len(parts) != 3 or parts[1] != "app" or parts[2] not in {"annotations.json", "architecture_runs.json"}:
            return None
        root = self.root_dir.resolve()
        candidate = (root / rel).resolve()
        if root not in candidate.parents:
            return None
        return candidate

    def do_OPTIONS(self) -> None:
        self._send(204, b"", "text/plain")

    def do_GET(self) -> None:
        self._serve_file(include_body=True)

    def do_HEAD(self) -> None:
        self._serve_file(include_body=False)

    def _serve_file(self, *, include_body: bool) -> None:
        path = self._safe_path()
        if path is None:
            self._send(403, b"Forbidden\n", "text/plain", include_body=include_body)
            return
        if not path.exists() or not path.is_file():
            self._send(404, b"Not found\n", "text/plain", include_body=include_body)
            return
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._send(200, path.read_bytes(), ctype, include_body=include_body)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        out = self._safe_put_path(parsed.path)
        if out is None:
            self._send(404, b"Only per-dataset annotations.json and architecture_runs.json can be updated\n", "text/plain")
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 20_000_000:
            self._send(413, b"Invalid request size\n", "text/plain")
            return
        raw = self.rfile.read(length)
        try:
            parsed_json = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            self._send(400, f"Invalid JSON: {exc}\n".encode(), "text/plain")
            return
        if out.name == "architecture_runs.json":
            try:
                parsed_json = as_run_manifest(parsed_json)
            except Exception as exc:
                self._send(400, f"Invalid architecture run manifest: {exc}\n".encode(), "text/plain")
                return
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(f"{out.name}.tmp")
        tmp.write_text(json.dumps(parsed_json, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, out)
        self._send(200, b'{"ok":true}\n', "application/json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the neuron workbench with local autosave.")
    parser.add_argument("--app-dir", type=Path, default=DEFAULT_APP_DIR)
    parser.add_argument("--root-dir", type=Path, default=None, help="Serve a multi-dataset Outputs/NeuronReview root.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.root_dir:
        root_dir = args.root_dir.resolve()
        if not (root_dir / "index.html").exists():
            raise SystemExit(f"index.html not found in {root_dir}")
        WorkbenchHandler.root_dir = root_dir
        WorkbenchHandler.app_dir = root_dir
        served = root_dir
    else:
        app_dir = args.app_dir.resolve()
        if not (app_dir / "index.html").exists():
            raise SystemExit(f"index.html not found in {app_dir}")
        WorkbenchHandler.root_dir = None
        WorkbenchHandler.app_dir = app_dir
        served = app_dir
    server = ThreadingHTTPServer((args.host, args.port), WorkbenchHandler)
    print(f"Serving {served}")
    print(f"Open http://{args.host}:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
