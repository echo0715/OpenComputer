# Tencent Cloud Setup Before `README.md`

This guide covers the manual setup that must exist before you follow [`README.md`](./README.md) or [`README_zh.md`](./README_zh.md) for the Tencent Cloud China `remote_docker` workflow.

## What Must Exist First

Before you run the Tencent Cloud flow end to end, you need:

- a Tencent Cloud China account with real-name verification
- a usable Tencent Cloud credential path for the local Python SDK
- COS activated
- TCR activated, with a Personal registry password initialized
- one VPC and one subnet in the target Region
- the subnet's Availability Zone
- one Ubuntu x86_64 public image ID for CVM
- enough CVM quota and balance for the instance type and zone you chose
- the public IP of the machine that will run the local controller

## What OpenComputer Creates For You

OpenComputer already creates or reuses these resources:

- the COS bucket, if `TENCENTCLOUD_COS_BUCKET` is unset
- the TCR Personal namespace, if `TENCENTCLOUD_TCR_PERSONAL_NAMESPACE` is unset
- the TCR Personal repository
- the worker security group
- the worker CVM instances
- the local worker pool file

So the main manual setup is narrower: account, credentials, TCR password, VPC/subnet, image ID, and controller CIDR.

## Console Checklist

### 1. Record the Main Account UIN and APPID

From the Tencent Cloud account page, record:

- the main account `UIN`
- the account `APPID`

Use them as follows:

- `TENCENTCLOUD_ACCOUNT_UIN` should normally be the main account UIN
- `APPID` matters only if you want to set `TENCENTCLOUD_COS_BUCKET` manually

### 2. Prepare API Credentials

You need one API key pair that the local Tencent Cloud Python SDK can use.

Common options:

- fastest path: a main-account API key
- safer path: an administrator sub-user API key

For a first OpenComputer setup, administrator-level permissions are the least ambiguous choice. If you use a sub-user key, `TENCENTCLOUD_ACCOUNT_UIN` should still normally be the main account UIN because TCR Personal login uses the account UIN.

### 3. Activate COS

You do not need to create the bucket manually unless you want a custom name.

If you set `TENCENTCLOUD_COS_BUCKET` yourself, it must end with `-<APPID>`.

### 4. Activate TCR Personal

Initialize or reset the Personal registry password and use that value as:

```bash
TENCENTCLOUD_TCR_PERSONAL_PASSWORD=...
```

Important:

- this password must be 8 to 16 characters
- `setup_prereqs.py` enforces that length
- `setup_prereqs.py` also aligns the TCR Personal-side password to the `.env` value each time it runs

### 5. Prepare the Network

Create or reuse:

- one VPC
- one subnet inside that VPC

Record:

- `TENCENTCLOUD_VPC_ID`
- `TENCENTCLOUD_SUBNET_ID`
- the subnet zone for `TENCENTCLOUD_CVM_ZONE`

The scripts do not create the VPC or subnet for you.

### 6. Choose an Image and Confirm Capacity

Use an Ubuntu x86_64 public image and record its `img-...` value as `TENCENTCLOUD_CVM_IMAGE_ID`.

Why Ubuntu x86_64:

- the worker bootstrap installs packages with `apt-get`
- first setup is simplest on Ubuntu
- ARM and non-Ubuntu images add unnecessary risk

Before launch, also confirm:

- the chosen instance type is available in the selected zone
- the account has enough quota and balance

## Local Machine Checklist

### 1. Install the Tencent Cloud SDK Dependencies

```bash
pip install tencentcloud-sdk-python cos-python-sdk-v5
```

### 2. Decide How the Local Machine Will Supply Credentials

The provisioning code supports:

- `TENCENTCLOUD_SECRET_ID` and `TENCENTCLOUD_SECRET_KEY`
- `~/.tencentcloud/credentials`

For a first setup, placing the values in the repository root `.env` is the simplest path.

### 3. Determine the Controller Public IP

```bash
curl https://checkip.amazonaws.com
```

If it prints `203.0.113.10`, use:

```bash
TENCENTCLOUD_CONTROLLER_CIDR=203.0.113.10/32
```

Keep it as narrow as possible.

### 4. Fill the Repository Root `.env`

At minimum:

```bash
TENCENTCLOUD_SECRET_ID=your-secret-id
TENCENTCLOUD_SECRET_KEY=your-secret-key

TENCENTCLOUD_REGION=ap-guangzhou
TENCENTCLOUD_NAME_PREFIX=opencomputer-dev
TENCENTCLOUD_CONTROLLER_CIDR=203.0.113.10/32

TENCENTCLOUD_CVM_ZONE=ap-guangzhou-6
TENCENTCLOUD_CVM_IMAGE_ID=img-xxxxxxxx
TENCENTCLOUD_VPC_ID=vpc-xxxxxxxx
TENCENTCLOUD_SUBNET_ID=subnet-xxxxxxxx

TENCENTCLOUD_ACCOUNT_UIN=100012345678
TENCENTCLOUD_TCR_PERSONAL_PASSWORD=replace-with-strong-password

REMOTE_DOCKER_POOL_FILE=~/.config/gui-synth-env/tencentcloud/worker_pool.json
```

Recommended companions:

```bash
TENCENTCLOUD_CVM_INSTANCE_TYPE=S5.LARGE8
TENCENTCLOUD_WORKER_COUNT=1
TENCENTCLOUD_CONTAINERS_PER_WORKER=6
TENCENTCLOUD_CVM_BANDWIDTH_OUT_Mbps=20
TENCENTCLOUD_CVM_SYSTEM_DISK_SIZE_GB=64

TENCENTCLOUD_TCR_PERSONAL_SERVER=ccr.ccs.tencentyun.com
TENCENTCLOUD_TCR_PERSONAL_REPOSITORY=desktop
```

Leave these unset unless you want custom names:

- `TENCENTCLOUD_COS_BUCKET`
- `TENCENTCLOUD_COS_PREFIX`
- `TENCENTCLOUD_TCR_PERSONAL_NAMESPACE`

Why `REMOTE_DOCKER_POOL_FILE` matters here:

- `launch_workers.py` defaults to a Tencent-specific pool path
- the shared `remote_docker` runtime otherwise falls back to the AWS pool path
- setting it explicitly keeps provisioning, `run_eval.py`, and `interactive_sandbox.py` aligned

### 5. Verify Base Prerequisites

Run:

```bash
python computer_env/provision/tencentcloud/setup_prereqs.py
```

If it succeeds, the local credential path works and COS/TCR prerequisites are ready. The script prints:

- `app_id`
- `cos_bucket`
- `tcr_namespace`
- `tcr_repository`
- `docker_image_uri`

Then copy:

```bash
DOCKER_ENV_IMAGE=<docker_image_uri from setup_prereqs.py output>
```

into the repository root `.env`, and continue with the main Tencent Cloud `README`.

## Required Parameters Checklist

| Variable | Needed for | Notes |
|---|---|---|
| `TENCENTCLOUD_SECRET_ID` | all Tencent steps | Main account or admin sub-user key |
| `TENCENTCLOUD_SECRET_KEY` | all Tencent steps | Save it at creation time |
| `TENCENTCLOUD_REGION` | all Tencent steps | For a first setup, `ap-guangzhou` is the simplest choice |
| `TENCENTCLOUD_NAME_PREFIX` | all Tencent steps | Used in derived names |
| `TENCENTCLOUD_ACCOUNT_UIN` | `setup_prereqs.py`, `launch_workers.py`, registry login | Normally use the main account UIN |
| `TENCENTCLOUD_TCR_PERSONAL_PASSWORD` | `setup_prereqs.py`, `launch_workers.py`, registry login | Must be 8 to 16 characters |
| `TENCENTCLOUD_CONTROLLER_CIDR` | `launch_workers.py` | Usually your current public IP with `/32` |
| `TENCENTCLOUD_CVM_ZONE` | `launch_workers.py` | Must match the chosen subnet |
| `TENCENTCLOUD_CVM_IMAGE_ID` | `launch_workers.py` | Use Ubuntu x86_64 |
| `TENCENTCLOUD_VPC_ID` | `launch_workers.py` | Existing VPC |
| `TENCENTCLOUD_SUBNET_ID` | `launch_workers.py` | Existing subnet |
| `REMOTE_DOCKER_POOL_FILE` | end-to-end Tencent workflow | Set `~/.config/gui-synth-env/tencentcloud/worker_pool.json` so runtime and launch use the same pool file |
| `TENCENTCLOUD_CVM_INSTANCE_TYPE` | recommended | Default is `S5.LARGE8` |
| `TENCENTCLOUD_WORKER_COUNT` | recommended | Default is `1` |
| `TENCENTCLOUD_CONTAINERS_PER_WORKER` | recommended | Default is `6` |
| `TENCENTCLOUD_CVM_BANDWIDTH_OUT_Mbps` | recommended | Must be at least `1` |
| `TENCENTCLOUD_CVM_SYSTEM_DISK_SIZE_GB` | recommended | Must be at least `50` |
| `TENCENTCLOUD_TCR_PERSONAL_SERVER` | recommended | Default is `ccr.ccs.tencentyun.com` |
| `TENCENTCLOUD_TCR_PERSONAL_REPOSITORY` | recommended | Default is `desktop` |

## Common Failure Cases

### `setup_prereqs.py` cannot find Tencent Cloud credentials

Likely causes:

- `TENCENTCLOUD_SECRET_ID` or `TENCENTCLOUD_SECRET_KEY` is missing
- the local environment did not load the expected `.env`
- `~/.tencentcloud/credentials` is missing or malformed

### `setup_prereqs.py` rejects the TCR password

Likely causes:

- `TENCENTCLOUD_TCR_PERSONAL_PASSWORD` is shorter than 8 characters
- `TENCENTCLOUD_TCR_PERSONAL_PASSWORD` is longer than 16 characters

### `setup_prereqs.py` rejects the COS bucket name

Likely causes:

- `TENCENTCLOUD_COS_BUCKET` was set manually
- the name does not end with `-<APPID>`

If you do not need a custom bucket name, leave `TENCENTCLOUD_COS_BUCKET` unset.

### `launch_workers.py` fails immediately with missing required settings

Most often one of these values is missing:

- `TENCENTCLOUD_CONTROLLER_CIDR`
- `TENCENTCLOUD_CVM_ZONE`
- `TENCENTCLOUD_CVM_IMAGE_ID`
- `TENCENTCLOUD_VPC_ID`
- `TENCENTCLOUD_SUBNET_ID`

### The CVM instance starts, but worker health never becomes ready

Likely causes:

- the selected image is not Ubuntu or not x86_64
- the TCR image was not pushed successfully before worker launch
- the target zone has transient capacity or network issues

If this happens, inspect:

- `/var/log/cloud-init-output.log`
- `systemctl status gui-synth-worker`
- `journalctl -u gui-synth-worker -n 200 --no-pager`
