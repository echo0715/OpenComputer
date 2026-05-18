from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CAPACITY_POLL_INTERVAL_SECONDS = max(
    0.1,
    float(os.getenv("REMOTE_DOCKER_CAPACITY_POLL_INTERVAL", "2.0")),
)
DEFAULT_SESSION_STATUS_POLL_INTERVAL_SECONDS = max(
    0.1,
    float(os.getenv("REMOTE_DOCKER_SESSION_STATUS_POLL_INTERVAL", "1.0")),
)


class RemoteDockerAPIError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, payload: Any = None) -> None:
        self.status = status
        self.payload = payload
        super().__init__(message)


@dataclass(frozen=True)
class WorkerRecord:
    worker_id: str
    base_url: str
    instance_id: str | None = None
    public_ip: str | None = None
    region: str | None = None
    max_sessions: int | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class RemoteSessionHandle:
    session_id: str
    worker_id: str
    base_url: str
    stream_url: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RemoteFleetCapacity:
    total_workers: int
    healthy_workers: int
    total_max_sessions: int
    total_current_sessions: int
    total_available_sessions: int
    unreachable_workers: tuple[str, ...]


class RemoteDockerWorkerClient:
    def __init__(
        self,
        *,
        worker_urls: tuple[str, ...],
        pool_file: str,
        api_token: str | None,
        request_timeout: int,
        session_create_timeout: int | None = None,
        session_acquire_timeout: int | None = None,
        command_timeout_grace_seconds: int | None = None,
        worker_cooldown_seconds: int | None = None,
    ) -> None:
        self._worker_urls = tuple(url.rstrip("/") for url in worker_urls if url.strip())
        self._pool_file = Path(pool_file).expanduser()
        self._api_token = api_token
        self._request_timeout = request_timeout
        self._session_create_timeout = session_create_timeout if session_create_timeout is not None else 240
        self._session_acquire_timeout = session_acquire_timeout if session_acquire_timeout is not None else 180
        self._command_timeout_grace_seconds = (
            command_timeout_grace_seconds if command_timeout_grace_seconds is not None else 30
        )
        self._worker_cooldown_seconds = worker_cooldown_seconds if worker_cooldown_seconds is not None else 15
        self._capacity_poll_interval = DEFAULT_CAPACITY_POLL_INTERVAL_SECONDS
        self._session_status_poll_interval = DEFAULT_SESSION_STATUS_POLL_INTERVAL_SECONDS
        self._worker_cooldowns: dict[str, float] = {}

    def discover_workers(self) -> list[WorkerRecord]:
        if self._worker_urls:
            return [
                WorkerRecord(
                    worker_id=f"explicit-{index + 1}",
                    base_url=base_url,
                )
                for index, base_url in enumerate(self._worker_urls)
            ]

        if not self._pool_file.exists():
            raise RuntimeError(
                "No remote worker pool file was found. "
                f"Expected: {self._pool_file}. "
                "Run the remote worker launch step first or set REMOTE_DOCKER_WORKER_URLS."
            )

        payload = json.loads(self._pool_file.read_text())
        workers: list[WorkerRecord] = []
        for index, item in enumerate(payload.get("workers", [])):
            base_url = str(item.get("base_url", "")).strip().rstrip("/")
            if not base_url:
                continue
            workers.append(
                WorkerRecord(
                    worker_id=str(item.get("worker_id") or item.get("instance_id") or f"worker-{index + 1}"),
                    base_url=base_url,
                    instance_id=str(item.get("instance_id")) if item.get("instance_id") else None,
                    public_ip=str(item.get("public_ip")) if item.get("public_ip") else None,
                    region=str(item.get("region")) if item.get("region") else None,
                    max_sessions=int(item["max_sessions"]) if item.get("max_sessions") is not None else None,
                    metadata=dict(item.get("metadata", {})),
                )
            )

        if not workers:
            raise RuntimeError(
                f"Remote worker pool file exists but contains no workers: {self._pool_file}"
            )
        return workers

    def _build_request(
        self,
        method: str,
        base_url: str,
        path: str,
        payload: dict[str, Any] | None,
        accept: str,
    ) -> urllib.request.Request:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": accept}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if self._api_token:
            headers["Authorization"] = f"Bearer {self._api_token}"
        return urllib.request.Request(
            f"{base_url.rstrip('/')}{path}",
            data=data,
            headers=headers,
            method=method,
        )

    def request_json(
        self,
        method: str,
        base_url: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        request = self._build_request(method, base_url, path, payload, "application/json")
        effective_timeout = self._request_timeout if timeout is None else timeout
        try:
            with urllib.request.urlopen(request, timeout=effective_timeout) as response:
                raw = response.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body) if body else {}
            except json.JSONDecodeError:
                parsed = {"error": body} if body else {}
            message = str(parsed.get("error") or parsed.get("message") or body or exc.reason)
            raise RemoteDockerAPIError(message, status=exc.code, payload=parsed) from exc
        except urllib.error.URLError as exc:
            raise RemoteDockerAPIError(
                f"Failed to reach remote worker at {base_url}: {exc.reason}"
            ) from exc

    def request_bytes(
        self,
        method: str,
        base_url: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: int | None = None,
    ) -> bytes:
        request = self._build_request(method, base_url, path, payload, "*/*")
        effective_timeout = self._request_timeout if timeout is None else timeout
        try:
            with urllib.request.urlopen(request, timeout=effective_timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RemoteDockerAPIError(
                f"Remote worker returned HTTP {exc.code} for {path}: {body or exc.reason}",
                status=exc.code,
                payload=body,
            ) from exc
        except urllib.error.URLError as exc:
            raise RemoteDockerAPIError(
                f"Failed to reach remote worker at {base_url}: {exc.reason}"
            ) from exc

    def _worker_available(self, worker_id: str) -> bool:
        expires_at = self._worker_cooldowns.get(worker_id)
        if expires_at is None:
            return True
        if expires_at <= time.time():
            self._worker_cooldowns.pop(worker_id, None)
            return True
        return False

    def _mark_worker_unhealthy(self, worker_id: str) -> None:
        self._worker_cooldowns[worker_id] = time.time() + self._worker_cooldown_seconds

    def choose_worker(self) -> WorkerRecord:
        workers = self.discover_workers()
        ranked, successful_capacity_checks, last_error = self._rank_workers_by_capacity(workers)
        if ranked:
            return ranked[0][2]
        if successful_capacity_checks == 0 and last_error is not None:
            raise RuntimeError(f"No usable remote workers were found: {last_error}") from last_error
        raise RuntimeError("No remote workers have free capacity.")

    def summarize_capacity(self) -> RemoteFleetCapacity:
        workers = self.discover_workers()
        healthy_workers = 0
        total_max_sessions = 0
        total_current_sessions = 0
        unreachable_workers: list[str] = []
        last_error: Exception | None = None
        for worker in workers:
            try:
                capacity = self.request_json("GET", worker.base_url, "/capacity")
            except Exception as exc:
                last_error = exc
                unreachable_workers.append(worker.worker_id)
                continue
            healthy_workers += 1
            max_sessions = int(capacity.get("max_sessions", 0))
            current_sessions = int(capacity.get("current_sessions", 0))
            total_max_sessions += max_sessions
            total_current_sessions += current_sessions
        if healthy_workers == 0 and last_error is not None:
            raise RuntimeError(f"No usable remote workers were found: {last_error}") from last_error
        return RemoteFleetCapacity(
            total_workers=len(workers),
            healthy_workers=healthy_workers,
            total_max_sessions=total_max_sessions,
            total_current_sessions=total_current_sessions,
            total_available_sessions=max(0, total_max_sessions - total_current_sessions),
            unreachable_workers=tuple(unreachable_workers),
        )

    def _rank_workers_by_capacity(
        self,
        workers: list[WorkerRecord],
    ) -> tuple[list[tuple[int, int, WorkerRecord]], int, Exception | None]:
        ranked: list[tuple[int, int, WorkerRecord]] = []
        successful_capacity_checks = 0
        last_error: Exception | None = None
        for worker in workers:
            if not self._worker_available(worker.worker_id):
                continue
            try:
                capacity = self.request_json("GET", worker.base_url, "/capacity")
            except Exception as exc:
                self._mark_worker_unhealthy(worker.worker_id)
                last_error = exc
                continue
            successful_capacity_checks += 1
            max_sessions = int(capacity.get("max_sessions", 0))
            current_sessions = int(capacity.get("current_sessions", 0))
            available = max_sessions - current_sessions
            if available <= 0:
                continue
            ranked.append((-available, current_sessions, worker))
        ranked.sort(key=lambda item: (item[0], item[1], item[2].worker_id))
        return ranked, successful_capacity_checks, last_error

    def _get_session_status(
        self,
        worker: WorkerRecord,
        session_id: str,
    ) -> dict[str, Any]:
        return self.request_json("GET", worker.base_url, f"/sessions/{session_id}")

    def _wait_for_session_ready(
        self,
        worker: WorkerRecord,
        session_id: str,
        metadata: dict[str, str],
    ) -> RemoteSessionHandle:
        deadline = time.time() + self._session_create_timeout
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                status_payload = self._get_session_status(worker, session_id)
            except RemoteDockerAPIError as exc:
                last_error = exc
                if exc.status == 404:
                    time.sleep(self._session_status_poll_interval)
                    continue
                raise
            status = str(status_payload.get("status", "unknown"))
            if status == "ready":
                stream_url = str(status_payload["stream_url"])
                return RemoteSessionHandle(
                    session_id=session_id,
                    worker_id=worker.worker_id,
                    base_url=worker.base_url,
                    stream_url=stream_url,
                    metadata=dict(metadata),
                )
            if status == "failed":
                reason = str(status_payload.get("last_error") or "unknown worker error")
                try:
                    self.delete_session(worker.base_url, session_id)
                except Exception:
                    pass
                raise RuntimeError(
                    f"Remote session {session_id} failed to become ready on {worker.worker_id}: {reason}"
                )
            if status == "deleted":
                raise RuntimeError(
                    f"Remote session {session_id} was deleted before becoming ready on {worker.worker_id}."
                )
            time.sleep(self._session_status_poll_interval)
        try:
            self.delete_session(worker.base_url, session_id)
        except Exception:
            pass
        raise TimeoutError(
            f"Remote session {session_id} did not become ready within {self._session_create_timeout}s"
        ) from last_error

    def create_session(
        self,
        *,
        image: str,
        resolution: tuple[int, int],
        timeout: int,
        app_name: str | None,
        metadata: dict[str, str] | None,
        docker_platform: str,
        docker_shm_size: str,
        docker_memory: str | None,
        docker_cpus: str | None,
        ready_timeout: int,
    ) -> RemoteSessionHandle:
        payload = {
            "image": image,
            "resolution": {"width": int(resolution[0]), "height": int(resolution[1])},
            "timeout": int(timeout),
            "ready_timeout": int(ready_timeout),
            "app_name": app_name,
            "metadata": metadata or {},
            "docker_platform": docker_platform,
            "docker_shm_size": docker_shm_size,
            "docker_memory": docker_memory,
            "docker_cpus": docker_cpus,
        }
        deadline = time.time() + self._session_acquire_timeout
        while True:
            workers = self.discover_workers()
            ranked, successful_capacity_checks, last_error = self._rank_workers_by_capacity(workers)
            if successful_capacity_checks == 0:
                if last_error is not None:
                    raise RuntimeError(f"No usable remote workers were found: {last_error}") from last_error
                raise RuntimeError("No usable remote workers were found.")

            if not ranked:
                if time.time() >= deadline:
                    raise TimeoutError(
                        "No remote workers had free capacity within "
                        f"{self._session_acquire_timeout}s."
                    )
                time.sleep(self._capacity_poll_interval)
                continue

            saw_capacity_conflict = False
            last_transient_error: Exception | None = None
            for _available, _current_sessions, worker in ranked:
                try:
                    response = self.request_json(
                        "POST",
                        worker.base_url,
                        "/sessions",
                        payload,
                    )
                except RemoteDockerAPIError as exc:
                    if exc.status == 409:
                        saw_capacity_conflict = True
                        continue
                    if exc.status is None or (exc.status is not None and exc.status >= 500):
                        self._mark_worker_unhealthy(worker.worker_id)
                        last_transient_error = exc
                        continue
                    raise
                except Exception as exc:
                    self._mark_worker_unhealthy(worker.worker_id)
                    last_transient_error = exc
                    continue

                session_id = str(response["session_id"])
                return self._wait_for_session_ready(worker, session_id, dict(payload["metadata"]))

            if time.time() >= deadline:
                if last_transient_error is not None:
                    raise RuntimeError(
                        "Failed to create a remote session on available workers within "
                        f"{self._session_acquire_timeout}s: {last_transient_error}"
                    ) from last_transient_error
                raise TimeoutError(
                    "No remote workers had free capacity within "
                    f"{self._session_acquire_timeout}s."
                )
            if last_transient_error is not None and not saw_capacity_conflict:
                time.sleep(self._capacity_poll_interval)
                continue
            time.sleep(self._capacity_poll_interval)

    def list_sessions(self) -> list[dict[str, Any]]:
        all_sessions: list[dict[str, Any]] = []
        for worker in self.discover_workers():
            response = self.request_json("GET", worker.base_url, "/sessions")
            for item in response.get("sessions", []):
                merged = dict(item)
                merged.setdefault("worker_id", worker.worker_id)
                merged.setdefault("base_url", worker.base_url)
                all_sessions.append(merged)
        return all_sessions

    def cleanup_sessions_by_metadata(self, metadata: dict[str, str]) -> list[str]:
        deleted: list[str] = []
        for session in self.list_sessions():
            session_metadata = dict(session.get("metadata", {}))
            if not all(session_metadata.get(key) == value for key, value in metadata.items()):
                continue
            session_id = str(session["session_id"])
            base_url = str(session["base_url"])
            self.delete_session(base_url, session_id)
            deleted.append(session_id)
        return deleted

    def run_command(
        self,
        handle: RemoteSessionHandle,
        *,
        command: str,
        timeout: int | None,
        background: bool,
    ) -> dict[str, Any]:
        payload = {"command": command, "timeout": timeout, "background": background}
        request_timeout = None
        if timeout and timeout > 0:
            request_timeout = max(
                self._request_timeout,
                int(timeout) + self._command_timeout_grace_seconds,
            )
        return self.request_json(
            "POST",
            handle.base_url,
            f"/sessions/{handle.session_id}/exec",
            payload,
            timeout=request_timeout,
        )

    def write_file(self, handle: RemoteSessionHandle, path: str, data: bytes | str) -> None:
        payload: dict[str, Any]
        if isinstance(data, bytes):
            payload = {
                "path": path,
                "encoding": "base64",
                "content": base64.b64encode(data).decode("ascii"),
            }
        else:
            payload = {
                "path": path,
                "encoding": "text",
                "content": data,
            }
        self.request_json("POST", handle.base_url, f"/sessions/{handle.session_id}/files/write", payload)

    def read_file(self, handle: RemoteSessionHandle, path: str, format: str = "text") -> bytes | str:
        payload = {"path": path, "format": format}
        response = self.request_json("POST", handle.base_url, f"/sessions/{handle.session_id}/files/read", payload)
        encoding = str(response.get("encoding", "text"))
        content = response.get("content", "")
        if encoding == "base64":
            data = base64.b64decode(content.encode("ascii"))
            if format in {"bytes", "binary"}:
                return data
            return data.decode("utf-8")
        return str(content)

    def remove_file(self, handle: RemoteSessionHandle, path: str) -> None:
        self.request_json(
            "POST",
            handle.base_url,
            f"/sessions/{handle.session_id}/files/remove",
            {"path": path},
        )

    def screenshot(self, handle: RemoteSessionHandle) -> bytes:
        return self.request_bytes("POST", handle.base_url, f"/sessions/{handle.session_id}/screenshot")

    def get_stream_url(self, handle: RemoteSessionHandle) -> str:
        response = self.request_json("GET", handle.base_url, f"/sessions/{handle.session_id}/stream-url")
        return str(response["stream_url"])

    def delete_session(self, base_url: str, session_id: str) -> None:
        self.request_json("DELETE", base_url, f"/sessions/{session_id}")
