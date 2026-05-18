#!/usr/bin/env python3
"""
Terminate remote_docker workers on Tencent Cloud CVM instances.

Usage:
    python -m computer_env.provision.tencentcloud.terminate_workers --all-by-prefix
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import dotenv
except ModuleNotFoundError:
    dotenv = None

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

if dotenv is not None:
    dotenv.load_dotenv(REPO_ROOT / ".env")

from computer_env.provision.tencentcloud import (
    DEFAULT_NAME_PREFIX,
    DEFAULT_TENCENTCLOUD_REGION,
    require_setting,
    worker_pool_path,
)
from computer_env.provision.tencentcloud import api as tc_api


def _log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[terminate_workers {timestamp}] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Terminate remote_docker Tencent Cloud workers.")
    parser.add_argument("--region", default=DEFAULT_TENCENTCLOUD_REGION)
    parser.add_argument("--name-prefix", default=DEFAULT_NAME_PREFIX)
    parser.add_argument("--pool-file", default=str(worker_pool_path()))
    parser.add_argument(
        "--all-by-prefix",
        action="store_true",
        help="Terminate every worker instance with the managed prefix tag.",
    )
    parser.add_argument("--keep-pool-file", action="store_true")
    parser.add_argument("--no-wait", action="store_true", help="Return immediately after submitting termination.")
    return parser.parse_args()


def instance_ids_from_pool_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    return [str(item["instance_id"]) for item in payload.get("workers", []) if item.get("instance_id")]


def instance_ids_from_prefix(cvm_client, name_prefix: str) -> list[str]:
    instance_ids: set[str] = set()
    offset = 0
    limit = 100
    while True:
        request = tc_api.build_request(
            tc_api.cvm_models.DescribeInstancesRequest,
            {
                "Filters": [
                    {"Name": "tag:ManagedBy", "Values": ["OpenComputer"]},
                    {"Name": "tag:NamePrefix", "Values": [name_prefix]},
                ],
                "Offset": offset,
                "Limit": limit,
            },
        )
        response = cvm_client.DescribeInstances(request)
        payload = tc_api.response_to_dict(response)
        instances = payload.get("InstanceSet", [])
        for item in instances:
            state = str(item.get("InstanceState") or "")
            if state in {"SHUTDOWN", "TERMINATED"}:
                continue
            instance_id = item.get("InstanceId")
            if instance_id:
                instance_ids.add(str(instance_id))
        if len(instances) < limit:
            break
        offset += limit
    return sorted(instance_ids)


def resolve_instance_ids(
    cvm_client,
    *,
    pool_file: Path,
    name_prefix: str,
    all_by_prefix: bool,
) -> tuple[list[str], str, list[str]]:
    pool_ids = instance_ids_from_pool_file(pool_file)
    prefix_ids = instance_ids_from_prefix(cvm_client, name_prefix)

    if all_by_prefix:
        return prefix_ids, "prefix", []

    if pool_ids:
        extra_prefix_ids = sorted(set(prefix_ids) - set(pool_ids))
        return pool_ids, "pool_file", extra_prefix_ids

    if prefix_ids:
        _log(
            f"Pool file {pool_file} is missing or empty; "
            f"falling back to managed prefix {name_prefix}."
        )
        return prefix_ids, "prefix_fallback", []

    return [], "none", []


def wait_for_termination(cvm_client, instance_ids: list[str], timeout_seconds: int = 600) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        request = tc_api.build_request(
            tc_api.cvm_models.DescribeInstancesRequest,
            {"InstanceIds": instance_ids},
        )
        try:
            response = cvm_client.DescribeInstances(request)
        except tc_api.TencentCloudSDKException as exc:
            if tc_api.is_not_found_error(exc):
                _log("Instance(s) are no longer returned by DescribeInstances.")
                return
            raise
        instances = tc_api.response_to_dict(response).get("InstanceSet", [])
        if not instances:
            _log("Instance(s) no longer returned by DescribeInstances.")
            return
        states = {str(item.get("InstanceId")): str(item.get("InstanceState")) for item in instances}
        if all(state in {"SHUTDOWN", "TERMINATED"} for state in states.values()):
            _log("Instance(s) are now terminated.")
            return
        time.sleep(5)
    raise TimeoutError(
        f"Instance(s) did not reach TERMINATED within {timeout_seconds}s: {', '.join(instance_ids)}"
    )


def main() -> None:
    args = parse_args()
    args.region = require_setting(
        args.region,
        env_name="TENCENTCLOUD_REGION",
        cli_flag="--region",
        example="ap-guangzhou",
    )
    args.name_prefix = require_setting(
        args.name_prefix,
        env_name="TENCENTCLOUD_NAME_PREFIX",
        cli_flag="--name-prefix",
        example="opencomputer-dev",
    )

    tc_api.require_tencentcloud_dependencies()
    cred = tc_api.get_credentials()
    cvm = tc_api.build_cvm_client(cred, args.region)

    pool_file = Path(args.pool_file).expanduser()
    _log(
        f"Resolving worker instances in region={args.region} "
        f"with name_prefix={args.name_prefix}."
    )
    instance_ids, source, extra_prefix_ids = resolve_instance_ids(
        cvm,
        pool_file=pool_file,
        name_prefix=args.name_prefix,
        all_by_prefix=args.all_by_prefix,
    )

    if extra_prefix_ids:
        _log(
            "Found additional managed instances not present in the local pool file: "
            f"{', '.join(extra_prefix_ids)}. Re-run with --all-by-prefix to terminate them too."
        )

    if not instance_ids:
        _log(
            "No worker instances to terminate. "
            "If billing is still active, re-check the Tencent Cloud account, region, and tag prefix used for launch."
        )
        return

    _log(f"Submitting termination for instance(s): {', '.join(instance_ids)}")
    terminate_request = tc_api.build_request(
        tc_api.cvm_models.TerminateInstancesRequest,
        {"InstanceIds": instance_ids},
    )
    cvm.TerminateInstances(terminate_request)
    if not args.no_wait:
        _log("Waiting for instance(s) to reach terminated state.")
        wait_for_termination(cvm, instance_ids)

    pool_file_removed = False
    if pool_file.exists() and not args.keep_pool_file:
        pool_file.unlink()
        pool_file_removed = True
    print(
        json.dumps(
            {
                "terminated_instance_ids": instance_ids,
                "resolution_source": source,
                "extra_prefix_instance_ids": extra_prefix_ids,
                "pool_file_removed": pool_file_removed,
                "waited_for_termination": not args.no_wait,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
