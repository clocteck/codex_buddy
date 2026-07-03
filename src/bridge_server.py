#!/usr/bin/env python3
"""Minimal Codex Buddy bridge service for local LAN testing."""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict
from urllib.parse import urlparse


STARTED_AT = time.time()
STATE: Dict[str, Any] = {
    "seq": 1,
    "total": 1,
    "running": 0,
    "waiting": 0,
    "tokens_today": 0,
    "tokens": 0,
    "cost_today": 0,
    "cost_month": 0,
    "quota_5h_pct": 100,
    "quota_7d_pct": 100,
    "entries": [
        "Codex Buddy bridge online",
        "Waiting for Codex activity",
    ],
    "pet": {
        "state": "idle",
    },
}
LAST_PERMISSION: Dict[str, Any] | None = None


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def state_snapshot() -> Dict[str, Any]:
    snapshot = dict(STATE)
    snapshot["uptime_sec"] = int(time.time() - STARTED_AT)
    snapshot["updated_at"] = int(time.time())
    if LAST_PERMISSION:
        snapshot["last_permission"] = LAST_PERMISSION
    return snapshot


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "CodexBuddyBridge/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args), flush=True)

    def send_json(self, status: int, value: Any) -> None:
        body = json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/state":
            self.send_json(200, state_snapshot())
            return
        if path == "/health":
            self.send_json(200, {"ok": True, "service": "codex-buddy-bridge"})
            return
        self.send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        global LAST_PERMISSION

        path = urlparse(self.path).path
        if path != "/permission":
            self.send_json(404, {"ok": False, "error": "not found"})
            return

        try:
            payload = self.read_json_body()
        except Exception as exc:  # noqa: BLE001 - return readable HTTP error.
            self.send_json(400, {"ok": False, "error": "bad json", "detail": str(exc)})
            return

        LAST_PERMISSION = {
            "id": payload.get("id", ""),
            "decision": payload.get("decision", ""),
            "at": int(time.time()),
        }
        STATE["seq"] = int(STATE.get("seq", 0)) + 1
        STATE["waiting"] = 0
        STATE.pop("prompt", None)
        STATE["entries"] = [
            "permission: %s" % (LAST_PERMISSION["decision"] or "--"),
            "id: %s" % (LAST_PERMISSION["id"] or "--"),
        ]
        STATE["pet"] = {"state": "heart" if LAST_PERMISSION["decision"] != "deny" else "dizzy"}
        self.send_json(202, {"ok": True, "accepted": True})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Codex Buddy bridge service.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), BridgeHandler)
    print("Codex Buddy bridge listening on http://%s:%s" % (args.host, args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping bridge", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
