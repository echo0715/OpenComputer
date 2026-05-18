#!/usr/bin/env python3
"""
Launch remote_docker workers on AWS EC2 instances.

Usage:
    python -m computer_env.provision.aws.launch_workers
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

try:
    import dotenv
except ModuleNotFoundError:
    dotenv = None

try:
    import boto3
    from botocore.exceptions import ClientError
except ModuleNotFoundError:
    boto3 = None

    class ClientError(Exception):
        pass

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

if dotenv is not None:
    dotenv.load_dotenv(REPO_ROOT / ".env")

from computer_env.provision.aws import (
    DEFAULT_AWS_PROFILE,
    DEFAULT_AWS_REGION,
    DEFAULT_BOOTSTRAP_PREFIX,
    DEFAULT_CONTAINERS_PER_WORKER,
    DEFAULT_CONTROLLER_CIDR,
    DEFAULT_DEBUG_ACCESS,
    DEFAULT_ECR_REPOSITORY,
    DEFAULT_INSTANCE_PROFILE_NAME,
    DEFAULT_NAME_PREFIX,
    DEFAULT_NOVNC_PORT_END,
    DEFAULT_NOVNC_PORT_START,
    DEFAULT_S3_BUCKET,
    DEFAULT_SUBNET_ID,
    DEFAULT_VPC_ID,
    DEFAULT_WORKER_AGENT_PORT,
    DEFAULT_WORKER_COUNT,
    DEFAULT_WORKER_INSTANCE_TYPE,
    DEFAULT_WORKER_ROOT_VOLUME_SIZE_GB,
    build_default_s3_bucket_name,
    build_ecr_image_uri,
    require_setting,
    resolve_bootstrap_prefix,
    resolve_ecr_repository,
    resolve_instance_profile_name,
    worker_pool_path,
)

WORKER_AGENT_DIR = Path(__file__).resolve().parent / "worker_agent"
USER_DATA_TEMPLATE = (Path(__file__).resolve().parent / "worker_user_data.sh").read_text()
DEFAULT_UBUNTU_RELEASE = os.getenv("AWS_WORKER_UBUNTU_RELEASE", "24.04")
UBUNTU_RELEASE_VOLUME_TYPE = {
    "20.04": "ebs-gp2",
    "22.04": "ebs-gp2",
    "24.04": "ebs-gp3",
    "26.04": "ebs-gp3",
}


def _log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[launch_workers {timestamp}] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch AWS remote_docker workers and write the local worker pool file.")
    parser.add_argument("--region", default=DEFAULT_AWS_REGION,
                        help="AWS deployment region. Required via .env or --region.")
    parser.add_argument("--name-prefix", default=DEFAULT_NAME_PREFIX,
                        help="Resource naming prefix. Required via .env or --name-prefix.")
    parser.add_argument("--controller-cidr", default=DEFAULT_CONTROLLER_CIDR,
                        help="Required ingress CIDR for the controller machine.")
    parser.add_argument("--ecr-repo", default=DEFAULT_ECR_REPOSITORY,
                        help="Optional ECR repository override. Defaults to <name-prefix>-desktop.")
    parser.add_argument("--s3-bucket", default=DEFAULT_S3_BUCKET,
                        help="Optional S3 bucket override. Defaults to <name-prefix>-assets-<account_id>.")
    parser.add_argument("--instance-profile-name", default=DEFAULT_INSTANCE_PROFILE_NAME,
                        help="Optional instance profile override. Defaults to <name-prefix>-worker.")
    parser.add_argument("--instance-type", default=DEFAULT_WORKER_INSTANCE_TYPE)
    parser.add_argument("--ubuntu-release", default=DEFAULT_UBUNTU_RELEASE, help="Ubuntu release for the worker AMI, e.g. 22.04 or 24.04.")
    parser.add_argument("--worker-count", type=int, default=DEFAULT_WORKER_COUNT)
    parser.add_argument("--containers-per-worker", type=int, default=DEFAULT_CONTAINERS_PER_WORKER)
    parser.add_argument("--vpc-id", default=DEFAULT_VPC_ID)
    parser.add_argument("--subnet-id", default=DEFAULT_SUBNET_ID)
    parser.add_argument("--debug-access", choices=["SSM", "SSH"], default=DEFAULT_DEBUG_ACCESS)
    parser.add_argument("--worker-agent-port", type=int, default=DEFAULT_WORKER_AGENT_PORT)
    parser.add_argument("--novnc-port-start", type=int, default=DEFAULT_NOVNC_PORT_START)
    parser.add_argument("--novnc-port-end", type=int, default=DEFAULT_NOVNC_PORT_END)
    parser.add_argument(
        "--root-volume-size-gb",
        type=int,
        default=DEFAULT_WORKER_ROOT_VOLUME_SIZE_GB,
        help="Root EBS volume size in GiB for worker instances.",
    )
    parser.add_argument("--bootstrap-prefix", default=DEFAULT_BOOTSTRAP_PREFIX,
                        help="Optional bootstrap S3 prefix override. Defaults to bootstrap/<name-prefix>.")
    parser.add_argument("--pool-file", default=str(worker_pool_path()))
    parser.add_argument("--api-token", default=os.getenv("REMOTE_DOCKER_API_TOKEN") or "")
    parser.add_argument("--key-name", default=None, help="Required only when --debug-access SSH.")
    parser.add_argument(
        "--keep-failed-instances",
        action="store_true",
        help="Keep EC2 instances running when launch fails after instance creation.",
    )
    parser.add_argument("--wait-seconds", type=int, default=360)
    return parser.parse_args()


def build_worker_bundle() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(WORKER_AGENT_DIR.rglob("*")):
            if path.is_dir():
                continue
            archive.write(path, path.relative_to(WORKER_AGENT_DIR))
    return buffer.getvalue()


def upload_worker_bundle(s3_client, bucket: str, key: str) -> None:
    payload = build_worker_bundle()
    _log(
        f"Uploading worker-agent bundle to s3://{bucket}/{key} "
        f"({len(payload) / 1024:.1f} KiB)"
    )
    s3_client.put_object(Bucket=bucket, Key=key, Body=payload, ContentType="application/zip")
    _log("Worker-agent bundle uploaded.")


def resolve_vpc_id(ec2_client, explicit_vpc_id: str | None, *, region: str) -> str:
    cleaned_vpc_id = (explicit_vpc_id or "").strip()
    if cleaned_vpc_id:
        return cleaned_vpc_id

    response = ec2_client.describe_vpcs(
        Filters=[{"Name": "is-default", "Values": ["true"]}]
    )
    vpcs = sorted(
        str(item["VpcId"])
        for item in response.get("Vpcs", [])
        if item.get("VpcId")
    )
    if len(vpcs) == 1:
        resolved = vpcs[0]
        _log(f"No VPC was specified. Using the default VPC in {region}: {resolved}")
        return resolved
    if not vpcs:
        raise RuntimeError(
            "No AWS_VPC_ID or --vpc-id was provided, and no default VPC was found "
            f"in region {region}. Create/select a VPC and set AWS_VPC_ID explicitly."
        )
    raise RuntimeError(
        "No AWS_VPC_ID or --vpc-id was provided, and multiple default VPC candidates were found. "
        "Set AWS_VPC_ID explicitly."
    )


def resolve_subnet_id(ec2_client, explicit_subnet_id: str | None, *, vpc_id: str) -> str:
    cleaned_subnet_id = (explicit_subnet_id or "").strip()
    if cleaned_subnet_id:
        return cleaned_subnet_id

    response = ec2_client.describe_subnets(
        Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
    )
    subnets = response.get("Subnets", [])
    default_subnets = sorted(
        (
            item for item in subnets
            if item.get("SubnetId") and item.get("DefaultForAz")
        ),
        key=lambda item: (str(item.get("AvailabilityZone") or ""), str(item["SubnetId"])),
    )
    if default_subnets:
        resolved = str(default_subnets[0]["SubnetId"])
        _log(f"No subnet was specified. Using a default subnet in VPC {vpc_id}: {resolved}")
        return resolved

    if len(subnets) == 1 and subnets[0].get("SubnetId"):
        resolved = str(subnets[0]["SubnetId"])
        _log(f"No subnet was specified. Using the only subnet in VPC {vpc_id}: {resolved}")
        return resolved

    if not subnets:
        raise RuntimeError(
            f"No AWS_SUBNET_ID or --subnet-id was provided, and VPC {vpc_id} has no subnets."
        )
    raise RuntimeError(
        "No AWS_SUBNET_ID or --subnet-id was provided, and a default subnet could not be "
        f"uniquely resolved inside VPC {vpc_id}. Set AWS_SUBNET_ID explicitly."
    )


def ensure_worker_security_group(ec2_client, *, vpc_id: str, name_prefix: str, controller_cidr: str, debug_access: str,
                                 worker_agent_port: int, novnc_port_start: int, novnc_port_end: int) -> str:
    group_name = f"{name_prefix}-worker-sg"
    _log(f"Ensuring worker security group {group_name} in VPC {vpc_id}.")
    response = ec2_client.describe_security_groups(
        Filters=[
            {"Name": "group-name", "Values": [group_name]},
            {"Name": "vpc-id", "Values": [vpc_id]},
        ]
    )
    if response["SecurityGroups"]:
        group_id = response["SecurityGroups"][0]["GroupId"]
        _log(f"Reusing existing security group {group_id}.")
    else:
        created = ec2_client.create_security_group(
            GroupName=group_name,
            Description="OpenComputer remote_docker workers",
            VpcId=vpc_id,
            TagSpecifications=[
                {
                    "ResourceType": "security-group",
                    "Tags": [
                        {"Key": "Name", "Value": group_name},
                        {"Key": "ManagedBy", "Value": "OpenComputer"},
                        {"Key": "NamePrefix", "Value": name_prefix},
                    ],
                }
            ],
        )
        group_id = created["GroupId"]
        _log(f"Created security group {group_id}.")

    desired_permissions = [
        {
            "IpProtocol": "tcp",
            "FromPort": worker_agent_port,
            "ToPort": worker_agent_port,
            "IpRanges": [{"CidrIp": controller_cidr, "Description": "controller"}],
        },
        {
            "IpProtocol": "tcp",
            "FromPort": novnc_port_start,
            "ToPort": novnc_port_end,
            "IpRanges": [{"CidrIp": controller_cidr, "Description": "controller novnc"}],
        },
    ]
    if debug_access == "SSH":
        desired_permissions.append(
            {
                "IpProtocol": "tcp",
                "FromPort": 22,
                "ToPort": 22,
                "IpRanges": [{"CidrIp": controller_cidr, "Description": "controller ssh"}],
            }
        )

    for permission in desired_permissions:
        try:
            ec2_client.authorize_security_group_ingress(GroupId=group_id, IpPermissions=[permission])
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "InvalidPermission.Duplicate":
                raise
    _log(
        f"Security group {group_id} allows controller access on "
        f"{worker_agent_port} and noVNC range {novnc_port_start}-{novnc_port_end}."
    )
    return group_id


def _canonical_ubuntu_ssm_parameter(release: str, volume_type: str) -> str:
    return f"/aws/service/canonical/ubuntu/server/{release}/stable/current/amd64/hvm/{volume_type}/ami-id"


def resolve_ubuntu_ami(ssm_client, ubuntu_release: str) -> str:
    preferred_volume_type = UBUNTU_RELEASE_VOLUME_TYPE.get(ubuntu_release, "ebs-gp3")
    candidate_volume_types = [preferred_volume_type]
    for fallback in ("ebs-gp3", "ebs-gp2"):
        if fallback not in candidate_volume_types:
            candidate_volume_types.append(fallback)

    last_error: Exception | None = None
    for volume_type in candidate_volume_types:
        parameter_name = _canonical_ubuntu_ssm_parameter(ubuntu_release, volume_type)
        _log(f"Resolving Ubuntu {ubuntu_release} AMI via SSM parameter {parameter_name}.")
        try:
            response = ssm_client.get_parameter(Name=parameter_name)
            _log(f"Resolved Ubuntu {ubuntu_release} AMI: {response['Parameter']['Value']}")
            return response["Parameter"]["Value"]
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code != "ParameterNotFound":
                raise
            last_error = exc

    raise RuntimeError(
        f"Could not resolve a Canonical Ubuntu AMI for release {ubuntu_release}. "
        f"Tried volume types: {', '.join(candidate_volume_types)}."
    ) from last_error


def resolve_root_device_name(ec2_client, image_id: str) -> str:
    _log(f"Resolving root device name for AMI {image_id}.")
    response = ec2_client.describe_images(ImageIds=[image_id])
    images = response.get("Images", [])
    if not images:
        raise RuntimeError(f"Could not resolve image metadata for AMI {image_id}.")
    root_device_name = images[0].get("RootDeviceName")
    if not root_device_name:
        raise RuntimeError(f"AMI {image_id} does not expose a root device name.")
    _log(f"AMI {image_id} root device name: {root_device_name}")
    return root_device_name


def render_user_data(*, region: str, account_id: str, s3_bucket: str, bootstrap_key: str, ecr_image: str,
                     worker_agent_port: int, api_token: str, max_sessions: int, novnc_port_start: int,
                     novnc_port_end: int) -> str:
    rendered = USER_DATA_TEMPLATE
    replacements = {
        "__REGION__": region,
        "__ACCOUNT_ID__": account_id,
        "__S3_BUCKET__": s3_bucket,
        "__BOOTSTRAP_KEY__": bootstrap_key,
        "__ECR_IMAGE__": ecr_image,
        "__WORKER_AGENT_PORT__": str(worker_agent_port),
        "__API_TOKEN__": api_token,
        "__MAX_SESSIONS__": str(max_sessions),
        "__NOVNC_PORT_START__": str(novnc_port_start),
        "__NOVNC_PORT_END__": str(novnc_port_end),
    }
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    return rendered


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
    headers = {}
    last_error = "no response received"
    next_progress_log = 0.0
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    _log(
        f"Waiting for worker-agent health at {base_url}/healthz (timeout {timeout_seconds}s). "
        "EC2 'running' only means the VM booted; worker-agent starts later, after cloud-init finishes "
        "installing dependencies and the initial desktop image pull completes."
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
    if args.debug_access == "SSH" and not args.key_name:
        raise SystemExit("--key-name is required when --debug-access SSH")
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
    args.controller_cidr = require_setting(
        args.controller_cidr,
        env_name="AWS_CONTROLLER_CIDR",
        cli_flag="--controller-cidr",
        example="203.0.113.10/32",
    )
    args.ecr_repo = resolve_ecr_repository(args.ecr_repo, args.name_prefix)
    args.instance_profile_name = resolve_instance_profile_name(
        args.instance_profile_name,
        args.name_prefix,
    )
    args.bootstrap_prefix = resolve_bootstrap_prefix(args.bootstrap_prefix, args.name_prefix)
    if boto3 is None:
        raise SystemExit("boto3 is required for AWS provisioning scripts. Install it with `pip install boto3`.")

    _log("Starting AWS worker launch.")
    _log(
        "Config: "
        f"region={args.region}, profile={DEFAULT_AWS_PROFILE or '<default credential chain>'}, "
        f"name_prefix={args.name_prefix}, workers={args.worker_count}, "
        f"containers_per_worker={args.containers_per_worker}, "
        f"instance_type={args.instance_type}, ubuntu_release={args.ubuntu_release}"
    )

    # Step 1: authenticate and resolve resources
    session = boto3.Session(region_name=args.region)
    sts = session.client("sts")
    s3 = session.client("s3")
    ec2 = session.client("ec2")
    ssm = session.client("ssm")
    account_id = sts.get_caller_identity()["Account"]
    if not (args.s3_bucket or "").strip():
        args.s3_bucket = build_default_s3_bucket_name(account_id, args.name_prefix)
        _log(f"No S3 bucket was specified. Using derived bucket name: {args.s3_bucket}")
    args.vpc_id = resolve_vpc_id(ec2, args.vpc_id, region=args.region)
    args.subnet_id = resolve_subnet_id(ec2, args.subnet_id, vpc_id=args.vpc_id)
    # build ECR image URI
    ecr_image = build_ecr_image_uri(account_id, args.region, args.ecr_repo)
    _log(f"Authenticated to AWS account {account_id}.")
    _log(f"Target ECR image: {ecr_image}")

    # Step 2: build and upload worker bundle to S3
    bootstrap_key = f"{args.bootstrap_prefix.strip('/')}/worker-agent.zip"
    upload_worker_bundle(s3, args.s3_bucket, bootstrap_key)
    
    # Step 3: prepare security group
    security_group_id = ensure_worker_security_group(
        ec2,
        vpc_id=args.vpc_id,
        name_prefix=args.name_prefix,
        controller_cidr=args.controller_cidr,
        debug_access=args.debug_access,
        worker_agent_port=args.worker_agent_port,
        novnc_port_start=args.novnc_port_start,
        novnc_port_end=args.novnc_port_end,
    )

    # Step 4: resolve AMI
    image_id = resolve_ubuntu_ami(ssm, args.ubuntu_release)
    root_device_name = resolve_root_device_name(ec2, image_id)

    # Step 5: prepare user data for worker instances
    user_data = render_user_data(
        region=args.region,
        account_id=account_id,
        s3_bucket=args.s3_bucket,
        bootstrap_key=bootstrap_key,
        ecr_image=ecr_image,
        worker_agent_port=args.worker_agent_port,
        api_token=args.api_token,
        max_sessions=args.containers_per_worker,
        novnc_port_start=args.novnc_port_start,
        novnc_port_end=args.novnc_port_end,
    )

    run_params = {
        "ImageId": image_id,
        "InstanceType": args.instance_type,
        "MinCount": args.worker_count,
        "MaxCount": args.worker_count,
        "IamInstanceProfile": {"Name": args.instance_profile_name},
        "UserData": user_data,
        "NetworkInterfaces": [
            {
                "DeviceIndex": 0,
                "AssociatePublicIpAddress": True,
                "SubnetId": args.subnet_id,
                "Groups": [security_group_id],
            }
        ],
        "TagSpecifications": [
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": f"{args.name_prefix}-worker"},
                    {"Key": "ManagedBy", "Value": "OpenComputer"},
                    {"Key": "NamePrefix", "Value": args.name_prefix},
                    {"Key": "Role", "Value": "remote-docker-worker"},
                ],
            },
            {
                "ResourceType": "volume",
                "Tags": [
                    {"Key": "ManagedBy", "Value": "OpenComputer"},
                    {"Key": "NamePrefix", "Value": args.name_prefix},
                ],
            },
        ],
        "BlockDeviceMappings": [
            {
                "DeviceName": root_device_name,
                "Ebs": {
                    "DeleteOnTermination": True,
                    "VolumeSize": args.root_volume_size_gb,
                    "VolumeType": "gp3",
                },
            }
        ],
    }
    if args.debug_access == "SSH" and args.key_name:
        run_params["KeyName"] = args.key_name

    _log(
        f"Launching {args.worker_count} worker EC2 instance(s) in subnet {args.subnet_id} "
        f"with security group {security_group_id}."
    )

    # Step 6: Launch EC2 instances
    instance_ids: list[str] = []
    launch_completed = False
    try:
        response = ec2.run_instances(**run_params)
        instance_ids = [instance["InstanceId"] for instance in response["Instances"]]
        _log(f"Created instance(s): {', '.join(instance_ids)}")
        _log("Waiting for EC2 instance(s) to reach running state.")
        # wait for instances to be running
        # only means the instance is ready, not that worker-agent is ready
        ec2.get_waiter("instance_running").wait(InstanceIds=instance_ids)
        _log(
            "EC2 instance(s) are now running. Bootstrap is still continuing inside user-data: "
            "installing Docker/AWS CLI, downloading the worker bundle, logging into ECR, and pulling the desktop image."
        )

        # get public IP addresses and health check
        _log("Describing running instance(s) to discover public IPs.")
        describe = ec2.describe_instances(InstanceIds=instance_ids)
        workers = []
        for reservation in describe["Reservations"]:
            for instance in reservation["Instances"]:
                # get public IP
                public_ip = instance.get("PublicIpAddress")
                if not public_ip:
                    raise RuntimeError(f"Instance {instance['InstanceId']} has no public IP.")
                base_url = f"http://{public_ip}:{args.worker_agent_port}"
                _log(
                    f"Checking worker {instance['InstanceId']} at public IP {public_ip} "
                    f"({base_url})."
                )
                # wait for worker-agent to be healthy
                wait_for_worker_health(base_url, args.api_token, timeout_seconds=args.wait_seconds)
                workers.append(
                    {
                        "worker_id": instance["InstanceId"],
                        "instance_id": instance["InstanceId"],
                        "public_ip": public_ip,
                        "base_url": base_url,
                        "region": args.region,
                        "max_sessions": args.containers_per_worker,
                        "metadata": {
                            "name_prefix": args.name_prefix,
                            "instance_type": args.instance_type,
                        },
                    }
                )

        # Step 7: write local pool file
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

        print(json.dumps({"pool_file": str(pool_file), "workers": workers, "security_group_id": security_group_id}, indent=2))
    except BaseException:
        if instance_ids and not launch_completed:
            if args.keep_failed_instances:
                _log(
                    "Launch failed after creating EC2 instance(s), "
                    "but leaving them running because --keep-failed-instances was set."
                )
            else:
                _log(
                    "Launch failed after creating EC2 instance(s). "
                    f"Submitting best-effort cleanup for: {', '.join(instance_ids)}"
                )
                try:
                    ec2.terminate_instances(InstanceIds=instance_ids)
                except Exception as cleanup_exc:  # pragma: no cover - cleanup path
                    _log(f"Automatic instance cleanup failed: {cleanup_exc}")
        raise


if __name__ == "__main__":
    main()
