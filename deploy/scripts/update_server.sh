#!/usr/bin/env bash
set -euo pipefail
cd /opt/f1-api

git pull --ff-only
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.bootstrap
sudo systemctl restart f1-api.service
sudo systemctl start f1-collector.service
