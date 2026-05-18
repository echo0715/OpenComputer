# 在执行 `README.md` 之前的腾讯云准备

[English](./TENCENTCLOUD_SETUP.md)

本文档说明在执行 [`README.md`](./README.md) 或 [`README_zh.md`](./README_zh.md) 的腾讯云中国站 `remote_docker` 流程之前，需要先手工准备哪些内容。

## 先决条件

在你完整跑通腾讯云流程之前，需要先具备：

- 一个完成实名认证的腾讯云中国站账号
- 一条本地 Python SDK 可用的腾讯云认证路径
- 已开通 COS
- 已开通 TCR，并初始化 Personal 仓库密码
- 目标地域内的一个 VPC 和一个子网
- 该子网所属的可用区
- 一个可用的 Ubuntu x86_64 CVM 公共镜像 ID
- 足够的 CVM 配额和余额
- 运行本地 controller 的机器当前公网 IP

## OpenComputer 会自动创建什么

OpenComputer 已经会创建或复用这些资源：

- 如果 `TENCENTCLOUD_COS_BUCKET` 未设置，则自动创建 COS bucket
- 如果 `TENCENTCLOUD_TCR_PERSONAL_NAMESPACE` 未设置，则自动创建 TCR Personal namespace
- TCR Personal repository
- worker 安全组
- worker CVM 实例
- 本地 worker pool file

所以你真正需要手工准备的，主要是账号、认证、TCR 密码、VPC/子网、镜像 ID 和 controller CIDR。

## 控制台准备清单

### 1. 记录主账号 UIN 和 APPID

在腾讯云账号信息页记录：

- 主账号 `UIN`
- 账号 `APPID`

它们的用途是：

- `TENCENTCLOUD_ACCOUNT_UIN` 通常填写主账号 UIN
- `APPID` 只有在你想手动设置 `TENCENTCLOUD_COS_BUCKET` 时才直接用到

### 2. 准备 API 凭证

你需要一组本地腾讯云 Python SDK 可用的 API Key。

常见做法：

- 最快的路径：主账号 API Key
- 更稳妥的路径：管理员子用户 API Key

第一次跑通 OpenComputer 时，管理员级权限最不容易出歧义。如果你使用子用户 Key，`.env` 里的 `TENCENTCLOUD_ACCOUNT_UIN` 通常仍应填写主账号 UIN，因为 TCR Personal 登录使用的是账号 UIN。

### 3. 开通 COS

除非你明确需要自定义 bucket 名，否则不需要手工创建 bucket。

如果你手动设置 `TENCENTCLOUD_COS_BUCKET`，它必须以 `-<APPID>` 结尾。

### 4. 开通 TCR Personal

初始化或重置 Personal 仓库密码，并把它写入：

```bash
TENCENTCLOUD_TCR_PERSONAL_PASSWORD=...
```

注意：

- 这个密码必须是 8 到 16 个字符
- `setup_prereqs.py` 会强制校验这个长度
- 每次运行 `setup_prereqs.py` 时，都会把 TCR Personal 侧密码对齐到 `.env` 中的值

### 5. 准备网络

创建或复用：

- 一个 VPC
- 该 VPC 下的一个子网

记录：

- `TENCENTCLOUD_VPC_ID`
- `TENCENTCLOUD_SUBNET_ID`
- 子网所属可用区，对应 `TENCENTCLOUD_CVM_ZONE`

脚本不会为你创建 VPC 或子网。

### 6. 选择镜像并确认容量

请选择 Ubuntu x86_64 公共镜像，并把它的 `img-...` 值记录为 `TENCENTCLOUD_CVM_IMAGE_ID`。

为什么建议 Ubuntu x86_64：

- worker bootstrap 会通过 `apt-get` 安装依赖
- 第一次配置时，Ubuntu 风险最小
- ARM 或非 Ubuntu 镜像容易引入额外问题

启动前还要确认：

- 目标可用区里确实提供所选实例类型
- 账号有足够的配额和余额

## 本地机器准备清单

### 1. 安装腾讯云 SDK 依赖

```bash
pip install tencentcloud-sdk-python cos-python-sdk-v5
```

### 2. 决定本地如何提供认证

当前 provisioning 代码支持：

- `TENCENTCLOUD_SECRET_ID` 和 `TENCENTCLOUD_SECRET_KEY`
- `~/.tencentcloud/credentials`

第一次配置时，最简单的方式通常是直接写到仓库根目录 `.env`。

### 3. 确定 controller 的公网 IP

```bash
curl https://checkip.amazonaws.com
```

如果输出是 `203.0.113.10`，就写成：

```bash
TENCENTCLOUD_CONTROLLER_CIDR=203.0.113.10/32
```

CIDR 尽量收窄。

### 4. 填写仓库根目录 `.env`

至少需要：

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

推荐同时设置：

```bash
TENCENTCLOUD_CVM_INSTANCE_TYPE=S5.LARGE8
TENCENTCLOUD_WORKER_COUNT=1
TENCENTCLOUD_CONTAINERS_PER_WORKER=6
TENCENTCLOUD_CVM_BANDWIDTH_OUT_Mbps=20
TENCENTCLOUD_CVM_SYSTEM_DISK_SIZE_GB=64

TENCENTCLOUD_TCR_PERSONAL_SERVER=ccr.ccs.tencentyun.com
TENCENTCLOUD_TCR_PERSONAL_REPOSITORY=desktop
```

除非你明确需要自定义名字，否则这些变量可以留空：

- `TENCENTCLOUD_COS_BUCKET`
- `TENCENTCLOUD_COS_PREFIX`
- `TENCENTCLOUD_TCR_PERSONAL_NAMESPACE`

这里 `REMOTE_DOCKER_POOL_FILE` 很重要，因为：

- `launch_workers.py` 默认会写腾讯云自己的 pool file
- 共享的 `remote_docker` runtime 默认仍会回退到 AWS 的 pool-file 路径
- 显式设置后，provisioning、`run_eval.py` 和 `interactive_sandbox.py` 才会读同一份 pool file

### 5. 验证基础前置资源

运行：

```bash
python computer_env/provision/tencentcloud/setup_prereqs.py
```

如果成功，说明本地认证路径可用、COS/TCR 前置资源也已就绪。脚本会输出：

- `app_id`
- `cos_bucket`
- `tcr_namespace`
- `tcr_repository`
- `docker_image_uri`

然后把下面这一行写进仓库根目录 `.env`：

```bash
DOCKER_ENV_IMAGE=<docker_image_uri from setup_prereqs.py output>
```

之后再继续执行主腾讯云 `README`。

## 参数清单

| 变量 | 用于 | 说明 |
|---|---|---|
| `TENCENTCLOUD_SECRET_ID` | 所有腾讯云步骤 | 主账号或管理员子用户 Key |
| `TENCENTCLOUD_SECRET_KEY` | 所有腾讯云步骤 | 创建时就要保存 |
| `TENCENTCLOUD_REGION` | 所有腾讯云步骤 | 首次配置建议 `ap-guangzhou` |
| `TENCENTCLOUD_NAME_PREFIX` | 所有腾讯云步骤 | 用于派生资源名称 |
| `TENCENTCLOUD_ACCOUNT_UIN` | `setup_prereqs.py`、`launch_workers.py`、镜像仓库登录 | 通常填写主账号 UIN |
| `TENCENTCLOUD_TCR_PERSONAL_PASSWORD` | `setup_prereqs.py`、`launch_workers.py`、镜像仓库登录 | 必须是 8 到 16 个字符 |
| `TENCENTCLOUD_CONTROLLER_CIDR` | `launch_workers.py` | 一般就是当前公网 IP 加 `/32` |
| `TENCENTCLOUD_CVM_ZONE` | `launch_workers.py` | 必须和所选子网一致 |
| `TENCENTCLOUD_CVM_IMAGE_ID` | `launch_workers.py` | 使用 Ubuntu x86_64 |
| `TENCENTCLOUD_VPC_ID` | `launch_workers.py` | 现有 VPC |
| `TENCENTCLOUD_SUBNET_ID` | `launch_workers.py` | 现有子网 |
| `REMOTE_DOCKER_POOL_FILE` | 腾讯云端到端流程 | 建议设为 `~/.config/gui-synth-env/tencentcloud/worker_pool.json`，让 runtime 和启动脚本使用同一份 pool file |
| `TENCENTCLOUD_CVM_INSTANCE_TYPE` | 推荐 | 默认是 `S5.LARGE8` |
| `TENCENTCLOUD_WORKER_COUNT` | 推荐 | 默认是 `1` |
| `TENCENTCLOUD_CONTAINERS_PER_WORKER` | 推荐 | 默认是 `6` |
| `TENCENTCLOUD_CVM_BANDWIDTH_OUT_Mbps` | 推荐 | 至少要大于等于 `1` |
| `TENCENTCLOUD_CVM_SYSTEM_DISK_SIZE_GB` | 推荐 | 至少要大于等于 `50` |
| `TENCENTCLOUD_TCR_PERSONAL_SERVER` | 推荐 | 默认是 `ccr.ccs.tencentyun.com` |
| `TENCENTCLOUD_TCR_PERSONAL_REPOSITORY` | 推荐 | 默认是 `desktop` |

## 常见失败场景

### `setup_prereqs.py` 找不到腾讯云凭证

常见原因：

- `TENCENTCLOUD_SECRET_ID` 或 `TENCENTCLOUD_SECRET_KEY` 缺失
- 本地环境没有加载到预期的 `.env`
- `~/.tencentcloud/credentials` 缺失或格式错误

### `setup_prereqs.py` 拒绝 TCR 密码

常见原因：

- `TENCENTCLOUD_TCR_PERSONAL_PASSWORD` 少于 8 个字符
- `TENCENTCLOUD_TCR_PERSONAL_PASSWORD` 多于 16 个字符

### `setup_prereqs.py` 拒绝 COS bucket 名称

常见原因：

- 手动设置了 `TENCENTCLOUD_COS_BUCKET`
- 名称没有以 `-<APPID>` 结尾

如果不需要自定义 bucket 名，直接把 `TENCENTCLOUD_COS_BUCKET` 留空即可。

### `launch_workers.py` 一启动就因为缺少必需设置而失败

最常见的是这些值缺失：

- `TENCENTCLOUD_CONTROLLER_CIDR`
- `TENCENTCLOUD_CVM_ZONE`
- `TENCENTCLOUD_CVM_IMAGE_ID`
- `TENCENTCLOUD_VPC_ID`
- `TENCENTCLOUD_SUBNET_ID`

### CVM 已经启动，但 worker health 一直无法就绪

常见原因：

- 选择的镜像不是 Ubuntu，或者不是 x86_64
- 启动 worker 之前，TCR 镜像没有成功 push
- 目标可用区存在临时容量或网络问题

这时请检查：

- `/var/log/cloud-init-output.log`
- `systemctl status gui-synth-worker`
- `journalctl -u gui-synth-worker -n 200 --no-pager`
