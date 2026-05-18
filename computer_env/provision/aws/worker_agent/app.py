#!/usr/bin/env python3
"""
Running on a remote worker machine, it provides a set of HTTP APIs externally, enabling the local controller to remotely create Docker desktop containers, execute commands, read and write files, take screenshots, and obtain noVNC access addresses.

It automatically cleans up expired sessions and exposes session status so the
controller can poll until a desktop becomes ready.

Request methods:
# GET  /healthz
# GET  /capacity
# GET  /sessions
# GET  /sessions/{session_id}
# GET  /sessions/{session_id}/stream-url

# POST /sessions
# POST /sessions/{session_id}/exec
# POST /sessions/{session_id}/files/write
# POST /sessions/{session_id}/files/read
# POST /sessions/{session_id}/files/remove
# POST /sessions/{session_id}/screenshot

# DELETE /sessions/{session_id}
"""

from __future__ import annotations

import base64
import json
import os
import shlex
import socket
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlparse

DOCKER_DBUS_ADDRESS = "unix:path=/tmp/runtime-user/bus"
DOCKER_TMPFS_MOUNTS = (
    "/tmp:rw,exec,nosuid,size=2g",
    "/home/user:rw,exec,nosuid,uid=1000,gid=1000,mode=700,size=4g",
)
WORKER_PORT = int(os.getenv("GUI_SYNTH_WORKER_PORT", "8088"))
API_TOKEN = os.getenv("GUI_SYNTH_WORKER_API_TOKEN", "")
DEFAULT_IMAGE = os.getenv("GUI_SYNTH_WORKER_DEFAULT_IMAGE", "")
MAX_SESSIONS = int(os.getenv("GUI_SYNTH_WORKER_MAX_SESSIONS", "2"))
DEFAULT_PLATFORM = os.getenv("GUI_SYNTH_WORKER_DOCKER_PLATFORM", "linux/amd64")
NOVNC_PORT_START = int(os.getenv("GUI_SYNTH_WORKER_NOVNC_PORT_START", "61000"))
NOVNC_PORT_END = int(os.getenv("GUI_SYNTH_WORKER_NOVNC_PORT_END", "61199"))
SESSION_CLEANUP_INTERVAL_SECONDS = 15
FAILED_SESSION_RETENTION_SECONDS = int(os.getenv("GUI_SYNTH_WORKER_FAILED_SESSION_RETENTION", "60"))
DELETED_SESSION_RETENTION_SECONDS = int(os.getenv("GUI_SYNTH_WORKER_DELETED_SESSION_RETENTION", "30"))


def _looks_like_placeholder(value: str) -> bool:
    return value.startswith("${") and value.endswith("}")


def _http_get(url: str, *, timeout: float = 2.0, headers: dict[str, str] | None = None) -> str:
    request = urllib_request.Request(url, headers=headers or {})
    with urllib_request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8").strip()


def _aws_imds_get(path: str, timeout: float = 2.0) -> str:
    token_request = urllib_request.Request(
        "http://169.254.169.254/latest/api/token",
        method="PUT",
        headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
    )
    with urllib_request.urlopen(token_request, timeout=timeout) as response:
        token = response.read().decode("utf-8")
    request = urllib_request.Request(
        f"http://169.254.169.254/latest/meta-data/{path.lstrip('/')}",
        headers={"X-aws-ec2-metadata-token": token},
    )
    with urllib_request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8").strip()


def _tencent_imds_get(path: str, timeout: float = 2.0) -> str:
    return _http_get(
        f"http://metadata.tencentyun.com/latest/meta-data/{path.lstrip('/')}",
        timeout=timeout,
    )


def _resolve_runtime_value(
    env_name: str,
    metadata_resolvers: tuple[Callable[[], str], ...],
) -> str:
    raw = os.getenv(env_name, "").strip()
    if raw and not _looks_like_placeholder(raw):
        return raw
    for resolver in metadata_resolvers:
        try:
            value = resolver()
        except (urllib_error.URLError, OSError, TimeoutError):
            continue
        if value:
            return value
    return ""


PUBLIC_HOST = _resolve_runtime_value(
    "GUI_SYNTH_WORKER_PUBLIC_HOST",
    (
        lambda: _aws_imds_get("public-ipv4"),
        lambda: _tencent_imds_get("public-ipv4"),
    ),
)
INSTANCE_ID = _resolve_runtime_value(
    "GUI_SYNTH_WORKER_INSTANCE_ID",
    (
        lambda: _aws_imds_get("instance-id"),
        lambda: _tencent_imds_get("instance-id"),
    ),
)


@dataclass
class SessionRecord:
    session_id: str
    container_id: str | None
    container_name: str
    stream_port: int
    width: int
    height: int
    created_at: float
    expires_at: float
    app_name: str | None
    image: str
    metadata: dict[str, str]
    ready_timeout: int
    status: str = "creating"
    last_error: str | None = None
    ready_at: float | None = None
    deleted_at: float | None = None
    cancel_requested: bool = False

    @property
    def stream_url(self) -> str:
        host = PUBLIC_HOST or "127.0.0.1"
        return f"http://{host}:{self.stream_port}/vnc.html?autoconnect=true&resize=scale"


SESSIONS: dict[str, SessionRecord] = {}
SESSIONS_LOCK = threading.Lock()


def _with_desktop_env(command: str) -> str:
    return (
        f"export DBUS_SESSION_BUS_ADDRESS=${{DBUS_SESSION_BUS_ADDRESS:-{shlex.quote(DOCKER_DBUS_ADDRESS)}}}; "
        f"{command}"
    )


def _run_subprocess(
    argv: list[str],
    timeout: int | None = None,
    *,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess:
    effective_timeout = None if timeout == 0 else timeout
    return subprocess.run(
        argv,
        input=input_bytes,
        capture_output=True,
        timeout=effective_timeout,
        check=False,
    )


def _run_checked(
    argv: list[str],
    timeout: int | None = None,
    *,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess:
    result = _run_subprocess(argv, timeout=timeout, input_bytes=input_bytes)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        stdout = result.stdout.decode(errors="replace").strip()
        raise RuntimeError(stderr or stdout or f"Command failed: {' '.join(argv)}")
    return result


def _container_exists(container_id: str) -> bool:
    result = _run_subprocess(["docker", "ps", "-aq", "--filter", f"id={container_id}"], timeout=10)
    return bool(result.stdout.decode().strip())


def _remove_container_if_present(container_id: str) -> None:
    result = _run_subprocess(["docker", "rm", "-f", container_id], timeout=20)
    if result.returncode != 0 and _container_exists(container_id):
        raise RuntimeError(result.stderr.decode(errors="replace").strip() or "Failed to remove container")


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def _session_counts_toward_capacity(session: SessionRecord) -> bool:
    return session.status in {"creating", "ready", "deleting"}


def _allocate_stream_port_locked() -> int:
    used = {session.stream_port for session in SESSIONS.values() if session.status != "deleted"}
    for port in range(NOVNC_PORT_START, NOVNC_PORT_END + 1):
        if port in used:
            continue
        if _is_port_free(port):
            return port
    raise RuntimeError("No free noVNC ports are available on this worker.")


def _current_session_count_locked() -> int:
    return sum(1 for session in SESSIONS.values() if _session_counts_toward_capacity(session))


def _reserve_session_slot(payload: dict[str, Any]) -> SessionRecord:
    resolution = payload.get("resolution", {}) or {}
    width = int(resolution.get("width", 1920))
    height = int(resolution.get("height", 1080))
    image = str(payload.get("image") or DEFAULT_IMAGE)
    if not image:
        raise RuntimeError("No docker image was specified for the remote worker session.")
    now = time.time()
    with SESSIONS_LOCK:
        if _current_session_count_locked() >= MAX_SESSIONS:
            raise RuntimeError("Worker is at capacity.")
        session_id = uuid.uuid4().hex
        session = SessionRecord(
            session_id=session_id,
            container_id=None,
            container_name=f"opencomputer-{session_id[:12]}",
            stream_port=_allocate_stream_port_locked(),
            width=width,
            height=height,
            created_at=now,
            expires_at=now + int(payload.get("timeout", 3600)),
            app_name=str(payload.get("app_name")) if payload.get("app_name") else None,
            image=image,
            metadata={str(key): str(value) for key, value in dict(payload.get("metadata", {})).items()},
            ready_timeout=int(payload.get("ready_timeout", 120)),
        )
        SESSIONS[session_id] = session
        return session


def _get_session_or_raise(session_id: str, *, require_ready: bool = False) -> SessionRecord:
    with SESSIONS_LOCK:
        session = SESSIONS.get(session_id)
    if session is None:
        raise KeyError(session_id)
    if require_ready and session.status != "ready":
        raise RuntimeError(f"Session {session_id} is not ready (status={session.status}).")
    return session


def _wait_ready(container_id: str, stream_port: int, timeout: int) -> None:
    deadline = time.time() + timeout
    last_error = "desktop not ready"
    while time.time() < deadline:
        result = _run_subprocess(["docker", "ps", "-q", "-f", f"id={container_id}"], timeout=10)
        if not result.stdout.decode().strip():
            raise RuntimeError("Container exited before becoming ready.")
        check = _run_subprocess(
            [
                "docker",
                "exec",
                container_id,
                "bash",
                "-lc",
                _with_desktop_env(
                    "DISPLAY=:0 xset q >/dev/null 2>&1 && "
                    "pgrep -f x11vnc >/dev/null 2>&1 && "
                    "pgrep -f websockify >/dev/null 2>&1"
                ),
            ],
            timeout=10,
        )
        if check.returncode == 0:
            try:
                with socket.create_connection(("127.0.0.1", stream_port), timeout=1):
                    return
            except OSError as exc:
                last_error = str(exc)
        else:
            last_error = (
                check.stderr.decode(errors="replace").strip()
                or check.stdout.decode(errors="replace").strip()
            )
        time.sleep(1)
    raise RuntimeError(f"Container did not become ready: {last_error}")


def _build_docker_run_argv(payload: dict[str, Any], container_name: str, stream_port: int) -> list[str]:
    resolution = payload.get("resolution", {}) or {}
    width = int(resolution.get("width", 1920))
    height = int(resolution.get("height", 1080))
    image = str(payload.get("image") or DEFAULT_IMAGE)
    if not image:
        raise RuntimeError("No docker image was specified for the remote worker session.")
    argv = [
        "docker",
        "run",
        "-d",
        "--rm",
        "--name",
        container_name,
        "--platform",
        str(payload.get("docker_platform") or DEFAULT_PLATFORM),
        "--shm-size",
        str(payload.get("docker_shm_size") or "2g"),
        "--security-opt",
        "seccomp=unconfined",
        "-p",
        f"0.0.0.0:{stream_port}:6080",
        "--label",
        "opencomputer.managed=true",
        "--label",
        "opencomputer.backend=remote_docker",
    ]
    for mount in DOCKER_TMPFS_MOUNTS:
        argv.extend(["--tmpfs", mount])
    if payload.get("docker_memory"):
        argv.extend(["--memory", str(payload["docker_memory"])])
    if payload.get("docker_cpus"):
        argv.extend(["--cpus", str(payload["docker_cpus"])])
    for key, value in dict(payload.get("metadata", {})).items():
        argv.extend(["--label", f"opencomputer.meta.{key}={value}"])
    argv.extend(
        [
            "-e",
            f"SCREEN_WIDTH={width}",
            "-e",
            f"SCREEN_HEIGHT={height}",
            "-e",
            f"ENV_TIMEOUT_SECONDS={int(payload.get('timeout', 3600))}",
            image,
        ]
    )
    return argv


def _serialize_session(session: SessionRecord) -> dict[str, Any]:
    return asdict(session) | {"stream_url": session.stream_url}


def _mark_session_deleted_locked(session: SessionRecord) -> None:
    session.status = "deleted"
    session.deleted_at = time.time()
    session.container_id = None
    session.last_error = None if session.cancel_requested else session.last_error


def _async_create_session(session_id: str, payload: dict[str, Any]) -> None:
    container_id: str | None = None
    try:
        with SESSIONS_LOCK:
            session = SESSIONS.get(session_id)
            if session is None:
                return
            if session.cancel_requested:
                _mark_session_deleted_locked(session)
                return
            run_argv = _build_docker_run_argv(payload, session.container_name, session.stream_port)
            ready_timeout = session.ready_timeout
            stream_port = session.stream_port
        result = _run_checked(run_argv, timeout=90)
        container_id = result.stdout.decode().strip()
        with SESSIONS_LOCK:
            session = SESSIONS.get(session_id)
            if session is None:
                raise RuntimeError("session disappeared during creation")
            session.container_id = container_id
            if session.cancel_requested:
                session.status = "deleting"
        if _get_session_or_raise(session_id).cancel_requested:
            _remove_container_if_present(container_id)
            with SESSIONS_LOCK:
                session = SESSIONS.get(session_id)
                if session is not None:
                    _mark_session_deleted_locked(session)
            return
        _wait_ready(container_id, stream_port, ready_timeout)
        with SESSIONS_LOCK:
            session = SESSIONS.get(session_id)
            if session is None:
                raise RuntimeError("session disappeared before ready")
            if session.cancel_requested:
                session.status = "deleting"
            else:
                session.status = "ready"
                session.ready_at = time.time()
                session.last_error = None
                return
        _remove_container_if_present(container_id)
        with SESSIONS_LOCK:
            session = SESSIONS.get(session_id)
            if session is not None:
                _mark_session_deleted_locked(session)
    except Exception as exc:
        if container_id:
            try:
                _remove_container_if_present(container_id)
            except Exception:
                pass
        with SESSIONS_LOCK:
            session = SESSIONS.get(session_id)
            if session is None:
                return
            session.container_id = None
            if session.cancel_requested:
                _mark_session_deleted_locked(session)
            else:
                session.status = "failed"
                session.last_error = str(exc)
                session.deleted_at = time.time()


def _cleanup_expired_sessions_loop() -> None:
    while True:
        time.sleep(SESSION_CLEANUP_INTERVAL_SECONDS)
        now = time.time()
        with SESSIONS_LOCK:
            expired = [
                session_id
                for session_id, session in SESSIONS.items()
                if session.expires_at <= now and session.status in {"creating", "ready", "deleting"}
            ]
        for session_id in expired:
            try:
                delete_session(session_id)
            except Exception:
                continue
        with SESSIONS_LOCK:
            stale_ids = [
                session_id
                for session_id, session in SESSIONS.items()
                if (
                    session.status == "failed"
                    and session.deleted_at is not None
                    and session.deleted_at <= now - FAILED_SESSION_RETENTION_SECONDS
                )
                or (
                    session.status == "deleted"
                    and session.deleted_at is not None
                    and session.deleted_at <= now - DELETED_SESSION_RETENTION_SECONDS
                )
            ]
            for session_id in stale_ids:
                SESSIONS.pop(session_id, None)


def create_session(payload: dict[str, Any]) -> dict[str, Any]:
    session = _reserve_session_slot(payload)
    creator = threading.Thread(
        target=_async_create_session,
        args=(session.session_id, dict(payload)),
        daemon=True,
    )
    creator.start()
    return {
        "session_id": session.session_id,
        "status": session.status,
        "worker_instance_id": INSTANCE_ID,
    }


def get_session(session_id: str) -> dict[str, Any]:
    session = _get_session_or_raise(session_id)
    return _serialize_session(session)


def list_sessions() -> list[dict[str, Any]]:
    with SESSIONS_LOCK:
        sessions = [_serialize_session(session) for session in SESSIONS.values() if session.status != "deleted"]
    return sessions


def delete_session(session_id: str) -> None:
    with SESSIONS_LOCK:
        session = SESSIONS.get(session_id)
        if session is None:
            return
        session.cancel_requested = True
        if session.status == "failed":
            _mark_session_deleted_locked(session)
            return
        if session.status == "deleted":
            return
        container_id = session.container_id
        session.status = "deleting"
    if container_id:
        _remove_container_if_present(container_id)
    with SESSIONS_LOCK:
        session = SESSIONS.get(session_id)
        if session is not None:
            _mark_session_deleted_locked(session)


def exec_command(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    session = _get_session_or_raise(session_id, require_ready=True)
    command = str(payload["command"])
    timeout = payload.get("timeout")
    background = bool(payload.get("background", False))
    argv = ["docker", "exec"]
    if background:
        argv.append("-d")
    argv.extend([session.container_id, "bash", "-lc", _with_desktop_env(command)])
    result = _run_subprocess(argv, timeout=timeout)
    body = {
        "stdout": result.stdout.decode(errors="replace"),
        "stderr": result.stderr.decode(errors="replace"),
        "exit_code": result.returncode,
    }
    if background:
        body["pid"] = None
    return body


def write_file(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    session = _get_session_or_raise(session_id, require_ready=True)
    path = str(payload["path"])
    encoding = str(payload.get("encoding", "text"))
    content = payload.get("content", "")
    if encoding == "base64":
        data = base64.b64decode(str(content).encode("ascii"))
    else:
        data = str(content).encode("utf-8")
    parent = str(Path(path).parent)
    _run_checked(
        [
            "docker",
            "exec",
            "--user",
            "root",
            session.container_id,
            "bash",
            "-lc",
            f"mkdir -p {shlex.quote(parent)}",
        ],
        timeout=10,
    )
    _run_checked(
        [
            "docker",
            "exec",
            "-i",
            "--user",
            "root",
            session.container_id,
            "bash",
            "-lc",
            f"cat > {shlex.quote(path)}",
        ],
        input_bytes=data,
        timeout=30,
    )
    _run_subprocess(
        [
            "docker",
            "exec",
            "--user",
            "root",
            session.container_id,
            "bash",
            "-lc",
            f"chown user:user {shlex.quote(path)} 2>/dev/null || true",
        ],
        timeout=10,
    )
    return {"ok": True}


def read_file(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    session = _get_session_or_raise(session_id, require_ready=True)
    path = str(payload["path"])
    format_name = str(payload.get("format", "text"))
    result = _run_subprocess(
        [
            "docker",
            "exec",
            session.container_id,
            "bash",
            "-lc",
            _with_desktop_env(f"cat {shlex.quote(path)}"),
        ],
        timeout=30,
    )
    if result.returncode != 0:
        raise FileNotFoundError(path)
    data = result.stdout
    if format_name in {"bytes", "binary"}:
        return {
            "encoding": "base64",
            "content": base64.b64encode(data).decode("ascii"),
        }
    return {
        "encoding": "text",
        "content": data.decode("utf-8"),
    }


def remove_file(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    session = _get_session_or_raise(session_id, require_ready=True)
    path = str(payload["path"])
    _run_checked(
        [
            "docker",
            "exec",
            "--user",
            "root",
            session.container_id,
            "bash",
            "-lc",
            f"rm -f {shlex.quote(path)}",
        ],
        timeout=10,
    )
    return {"ok": True}


def screenshot(session_id: str) -> bytes:
    session = _get_session_or_raise(session_id, require_ready=True)
    screenshot_path = f"/tmp/opencomputer-screenshot-{uuid.uuid4().hex}.png"
    try:
        _run_checked(
            [
                "docker",
                "exec",
                session.container_id,
                "bash",
                "-lc",
                _with_desktop_env(f"DISPLAY=:0 scrot --pointer {shlex.quote(screenshot_path)}"),
            ],
            timeout=20,
        )
        result = _run_checked(
            [
                "docker",
                "exec",
                session.container_id,
                "bash",
                "-lc",
                _with_desktop_env(f"cat {shlex.quote(screenshot_path)}"),
            ],
            timeout=30,
        )
        return result.stdout
    finally:
        _run_subprocess(
            [
                "docker",
                "exec",
                session.container_id,
                "bash",
                "-lc",
                _with_desktop_env(f"rm -f {shlex.quote(screenshot_path)}"),
            ],
            timeout=10,
        )


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "OpenComputerWorker/0.1"

    def _authenticate(self) -> bool:
        if not API_TOKEN:
            return True
        header = self.headers.get("Authorization", "")
        return header == f"Bearer {API_TOKEN}"

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_bytes(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _route(self) -> tuple[str, list[str]]:
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        return parsed.path, parts

    def do_GET(self) -> None:
        if not self._authenticate():
            self._write_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        path, parts = self._route()
        try:
            if path == "/healthz":
                self._write_json(HTTPStatus.OK, {"ok": True, "instance_id": INSTANCE_ID})
                return
            if path == "/capacity":
                with SESSIONS_LOCK:
                    current = _current_session_count_locked()
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "current_sessions": current,
                        "max_sessions": MAX_SESSIONS,
                        "instance_id": INSTANCE_ID,
                    },
                )
                return
            if path == "/sessions":
                self._write_json(HTTPStatus.OK, {"sessions": list_sessions()})
                return
            if len(parts) == 2 and parts[0] == "sessions":
                self._write_json(HTTPStatus.OK, get_session(parts[1]))
                return
            if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "stream-url":
                session = _get_session_or_raise(parts[1])
                self._write_json(HTTPStatus.OK, {"stream_url": session.stream_url})
                return
        except KeyError:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "session not found"})
            return
        except RuntimeError as exc:
            self._write_json(HTTPStatus.CONFLICT, {"error": str(exc)})
            return
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._authenticate():
            self._write_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        path, parts = self._route()
        try:
            if path == "/sessions":
                payload = self._read_json()
                self._write_json(HTTPStatus.ACCEPTED, create_session(payload))
                return
            if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "exec":
                self._write_json(HTTPStatus.OK, exec_command(parts[1], self._read_json()))
                return
            if len(parts) == 4 and parts[0] == "sessions" and parts[2] == "files":
                action = parts[3]
                payload = self._read_json()
                if action == "write":
                    self._write_json(HTTPStatus.OK, write_file(parts[1], payload))
                    return
                if action == "read":
                    self._write_json(HTTPStatus.OK, read_file(parts[1], payload))
                    return
                if action == "remove":
                    self._write_json(HTTPStatus.OK, remove_file(parts[1], payload))
                    return
            if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "screenshot":
                self._write_bytes(HTTPStatus.OK, screenshot(parts[1]), "image/png")
                return
        except KeyError:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "session not found"})
            return
        except FileNotFoundError as exc:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        except RuntimeError as exc:
            message = str(exc)
            if "capacity" in message.lower() or "not ready" in message.lower():
                status = HTTPStatus.CONFLICT
            else:
                status = HTTPStatus.BAD_REQUEST
            self._write_json(status, {"error": message})
            return
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_DELETE(self) -> None:
        if not self._authenticate():
            self._write_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        _path, parts = self._route()
        try:
            if len(parts) == 2 and parts[0] == "sessions":
                delete_session(parts[1])
                self._write_json(HTTPStatus.OK, {"ok": True})
                return
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    janitor = threading.Thread(target=_cleanup_expired_sessions_loop, daemon=True)
    janitor.start()
    server = ThreadingHTTPServer(("0.0.0.0", WORKER_PORT), RequestHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
