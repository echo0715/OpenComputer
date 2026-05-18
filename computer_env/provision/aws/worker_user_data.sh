#!/usr/bin/env bash
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y docker.io python3 unzip curl ca-certificates
systemctl enable docker
systemctl start docker

if ! command -v aws >/dev/null 2>&1; then
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
  unzip -q /tmp/awscliv2.zip -d /tmp
  /tmp/aws/install --update
fi

apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/aws /tmp/awscliv2.zip

mkdir -p /opt/opencomputer /etc/opencomputer

TOKEN=$(curl -sS -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
INSTANCE_ID=$(curl -sS -H "X-aws-ec2-metadata-token: ${TOKEN}" \
  http://169.254.169.254/latest/meta-data/instance-id)
PUBLIC_IP=$(curl -sS -H "X-aws-ec2-metadata-token: ${TOKEN}" \
  http://169.254.169.254/latest/meta-data/public-ipv4 || true)

aws s3 cp "s3://__S3_BUCKET__/__BOOTSTRAP_KEY__" /tmp/opencomputer-worker-agent.zip --region "__REGION__"
unzip -o /tmp/opencomputer-worker-agent.zip -d /opt/opencomputer/worker-agent
rm -f /tmp/opencomputer-worker-agent.zip

aws ecr get-login-password --region "__REGION__" \
  | docker login --username AWS --password-stdin "__ACCOUNT_ID__.dkr.ecr.__REGION__.amazonaws.com"
docker pull "__ECR_IMAGE__"

cat >/etc/opencomputer/worker-agent.env <<EOF
GUI_SYNTH_WORKER_PORT=__WORKER_AGENT_PORT__
GUI_SYNTH_WORKER_API_TOKEN=__API_TOKEN__
GUI_SYNTH_WORKER_DEFAULT_IMAGE=__ECR_IMAGE__
GUI_SYNTH_WORKER_PUBLIC_HOST=${PUBLIC_IP}
GUI_SYNTH_WORKER_INSTANCE_ID=${INSTANCE_ID}
GUI_SYNTH_WORKER_MAX_SESSIONS=__MAX_SESSIONS__
GUI_SYNTH_WORKER_DOCKER_PLATFORM=linux/amd64
GUI_SYNTH_WORKER_NOVNC_PORT_START=__NOVNC_PORT_START__
GUI_SYNTH_WORKER_NOVNC_PORT_END=__NOVNC_PORT_END__
EOF

cp /opt/opencomputer/worker-agent/systemd/gui-synth-worker.service /etc/systemd/system/gui-synth-worker.service
systemctl daemon-reload
systemctl enable gui-synth-worker.service
systemctl restart gui-synth-worker.service
