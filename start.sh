#!/bin/bash
set -euo pipefail

PROFILE="${CUTAWAY_PROFILE:-local}"
VENV_ROOT="${CUTAWAY_VENV_ROOT:-.orchestrator/venvs}"
HUB_PYTHON="$VENV_ROOT/$PROFILE/hub/bin/python"

if [ ! -x "$HUB_PYTHON" ]; then
    HUB_PYTHON="${PYTHON:-python}"
fi

echo "Starting cutaway hub (profile=$PROFILE, isolation=${CUTAWAY_ISOLATION:-profile-default})..."
exec "$HUB_PYTHON" -m uvicorn main:app \
    --host 0.0.0.0 \
    --port "${PORT:-7860}" \
    --loop asyncio \
    --proxy-headers \
    --forwarded-allow-ips "*"
