#!/usr/bin/env python3
"""Serve the neuron annotation workbench with local autosave.

Usage:
    python3 tools/serve_neuron_workbench.py

Then open:
    http://127.0.0.1:8765/
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


PROJECT_ROOT = Path("/home/jibby2k1/CNEL/State Analysis (Fish)/Separable-Gamma-CFAR")
DEFAULT_APP_DIR = PROJECT_ROOT / "Outputs/NeuronReview/calcium_video_2/app"


class WorkbenchHandler(BaseHTTPRequestHandler):
    app_dir: Path

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _safe_path(self) -> Path | None:
        parsed = urlparse(self.path)
        rel = unquote(parsed.path).lstrip("/")
        if not rel:
            rel = "index.html"
        candidate = (self.app_dir / rel).resolve()
        root = self.app_dir.resolve()
        if candidate == root or root not in candidate.parents:
            return None
        return candidate

    def do_OPTIONS(self) -> None:
        self._send(204, b"", "text/plain")

    def do_GET(self) -> None:
        path = self._safe_path()
        if path is None:
            self._send(403, b"Forbidden\n", "text/plain")
            return
        if not path.exists() or not path.is_file():
            self._send(404, b"Not found\n", "text/plain")
            return
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._send(200, path.read_bytes(), ctype)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/annotations.json":
            self._send(404, b"Only annotations.json can be updated\n", "text/plain")
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
        out = self.app_dir / "annotations.json"
        tmp = self.app_dir / "annotations.json.tmp"
        tmp.write_text(json.dumps(parsed_json, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, out)
        self._send(200, b'{"ok":true}\n', "application/json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the neuron workbench with local autosave.")
    parser.add_argument("--app-dir", type=Path, default=DEFAULT_APP_DIR)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    app_dir = args.app_dir.resolve()
    if not (app_dir / "index.html").exists():
        raise SystemExit(f"index.html not found in {app_dir}")
    WorkbenchHandler.app_dir = app_dir
    server = ThreadingHTTPServer((args.host, args.port), WorkbenchHandler)
    print(f"Serving {app_dir}")
    print(f"Open http://{args.host}:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
