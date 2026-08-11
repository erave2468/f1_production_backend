#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/f1-api

sudo dnf update -y
sudo dnf install -y python3.13 python3.13-pip git nginx mariadb105 curl unzip

sudo mkdir -p "$APP_DIR" /var/cache/f1-api/fastf1 /etc/pki/rds
sudo chown -R ec2-user:ec2-user "$APP_DIR" /var/cache/f1-api

# AWS RDS CA bundle for verified TLS from PyMySQL.
sudo curl -fsSL \
  https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem \
  -o /etc/pki/rds/global-bundle.pem

echo "Host packages are ready. Copy/clone this project into $APP_DIR, then run deploy/scripts/install_app.sh"
