from __future__ import annotations

import atexit
import threading
import time
from typing import Any

from computer_env.backends.base import (
    BackgroundCommandHandle,
    BaseComputerEnvironment,
    CommandExitException,
    CommandResult,
)
from computer_env.config import EnvCreateOptions

from .worker_client import (
    RemoteDockerAPIError,
    RemoteDockerWorkerClient,
    RemoteFleetCapacity,
    RemoteSessionHandle,
)

_ACTIVE_REMOTE_SESSIONS: dict[str, tuple[RemoteDockerWorkerClient, RemoteSessionHandle]] = {}
_ACTIVE_REMOTE_SESSIONS_LOCK = threading.Lock()
REMOTE_CLEANUP_RETRY_ATTEMPTS = 5
REMOTE_CLEANUP_RETRY_INTERVAL_SECONDS = 1.0


def _register_active_session(client: RemoteDockerWorkerClient, handle: RemoteSessionHandle) -> None:
    with _ACTIVE_REMOTE_SESSIONS_LOCK:
        _ACTIVE_REMOTE_SESSIONS[handle.session_id] = (client, handle)


def _unregister_active_session(session_or_id: RemoteSessionHandle | str) -> None:
    session_id = session_or_id if isinstance(session_or_id, str) else session_or_id.session_id
    with _ACTIVE_REMOTE_SESSIONS_LOCK:
        _ACTIVE_REMOTE_SESSIONS.pop(session_id, None)


def cleanup_active_remote_sessions() -> list[str]:
    with _ACTIVE_REMOTE_SESSIONS_LOCK:
        sessions = list(_ACTIVE_REMOTE_SESSIONS.values())
    cleaned: list[str] = []
    for client, handle in sessions:
        try:
            client.delete_session(handle.base_url, handle.session_id)
        except RemoteDockerAPIError as exc:
            if exc.status == 404:
                _unregister_active_session(handle.session_id)
                cleaned.append(handle.session_id)
            continue
        except Exception:
            continue
        _unregister_active_session(handle.session_id)
        cleaned.append(handle.session_id)
    return cleaned


def _create_remote_docker_client(options: EnvCreateOptions) -> RemoteDockerWorkerClient:
    return RemoteDockerWorkerClient(
        worker_urls=options.remote_docker_worker_urls,
        pool_file=options.remote_docker_pool_file,
        api_token=options.remote_docker_api_token,
        request_timeout=options.remote_docker_request_timeout,
        session_create_timeout=options.remote_docker_session_create_timeout,
        session_acquire_timeout=options.remote_docker_session_acquire_timeout,
        command_timeout_grace_seconds=options.remote_docker_command_timeout_grace_seconds,
        worker_cooldown_seconds=options.remote_docker_worker_cooldown_seconds,
    )


def _match_session_metadata(session: dict[str, Any], metadata: dict[str, str]) -> bool:
    session_metadata = dict(session.get("metadata", {}))
    return all(session_metadata.get(key) == value for key, value in metadata.items())


def _get_cleanup_client() -> RemoteDockerWorkerClient:
    try:
        return next(iter(_ACTIVE_REMOTE_SESSIONS.values()))[0]
    except StopIteration:
        return _create_remote_docker_client(EnvCreateOptions())


def list_remote_sessions_by_metadata(metadata: dict[str, str] | None) -> list[dict[str, Any]]:
    if not metadata:
        return []
    client = _get_cleanup_client()
    return [session for session in client.list_sessions() if _match_session_metadata(session, metadata)]


def cleanup_remote_sessions_by_metadata(metadata: dict[str, str] | None) -> list[str]:
    if not metadata:
        return []

    client = _get_cleanup_client()
    deleted_ids: set[str] = set()
    attempts = max(1, REMOTE_CLEANUP_RETRY_ATTEMPTS)

    for attempt in range(attempts):
        matching_sessions = [session for session in client.list_sessions() if _match_session_metadata(session, metadata)]
        if not matching_sessions:
            break

        for session in matching_sessions:
            session_id = str(session["session_id"])
            base_url = str(session["base_url"])
            try:
                client.delete_session(base_url, session_id)
            except RemoteDockerAPIError as exc:
                if exc.status != 404:
                    continue
            except Exception:
                continue
            deleted_ids.add(session_id)

        if attempt < attempts - 1:
            time.sleep(REMOTE_CLEANUP_RETRY_INTERVAL_SECONDS)

    return sorted(deleted_ids)


def summarize_remote_fleet_capacity(options: EnvCreateOptions | None = None) -> RemoteFleetCapacity:
    client = _create_remote_docker_client(options or EnvCreateOptions())
    return client.summarize_capacity()


atexit.register(cleanup_active_remote_sessions)


class RemoteDockerCommandsClient:
    def __init__(self, env: "RemoteDockerEnvironment") -> None:
        self._env = env

    def run(self, command: str, timeout: int | None = None, background: bool = False):
        result = self._env.client.run_command(
            self._env.handle,
            command=command,
            timeout=timeout,
            background=background,
        )
        exit_code = int(result.get("exit_code", 0))
        if exit_code != 0 and not background:
            raise CommandExitException(
                command=command,
                exit_code=exit_code,
                stdout=str(result.get("stdout", "") or ""),
                stderr=str(result.get("stderr", "") or ""),
            )
        if background:
            return BackgroundCommandHandle(
                command=command,
                backend="remote_docker",
                pid=int(result["pid"]) if result.get("pid") is not None else None,
                raw_handle=result,
            )
        return CommandResult(
            command=command,
            stdout=str(result.get("stdout", "") or ""),
            stderr=str(result.get("stderr", "") or ""),
            exit_code=exit_code,
        )


class RemoteDockerFilesClient:
    def __init__(self, env: "RemoteDockerEnvironment") -> None:
        self._env = env

    def write(self, path: str, data: Any) -> None:
        self._env.client.write_file(self._env.handle, path, data)

    def read(self, path: str, format: str = "text") -> Any:
        return self._env.client.read_file(self._env.handle, path, format=format)

    def remove(self, path: str) -> None:
        self._env.client.remove_file(self._env.handle, path)


class RemoteDockerStreamClient:
    def __init__(self, env: "RemoteDockerEnvironment") -> None:
        self._env = env

    def start(self, **kwargs):
        return None

    def get_url(self, **kwargs) -> str:
        return self._env.client.get_stream_url(self._env.handle)

    def stop(self):
        return None


class RemoteDockerEnvironment(BaseComputerEnvironment):
    backend_name = "remote_docker"

    def __init__(
        self,
        *,
        client: RemoteDockerWorkerClient,
        handle: RemoteSessionHandle,
        timeout: int,
        resolution: tuple[int, int],
    ) -> None:
        self.client = client
        self.handle = handle
        self.timeout = timeout
        self.resolution = resolution
        self.commands = RemoteDockerCommandsClient(self)
        self.files = RemoteDockerFilesClient(self)
        self.stream = RemoteDockerStreamClient(self)
        self._killed = False

    def screenshot(self) -> bytes:
        return self.client.screenshot(self.handle)

    def kill(self) -> None:
        if self._killed:
            return
        try:
            self.client.delete_session(self.handle.base_url, self.handle.session_id)
        except RemoteDockerAPIError as exc:
            if exc.status != 404:
                raise
        self._killed = True
        _unregister_active_session(self.handle.session_id)

    def get_screen_size(self):
        return {"width": self.resolution[0], "height": self.resolution[1]}


def create_remote_docker_env(options: EnvCreateOptions) -> RemoteDockerEnvironment:
    client = _create_remote_docker_client(options)
    handle = client.create_session(
        image=options.docker_image,
        resolution=options.resolution,
        timeout=options.timeout,
        app_name=options.app_name,
        metadata=options.docker_metadata,
        docker_platform=options.docker_platform,
        docker_shm_size=options.docker_shm_size,
        docker_memory=options.docker_memory,
        docker_cpus=options.docker_cpus,
        ready_timeout=options.docker_ready_timeout,
    )
    _register_active_session(client, handle)
    return RemoteDockerEnvironment(
        client=client,
        handle=handle,
        timeout=options.timeout,
        resolution=options.resolution,
    )
