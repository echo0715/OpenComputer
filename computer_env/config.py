from __future__ import annotations

import os
from dataclasses import dataclass


def _parse_csv_env(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    if not raw.strip():
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())

DEFAULT_ENV_BACKEND = os.getenv("ENV_BACKEND", "e2b")
# e2b backend
DEFAULT_E2B_TEMPLATE = os.getenv("E2B_ENV_TEMPLATE", "desktop-all-apps")
# docker backend (local and remote)
DEFAULT_DOCKER_IMAGE = os.getenv("DOCKER_ENV_IMAGE", "gui-synth-env-desktop:latest")
DEFAULT_DOCKER_PLATFORM = os.getenv("DOCKER_ENV_PLATFORM", "linux/amd64")
DEFAULT_DOCKER_SHM_SIZE = os.getenv("DOCKER_ENV_SHM_SIZE", "2g")
DEFAULT_DOCKER_MEMORY = os.getenv("DOCKER_ENV_MEMORY") or None
DEFAULT_DOCKER_CPUS = os.getenv("DOCKER_ENV_CPUS") or None
DEFAULT_DOCKER_READY_TIMEOUT = int(os.getenv("DOCKER_ENV_READY_TIMEOUT", "90"))
DEFAULT_REMOTE_DOCKER_POOL_FILE = os.path.expanduser(
    os.getenv("REMOTE_DOCKER_POOL_FILE", "~/.config/gui-synth-env/aws/worker_pool.json")
)
DEFAULT_REMOTE_DOCKER_WORKER_URLS = _parse_csv_env("REMOTE_DOCKER_WORKER_URLS")
DEFAULT_REMOTE_DOCKER_API_TOKEN = os.getenv("REMOTE_DOCKER_API_TOKEN") or None
DEFAULT_REMOTE_DOCKER_REQUEST_TIMEOUT = int(os.getenv("REMOTE_DOCKER_REQUEST_TIMEOUT", "30"))
DEFAULT_REMOTE_DOCKER_SESSION_CREATE_TIMEOUT = int(
    os.getenv("REMOTE_DOCKER_SESSION_CREATE_TIMEOUT", "240")
)
DEFAULT_REMOTE_DOCKER_SESSION_ACQUIRE_TIMEOUT = int(
    os.getenv("REMOTE_DOCKER_SESSION_ACQUIRE_TIMEOUT", "180")
)
DEFAULT_REMOTE_DOCKER_COMMAND_TIMEOUT_GRACE_SECONDS = int(
    os.getenv("REMOTE_DOCKER_COMMAND_TIMEOUT_GRACE_SECONDS", "30")
)
DEFAULT_REMOTE_DOCKER_WORKER_COOLDOWN_SECONDS = int(
    os.getenv("REMOTE_DOCKER_WORKER_COOLDOWN_SECONDS", "15")
)


@dataclass(frozen=True)
class EnvCreateOptions:
    backend: str = DEFAULT_ENV_BACKEND
    timeout: int = 3600
    resolution: tuple[int, int] = (1920, 1080)
    template: str = DEFAULT_E2B_TEMPLATE
    docker_image: str = DEFAULT_DOCKER_IMAGE
    docker_platform: str = DEFAULT_DOCKER_PLATFORM
    docker_shm_size: str = DEFAULT_DOCKER_SHM_SIZE
    docker_memory: str | None = DEFAULT_DOCKER_MEMORY
    docker_cpus: str | None = DEFAULT_DOCKER_CPUS
    docker_ready_timeout: int = DEFAULT_DOCKER_READY_TIMEOUT
    remote_docker_pool_file: str = DEFAULT_REMOTE_DOCKER_POOL_FILE
    remote_docker_worker_urls: tuple[str, ...] = DEFAULT_REMOTE_DOCKER_WORKER_URLS
    remote_docker_api_token: str | None = DEFAULT_REMOTE_DOCKER_API_TOKEN
    remote_docker_request_timeout: int = DEFAULT_REMOTE_DOCKER_REQUEST_TIMEOUT
    remote_docker_session_create_timeout: int = DEFAULT_REMOTE_DOCKER_SESSION_CREATE_TIMEOUT
    remote_docker_session_acquire_timeout: int = DEFAULT_REMOTE_DOCKER_SESSION_ACQUIRE_TIMEOUT
    remote_docker_command_timeout_grace_seconds: int = (
        DEFAULT_REMOTE_DOCKER_COMMAND_TIMEOUT_GRACE_SECONDS
    )
    remote_docker_worker_cooldown_seconds: int = DEFAULT_REMOTE_DOCKER_WORKER_COOLDOWN_SECONDS
    app_name: str | None = None
    docker_metadata: dict[str, str] | None = None
    e2b_metadata: dict[str, str] | None = None


def normalize_backend(backend: str | None) -> str:
    return (backend or DEFAULT_ENV_BACKEND).strip().lower()
