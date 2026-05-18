# Computer Env

`computer_env/` is the environment layer for GUI task execution.

- `backends/` contains runtime adapters
- `provision/` contains backend-specific setup/build assets

## Configuration Scope

The repository root [`README.md`](../README.md) only lists the top-level variables most users need to run evaluations.
This document is the backend/runtime reference for settings that are specific to `computer_env/`.

Configuration precedence is:

1. CLI flags
2. shell environment / repository root `.env`
3. code defaults

### Runtime Environment Variables

These variables affect sandbox creation across the backend layer:

| Variable | Default | Meaning |
|---|---|---|
| `ENV_BACKEND` | `e2b` | Default backend for `run_eval.py` and `interactive_sandbox.py`. |
| `E2B_ENV_TEMPLATE` | `desktop-all-apps` | E2B template name used when creating new sandboxes. |
| `DOCKER_ENV_IMAGE` | `gui-synth-env-desktop:latest` | Desktop image for the local Docker backend and the base image reference for `remote_docker`. |
| `DOCKER_ENV_PLATFORM` | `linux/amd64` | Docker platform passed to local and remote Docker sessions. |
| `DOCKER_ENV_SHM_SIZE` | `2g` | Shared-memory size for Docker desktop containers. |
| `DOCKER_ENV_MEMORY` | unset | Optional Docker memory limit. |
| `DOCKER_ENV_CPUS` | unset | Optional Docker CPU limit. |
| `DOCKER_ENV_READY_TIMEOUT` | `90` | Time limit for waiting for the desktop stack to become ready. |

### Variables Kept In Subsystem Docs

- E2B account and self-hosting settings such as `E2B_API_KEY` and `E2B_DOMAIN` are referenced below where they are used.
- `remote_docker` runtime variables (`REMOTE_DOCKER_*`) and provider provisioning variables (`AWS_*`, `TENCENTCLOUD_*`) live in the provider docs under [`provision/`](./provision/).
- Tencent Cloud users should set `REMOTE_DOCKER_POOL_FILE` explicitly as shown in the Tencent guide; the shared `remote_docker` runtime otherwise falls back to the AWS pool-file path.
- Worker-agent variables (`GUI_SYNTH_WORKER_*`) are intentionally documented in the provider guides, not here. They are launch-time internals written onto the worker and are not part of the usual local `.env` surface.

## Backend Option 1: E2B

### Setup E2B Backend

Build the all-apps E2B template.

From the repository root:

```bash
python computer_env/provision/e2b/build_all_apps_template.py
```

Common E2B variables:

| Variable | Default | Meaning |
|---|---|---|
| `E2B_API_KEY` | — | Required for E2B API access. |
| `E2B_ENV_TEMPLATE` | `desktop-all-apps` | Template used for new E2B sandboxes. |
| `E2B_DOMAIN` | `e2b.app` | Domain override when self-hosting E2B. |

### E2B Sandbox CLI

Open or resume an E2B sandbox from the local sandbox registry:

```bash
python -m computer_env.backends.e2b.sandbox_cli --list
python -m computer_env.backends.e2b.sandbox_cli <sandbox_id>
```

The sandbox registry defaults to:

```text
~/.config/gui-synth-env/e2b/sandboxes.json
```

Override it with `GUI_SYNTH_E2B_SANDBOXES_FILE` if needed.

To list or clean up active E2B sandboxes in your account:

```bash
python -m computer_env.backends.e2b.cleanup_sandboxes
python -m computer_env.backends.e2b.cleanup_sandboxes --force
```

E2B utility-only variables:

| Variable | Default | Meaning |
|---|---|---|
| `GUI_SYNTH_E2B_SANDBOXES_FILE` | `~/.config/gui-synth-env/e2b/sandboxes.json` | Local sandbox-registry path used by `sandbox_cli.py`. |
| `E2B_API_URL` | derived from `E2B_DOMAIN` | Direct API base URL override used by `cleanup_sandboxes.py`. |
| `E2B_DEBUG` | `false` | When `true`, the cleanup utility targets local E2B dev API endpoints. |


## Backend Option 2: Local Docker

### Setup Local Docker Backend

Build the Docker desktop image.

From the repository root:

```bash
bash computer_env/provision/docker/build_image.sh
```

### Local Docker Cleanup CLI

List or clean up Docker containers managed by `gui-synth-env`:

```bash
python -m computer_env.backends.docker.cleanup_containers
python -m computer_env.backends.docker.cleanup_containers --state running
python -m computer_env.backends.docker.cleanup_containers --metadata run_id=<run_id>
python -m computer_env.backends.docker.cleanup_containers --force
```

## Backend Option 3: Remote Docker

### Setup Remote Docker Backend

`remote_docker` reuses the same desktop image as the local Docker backend, but runs sessions on a worker fleet instead of the local host.

This backend uses:

- the Docker runtime variables listed at the top of this document
- `REMOTE_DOCKER_*` controller/runtime variables shared across providers
- provider provisioning variables from one of the provider guides:
  - [`provision/aws/README.md`](./provision/aws/README.md)
  - [`provision/tencentcloud/README.md`](./provision/tencentcloud/README.md)

Primary entrypoints:

- AWS worker provisioning and ops guide: `computer_env/provision/aws/README.md`
- Tencent Cloud China provisioning and ops guide: `computer_env/provision/tencentcloud/README.md`
- Eval entrypoint: `python evaluation/run_eval.py --env-backend remote_docker ...`
- Interactive sandbox entrypoint: `python evaluation/interactive_sandbox.py --env-backend remote_docker ...`

Minimal flow:

```bash
python computer_env/provision/aws/setup_prereqs.py
bash computer_env/provision/docker/build_image.sh <local-tag>
# tag + push the image to ECR
python computer_env/provision/aws/launch_workers.py

# or Tencent Cloud China
python computer_env/provision/tencentcloud/setup_prereqs.py
bash computer_env/provision/docker/build_image.sh <local-tag>
# tag + push the image to TCR Personal
python computer_env/provision/tencentcloud/launch_workers.py
```

Core runtime behavior:

- Session creation is asynchronous: the controller submits `POST /sessions`, then polls session state until it becomes `ready`.
- `--docker-ready-timeout` is enforced on the worker while waiting for X11, x11vnc, websockify, and the noVNC port to become ready.
- `run_eval.py --env-backend remote_docker --parallel N` clamps `N` to the fleet's reported total capacity before tasks start.
- `--keep-alive` cannot be combined with `--parallel > 1`.
- Active remote sessions are tracked locally for retryable cleanup, and worker-side janitors clean up expired or failed sessions.

### Remote Docker Operational Notes

- The noVNC URL returned by `remote_docker` is a worker public URL, not localhost.
- Keep provider security-group ingress CIDRs narrow. Do not expose the noVNC port range to `0.0.0.0/0`.
- `cleanup_active_remote_sessions()` retries local in-process sessions on interrupt/exit, and `cleanup_remote_sessions_by_metadata()` can recover by `run_id` / `task_id` when the local registry is incomplete.
