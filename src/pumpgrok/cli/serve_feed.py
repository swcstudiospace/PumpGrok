"""Read-only feed endpoint for a sealed dataset (REC-03; D-01 paper-only).

`live serve` exposes a dataset over HTTP: GET /healthz returns the
dataset name and tick count, every other path 404s. The endpoint never
writes, never places orders, and never reaches the live adapter; it is
a read-only health view over recorded data.
"""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from pumpgrok.replay.fixtures import load_dataset

__all__ = ["FeedServer", "health_probe", "serve_feed_once"]


class _Handler(BaseHTTPRequestHandler):
    """One handler class bound to one dataset directory."""

    dataset_dir: Path = Path(".")

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/healthz":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")
            return
        dataset = load_dataset(type(self).dataset_dir)
        body = json.dumps(
            {"ok": True, "dataset": dataset.manifest.dataset, "ticks": len(dataset.events)},
            sort_keys=True,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        """Silence the default request logging."""


class FeedServer:
    """HTTP server for the read-only feed endpoint (test-friendly)."""

    def __init__(self, dataset_dir: Path, port: int) -> None:
        handler = type("BoundHandler", (_Handler,), {"dataset_dir": Path(dataset_dir)})
        self._server = HTTPServer(("127.0.0.1", port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        """The bound port (actual port when 0 was requested)."""
        return int(self._server.server_address[1])

    def start(self) -> None:
        """Start serving in a daemon thread."""
        self._thread.start()

    def stop(self) -> None:
        """Stop serving and release the port."""
        self._server.shutdown()
        self._server.server_close()


def health_probe(port: int) -> dict[str, Any]:
    """GET /healthz on localhost and decode the JSON body."""
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def serve_feed_once(dataset_dir: Path, port: int) -> int:
    """Serve one health probe, then exit (test/CLI --once path)."""
    server = FeedServer(dataset_dir, port)
    server.start()
    try:
        probe = health_probe(server.port)
        return 0 if probe.get("ok") is True else 1
    finally:
        server.stop()
