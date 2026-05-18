# AWS Remote Docker

This directory contains the AWS scaffold for the `remote_docker` backend.

The model is:

- local controller
- AWS EC2 workers
- one `worker-agent` process per worker
- multiple desktop Docker sessions per worker

Current controller/worker behavior:

- the controller submits session creation asynchronously, then polls worker session state until it becomes `ready`
- the worker keeps session state (`creating`, `ready`, `failed`, `deleting`, `deleted`) in-memory
- the worker janitor reaps expired sessions and eventually purges failed/deleted session records
- `run_eval.py` clamps `--parallel` to the fleet's reported total capacity before task execution starts

## Configuration Scope

This document is the source of truth for the `remote_docker` configuration surface:

- `AWS_*` variables control provisioning and worker launch.
- `REMOTE_DOCKER_*` variables control controller-side runtime behavior after workers exist.
- `GUI_SYNTH_WORKER_*` variables are worker-agent internals written by `launch_workers.py` into EC2 user data. Most users should not set them manually in the local `.env`.

The repository root [`README.md`](../../../README.md) intentionally keeps only a short configuration overview and links here for the full remote/AWS reference.

## 0. Setup AWS

If you have not yet installed AWS CLI v2, configured AWS IAM Identity Center access, or been assigned to an AWS account and role, read [`AWS_SSO_SETUP.md`](./AWS_SSO_SETUP.md) first.

## 1. Fill in `.env`

Before you run `setup_prereqs.py`, fill in the repository root `.env`.

At minimum:

```bash
AWS_PROFILE=opencomputer-dev          # if using AWS SSO
AWS_REGION=us-east-1                  # required
AWS_NAME_PREFIX=opencomputer-dev      # required
AWS_CONTROLLER_CIDR=203.0.113.10/32   # required
```

The Python provisioning scripts load the repository root `.env`. The `aws` CLI does not, so when you verify auth below, pass `--profile <AWS_PROFILE>` explicitly or export `AWS_PROFILE` in your shell first.

### How to choose `AWS_CONTROLLER_CIDR`

In the common case, this is just your current public IP with a `/32` suffix.

You can discover that IP with either of these commands:

```bash
curl https://checkip.amazonaws.com
curl https://ifconfig.me
```

If the command prints `203.0.113.10`, set:

```bash
AWS_CONTROLLER_CIDR=203.0.113.10/32
```

Use a different CIDR only if you intentionally want to allow a broader but still
controlled source range, such as a corporate VPN egress block or office NAT
range.

Important caveats:

- If you disconnect or reconnect to a VPN, your public egress IP may change.
- If you are on residential internet, your public IP may change over time.
- If the controller IP changes after workers are launched, the security-group
  ingress may stop matching and `remote_docker` access will fail until you
  relaunch workers or otherwise update the security group.

Optional overrides that must also be decided before `setup_prereqs.py` if you
want non-derived names:

```bash
# AWS_ECR_REPOSITORY=<custom-repository-name>
# AWS_INSTANCE_PROFILE_NAME=<custom-instance-profile-name>
# AWS_BOOTSTRAP_PREFIX=<custom-bootstrap-prefix>
```

You can copy the rest of the AWS section from [`.env.example`](../../../.env.example).
The tables below also include a few less-common overrides that are intentionally omitted from `.env.example` to keep the sample file short.

Common provisioning variables:

| Variable | Default | Meaning |
|---|---|---|
| `AWS_PROFILE` | credential-chain default | AWS CLI/boto3 profile, commonly used with AWS SSO. |
| `AWS_REGION` | — | Required deployment region. |
| `AWS_NAME_PREFIX` | — | Required prefix used to derive AWS resource names. |
| `AWS_CONTROLLER_CIDR` | — | Required narrow ingress CIDR for worker-agent and noVNC access. |
| `DOCKER_ENV_IMAGE` | — | Required ECR image URI after `setup_prereqs.py` prints it. |
| `AWS_WORKER_INSTANCE_TYPE` | `m6i.2xlarge` | EC2 instance type for each worker. |
| `AWS_WORKER_COUNT` | `1` | Number of workers to launch. |
| `AWS_CONTAINERS_PER_WORKER` | `2` | Max desktop sessions per worker. Set it higher explicitly if you want denser workers. |

Advanced provisioning overrides:

| Variable | Default | Meaning |
|---|---|---|
| `AWS_S3_BUCKET` | derived | Explicit asset bucket name instead of `${AWS_NAME_PREFIX}-assets-<account_id>`. |
| `AWS_VPC_ID` | auto-resolved | Explicit VPC to use for workers. |
| `AWS_SUBNET_ID` | auto-resolved | Explicit subnet to use for workers. |
| `AWS_ECR_REPOSITORY` | `${AWS_NAME_PREFIX}-desktop` | Override the ECR repository name used for the desktop image. |
| `AWS_INSTANCE_PROFILE_NAME` | `${AWS_NAME_PREFIX}-worker` | Override the worker instance profile name. |
| `AWS_BOOTSTRAP_PREFIX` | `bootstrap/${AWS_NAME_PREFIX}` | Override the S3 prefix used for the worker bootstrap bundle. |
| `AWS_DEBUG_ACCESS` | `SSM` | Worker debug access mode; `SSH` also requires `--key-name` at launch time. |
| `AWS_WORKER_ROOT_VOLUME_SIZE_GB` | `64` | Root EBS volume size for worker instances. |
| `AWS_WORKER_UBUNTU_RELEASE` | `24.04` | Ubuntu release used when resolving the worker AMI. |
| `AWS_WORKER_AGENT_PORT` | `8088` | Port exposed by the worker-agent service. Rarely changed. |
| `AWS_NOVNC_PORT_START` | `61000` | First noVNC port reserved on each worker. Rarely changed. |
| `AWS_NOVNC_PORT_END` | `61199` | Last noVNC port reserved on each worker. Rarely changed. |

## 2. Verify local AWS auth

If you use AWS SSO, verify the intended profile explicitly:

```bash
aws sts get-caller-identity --profile opencomputer-dev
```

If you use another credential chain and have already exported it in your shell, plain `aws sts get-caller-identity` is also fine.

If the command fails with `InvalidClientTokenId` and you are using AWS SSO, re-authenticate and retry:

```bash
aws sso login --profile opencomputer-dev
aws sts get-caller-identity --profile opencomputer-dev
```

## 3. Create base AWS prerequisites

This step creates or verifies:

- the S3 bucket
- the ECR repository
- the EC2 worker IAM role + instance profile

```bash
python computer_env/provision/aws/setup_prereqs.py
```

Expected output includes:

- `account_id`
- `ecr_image_uri`
- `ecr_repository`
- `instance_profile_name`
- `s3_bucket`

After this step, copy the exact `ecr_image_uri` value into `.env` as:

```bash
DOCKER_ENV_IMAGE=<ecr_image_uri from setup_prereqs.py output>
```

Every later step should use that exact image URI. Do not hand-construct a
repository name.

## 4. Build and push the desktop image

Build:

```bash
# Any local tag is fine; this one is just an example.
bash computer_env/provision/docker/build_image.sh opencomputer-desktop:latest
```

Login to ECR:

```bash
# Replace <account_id> with the `account_id` from step 3 output.
aws ecr get-login-password --region <AWS_REGION> \
  | docker login --username AWS --password-stdin <account_id>.dkr.ecr.<AWS_REGION>.amazonaws.com
```

Tag and push:

```bash
# Replace <ecr_image_uri> with the exact `ecr_image_uri` from step 3 output.
docker tag opencomputer-desktop:latest <ecr_image_uri>

docker push <ecr_image_uri>
```

## 5. Launch workers

This step:

- uploads the worker-agent bundle to S3
- creates or reuses a worker security group
- launches EC2 workers
- provisions a larger root EBS volume so the desktop image can be pulled successfully
- waits for `worker-agent` health
- writes the local worker pool file consumed by `remote_docker`
- defaults to Canonical Ubuntu `24.04` for worker boot unless `--ubuntu-release` is specified
- automatically terminates just-created instances if launch fails later, unless `--keep-failed-instances` is set

If you want worker-agent API auth, set `REMOTE_DOCKER_API_TOKEN` in `.env`
before launching. `run_eval.py` will read the same value later.

```bash
python computer_env/provision/aws/launch_workers.py
```

The script writes a pool file at `REMOTE_DOCKER_POOL_FILE` (default: `~/.config/gui-synth-env/aws/worker_pool.json`)

The worker security group exposes:

- the worker-agent HTTP port to `AWS_CONTROLLER_CIDR`
- the noVNC port range to `AWS_CONTROLLER_CIDR`

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
# Add these to `.env` first if you want non-default remote timing:
# REMOTE_DOCKER_SESSION_CREATE_TIMEOUT=240
# REMOTE_DOCKER_SESSION_ACQUIRE_TIMEOUT=180

python evaluation/run_eval.py \
  --env-backend remote_docker \
  --tasks-per-app 1 \
  --parallel 2
```

This assumes `DOCKER_ENV_IMAGE` in `.env` has already been set to the
`ecr_image_uri` from step 3. If you prefer not to store it in `.env`, pass
`--docker-image <ecr_image_uri>` explicitly.

With one worker and the code default `AWS_CONTAINERS_PER_WORKER=2`, start with `--parallel 2`. Raise it only after you increase worker count or per-worker capacity.

Operational notes for the eval runner:

- `--docker-ready-timeout` now applies to `remote_docker` and is enforced by the worker while the desktop stack is coming up.
- `--parallel N` is clamped to the fleet's reported total capacity before task execution starts.
- `--keep-alive` cannot be combined with `--parallel > 1`.
- if the fleet is full, session acquisition is bounded by `REMOTE_DOCKER_SESSION_ACQUIRE_TIMEOUT`; it no longer waits forever.

Common remote runtime environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `REMOTE_DOCKER_POOL_FILE` | `~/.config/gui-synth-env/aws/worker_pool.json` | Local worker pool file written by `launch_workers.py` |
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

### Session lifecycle

Current worker-agent session flow:

1. `POST /sessions`
   - returns `202 Accepted`
   - returns `session_id` and initial `status=creating`
2. `GET /sessions/{session_id}`
   - returns the current session state
   - returns `stream_url` once the state becomes `ready`
3. `DELETE /sessions/{session_id}`
   - cancels or deletes the session
   - works for both `creating` and `ready` sessions

This is intentional: the controller should never rely on the initial `POST /sessions` response alone to infer readiness.

### Capacity and parallelism

Parallelism is one session per task.

- total effective capacity is `sum(worker.max_sessions)` across reachable workers
- `run_eval.py` clamps requested parallelism to that total before starting
- transiently unhealthy workers are put on a short cooldown before reuse
- failed capacity acquisition now fails explicitly after `REMOTE_DOCKER_SESSION_ACQUIRE_TIMEOUT`

Example after setting `AWS_CONTAINERS_PER_WORKER=6`:

- 1 worker with `AWS_CONTAINERS_PER_WORKER=6` means effective `parallel <= 6`
- 2 workers with `AWS_CONTAINERS_PER_WORKER=6` means effective `parallel <= 12`

### Cleanup and recovery

There are three cleanup layers:

1. normal task teardown
   - each task calls `sandbox.kill()`
2. controller interrupt/exit cleanup
   - `run_eval.py` cleans active sessions and then tries metadata-based cleanup by `run_id`
3. worker-side janitor
   - expires stale `creating` / `ready` / `deleting` sessions by TTL
   - later purges retained `failed` / `deleted` records

If the controller process crashes after submitting a session create request, the worker janitor still provides a final cleanup backstop.

### Troubleshooting

- `No usable remote workers were found`: check worker health with `python computer_env/provision/remote_docker/stream_dashboard.py`, verify security-group ingress still matches `AWS_CONTROLLER_CIDR`, and verify `REMOTE_DOCKER_API_TOKEN` still matches the launch-time token.
- `Remote docker fleet reported zero session capacity`: confirm the worker service is running and the configured max sessions are nonzero.
- session stuck in `creating`: raise `--docker-ready-timeout` or inspect the worker logs; the desktop image may still be booting XFCE/x11vnc/websockify.
- noVNC URL loads from an unexpected source: remember `remote_docker` returns the worker public host, not localhost; keep the port range restricted to the controller CIDR.

## 8. Terminate workers

```bash
python computer_env/provision/aws/terminate_workers.py
```

Termination behavior:

- by default, the script terminates the instances listed in `REMOTE_DOCKER_POOL_FILE`
- if that pool file is missing or empty, it falls back to scanning EC2 for `ManagedBy=OpenComputer` and `NamePrefix=$AWS_NAME_PREFIX`
- if the script reports extra managed instances outside the pool file, re-run with:

```bash
python computer_env/provision/aws/terminate_workers.py --all-by-prefix
```

- the script now waits for the instances to actually reach `terminated` before returning
- if `launch_workers.py` failed before writing the pool file, `--all-by-prefix` is the safest manual cleanup command
