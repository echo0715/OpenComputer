#!/usr/bin/env python3
"""
Create or verify AWS prerequisites for remote_docker workers.

Usage:
    python -m computer_env.provision.aws.setup_prereqs
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
    DEFAULT_AWS_REGION,
    DEFAULT_DEBUG_ACCESS,
    DEFAULT_ECR_REPOSITORY,
    DEFAULT_INSTANCE_PROFILE_NAME,
    DEFAULT_NAME_PREFIX,
    DEFAULT_S3_BUCKET,
    build_default_s3_bucket_name,
    build_ecr_image_uri,
    require_setting,
    resolve_ecr_repository,
    resolve_instance_profile_name,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or verify AWS prerequisites for remote_docker workers.")
    parser.add_argument("--region", default=DEFAULT_AWS_REGION,
                        help="AWS deployment region. Required via .env or --region.")
    parser.add_argument("--name-prefix", default=DEFAULT_NAME_PREFIX,
                        help="Resource naming prefix. Required via .env or --name-prefix.")
    parser.add_argument("--ecr-repo", default=DEFAULT_ECR_REPOSITORY,
                        help="Optional ECR repository override. Defaults to <name-prefix>-desktop.")
    parser.add_argument("--s3-bucket", default=DEFAULT_S3_BUCKET,
                        help="Optional S3 bucket override. Defaults to <name-prefix>-assets-<account_id>.")
    parser.add_argument("--instance-profile-name", default=DEFAULT_INSTANCE_PROFILE_NAME,
                        help="Optional instance profile override. Defaults to <name-prefix>-worker.")
    parser.add_argument("--debug-access", choices=["SSM", "SSH"], default=DEFAULT_DEBUG_ACCESS,
                        help="Worker debug access mode (default: SSM).")
    return parser.parse_args()


def ensure_bucket(s3_client, region: str, bucket: str) -> None:
    try:
        s3_client.head_bucket(Bucket=bucket)
        return
    except ClientError:
        pass

    kwargs = {"Bucket": bucket}
    if region != "us-east-1":
        kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
    s3_client.create_bucket(**kwargs)


def ensure_ecr_repo(ecr_client, repository: str) -> None:
    try:
        ecr_client.describe_repositories(repositoryNames=[repository])
        return
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code != "RepositoryNotFoundException":
            raise
    ecr_client.create_repository(repositoryName=repository)


def ensure_role_and_profile(iam_client, role_name: str, profile_name: str, bucket: str, debug_access: str) -> str:
    assume_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
    try:
        iam_client.get_role(RoleName=role_name)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchEntity":
            raise
        iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(assume_policy),
            Description="Remote docker worker role for OpenComputer AWS sessions.",
        )

    inline_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchCheckLayerAvailability",
                ],
                "Resource": "*",
            },
            {
                "Effect": "Allow",
                "Action": [
                    "s3:ListBucket",
                ],
                "Resource": f"arn:aws:s3:::{bucket}",
            },
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                ],
                "Resource": f"arn:aws:s3:::{bucket}/*",
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                "Resource": "*",
            },
        ],
    }
    iam_client.put_role_policy(
        RoleName=role_name,
        PolicyName=f"{role_name}-inline",
        PolicyDocument=json.dumps(inline_policy),
    )

    if debug_access == "SSM":
        iam_client.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
        )

    try:
        iam_client.get_instance_profile(InstanceProfileName=profile_name)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchEntity":
            raise
        iam_client.create_instance_profile(InstanceProfileName=profile_name)
        time.sleep(2)

    profile = iam_client.get_instance_profile(InstanceProfileName=profile_name)["InstanceProfile"]
    attached_roles = {item["RoleName"] for item in profile.get("Roles", [])}
    if role_name not in attached_roles:
        iam_client.add_role_to_instance_profile(InstanceProfileName=profile_name, RoleName=role_name)
        time.sleep(5)
    return role_name


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
    args.ecr_repo = resolve_ecr_repository(args.ecr_repo, args.name_prefix)
    args.instance_profile_name = resolve_instance_profile_name(
        args.instance_profile_name,
        args.name_prefix,
    )
    if boto3 is None:
        raise SystemExit("boto3 is required for AWS provisioning scripts. Install it with `pip install boto3`.")

    session = boto3.Session(region_name=args.region)
    sts = session.client("sts")
    s3 = session.client("s3")
    ecr = session.client("ecr")
    iam = session.client("iam")

    account_id = sts.get_caller_identity()["Account"]
    if not (args.s3_bucket or "").strip():
        args.s3_bucket = build_default_s3_bucket_name(account_id, args.name_prefix)
    ensure_bucket(s3, args.region, args.s3_bucket)
    ensure_ecr_repo(ecr, args.ecr_repo)
    role_name = ensure_role_and_profile(
        iam,
        role_name=f"{args.name_prefix}-worker-role",
        profile_name=args.instance_profile_name,
        bucket=args.s3_bucket,
        debug_access=args.debug_access,
    )

    summary = {
        "account_id": account_id,
        "region": args.region,
        "ecr_repository": args.ecr_repo,
        "ecr_image_uri": build_ecr_image_uri(account_id, args.region, args.ecr_repo),
        "s3_bucket": args.s3_bucket,
        "instance_profile_name": args.instance_profile_name,
        "role_name": role_name,
        "debug_access": args.debug_access,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
