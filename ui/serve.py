#!/usr/bin/env python3
"""Serve the Jev guide locally and proxy the TypeSafe API.

Two reasons this exists:

1. CORS. api.typesafe.ai does not return Access-Control-Allow-Origin for
   third-party origins, so a static page cannot call it from a browser. This
   server forwards the request from the server side instead.
2. Key safety. The key is read from the environment (TYPESAFE_API_KEY) and is
   never sent to the browser when it is present there.

Usage:
    export TYPESAFE_API_KEY=ts_...
    python3 ui/serve.py            # http://127.0.0.1:8765/
    python3 ui/serve.py --port 9000

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

API_URL = "https://api.typesafe.ai/v1/systemone"
MAX_BODY = 4 * 1024 * 1024
TIMEOUT = 60
UI_DIR = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    # Injected by make_server().
    api_key: str | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

    # ------------------------------------------------------------- helpers

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ValueError("empty request body")
        if length > MAX_BODY:
            raise ValueError("request body too large")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    # -------------------------------------------------------------- routes

    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        if self.path.split("?")[0] == "/api/health":
            self._json(
                200,
                {
                    "ok": True,
                    "live": True,
                    "hasEnvKey": bool(self.api_key),
                },
            )
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        if self.path.split("?")[0] != "/api/evaluate":
            self.send_error(404, "unknown endpoint")
            return

        try:
            body = self._read_json()
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"ok": False, "error": f"bad request: {exc}"})
            return

        payload = body.get("payload")
        if not isinstance(payload, dict):
            self._json(400, {"ok": False, "error": "missing 'payload' object"})
            return

        # Environment key wins; a key supplied in the request is a local-only
        # fallback so the page can be used without exporting anything.
        key = self.api_key or (body.get("key") or "").strip()
        if not key:
            self._json(
                400,
                {
                    "ok": False,
                    "error": "no API key. Export TYPESAFE_API_KEY and restart, "
                    "or paste a key into the page.",
                },
            )
            return

        request = urllib.request.Request(
            API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                raw = response.read().decode("utf-8")
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            status = exc.code
        except urllib.error.URLError as exc:
            self._json(
                502, {"ok": False, "error": f"upstream unreachable: {exc.reason}"}
            )
            return
        except TimeoutError:
            self._json(504, {"ok": False, "error": "upstream timed out"})
            return

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            self._json(
                502,
                {
                    "ok": False,
                    "error": "upstream returned non-JSON",
                    "body": raw[:2000],
                },
            )
            return

        # Mirror the upstream status so the caller can rely on res.ok alone.
        self._json(status, {"ok": status < 400, "status": status, "body": parsed})

    def log_message(self, fmt: str, *args) -> None:  # quieter, single-line
        sys.stderr.write("  %s\n" % (fmt % args))


def make_server(port: int, host: str, api_key: str | None) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"api_key": api_key})
    return ThreadingHTTPServer((host, port), handler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    api_key = os.environ.get("TYPESAFE_API_KEY", "").strip() or None
    server = make_server(args.port, args.host, api_key)

    print(f"Jev guide  ->  http://{args.host}:{args.port}/")
    print(
        f"Live API   ->  {'enabled (key from TYPESAFE_API_KEY)' if api_key else 'disabled (no TYPESAFE_API_KEY set)'}"
    )
    print("The key is never written to disk or sent to the browser.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
