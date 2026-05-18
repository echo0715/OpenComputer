# 腾讯云中国站 Remote Docker
[English Version](./README.md)

这个目录包含 `remote_docker` backend 的腾讯云中国站 provisioning 脚手架。

runtime backend 仍然是 `remote_docker`，腾讯云只负责 provisioning：

- 本地 controller
- 腾讯云 CVM worker
- 每台 worker 上 1 个 `worker-agent` 进程
- 每台 worker 上可并发多个桌面 Docker session
- 使用 TCR Personal 托管桌面镜像
- 使用 COS 分发 worker bootstrap bundle

## 配置范围

本文是腾讯云中国站 `remote_docker` provisioning 的配置说明主文档：

- `TENCENTCLOUD_*` 变量控制 provisioning 和 worker 启动
- `REMOTE_DOCKER_*` 变量控制 worker 已经存在后的 controller 侧 runtime 行为
- `GUI_SYNTH_WORKER_*` 变量是 `launch_workers.py` 写入 CVM user-data 的 worker-agent 内部变量。大多数用户不需要在本地 `.env` 里手动设置

仓库根目录的 [`README.md`](../../../README.md) 只保留简要概览，完整腾讯云流程以本文为准。

如果你还没有准备好这个流程需要的腾讯云账号、API Key、TCR Personal 密码、VPC/子网或 CVM 镜像 ID，请先阅读 [`TENCENTCLOUD_SETUP_zh.md`](./TENCENTCLOUD_SETUP_zh.md)。

## 1. 填写 `.env`

至少需要：

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

腾讯云路径需要显式设置 `REMOTE_DOCKER_POOL_FILE`。`launch_workers.py` 默认会写腾讯云自己的 pool file，但共享的 `remote_docker` runtime 默认仍会回退到 AWS 的 pool-file 路径。

推荐同时设置：

```bash
TENCENTCLOUD_CVM_INSTANCE_TYPE=S5.LARGE8
TENCENTCLOUD_WORKER_COUNT=1
TENCENTCLOUD_CONTAINERS_PER_WORKER=6
TENCENTCLOUD_CVM_BANDWIDTH_OUT_Mbps=20
TENCENTCLOUD_CVM_SYSTEM_DISK_SIZE_GB=64

TENCENTCLOUD_TCR_PERSONAL_SERVER=ccr.ccs.tencentyun.com
# 可选；如果不填，setup_prereqs.py 会自动派生一个低冲突命名空间
# TENCENTCLOUD_TCR_PERSONAL_NAMESPACE=oc-123456-opencomputer-dev
TENCENTCLOUD_TCR_PERSONAL_REPOSITORY=desktop
```

说明：

- `TENCENTCLOUD_CVM_IMAGE_ID` 必填。当前实现不会自动帮你解析公共 Ubuntu 镜像 ID
- `TENCENTCLOUD_COS_BUCKET` 可选。不填时，`setup_prereqs.py` 会自动派生 `<name-prefix>-assets-<app_id>`
- COS bucket 名必须包含当前账号的 AppId 后缀
- `TENCENTCLOUD_TCR_PERSONAL_PASSWORD` 是长效的 TCR Personal 密码。每次运行 setup 脚本时，都会把 Personal 侧密码对齐到这个值

### 如何选择 `TENCENTCLOUD_CONTROLLER_CIDR`

常见情况就是你当前公网 IP 加 `/32`。

```bash
curl https://checkip.amazonaws.com
curl https://ifconfig.me
```

如果命令输出 `203.0.113.10`，就设置为：

```bash
TENCENTCLOUD_CONTROLLER_CIDR=203.0.113.10/32
```

这个 CIDR 要尽量收窄，因为 worker-agent API 和 noVNC 端口范围都会只对这个来源开放。

## 2. 验证本地腾讯云认证

当前 provisioning 脚本使用腾讯云官方 Python SDK 的 credential chain。支持的常见来源包括：

- `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`
- `~/.tencentcloud/credentials`

最直接的自检方式就是运行：

```bash
python computer_env/provision/tencentcloud/setup_prereqs.py
```

如果 SDK 不能解析到凭证，脚本会直接报出清晰错误。

## 3. 创建腾讯云基础前置资源

这一步会创建或校验：

- COS bucket
- TCR Personal 用户密码状态
- TCR Personal namespace
- TCR Personal repository

```bash
python computer_env/provision/tencentcloud/setup_prereqs.py
```

预期输出至少包含：

- `app_id`
- `cos_bucket`
- `tcr_namespace`
- `tcr_repository`
- `docker_image_uri`

执行完之后，把输出里的 `docker_image_uri` 原样写进 `.env`：

```bash
DOCKER_ENV_IMAGE=<docker_image_uri from setup_prereqs.py output>
```

## 4. 构建并推送桌面镜像

先构建：

```bash
bash computer_env/provision/docker/build_image.sh opencomputer-desktop:latest
```

登录 TCR Personal：

```bash
docker login ccr.ccs.tencentyun.com \
  -u <TENCENTCLOUD_ACCOUNT_UIN> \
  -p <TENCENTCLOUD_TCR_PERSONAL_PASSWORD>
```

然后打 tag 并推送：

```bash
docker tag opencomputer-desktop:latest <docker_image_uri>
docker push <docker_image_uri>
```

在中国站 Personal 方案下，镜像 URI 一般是：

```text
ccr.ccs.tencentyun.com/<namespace>/<repo>:latest
```

## 5. 启动 workers

这一步会：

- 上传 worker-agent bundle 到 COS
- 创建或复用 worker 安全组
- 启动带公网 IP 的 CVM workers
- 通过 user-data 注入 COS 预签名 bundle 下载地址和 TCR Personal 凭证
- 轮询 worker `/healthz`
- 写出 `remote_docker` 使用的本地 worker pool file

```bash
python computer_env/provision/tencentcloud/launch_workers.py
```

脚本会把 pool file 写到 `REMOTE_DOCKER_POOL_FILE`。

worker 安全组会暴露：

- worker-agent HTTP 端口给 `TENCENTCLOUD_CONTROLLER_CIDR`
- noVNC 端口范围给 `TENCENTCLOUD_CONTROLLER_CIDR`

这意味着 `remote_docker` 返回的 noVNC URL 是 worker 公网地址，应该按敏感入口对待。

## 6. 查看当前活动流

```bash
python computer_env/provision/remote_docker/stream_dashboard.py
```

然后打开：

```text
http://127.0.0.1:8787
```

## 7. 使用远端 backend 跑评测

```bash
python evaluation/run_eval.py \
  --env-backend remote_docker \
  --tasks-per-app 1 \
  --parallel 6
```

这里默认你已经把第 3 步输出的 `docker_image_uri` 写进了 `.env` 的 `DOCKER_ENV_IMAGE`。如果你不想写入 `.env`，也可以显式传 `--docker-image <docker_image_uri>`。

运行说明：

- `run_eval.py` 仍然使用 `--env-backend remote_docker`，不会新增腾讯云专属 backend enum
- `--docker-ready-timeout` 对 `remote_docker` 生效，并由 worker 侧在桌面栈启动期间真正执行
- `--parallel N` 会在任务开始前被 clamp 到当前 fleet 的总容量
- `--keep-alive` 不能和 `--parallel > 1` 一起使用
- 如果 fleet 已满，session 获取会受到 `REMOTE_DOCKER_SESSION_ACQUIRE_TIMEOUT` 限制，不会无限等待

常见远端 runtime 环境变量：

| 变量 | 默认值 | 含义 |
|---|---|---|
| `REMOTE_DOCKER_POOL_FILE` | 需要显式设置 | 建议设为 `~/.config/gui-synth-env/tencentcloud/worker_pool.json`，让启动脚本和 runtime 读取同一份 pool file |
| `REMOTE_DOCKER_WORKER_URLS` | — | 逗号分隔的 worker URL。设置后会绕过 pool file |
| `REMOTE_DOCKER_API_TOKEN` | — | worker-agent API 使用的 Bearer token |
| `REMOTE_DOCKER_REQUEST_TIMEOUT` | `30` | 默认单次 HTTP 请求超时 |
| `REMOTE_DOCKER_SESSION_CREATE_TIMEOUT` | `240` | 等待已提交 session 进入 `ready` 的最大时间 |
| `REMOTE_DOCKER_SESSION_ACQUIRE_TIMEOUT` | `180` | 等待 fleet 出现空闲容量的最大时间 |

进阶远端 runtime 环境变量：

| 变量 | 默认值 | 含义 |
|---|---|---|
| `REMOTE_DOCKER_COMMAND_TIMEOUT_GRACE_SECONDS` | `30` | 在单条命令超时之外额外保留的 HTTP 宽限时间 |
| `REMOTE_DOCKER_WORKER_COOLDOWN_SECONDS` | `15` | worker 异常后的临时冷却时间 |
| `REMOTE_DOCKER_CAPACITY_POLL_INTERVAL` | `2.0` | controller 轮询容量的间隔 |
| `REMOTE_DOCKER_SESSION_STATUS_POLL_INTERVAL` | `1.0` | controller 轮询 session 状态的间隔 |

## 8. 终止 workers

```bash
python computer_env/provision/tencentcloud/terminate_workers.py
```

终止行为：

- 默认优先终止 `REMOTE_DOCKER_POOL_FILE` 里记录的实例
- 如果 pool file 缺失或为空，脚本会回退为按 `ManagedBy=OpenComputer` 和 `NamePrefix=$TENCENTCLOUD_NAME_PREFIX` 扫描 CVM
- 如果脚本提示还有额外的托管实例不在本地 pool file 里，可以改用：

```bash
python computer_env/provision/tencentcloud/terminate_workers.py --all-by-prefix
```
