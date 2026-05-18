#!/usr/bin/env python3
"""
Launch remote_docker workers on Tencent Cloud CVM instances.

Usage:
    python -m computer_env.provision.tencentcloud.launch_workers
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import shlex
import sys
import time
import urllib.request
import uuid
import zipfile
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
    DEFAULT_ACCOUNT_UIN,
    DEFAULT_CONTAINERS_PER_WORKER,
    DEFAULT_CONTROLLER_CIDR,
    DEFAULT_COS_BUCKET,
    DEFAULT_COS_PREFIX,
    DEFAULT_CVM_BANDWIDTH_OUT_MBPS,
    DEFAULT_CVM_IMAGE_ID,
    DEFAULT_CVM_INSTANCE_TYPE,
    DEFAULT_CVM_SYSTEM_DISK_SIZE_GB,
    DEFAULT_CVM_ZONE,
    DEFAULT_NAME_PREFIX,
    DEFAULT_NOVNC_PORT_END,
    DEFAULT_NOVNC_PORT_START,
    DEFAULT_SUBNET_ID,
    DEFAULT_TCR_PERSONAL_NAMESPACE,
    DEFAULT_TCR_PERSONAL_PASSWORD,
    DEFAULT_TCR_PERSONAL_REPOSITORY,
    DEFAULT_TCR_PERSONAL_SERVER,
    DEFAULT_TENCENTCLOUD_REGION,
    DEFAULT_VPC_ID,
    DEFAULT_WORKER_AGENT_PORT,
    DEFAULT_WORKER_COUNT,
    build_default_cos_bucket_name,
    build_tcr_image_uri,
    require_setting,
    resolve_cos_prefix,
    resolve_tcr_namespace,
    validate_tcr_password,
    worker_pool_path,
)
from computer_env.provision.tencentcloud import api as tc_api

WORKER_AGENT_DIR = Path(__file__).resolve().parent.parent / "aws" / "worker_agent"
USER_DATA_TEMPLATE = (Path(__file__).resolve().parent / "worker_user_data.sh").read_text()


def _log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[launch_workers {timestamp}] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch Tencent Cloud remote_docker workers and write the local worker pool file."
    )
    parser.add_argument("--region", default=DEFAULT_TENCENTCLOUD_REGION)
    parser.add_argument("--name-prefix", default=DEFAULT_NAME_PREFIX)
    parser.add_argument("--controller-cidr", default=DEFAULT_CONTROLLER_CIDR)
    parser.add_argument("--zone", default=DEFAULT_CVM_ZONE)
    parser.add_argument("--image-id", default=DEFAULT_CVM_IMAGE_ID)
    parser.add_argument("--instance-type", default=DEFAULT_CVM_INSTANCE_TYPE)
    parser.add_argument("--worker-count", type=int, default=DEFAULT_WORKER_COUNT)
    parser.add_argument("--containers-per-worker", type=int, default=DEFAULT_CONTAINERS_PER_WORKER)
    parser.add_argument("--vpc-id", default=DEFAULT_VPC_ID)
    parser.add_argument("--subnet-id", default=DEFAULT_SUBNET_ID)
    parser.add_argument("--bandwidth-out-mbps", type=int, default=DEFAULT_CVM_BANDWIDTH_OUT_MBPS)
    parser.add_argument("--system-disk-size-gb", type=int, default=DEFAULT_CVM_SYSTEM_DISK_SIZE_GB)
    parser.add_argument("--cos-bucket", default=DEFAULT_COS_BUCKET)
    parser.add_argument("--cos-prefix", default=DEFAULT_COS_PREFIX)
    parser.add_argument("--account-uin", default=DEFAULT_ACCOUNT_UIN)
    parser.add_argument("--tcr-personal-server", default=DEFAULT_TCR_PERSONAL_SERVER)
    parser.add_argument("--tcr-namespace", default=DEFAULT_TCR_PERSONAL_NAMESPACE)
    parser.add_argument("--tcr-repository", default=DEFAULT_TCR_PERSONAL_REPOSITORY)
    parser.add_argument("--tcr-password", default=DEFAULT_TCR_PERSONAL_PASSWORD)
    parser.add_argument("--worker-agent-port", type=int, default=DEFAULT_WORKER_AGENT_PORT)
    parser.add_argument("--novnc-port-start", type=int, default=DEFAULT_NOVNC_PORT_START)
    parser.add_argument("--novnc-port-end", type=int, default=DEFAULT_NOVNC_PORT_END)
    parser.add_argument("--pool-file", default=str(worker_pool_path()))
    parser.add_argument("--api-token", default=os.getenv("REMOTE_DOCKER_API_TOKEN") or "")
    parser.add_argument("--wait-seconds", type=int, default=420)
    parser.add_argument(
        "--keep-failed-instances",
        action="store_true",
        help="Keep CVM instances running when launch fails after instance creation.",
    )
    return parser.parse_args()


def build_worker_bundle() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(WORKER_AGENT_DIR.rglob("*")):
            if path.is_dir():
                continue
            archive.write(path, path.relative_to(WORKER_AGENT_DIR))
    return buffer.getvalue()


def upload_worker_bundle(cos_client, bucket: str, key: str) -> None:
    payload = build_worker_bundle()
    _log(
        f"Uploading worker-agent bundle to cos://{bucket}/{key} "
        f"({len(payload) / 1024:.1f} KiB)"
    )
    cos_client.put_object(Bucket=bucket, Key=key, Body=payload, EnableMD5=True)
    _log("Worker-agent bundle uploaded.")


def resolve_subnet_launch_context(
    vpc_client,
    *,
    subnet_id: str,
    requested_vpc_id: str,
    requested_zone: str,
) -> tuple[str, str]:
    request = tc_api.build_request(
        tc_api.vpc_models.DescribeSubnetsRequest,
        {
            "SubnetIds": [subnet_id],
        },
    )
    response = vpc_client.DescribeSubnets(request)
    subnets = response.SubnetSet or []
    if not subnets:
        raise RuntimeError(f"Subnet {subnet_id} was not found in the configured region.")

    subnet = subnets[0]
    subnet_vpc_id = str(subnet.VpcId or "")
    subnet_zone = str(subnet.Zone or "")
    if not subnet_vpc_id:
        raise RuntimeError(f"Subnet {subnet_id} did not return an owning VPC ID.")
    if not subnet_zone:
        raise RuntimeError(f"Subnet {subnet_id} did not return an availability zone.")
    if subnet_vpc_id != requested_vpc_id:
        raise RuntimeError(
            f"Subnet {subnet_id} belongs to VPC {subnet_vpc_id}, "
            f"but TENCENTCLOUD_VPC_ID/--vpc-id is {requested_vpc_id}."
        )

    _log(
        f"Resolved subnet {subnet_id}: vpc={subnet_vpc_id}, zone={subnet_zone}. "
        f"Requested launch zone={requested_zone}."
    )

    if requested_zone != subnet_zone:
        _log(
            f"Requested zone {requested_zone} does not match subnet {subnet_id} zone {subnet_zone}. "
            f"Using subnet zone {subnet_zone} for CVM launch."
        )
    return subnet_vpc_id, subnet_zone


def build_run_instances_payload(
    *,
    zone: str | None,
    instance_type: str,
    image_id: str,
    system_disk_size_gb: int,
    vpc_id: str,
    subnet_id: str,
    bandwidth_out_mbps: int,
    worker_count: int,
    name_prefix: str,
    security_group_id: str,
    encoded_user_data: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "InstanceChargeType": "POSTPAID_BY_HOUR",
        "InstanceType": instance_type,
        "ImageId": image_id,
        "SystemDisk": {
            "DiskSize": system_disk_size_gb,
            "DiskType": "CLOUD_PREMIUM",
        },
        "VirtualPrivateCloud": {
            "VpcId": vpc_id,
            "SubnetId": subnet_id,
        },
        "InternetAccessible": {
            "PublicIpAssigned": True,
            "InternetMaxBandwidthOut": bandwidth_out_mbps,
        },
        "InstanceCount": worker_count,
        "InstanceName": f"{name_prefix}-worker-{{R:1}}",
        "SecurityGroupIds": [security_group_id],
        "EnhancedService": {
            "SecurityService": {"Enabled": True},
            "MonitorService": {"Enabled": True},
            "AutomationService": {"Enabled": True},
        },
        "UserData": encoded_user_data,
        "TagSpecification": [
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "ManagedBy", "Value": "OpenComputer"},
                    {"Key": "NamePrefix", "Value": name_prefix},
                    {"Key": "Role", "Value": "remote-docker-worker"},
                ],
            }
        ],
        "ClientToken": uuid.uuid4().hex,
    }
    cleaned_zone = (zone or "").strip()
    if cleaned_zone:
        payload["Placement"] = {"Zone": cleaned_zone}
    return payload


def render_user_data(
    *,
    bundle_url: str,
    tcr_personal_server: str,
    account_uin: str,
    tcr_password: str,
    image_uri: str,
    worker_agent_port: int,
    api_token: str,
    max_sessions: int,
    novnc_port_start: int,
    novnc_port_end: int,
) -> str:
    rendered = USER_DATA_TEMPLATE
    replacements = {
        "__BUNDLE_URL_SH__": shlex.quote(bundle_url),
        "__TCR_PERSONAL_SERVER_SH__": shlex.quote(tcr_personal_server),
        "__ACCOUNT_UIN_SH__": shlex.quote(account_uin),
        "__TCR_PASSWORD_SH__": shlex.quote(tcr_password),
        "__IMAGE_URI_SH__": shlex.quote(image_uri),
        "__API_TOKEN_SH__": shlex.quote(api_token),
        "__WORKER_AGENT_PORT__": str(worker_agent_port),
        "__MAX_SESSIONS__": str(max_sessions),
        "__NOVNC_PORT_START__": str(novnc_port_start),
        "__NOVNC_PORT_END__": str(novnc_port_end),
    }
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    return rendered


def _rule_signature(policy: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        str(policy.get("Protocol", "")).upper(),
        str(policy.get("Port", "")).lower(),
        str(policy.get("CidrBlock", "")),
        str(policy.get("Action", "")).upper(),
    )


def _policy_signature(policy) -> tuple[str, str, str, str]:
    return (
        str(getattr(policy, "Protocol", "")).upper(),
        str(getattr(policy, "Port", "")).lower(),
        str(getattr(policy, "CidrBlock", "")),
        str(getattr(policy, "Action", "")).upper(),
    )


def ensure_worker_security_group(
    vpc_client,
    *,
    name_prefix: str,
    controller_cidr: str,
    vpc_id: str,
    worker_agent_port: int,
    novnc_port_start: int,
    novnc_port_end: int,
) -> str:
    group_name = f"{name_prefix}-worker-sg"
    _log(f"Ensuring worker security group {group_name} in VPC {vpc_id}.")
    describe_request = tc_api.build_request(
        tc_api.vpc_models.DescribeSecurityGroupsRequest,
        {
            "Filters": [
                {"Name": "security-group-name", "Values": [group_name]},
                {"Name": "tag:NamePrefix", "Values": [name_prefix]},
            ],
            "Limit": "100",
        },
    )
    describe_response = vpc_client.DescribeSecurityGroups(describe_request)
    groups = sorted(
        describe_response.SecurityGroupSet or [],
        key=lambda item: str(item.SecurityGroupId or ""),
    )
    if groups:
        group = groups[0]
        group_id = str(group.SecurityGroupId)
        _log(f"Reusing existing security group {group_id}.")
    else:
        create_request = tc_api.build_request(
            tc_api.vpc_models.CreateSecurityGroupRequest,
            {
                "GroupName": group_name,
                "GroupDescription": "OpenComputer remote_docker workers",
                "Tags": [
                    {"Key": "ManagedBy", "Value": "OpenComputer"},
                    {"Key": "NamePrefix", "Value": name_prefix},
                    {"Key": "Role", "Value": "remote-docker-worker"},
                ],
            },
        )
        create_response = vpc_client.CreateSecurityGroup(create_request)
        group_id = str(create_response.SecurityGroup.SecurityGroupId)
        _log(f"Created security group {group_id}.")

    desired_ingress = [
        {
            "Protocol": "TCP",
            "Port": str(worker_agent_port),
            "CidrBlock": controller_cidr,
            "Action": "ACCEPT",
            "PolicyDescription": "controller worker agent",
        },
        {
            "Protocol": "TCP",
            "Port": f"{novnc_port_start}-{novnc_port_end}",
            "CidrBlock": controller_cidr,
            "Action": "ACCEPT",
            "PolicyDescription": "controller novnc",
        },
    ]
    desired_egress = [
        {
            "Protocol": "ALL",
            "Port": "all",
            "CidrBlock": "0.0.0.0/0",
            "Action": "ACCEPT",
            "PolicyDescription": "internet egress",
        }
    ]

    policies_request = tc_api.build_request(
        tc_api.vpc_models.DescribeSecurityGroupPoliciesRequest,
        {"SecurityGroupId": group_id},
    )
    policies_response = vpc_client.DescribeSecurityGroupPolicies(policies_request)
    policy_set = policies_response.SecurityGroupPolicySet
    existing_ingress = {
        _policy_signature(policy)
        for policy in ((policy_set.Ingress if policy_set else None) or [])
    }
    existing_egress = {
        _policy_signature(policy)
        for policy in ((policy_set.Egress if policy_set else None) or [])
    }
    missing_ingress = [
        rule for rule in desired_ingress if _rule_signature(rule) not in existing_ingress
    ]
    missing_egress = [
        rule for rule in desired_egress if _rule_signature(rule) not in existing_egress
    ]

    if missing_ingress:
        create_ingress_request = tc_api.build_request(
            tc_api.vpc_models.CreateSecurityGroupPoliciesRequest,
            {
                "SecurityGroupId": group_id,
                "SecurityGroupPolicySet": {
                    "Ingress": missing_ingress,
                },
            },
        )
        vpc_client.CreateSecurityGroupPolicies(create_ingress_request)
    if missing_egress:
        create_egress_request = tc_api.build_request(
            tc_api.vpc_models.CreateSecurityGroupPoliciesRequest,
            {
                "SecurityGroupId": group_id,
                "SecurityGroupPolicySet": {
                    "Egress": missing_egress,
                },
            },
        )
        vpc_client.CreateSecurityGroupPolicies(create_egress_request)
    _log(
        f"Security group {group_id} allows controller access on "
        f"{worker_agent_port} and noVNC range {novnc_port_start}-{novnc_port_end}."
    )
    return group_id


def describe_instances(cvm_client, instance_ids: list[str]) -> list[dict[str, object]]:
    if not instance_ids:
        return []
    request = tc_api.build_request(
        tc_api.cvm_models.DescribeInstancesRequest,
        {"InstanceIds": instance_ids},
    )
    response = cvm_client.DescribeInstances(request)
    return tc_api.response_to_dict(response).get("InstanceSet", [])


def wait_for_instances_running(cvm_client, instance_ids: list[str], timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    started_at = time.time()
    next_progress_log = 0.0
    while time.time() < deadline:
        instances = describe_instances(cvm_client, instance_ids)
        states = {
            str(item.get("InstanceId")): str(item.get("InstanceState"))
            for item in instances
        }
        if len(states) == len(instance_ids) and all(state == "RUNNING" for state in states.values()):
            _log("All CVM instances reached RUNNING state.")
            return
        now = time.time()
        if now >= next_progress_log:
            elapsed = int(now - started_at)
            _log(
                f"Waiting for CVM instances to reach RUNNING after {elapsed}s. "
                f"Current states: {states or 'pending visibility'}."
            )
            next_progress_log = now + 15
        time.sleep(5)
    raise TimeoutError(
        f"Instances did not reach RUNNING state within {timeout_seconds}s: {', '.join(instance_ids)}"
    )


def _health_check_hint(last_error: str) -> str:
    error_text = last_error.lower()
    if last_error == "no response received":
        return "instance is booting and worker bootstrap may still be in progress"
    if "connection refused" in error_text or "errno 61" in error_text or "errno 111" in error_text:
        return (
            "instance is reachable but worker-agent is not listening yet; "
            "cloud-init may still be installing packages or pulling the desktop image"
        )
    if "timed out" in error_text:
        return "worker-agent may be starting slowly or the instance may be under transient network load"
    if "401" in error_text or "403" in error_text:
        return "worker-agent responded but rejected the request; verify REMOTE_DOCKER_API_TOKEN"
    return "worker bootstrap or worker-agent startup may still be in progress"


def wait_for_worker_health(base_url: str, api_token: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    started_at = time.time()
    headers: dict[str, str] = {}
    last_error = "no response received"
    next_progress_log = 0.0
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    _log(
        f"Waiting for worker-agent health at {base_url}/healthz (timeout {timeout_seconds}s). "
        "CVM RUNNING only means the VM booted; worker-agent starts later, after cloud-init finishes "
        "installing dependencies, downloading the worker bundle, and pulling the desktop image."
    )
    while time.time() < deadline:
        now = time.time()
        if now >= next_progress_log:
            elapsed = int(now - started_at)
            _log(
                f"Health check still pending for {base_url} after {elapsed}s. "
                f"Last error: {last_error}. Likely state: {_health_check_hint(last_error)}."
            )
            next_progress_log = now + 15
        try:
            request = urllib.request.Request(f"{base_url}/healthz", headers=headers)
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status == 200:
                    _log(f"Worker-agent became healthy at {base_url}.")
                    return
                last_error = f"unexpected status {response.status}"
        except Exception as exc:
            last_error = str(exc) or exc.__class__.__name__
            time.sleep(5)
            continue
    raise TimeoutError(
        f"Worker agent at {base_url} did not become healthy within {timeout_seconds}s. "
        f"Last error: {last_error}. Last known state: {_health_check_hint(last_error)}. "
        "Check /var/log/cloud-init-output.log, systemctl status gui-synth-worker, and "
        "journalctl -u gui-synth-worker -n 200 --no-pager on the instance."
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
    args.controller_cidr = require_setting(
        args.controller_cidr,
        env_name="TENCENTCLOUD_CONTROLLER_CIDR",
        cli_flag="--controller-cidr",
        example="203.0.113.10/32",
    )
    args.zone = require_setting(
        args.zone,
        env_name="TENCENTCLOUD_CVM_ZONE",
        cli_flag="--zone",
        example="ap-guangzhou-3",
    )
    args.image_id = require_setting(
        args.image_id,
        env_name="TENCENTCLOUD_CVM_IMAGE_ID",
        cli_flag="--image-id",
        example="img-xxxxxxxx",
    )
    args.vpc_id = require_setting(
        args.vpc_id,
        env_name="TENCENTCLOUD_VPC_ID",
        cli_flag="--vpc-id",
        example="vpc-xxxxxxxx",
    )
    args.subnet_id = require_setting(
        args.subnet_id,
        env_name="TENCENTCLOUD_SUBNET_ID",
        cli_flag="--subnet-id",
        example="subnet-xxxxxxxx",
    )
    args.account_uin = require_setting(
        args.account_uin,
        env_name="TENCENTCLOUD_ACCOUNT_UIN",
        cli_flag="--account-uin",
        example="100012345678",
    )
    args.tcr_password = require_setting(
        args.tcr_password,
        env_name="TENCENTCLOUD_TCR_PERSONAL_PASSWORD",
        cli_flag="--tcr-password",
        example="replace-with-strong-password",
    )
    validate_tcr_password(args.tcr_password)
    if args.worker_count < 1:
        raise SystemExit("--worker-count must be at least 1.")
    if args.containers_per_worker < 1:
        raise SystemExit("--containers-per-worker must be at least 1.")
    if args.bandwidth_out_mbps < 1:
        raise SystemExit("--bandwidth-out-mbps must be at least 1 so workers receive public egress.")
    if args.system_disk_size_gb < 50:
        raise SystemExit("--system-disk-size-gb must be at least 50 GiB for the worker root disk.")
    args.cos_prefix = resolve_cos_prefix(args.cos_prefix, args.name_prefix)
    args.tcr_namespace = resolve_tcr_namespace(
        args.tcr_namespace,
        account_uin=args.account_uin,
        name_prefix=args.name_prefix,
    )

    tc_api.require_tencentcloud_dependencies()
    _log("Starting Tencent Cloud worker launch.")
    _log(
        "Config: "
        f"region={args.region}, zone={args.zone}, name_prefix={args.name_prefix}, "
        f"workers={args.worker_count}, containers_per_worker={args.containers_per_worker}, "
        f"instance_type={args.instance_type}"
    )
    cred = tc_api.get_credentials()
    cam = tc_api.build_cam_client(cred, args.region)
    cvm = tc_api.build_cvm_client(cred, args.region)
    vpc = tc_api.build_vpc_client(cred, args.region)
    cos_client = tc_api.build_cos_client(cred, args.region)

    identity = cam.GetUserAppId(tc_api.build_request(tc_api.cam_models.GetUserAppIdRequest))
    app_id = str(identity.AppId)
    if not (args.cos_bucket or "").strip():
        args.cos_bucket = build_default_cos_bucket_name(app_id, args.name_prefix)
        _log(f"No COS bucket was specified. Using derived bucket name: {args.cos_bucket}")
    if not args.cos_bucket.endswith(f"-{app_id}"):
        raise SystemExit(
            f"TENCENTCLOUD_COS_BUCKET must include the AppId suffix `-{app_id}`. "
            f"Current value: {args.cos_bucket}"
        )

    image_uri = build_tcr_image_uri(
        args.tcr_personal_server,
        args.tcr_namespace,
        args.tcr_repository,
    )
    _log(f"Target TCR image: {image_uri}")

    args.vpc_id, launch_zone = resolve_subnet_launch_context(
        vpc,
        subnet_id=args.subnet_id,
        requested_vpc_id=args.vpc_id,
        requested_zone=args.zone,
    )
    if launch_zone != args.zone:
        args.zone = launch_zone

    bootstrap_key = f"{args.cos_prefix.strip('/')}/worker-agent.zip"
    upload_worker_bundle(cos_client, args.cos_bucket, bootstrap_key)
    bundle_url = cos_client.get_presigned_download_url(
        Bucket=args.cos_bucket,
        Key=bootstrap_key,
        Expired=max(args.wait_seconds, 1800),
    )

    security_group_id = ensure_worker_security_group(
        vpc,
        name_prefix=args.name_prefix,
        controller_cidr=args.controller_cidr,
        vpc_id=args.vpc_id,
        worker_agent_port=args.worker_agent_port,
        novnc_port_start=args.novnc_port_start,
        novnc_port_end=args.novnc_port_end,
    )

    user_data = render_user_data(
        bundle_url=bundle_url,
        tcr_personal_server=args.tcr_personal_server,
        account_uin=args.account_uin,
        tcr_password=args.tcr_password,
        image_uri=image_uri,
        worker_agent_port=args.worker_agent_port,
        api_token=args.api_token,
        max_sessions=args.containers_per_worker,
        novnc_port_start=args.novnc_port_start,
        novnc_port_end=args.novnc_port_end,
    )
    encoded_user_data = base64.b64encode(user_data.encode("utf-8")).decode("ascii")

    run_payload = build_run_instances_payload(
        zone=args.zone,
        instance_type=args.instance_type,
        image_id=args.image_id,
        system_disk_size_gb=args.system_disk_size_gb,
        vpc_id=args.vpc_id,
        subnet_id=args.subnet_id,
        bandwidth_out_mbps=args.bandwidth_out_mbps,
        worker_count=args.worker_count,
        name_prefix=args.name_prefix,
        security_group_id=security_group_id,
        encoded_user_data=encoded_user_data,
    )

    instance_ids: list[str] = []
    launch_completed = False
    try:
        run_request = tc_api.build_request(tc_api.cvm_models.RunInstancesRequest, run_payload)
        try:
            response = cvm.RunInstances(run_request)
        except tc_api.TencentCloudSDKException as exc:
            if exc.code == "InvalidZone.MismatchRegion":
                raise SystemExit(
                    "CVM rejected the launch with `InvalidZone.MismatchRegion`, but the controller-side "
                    "checks already confirmed that the configured subnet and zone are consistent. "
                    f"Current config: region={args.region}, requested_zone={args.zone}, "
                    f"subnet={args.subnet_id}, vpc={args.vpc_id}, image_id={args.image_id}. "
                    "This is most likely not a provisioning code bug. It usually means the configured "
                    "`TENCENTCLOUD_CVM_IMAGE_ID` is not a standard CVM image usable in this target region "
                    "or target resource pool. Please verify this image in the Tencent Cloud console under "
                    "the same region, or replace it with a public Ubuntu image ID from the target region. "
                    "If the image is confirmed valid, then check whether the chosen instance type is actually "
                    "sellable in this zone."
                ) from exc
            raise
        instance_ids = list(response.InstanceIdSet or [])
        _log(f"Created instance(s): {', '.join(instance_ids)}")
        wait_for_instances_running(cvm, instance_ids, timeout_seconds=args.wait_seconds)

        workers: list[dict[str, object]] = []
        for item in describe_instances(cvm, instance_ids):
            instance_id = str(item.get("InstanceId"))
            public_ips = item.get("PublicIpAddresses") or []
            public_ip = str(public_ips[0]) if public_ips else ""
            if not public_ip:
                raise RuntimeError(f"Instance {instance_id} has no public IP.")
            base_url = f"http://{public_ip}:{args.worker_agent_port}"
            _log(
                f"Checking worker {instance_id} at public IP {public_ip} ({base_url})."
            )
            wait_for_worker_health(base_url, args.api_token, timeout_seconds=args.wait_seconds)
            workers.append(
                {
                    "worker_id": instance_id,
                    "instance_id": instance_id,
                    "public_ip": public_ip,
                    "base_url": base_url,
                    "region": args.region,
                    "max_sessions": args.containers_per_worker,
                    "metadata": {
                        "provider": "tencentcloud",
                        "registry_mode": "tcr_personal",
                        "name_prefix": args.name_prefix,
                        "instance_type": args.instance_type,
                        "zone": args.zone,
                    },
                }
            )

        pool_file = Path(args.pool_file).expanduser()
        pool_file.parent.mkdir(parents=True, exist_ok=True)
        _log(f"Writing local worker pool file to {pool_file}.")
        pool_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "region": args.region,
                    "updated_at": int(time.time()),
                    "workers": workers,
                },
                indent=2,
            )
            + "\n"
        )
        launch_completed = True
        _log("Worker launch completed successfully.")
        print(
            json.dumps(
                {
                    "pool_file": str(pool_file),
                    "workers": workers,
                    "security_group_id": security_group_id,
                    "docker_image_uri": image_uri,
                },
                indent=2,
            )
        )
    except BaseException:
        if instance_ids and not launch_completed:
            if args.keep_failed_instances:
                _log(
                    "Launch failed after creating CVM instance(s), "
                    "but leaving them running because --keep-failed-instances was set."
                )
            else:
                _log(
                    "Launch failed after creating CVM instance(s). "
                    f"Submitting best-effort cleanup for: {', '.join(instance_ids)}"
                )
                try:
                    terminate_request = tc_api.build_request(
                        tc_api.cvm_models.TerminateInstancesRequest,
                        {"InstanceIds": instance_ids},
                    )
                    cvm.TerminateInstances(terminate_request)
                except Exception as cleanup_exc:  # pragma: no cover - cleanup path
                    _log(f"Automatic instance cleanup failed: {cleanup_exc}")
        raise


if __name__ == "__main__":
    main()
