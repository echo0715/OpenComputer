from __future__ import annotations

import json
from typing import Any

try:
    from qcloud_cos import CosConfig, CosS3Client
    from tencentcloud.cam.v20190116 import cam_client, models as cam_models
    from tencentcloud.common import credential
    from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.cvm.v20170312 import cvm_client, models as cvm_models
    from tencentcloud.tcr.v20190924 import tcr_client, models as tcr_models
    from tencentcloud.vpc.v20170312 import vpc_client, models as vpc_models
except ModuleNotFoundError as exc:  # pragma: no cover - dependency gate
    CosConfig = None
    CosS3Client = None
    cam_client = None
    cam_models = None
    credential = None
    TencentCloudSDKException = Exception
    ClientProfile = None
    HttpProfile = None
    cvm_client = None
    cvm_models = None
    tcr_client = None
    tcr_models = None
    vpc_client = None
    vpc_models = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


def require_tencentcloud_dependencies() -> None:
    if IMPORT_ERROR is not None:
        raise SystemExit(
            "Tencent Cloud provisioning scripts require `tencentcloud-sdk-python` and "
            "`cos-python-sdk-v5`. Install them with "
            "`pip install tencentcloud-sdk-python cos-python-sdk-v5`."
        ) from IMPORT_ERROR


def get_credentials() -> Any:
    require_tencentcloud_dependencies()
    try:
        cred = credential.DefaultCredentialProvider().get_credential()
    except Exception as exc:  # pragma: no cover - depends on local auth state
        raise SystemExit(
            "Tencent Cloud credentials were not found. Set "
            "`TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`, or configure "
            "`~/.tencentcloud/credentials`."
        ) from exc
    if not getattr(cred, "secret_id", None) or not getattr(cred, "secret_key", None):
        raise SystemExit(
            "Tencent Cloud credentials were resolved, but SecretId/SecretKey are missing."
        )
    return cred


def build_client_profile(timeout_seconds: int = 60) -> Any:
    require_tencentcloud_dependencies()
    return ClientProfile(httpProfile=HttpProfile(reqTimeout=timeout_seconds))


def build_request(model_class: Any, payload: dict[str, Any] | None = None) -> Any:
    request = model_class()
    if payload:
        request.from_json_string(json.dumps(payload))
    return request


def response_to_dict(response: Any) -> dict[str, Any]:
    return json.loads(response.to_json_string())


def build_cam_client(cred: Any, region: str) -> Any:
    require_tencentcloud_dependencies()
    return cam_client.CamClient(cred, region, build_client_profile())


def build_cvm_client(cred: Any, region: str) -> Any:
    require_tencentcloud_dependencies()
    return cvm_client.CvmClient(cred, region, build_client_profile())


def build_vpc_client(cred: Any, region: str) -> Any:
    require_tencentcloud_dependencies()
    return vpc_client.VpcClient(cred, region, build_client_profile())


def build_tcr_client(cred: Any, region: str) -> Any:
    require_tencentcloud_dependencies()
    return tcr_client.TcrClient(cred, region, build_client_profile())


def build_cos_client(cred: Any, region: str) -> Any:
    require_tencentcloud_dependencies()
    config = CosConfig(
        Region=region,
        SecretId=cred.secret_id,
        SecretKey=cred.secret_key,
        Token=cred.token,
        Scheme="https",
    )
    return CosS3Client(config)


def exception_text(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None)
    if code and message:
        return f"{code}: {message}"
    if code:
        return str(code)
    if message:
        return str(message)
    return str(exc)


def error_matches(exc: Exception, *needles: str) -> bool:
    haystack = exception_text(exc).lower()
    return any(needle.lower() in haystack for needle in needles)


def is_already_exists_error(exc: Exception) -> bool:
    return error_matches(exc, "already", "exist", "duplicate", "conflict")


def is_not_found_error(exc: Exception) -> bool:
    return error_matches(exc, "not found", "not exist", "no such", "invalid", "resource not found")

