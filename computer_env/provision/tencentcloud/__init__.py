from __future__ import annotations

import os
import re
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


DEFAULT_TENCENTCLOUD_REGION = _read_env("TENCENTCLOUD_REGION")
DEFAULT_NAME_PREFIX = _read_env("TENCENTCLOUD_NAME_PREFIX")
DEFAULT_CONTROLLER_CIDR = _read_env("TENCENTCLOUD_CONTROLLER_CIDR")
DEFAULT_CVM_ZONE = _read_env("TENCENTCLOUD_CVM_ZONE")
DEFAULT_CVM_IMAGE_ID = _read_env("TENCENTCLOUD_CVM_IMAGE_ID")
DEFAULT_CVM_INSTANCE_TYPE = _read_env("TENCENTCLOUD_CVM_INSTANCE_TYPE") or "S5.LARGE8"
DEFAULT_WORKER_COUNT = _read_int_env("TENCENTCLOUD_WORKER_COUNT", 1)
DEFAULT_CONTAINERS_PER_WORKER = _read_int_env("TENCENTCLOUD_CONTAINERS_PER_WORKER", 6)
DEFAULT_VPC_ID = _read_env("TENCENTCLOUD_VPC_ID")
DEFAULT_SUBNET_ID = _read_env("TENCENTCLOUD_SUBNET_ID")
DEFAULT_CVM_BANDWIDTH_OUT_MBPS = _read_int_env("TENCENTCLOUD_CVM_BANDWIDTH_OUT_Mbps", 20)
DEFAULT_CVM_SYSTEM_DISK_SIZE_GB = _read_int_env("TENCENTCLOUD_CVM_SYSTEM_DISK_SIZE_GB", 64)
DEFAULT_COS_BUCKET = _read_env("TENCENTCLOUD_COS_BUCKET")
DEFAULT_COS_PREFIX = _read_env("TENCENTCLOUD_COS_PREFIX")
DEFAULT_ACCOUNT_UIN = _read_env("TENCENTCLOUD_ACCOUNT_UIN")
DEFAULT_TCR_PERSONAL_SERVER = _read_env("TENCENTCLOUD_TCR_PERSONAL_SERVER") or "ccr.ccs.tencentyun.com"
DEFAULT_TCR_PERSONAL_NAMESPACE = _read_env("TENCENTCLOUD_TCR_PERSONAL_NAMESPACE")
DEFAULT_TCR_PERSONAL_REPOSITORY = _read_env("TENCENTCLOUD_TCR_PERSONAL_REPOSITORY") or "desktop"
DEFAULT_TCR_PERSONAL_PASSWORD = _read_env("TENCENTCLOUD_TCR_PERSONAL_PASSWORD")
DEFAULT_WORKER_AGENT_PORT = _read_int_env("TENCENTCLOUD_WORKER_AGENT_PORT", 8088)
DEFAULT_NOVNC_PORT_START = _read_int_env("TENCENTCLOUD_NOVNC_PORT_START", 61000)
DEFAULT_NOVNC_PORT_END = _read_int_env("TENCENTCLOUD_NOVNC_PORT_END", 61199)
DEFAULT_WORKER_POOL_FILE = os.path.expanduser(
    os.getenv("REMOTE_DOCKER_POOL_FILE", "~/.config/gui-synth-env/tencentcloud/worker_pool.json")
)


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


def resolve_cos_prefix(prefix: str | None, name_prefix: str) -> str:
    cleaned = (prefix or "").strip().strip("/")
    return cleaned or f"bootstrap/{name_prefix}"


def build_default_cos_bucket_name(app_id: str | int, name_prefix: str) -> str:
    return f"{sanitize_name_prefix(name_prefix)}-assets-{app_id}"


def sanitize_name_prefix(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or "opencomputer"


def derive_default_namespace(account_uin: str, name_prefix: str) -> str:
    digits = "".join(ch for ch in account_uin if ch.isdigit())
    suffix = digits[-6:] if digits else "000000"
    return f"oc-{suffix}-{sanitize_name_prefix(name_prefix)}"


def resolve_tcr_namespace(namespace: str | None, *, account_uin: str, name_prefix: str) -> str:
    cleaned = (namespace or "").strip()
    return cleaned or derive_default_namespace(account_uin, name_prefix)


def build_tcr_image_uri(server: str, namespace: str, repository: str, tag: str = "latest") -> str:
    return f"{server.rstrip('/')}/{namespace}/{repository}:{tag}"


def validate_tcr_password(password: str) -> None:
    if not (8 <= len(password) <= 16):
        raise SystemExit(
            "TENCENTCLOUD_TCR_PERSONAL_PASSWORD must be 8 to 16 characters long "
            "to satisfy TCR Personal password rules."
        )

