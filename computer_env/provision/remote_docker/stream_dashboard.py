#!/usr/bin/env python3
"""
Serve a local dashboard showing active remote_docker streams.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import dotenv
except ModuleNotFoundError:
    dotenv = None

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

if dotenv is not None:
    dotenv.load_dotenv(REPO_ROOT / ".env")

from computer_env import (
    DEFAULT_REMOTE_DOCKER_API_TOKEN,
    DEFAULT_REMOTE_DOCKER_POOL_FILE,
    DEFAULT_REMOTE_DOCKER_REQUEST_TIMEOUT,
    DEFAULT_REMOTE_DOCKER_WORKER_URLS,
)
from computer_env.backends.remote_docker.worker_client import RemoteDockerWorkerClient

DELETED_SESSION_DISPLAY_SECONDS = 90


_SESSION_HISTORY: dict[tuple[str, str], dict[str, object]] = {}
_SESSION_HISTORY_LOCK = threading.Lock()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve a local dashboard showing active remote_docker streams.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--pool-file", default=DEFAULT_REMOTE_DOCKER_POOL_FILE)
    parser.add_argument("--api-token", default=DEFAULT_REMOTE_DOCKER_API_TOKEN)
    parser.add_argument("--request-timeout", type=int, default=DEFAULT_REMOTE_DOCKER_REQUEST_TIMEOUT)
    return parser.parse_args()


def build_client(args: argparse.Namespace) -> RemoteDockerWorkerClient:
    return RemoteDockerWorkerClient(
        worker_urls=DEFAULT_REMOTE_DOCKER_WORKER_URLS,
        pool_file=args.pool_file,
        api_token=args.api_token,
        request_timeout=args.request_timeout,
    )


def _format_age(timestamp: object | None) -> str:
    if not isinstance(timestamp, (int, float)):
        return "-"
    seconds = max(0, int(time.time() - timestamp))
    if seconds < 60:
        return f"{seconds}s ago"
    minutes, rem = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {rem}s ago"
    hours, rem_minutes = divmod(minutes, 60)
    return f"{hours}h {rem_minutes}m ago"


def _status_class(status: str) -> str:
    normalized = status.lower()
    if normalized == "ready":
        return "ready"
    if normalized == "creating":
        return "creating"
    if normalized == "deleting":
        return "deleting"
    if normalized == "deleted":
        return "deleted"
    if normalized == "failed":
        return "failed"
    return "unknown"


def _snapshot_sessions(client: RemoteDockerWorkerClient) -> list[dict[str, object]]:
    now = time.time()
    live_sessions = client.list_sessions()
    live_keys: set[tuple[str, str]] = set()

    with _SESSION_HISTORY_LOCK:
        for session in live_sessions:
            base_url = str(session.get("base_url", ""))
            session_id = str(session.get("session_id", ""))
            if not base_url or not session_id:
                continue
            key = (base_url, session_id)
            live_keys.add(key)
            previous = _SESSION_HISTORY.get(key, {})
            merged = dict(previous)
            merged.update(session)
            merged["last_seen_at"] = now
            if merged.get("first_seen_at") is None:
                merged["first_seen_at"] = now
            _SESSION_HISTORY[key] = merged

        for key, cached in list(_SESSION_HISTORY.items()):
            if key in live_keys:
                continue
            if cached.get("status") != "deleted":
                cached = dict(cached)
                cached["status"] = "deleted"
                cached["deleted_at"] = now
                _SESSION_HISTORY[key] = cached
            deleted_at = _SESSION_HISTORY[key].get("deleted_at")
            if isinstance(deleted_at, (int, float)) and deleted_at <= now - DELETED_SESSION_DISPLAY_SECONDS:
                _SESSION_HISTORY.pop(key, None)

        sessions = list(_SESSION_HISTORY.values())

    return sorted(sessions, key=lambda item: (str(item.get("worker_id", "")), str(item.get("session_id", ""))))


def render_dashboard(sessions: list[dict[str, object]]) -> str:
    cards = []
    for session in sessions:
        stream_url = str(session.get("stream_url", ""))
        status = str(session.get("status", "unknown"))
        status_class = _status_class(status)
        deleted_note = ""
        if status == "deleted":
            deleted_note = f"<p><strong>Deleted:</strong> {_format_age(session.get('deleted_at'))}</p>"
        stream_block = (
            f'<iframe src="{html.escape(stream_url)}" loading="lazy"></iframe>'
            if stream_url and status != "deleted"
            else '<div class="empty-stream">Session no longer has a live stream.</div>'
        )
        cards.append(
            f"""
            <section class="card">
              <header>
                <strong>{html.escape(str(session.get("app_name") or session.get("session_id")))}</strong>
                <div class="meta">
                  <span>{html.escape(str(session.get("worker_id", "")))}</span>
                  <span class="status {status_class}">{html.escape(status)}</span>
                </div>
              </header>
              <p><strong>Session:</strong> {html.escape(str(session.get("session_id", "")))}</p>
              <p><strong>Stream:</strong> {html.escape(stream_url or "-")}</p>
              <p><strong>Last seen:</strong> {_format_age(session.get("last_seen_at"))}</p>
              {deleted_note}
              {stream_block}
            </section>
            """
        )
    if not cards:
        cards.append("<p>No active remote sessions.</p>")
    return f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8">
        <meta http-equiv="refresh" content="15">
        <title>OpenComputer Stream Dashboard</title>
        <style>
          body {{ font-family: sans-serif; margin: 0; padding: 24px; background: #f5f5f5; }}
          .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(540px, 1fr)); gap: 20px; }}
          .card {{ background: white; border: 1px solid #ddd; border-radius: 10px; padding: 12px; }}
          header {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 8px; }}
          .meta {{ display: flex; align-items: center; gap: 8px; }}
          .status {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 700; text-transform: uppercase; }}
          .status.ready {{ background: #dff7e5; color: #146c2e; }}
          .status.creating {{ background: #e8f0fe; color: #174ea6; }}
          .status.deleting {{ background: #fff4d6; color: #8a5a00; }}
          .status.deleted {{ background: #eceff1; color: #455a64; }}
          .status.failed {{ background: #fde7e9; color: #b3261e; }}
          .status.unknown {{ background: #f1f3f4; color: #3c4043; }}
          iframe {{ width: 100%; height: 420px; border: 1px solid #ccc; }}
          p {{ word-break: break-all; font-size: 12px; color: #555; }}
          .empty-stream {{ display: flex; align-items: center; justify-content: center; height: 420px; border: 1px dashed #bbb; color: #666; background: #fafafa; }}
        </style>
      </head>
      <body>
        <h1>OpenComputer Remote Streams</h1>
        <div class="grid">
          {''.join(cards)}
        </div>
      </body>
    </html>
    """


def render_json(sessions: list[dict[str, object]]) -> str:
    return json.dumps({"sessions": sessions}, indent=2)


def main() -> None:
    args = parse_args()
    client = build_client(args)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            sessions = _snapshot_sessions(client)
            if self.path == "/api/sessions":
                body = render_json(sessions).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = render_dashboard(sessions).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Dashboard listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
