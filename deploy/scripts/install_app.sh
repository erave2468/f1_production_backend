#!/usr/bin/env bash
set -euo pipefail
cd /opt/f1-api
python3.13 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "Python environment is ready. Copy .env.example to .env and edit the RDS/frontend settings."
