#!/usr/bin/env bash
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive

BUNDLE_URL=__BUNDLE_URL_SH__
TCR_SERVER=__TCR_PERSONAL_SERVER_SH__
TCR_USERNAME=__ACCOUNT_UIN_SH__
TCR_PASSWORD=__TCR_PASSWORD_SH__
IMAGE_URI=__IMAGE_URI_SH__
API_TOKEN=__API_TOKEN_SH__

apt-get update
apt-get install -y docker.io python3 unzip curl ca-certificates
systemctl enable docker
systemctl start docker

apt-get clean
rm -rf /var/lib/apt/lists/*

mkdir -p /opt/opencomputer /etc/opencomputer

curl -fsSL --retry 5 --retry-delay 3 "${BUNDLE_URL}" -o /tmp/opencomputer-worker-agent.zip
unzip -o /tmp/opencomputer-worker-agent.zip -d /opt/opencomputer/worker-agent
rm -f /tmp/opencomputer-worker-agent.zip

printf '%s' "${TCR_PASSWORD}" | docker login "${TCR_SERVER}" -u "${TCR_USERNAME}" --password-stdin
docker pull "${IMAGE_URI}"

INSTANCE_ID=$(curl -fsSL http://metadata.tencentyun.com/latest/meta-data/instance-id)
PUBLIC_IP=$(curl -fsSL http://metadata.tencentyun.com/latest/meta-data/public-ipv4 || true)

cat >/etc/opencomputer/worker-agent.env <<EOF
GUI_SYNTH_WORKER_PORT=__WORKER_AGENT_PORT__
GUI_SYNTH_WORKER_API_TOKEN=${API_TOKEN}
GUI_SYNTH_WORKER_DEFAULT_IMAGE=${IMAGE_URI}
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
