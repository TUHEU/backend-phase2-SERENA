#!/usr/bin/env bash
# Pull the latest backend-phase2 code and rebuild/restart the stack.
# Run this from inside the backend-phase2 folder on the VPS.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Pulling latest code..."
git pull

echo "==> Rebuilding and restarting containers..."
docker compose up -d --build

echo "==> Current status:"
docker compose ps
