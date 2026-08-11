#!/usr/bin/env bash
set -euo pipefail

cd /opt/f1-api

sudo cp deploy/systemd/f1-api.service /etc/systemd/system/f1-api.service
sudo cp deploy/systemd/f1-collector.service /etc/systemd/system/f1-collector.service
sudo cp deploy/systemd/f1-collector.timer /etc/systemd/system/f1-collector.timer
sudo cp deploy/nginx/f1-api.conf /etc/nginx/conf.d/f1-api.conf

sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now nginx
sudo systemctl enable --now f1-api.service
sudo systemctl enable --now f1-collector.timer

sudo systemctl --no-pager status f1-api.service || true
sudo systemctl --no-pager status f1-collector.timer || true
