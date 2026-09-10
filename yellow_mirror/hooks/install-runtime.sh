#!/bin/bash
set -euo pipefail

if [ -z "${CUTAWAY_PROJECT_PYTHON:-}" ]; then
    echo "CUTAWAY_PROJECT_PYTHON is required" >&2
    exit 1
fi

"$CUTAWAY_PROJECT_PYTHON" -m playwright install chromium
