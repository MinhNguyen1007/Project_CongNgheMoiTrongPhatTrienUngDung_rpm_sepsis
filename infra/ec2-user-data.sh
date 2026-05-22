#!/bin/bash
# WHY swap: t3.micro 1GB RAM không đủ cho 7 containers (Kafka + backend + mlflow + frontend + postgres + prometheus + grafana).
# Swap 4GB tránh OOM killer. Phải làm trước khi start Docker.
set -e

# 1. Tạo swap 2GB
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# 2. Cài Docker CE
apt-get update -y
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 3. Cho ubuntu user dùng docker không cần sudo
usermod -aG docker ubuntu

# 4. Enable + start docker
systemctl enable docker
systemctl start docker

echo "DONE: swap + docker ready" >> /var/log/user-data-done.log
