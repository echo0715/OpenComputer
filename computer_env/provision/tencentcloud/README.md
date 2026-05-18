# Tencent Cloud China Remote Docker 

[中文文档](./README_zh.md)

This directory contains the Tencent Cloud China scaffold for the `remote_docker` backend. 

The runtime backend is still `remote_docker`. Tencent Cloud is only the provisioning provider:

- local controller
- Tencent Cloud CVM workers
- one `worker-agent` process per worker
- multiple desktop Docker sessions per worker
- TCR Personal for the desktop image
- COS for worker bootstrap bundle distribution

## Configuration Scope

This document is the source of truth for the Tencent Cloud China `remote_docker` provisioning surface:

- `TENCENTCLOUD_*` variables control provisioning and worker launch.
- `REMOTE_DOCKER_*` variables control controller-side runtime behavior after workers exist.
- `GUI_SYNTH_WORKER_*` variables are worker-agent internals written by `launch_workers.py` into CVM user-data. Most users should not set them manually in the local `.env`.

The repository root [`README.md`](../../../README.md) keeps only a short configuration overview and links here for the full Tencent Cloud path.

If you have not yet set up the Tencent Cloud account, API key, TCR Personal password, VPC/subnet, or CVM image ID required by this flow, read [`TENCENTCLOUD_SETUP.md`](./TENCENTCLOUD_SETUP.md) first.

## 1. Fill in `.env`

At minimum:

```bash
TENCENTCLOUD_SECRET_ID=xxxxxx
TENCENTCLOUD_SECRET_KEY=xxxxxxx

TENCENTCLOUD_REGION=ap-guangzhou
TENCENTCLOUD_NAME_PREFIX=opencomputer-dev
TENCENTCLOUD_CONTROLLER_CIDR=xxx.xxx.xxx.xxx/32

TENCENTCLOUD_CVM_ZONE=ap-guangzhou-6
TENCENTCLOUD_CVM_IMAGE_ID=img-xxxxxxxx
TENCENTCLOUD_VPC_ID=vpc-xxxxxxxx
TENCENTCLOUD_SUBNET_ID=subnet-xxxxxxxx

TENCENTCLOUD_ACCOUNT_UIN=<your-account-UIN>
TENCENTCLOUD_TCR_PERSONAL_PASSWORD=replace-with-strong-password

REMOTE_DOCKER_POOL_FILE=~/.config/gui-synth-env/tencentcloud/worker_pool.json
```

Set `REMOTE_DOCKER_POOL_FILE` explicitly for the Tencent Cloud path. `launch_workers.py` defaults to a Tencent-specific pool file, but the shared `remote_docker` runtime otherwise falls back to the AWS pool-file path.

Recommended companion values:

```bash
TENCENTCLOUD_CVM_INSTANCE_TYPE=S5.LARGE8
TENCENTCLOUD_WORKER_COUNT=1
TENCENTCLOUD_CONTAINERS_PER_WORKER=6
TENCENTCLOUD_CVM_BANDWIDTH_OUT_Mbps=20
TENCENTCLOUD_CVM_SYSTEM_DISK_SIZE_GB=64

TENCENTCLOUD_TCR_PERSONAL_SERVER=ccr.ccs.tencentyun.com
# Optional; if unset, setup_prereqs.py derives a low-collision namespace:
# TENCENTCLOUD_TCR_PERSONAL_NAMESPACE=oc-123456-opencomputer-dev
TENCENTCLOUD_TCR_PERSONAL_REPOSITORY=desktop
```

Notes:

- `TENCENTCLOUD_CVM_IMAGE_ID` is required. This flow does not auto-resolve a public Ubuntu image ID for you.
- `TENCENTCLOUD_COS_BUCKET` is optional. If unset, `setup_prereqs.py` derives `<name-prefix>-assets-<app_id>`.
- COS bucket names must include the account AppId suffix.
- `TENCENTCLOUD_TCR_PERSONAL_PASSWORD` is a long-lived Personal registry password. The setup script aligns TCR Personal to this value each time it runs.

### How to choose `TENCENTCLOUD_CONTROLLER_CIDR`

In the common case, this is your current public IP with a `/32` suffix.

```bash
curl https://checkip.amazonaws.com
curl https://ifconfig.me
```

If the command prints `203.0.113.10`, set:

```bash
TENCENTCLOUD_CONTROLLER_CIDR=203.0.113.10/32
```

Keep this CIDR narrow. Both the worker-agent API and the noVNC range are exposed only to this source range.

## 2. Verify local Tencent Cloud auth

The provisioning scripts use the official Tencent Cloud Python SDK credential chain. Supported sources include:

- `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`
- `~/.tencentcloud/credentials`

You can sanity-check the same credentials by running:

```bash
python computer_env/provision/tencentcloud/setup_prereqs.py
```

If the SDK cannot resolve credentials, the script exits with a clear error.

## 3. Create base Tencent Cloud prerequisites

This step creates or verifies:

- the COS bucket
- the TCR Personal user password state
- the TCR Personal namespace
- the TCR Personal repository

```bash
python computer_env/provision/tencentcloud/setup_prereqs.py
```

Expected output includes:

- `app_id`
- `cos_bucket`
- `tcr_namespace`
- `tcr_repository`
- `docker_image_uri`

After this step, copy the exact `docker_image_uri` value into `.env` as:

```bash
DOCKER_ENV_IMAGE=<docker_image_uri from setup_prereqs.py output>
```

## 4. Build and push the desktop image

Build:

```bash
bash computer_env/provision/docker/build_image.sh opencomputer-desktop:latest
```

Login to TCR Personal:

```bash
docker login ccr.ccs.tencentyun.com \
  -u <TENCENTCLOUD_ACCOUNT_UIN> \
  -p <TENCENTCLOUD_TCR_PERSONAL_PASSWORD>
```

Tag and push:

```bash
docker tag opencomputer-desktop:latest <docker_image_uri>
docker push <docker_image_uri>
```

For the China site Personal flow, the image URI is normally:

```text
ccr.ccs.tencentyun.com/<namespace>/<repo>:latest
```

## 5. Launch workers

This step:

- uploads the worker-agent bundle to COS
- creates or reuses a worker security group
- launches CVM workers with public IPs
- injects a COS pre-signed bundle URL and TCR Personal credentials via user-data
- waits for worker `/healthz`
- writes the local worker pool file consumed by `remote_docker`

```bash
python computer_env/provision/tencentcloud/launch_workers.py
```

The script writes a pool file at `REMOTE_DOCKER_POOL_FILE`.

The worker security group exposes:

- the worker-agent HTTP port to `TENCENTCLOUD_CONTROLLER_CIDR`
- the noVNC port range to `TENCENTCLOUD_CONTROLLER_CIDR`

That means noVNC URLs returned by `remote_docker` are worker public URLs and should be treated as sensitive.

## 6. Inspect active streams

```bash
python computer_env/provision/remote_docker/stream_dashboard.py
```

Then open:

```text
http://127.0.0.1:8787
```

## 7. Run evaluation with the remote backend

```bash
python evaluation/run_eval.py \
  --env-backend remote_docker \
  --tasks-per-app 1 \
  --parallel 6
```

This assumes `DOCKER_ENV_IMAGE` in `.env` has already been set to the `docker_image_uri` from step 3. If you prefer not to store it in `.env`, pass `--docker-image <docker_image_uri>` explicitly.

Operational notes:

- `run_eval.py` still uses `--env-backend remote_docker`; there is no Tencent-specific backend enum.
- `--docker-ready-timeout` applies to `remote_docker` and is enforced by the worker while the desktop stack is coming up.
- `--parallel N` is clamped to the fleet's reported total capacity before task execution starts.
- `--keep-alive` cannot be combined with `--parallel > 1`.
- if the fleet is full, session acquisition is bounded by `REMOTE_DOCKER_SESSION_ACQUIRE_TIMEOUT`.

Common remote runtime environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `REMOTE_DOCKER_POOL_FILE` | set explicitly | Use `~/.config/gui-synth-env/tencentcloud/worker_pool.json` so launch and runtime read the same pool file. |
| `REMOTE_DOCKER_WORKER_URLS` | — | Comma-separated worker URLs; bypasses the pool file when set |
| `REMOTE_DOCKER_API_TOKEN` | — | Bearer token used by the worker-agent API |
| `REMOTE_DOCKER_REQUEST_TIMEOUT` | `30` | Default per-request HTTP timeout |
| `REMOTE_DOCKER_SESSION_CREATE_TIMEOUT` | `240` | Max time to wait for a submitted session to reach `ready` |
| `REMOTE_DOCKER_SESSION_ACQUIRE_TIMEOUT` | `180` | Max time to wait for free fleet capacity |

Advanced remote runtime environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `REMOTE_DOCKER_COMMAND_TIMEOUT_GRACE_SECONDS` | `30` | Extra HTTP slack added on top of per-command execution timeouts |
| `REMOTE_DOCKER_WORKER_COOLDOWN_SECONDS` | `15` | Temporary backoff for unhealthy workers before reuse |
| `REMOTE_DOCKER_CAPACITY_POLL_INTERVAL` | `2.0` | Capacity retry polling interval on the controller |
| `REMOTE_DOCKER_SESSION_STATUS_POLL_INTERVAL` | `1.0` | Session-status polling interval on the controller |

## 8. Terminate workers

```bash
python computer_env/provision/tencentcloud/terminate_workers.py
```

Termination behavior:

- by default, the script terminates the instances listed in `REMOTE_DOCKER_POOL_FILE`
- if that pool file is missing or empty, it falls back to scanning CVM for `ManagedBy=OpenComputer` and `NamePrefix=$TENCENTCLOUD_NAME_PREFIX`
- if the script reports extra managed instances outside the pool file, re-run with:

```bash
python computer_env/provision/tencentcloud/terminate_workers.py --all-by-prefix
```
