#!/usr/bin/env python3
"""
Create or verify Tencent Cloud prerequisites for remote_docker workers.

Usage:
    python -m computer_env.provision.tencentcloud.setup_prereqs
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
    DEFAULT_ACCOUNT_UIN,
    DEFAULT_COS_BUCKET,
    DEFAULT_COS_PREFIX,
    DEFAULT_NAME_PREFIX,
    DEFAULT_TCR_PERSONAL_NAMESPACE,
    DEFAULT_TCR_PERSONAL_PASSWORD,
    DEFAULT_TCR_PERSONAL_REPOSITORY,
    DEFAULT_TCR_PERSONAL_SERVER,
    DEFAULT_TENCENTCLOUD_REGION,
    build_default_cos_bucket_name,
    build_tcr_image_uri,
    require_setting,
    resolve_cos_prefix,
    resolve_tcr_namespace,
    validate_tcr_password,
)
from computer_env.provision.tencentcloud import api as tc_api


def _log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[setup_prereqs {timestamp}] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or verify Tencent Cloud prerequisites for remote_docker workers."
    )
    parser.add_argument("--region", default=DEFAULT_TENCENTCLOUD_REGION)
    parser.add_argument("--name-prefix", default=DEFAULT_NAME_PREFIX)
    parser.add_argument("--cos-bucket", default=DEFAULT_COS_BUCKET)
    parser.add_argument("--cos-prefix", default=DEFAULT_COS_PREFIX)
    parser.add_argument("--account-uin", default=DEFAULT_ACCOUNT_UIN)
    parser.add_argument("--tcr-personal-server", default=DEFAULT_TCR_PERSONAL_SERVER)
    parser.add_argument("--tcr-namespace", default=DEFAULT_TCR_PERSONAL_NAMESPACE)
    parser.add_argument("--tcr-repository", default=DEFAULT_TCR_PERSONAL_REPOSITORY)
    parser.add_argument("--tcr-password", default=DEFAULT_TCR_PERSONAL_PASSWORD)
    return parser.parse_args()


def ensure_bucket(cos_client, bucket: str) -> str:
    if cos_client.bucket_exists(Bucket=bucket):
        return "reused"
    cos_client.create_bucket(Bucket=bucket)
    return "created"


def ensure_tcr_user_password(tcr, password: str) -> str:
    create_request = tc_api.build_request(
        tc_api.tcr_models.CreateUserPersonalRequest,
        {"Password": password},
    )
    try:
        tcr.CreateUserPersonal(create_request)
        return "created"
    except tc_api.TencentCloudSDKException as exc:
        if not tc_api.is_already_exists_error(exc):
            raise
    modify_request = tc_api.build_request(
        tc_api.tcr_models.ModifyUserPasswordPersonalRequest,
        {"Password": password},
    )
    tcr.ModifyUserPasswordPersonal(modify_request)
    return "password_reset"


def ensure_namespace(tcr, namespace: str) -> str:
    validate_request = tc_api.build_request(
        tc_api.tcr_models.ValidateNamespaceExistPersonalRequest,
        {"Namespace": namespace},
    )
    validate_response = tcr.ValidateNamespaceExistPersonal(validate_request)
    if validate_response.Data and validate_response.Data.IsExist:
        return "reused"
    if validate_response.Data and validate_response.Data.IsPreserved:
        raise SystemExit(
            f"TCR Personal namespace `{namespace}` is reserved by Tencent Cloud. "
            "Set TENCENTCLOUD_TCR_PERSONAL_NAMESPACE to a different value."
        )
    create_request = tc_api.build_request(
        tc_api.tcr_models.CreateNamespacePersonalRequest,
        {"Namespace": namespace},
    )
    try:
        tcr.CreateNamespacePersonal(create_request)
        return "created"
    except tc_api.TencentCloudSDKException as exc:
        if tc_api.is_already_exists_error(exc):
            return "reused"
        raise


def ensure_repository(tcr, namespace: str, repository: str) -> str:
    repo_name = f"{namespace}/{repository}"
    validate_request = tc_api.build_request(
        tc_api.tcr_models.ValidateRepositoryExistPersonalRequest,
        {"RepoName": repo_name},
    )
    validate_response = tcr.ValidateRepositoryExistPersonal(validate_request)
    if validate_response.Data and validate_response.Data.IsExist:
        return "reused"

    create_request = tc_api.build_request(
        tc_api.tcr_models.CreateRepositoryPersonalRequest,
        {
            "RepoName": repo_name,
            "Public": 0,
            "Description": "OpenComputer remote_docker desktop image",
        },
    )
    try:
        tcr.CreateRepositoryPersonal(create_request)
        return "created"
    except tc_api.TencentCloudSDKException as exc:
        if tc_api.is_already_exists_error(exc):
            return "reused"
        raise


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
    args.cos_prefix = resolve_cos_prefix(args.cos_prefix, args.name_prefix)
    args.tcr_namespace = resolve_tcr_namespace(
        args.tcr_namespace,
        account_uin=args.account_uin,
        name_prefix=args.name_prefix,
    )

    tc_api.require_tencentcloud_dependencies()
    cred = tc_api.get_credentials()
    cam = tc_api.build_cam_client(cred, args.region)
    tcr = tc_api.build_tcr_client(cred, args.region)

    _log("Resolving current Tencent Cloud account identity.")
    identity = cam.GetUserAppId(tc_api.build_request(tc_api.cam_models.GetUserAppIdRequest))
    app_id = str(identity.AppId)
    detected_uin = str(identity.Uin)
    owner_uin = str(identity.OwnerUin)
    if not (args.cos_bucket or "").strip():
        args.cos_bucket = build_default_cos_bucket_name(app_id, args.name_prefix)
        _log(f"No COS bucket was specified. Using derived bucket name: {args.cos_bucket}")
    expected_bucket_suffix = f"-{app_id}"
    if not args.cos_bucket.endswith(expected_bucket_suffix):
        raise SystemExit(
            f"TENCENTCLOUD_COS_BUCKET must include the AppId suffix `{expected_bucket_suffix}`. "
            f"Current value: {args.cos_bucket}"
        )

    cos_client = tc_api.build_cos_client(cred, args.region)
    _log(f"Ensuring COS bucket `{args.cos_bucket}` in region {args.region}.")
    bucket_action = ensure_bucket(cos_client, args.cos_bucket)

    _log("Ensuring TCR Personal user state.")
    user_action = ensure_tcr_user_password(tcr, args.tcr_password)

    _log(f"Ensuring TCR Personal namespace `{args.tcr_namespace}`.")
    namespace_action = ensure_namespace(tcr, args.tcr_namespace)

    _log(f"Ensuring TCR Personal repository `{args.tcr_namespace}/{args.tcr_repository}`.")
    repository_action = ensure_repository(tcr, args.tcr_namespace, args.tcr_repository)

    docker_image_uri = build_tcr_image_uri(
        args.tcr_personal_server,
        args.tcr_namespace,
        args.tcr_repository,
    )
    summary = {
        "region": args.region,
        "app_id": app_id,
        "account_uin": args.account_uin,
        "detected_uin": detected_uin,
        "owner_uin": owner_uin,
        "cos_bucket": args.cos_bucket,
        "cos_prefix": args.cos_prefix,
        "cos_bucket_action": bucket_action,
        "tcr_personal_server": args.tcr_personal_server,
        "tcr_namespace": args.tcr_namespace,
        "tcr_namespace_action": namespace_action,
        "tcr_repository": args.tcr_repository,
        "tcr_repository_action": repository_action,
        "tcr_user_action": user_action,
        "docker_image_uri": docker_image_uri,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
