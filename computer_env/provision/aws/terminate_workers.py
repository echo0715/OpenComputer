#!/usr/bin/env python3
"""
Terminate remote_docker workers on AWS EC2 instances.

Usage:
    python -m computer_env.provision.aws.terminate_workers --all-by-prefix
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

try:
    import boto3
except ModuleNotFoundError:
    boto3 = None

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

if dotenv is not None:
    dotenv.load_dotenv(REPO_ROOT / ".env")

from computer_env.provision.aws import (
    DEFAULT_AWS_REGION,
    DEFAULT_NAME_PREFIX,
    require_setting,
    worker_pool_path,
)


def _log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[terminate_workers {timestamp}] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Terminate remote_docker AWS workers.")
    parser.add_argument("--region", default=DEFAULT_AWS_REGION,
                        help="AWS deployment region. Required via .env or --region.")
    parser.add_argument("--name-prefix", default=DEFAULT_NAME_PREFIX,
                        help="Resource naming prefix. Required via .env or --name-prefix.")
    parser.add_argument("--pool-file", default=str(worker_pool_path()))
    parser.add_argument("--all-by-prefix", action="store_true", help="Terminate every worker instance with the managed prefix tag.")
    parser.add_argument("--keep-pool-file", action="store_true")
    parser.add_argument("--no-wait", action="store_true", help="Return immediately after submitting termination.")
    return parser.parse_args()


def instance_ids_from_pool_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    return [str(item["instance_id"]) for item in payload.get("workers", []) if item.get("instance_id")]


def instance_ids_from_prefix(ec2_client, name_prefix: str) -> list[str]:
    response = ec2_client.describe_instances(
        Filters=[
            {"Name": "tag:ManagedBy", "Values": ["OpenComputer"]},
            {"Name": "tag:NamePrefix", "Values": [name_prefix]},
            {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]},
        ]
    )
    instance_ids: list[str] = []
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            instance_ids.append(instance["InstanceId"])
    return sorted(set(instance_ids))


def resolve_instance_ids(
    ec2_client,
    *,
    pool_file: Path,
    name_prefix: str,
    all_by_prefix: bool,
) -> tuple[list[str], str, list[str]]:
    pool_ids = instance_ids_from_pool_file(pool_file)
    prefix_ids = instance_ids_from_prefix(ec2_client, name_prefix)

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


def main() -> None:
    args = parse_args()
    args.region = require_setting(
        args.region,
        env_name="AWS_REGION",
        cli_flag="--region",
        example="us-east-1",
    )
    args.name_prefix = require_setting(
        args.name_prefix,
        env_name="AWS_NAME_PREFIX",
        cli_flag="--name-prefix",
        example="opencomputer-dev",
    )
    if boto3 is None:
        raise SystemExit("boto3 is required for AWS provisioning scripts. Install it with `pip install boto3`.")
    session = boto3.Session(region_name=args.region)
    ec2 = session.client("ec2")

    pool_file = Path(args.pool_file).expanduser()
    _log(
        f"Resolving worker instances in region={args.region} "
        f"with name_prefix={args.name_prefix}."
    )
    instance_ids, source, extra_prefix_ids = resolve_instance_ids(
        ec2,
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
            "If billing is still active, re-check the AWS account, region, and profile used for launch."
        )
        return

    _log(f"Submitting termination for instance(s): {', '.join(instance_ids)}")
    ec2.terminate_instances(InstanceIds=instance_ids)
    if not args.no_wait:
        _log("Waiting for instance(s) to reach terminated state.")
        ec2.get_waiter("instance_terminated").wait(InstanceIds=instance_ids)
        _log("Instance(s) are now terminated.")

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
