from __future__ import annotations

import os
from pathlib import Path

def _read_env(name: str) -> str | None:
    raw = os.getenv(name, "")
    cleaned = raw.strip()
    return cleaned or None


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer; got {raw!r}") from exc


DEFAULT_AWS_PROFILE = _read_env("AWS_PROFILE")
DEFAULT_AWS_REGION = _read_env("AWS_REGION")
DEFAULT_NAME_PREFIX = _read_env("AWS_NAME_PREFIX")
DEFAULT_CONTROLLER_CIDR = _read_env("AWS_CONTROLLER_CIDR")
DEFAULT_ECR_REPOSITORY = _read_env("AWS_ECR_REPOSITORY")
DEFAULT_S3_BUCKET = _read_env("AWS_S3_BUCKET")
DEFAULT_WORKER_INSTANCE_TYPE = _read_env("AWS_WORKER_INSTANCE_TYPE") or "m6i.2xlarge"
DEFAULT_WORKER_COUNT = _read_int_env("AWS_WORKER_COUNT", 1)
DEFAULT_CONTAINERS_PER_WORKER = _read_int_env("AWS_CONTAINERS_PER_WORKER", 2)
DEFAULT_VPC_ID = _read_env("AWS_VPC_ID")
DEFAULT_SUBNET_ID = _read_env("AWS_SUBNET_ID")
DEFAULT_DEBUG_ACCESS = _read_env("AWS_DEBUG_ACCESS") or "SSM"
DEFAULT_INSTANCE_PROFILE_NAME = _read_env("AWS_INSTANCE_PROFILE_NAME")
DEFAULT_WORKER_AGENT_PORT = _read_int_env("AWS_WORKER_AGENT_PORT", 8088)
DEFAULT_NOVNC_PORT_START = _read_int_env("AWS_NOVNC_PORT_START", 61000)
DEFAULT_NOVNC_PORT_END = _read_int_env("AWS_NOVNC_PORT_END", 61199)
DEFAULT_WORKER_ROOT_VOLUME_SIZE_GB = _read_int_env("AWS_WORKER_ROOT_VOLUME_SIZE_GB", 64)
DEFAULT_WORKER_POOL_FILE = os.path.expanduser(
    os.getenv("REMOTE_DOCKER_POOL_FILE", "~/.config/gui-synth-env/aws/worker_pool.json")
)
DEFAULT_BOOTSTRAP_PREFIX = _read_env("AWS_BOOTSTRAP_PREFIX")


def worker_pool_path() -> Path:
    return Path(DEFAULT_WORKER_POOL_FILE).expanduser()


def require_setting(
    value: str | None,
    *,
    env_name: str,
    cli_flag: str,
    example: str,
) -> str:
    cleaned = (value or "").strip()
    if cleaned:
        return cleaned
    raise SystemExit(
        f"Missing required setting {env_name}. Add `{env_name}=...` to the repository root "
        f"`.env` file or pass `{cli_flag}`. Example: {env_name}={example}"
    )


def resolve_ecr_repository(repository: str | None, name_prefix: str) -> str:
    cleaned = (repository or "").strip()
    return cleaned or f"{name_prefix}-desktop"


def resolve_instance_profile_name(profile_name: str | None, name_prefix: str) -> str:
    cleaned = (profile_name or "").strip()
    return cleaned or f"{name_prefix}-worker"


def resolve_bootstrap_prefix(prefix: str | None, name_prefix: str) -> str:
    cleaned = (prefix or "").strip()
    return cleaned or f"bootstrap/{name_prefix}"


def build_default_s3_bucket_name(account_id: str, name_prefix: str) -> str:
    return f"{name_prefix}-assets-{account_id}"


def build_ecr_image_uri(account_id: str, region: str, repository: str, tag: str = "latest") -> str:
    return f"{account_id}.dkr.ecr.{region}.amazonaws.com/{repository}:{tag}"
