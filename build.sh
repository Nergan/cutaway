#!/bin/bash
set -euo pipefail

PROFILE="${CUTAWAY_PROFILE:-local}"
VENV_ROOT="${CUTAWAY_VENV_ROOT:-.orchestrator/venvs}"

pip_try() {
    local python_bin="$1"
    shift
    local n=1
    until "$python_bin" -m pip install --no-cache-dir "$@"; do
        n=$((n + 1))
        if [ "$n" -gt 3 ]; then
            echo "pip failed after 3 attempts: $*" >&2
            return 1
        fi
        echo "pip retry $n/3 after failure..."
        sleep 5
    done
}

python -m orchestrator.config --profile "$PROFILE" validate
DEPENDENCY_ISOLATION="$(
    python -m orchestrator.config --profile "$PROFILE" settings --field dependency_isolation
)"
mapfile -t ACTIVE_PROJECTS < <(
    python -m orchestrator.config --profile "$PROFILE" list --phase build --field project_id
)

declare -a build_pids=()

build_frontend() {
    local project="$1"
    if [ ! -f "$project/package.json" ]; then
        return
    fi
    echo "Building frontend for $project..."
    (
        cd "$project"
        if npm ci || npm install --no-audit --no-fund; then
            npm run build || echo "WARNING: frontend build failed for $project" >&2
        else
            echo "WARNING: frontend dependency install failed for $project" >&2
        fi
    ) &
    build_pids+=("$!")
}

if [ "$DEPENDENCY_ISOLATION" = "true" ]; then
    echo "Installing isolated dependencies for profile $PROFILE..."
    HUB_VENV="$VENV_ROOT/$PROFILE/hub"
    python -m venv "$HUB_VENV"
    HUB_PYTHON="$HUB_VENV/bin/python"
    if [ ! -x "$HUB_PYTHON" ]; then
        HUB_PYTHON="$HUB_VENV/Scripts/python.exe"
    fi
    pip_try "$HUB_PYTHON" -r requirements.txt

    for project in "${ACTIVE_PROJECTS[@]}"; do
        project_venv="$VENV_ROOT/$PROFILE/$project"
        python -m venv "$project_venv"
        project_python="$project_venv/bin/python"
        if [ ! -x "$project_python" ]; then
            project_python="$project_venv/Scripts/python.exe"
        fi

        # Every worker needs FastAPI, uvicorn and shared hub modules. Its own
        # requirements are installed afterwards but remain private to this venv.
        if ! pip_try "$project_python" -r requirements.txt; then
            echo "WARNING: core dependencies failed for $project" >&2
            continue
        fi
        if [ -f "$project/requirements.txt" ]; then
            if ! pip_try "$project_python" -r "$project/requirements.txt"; then
                echo "WARNING: project dependencies failed for $project" >&2
            fi
        fi
        build_frontend "$project"
    done
else
    echo "Installing shared dependencies for embedded profile $PROFILE..."
    pip_try python -r requirements.txt
    for project in "${ACTIVE_PROJECTS[@]}"; do
        if [ -f "$project/requirements.txt" ]; then
            if ! pip_try python -r "$project/requirements.txt"; then
                echo "WARNING: project dependencies failed for $project" >&2
            fi
        fi
        build_frontend "$project"
    done
fi

echo "Waiting for frontend builds..."
for pid in "${build_pids[@]}"; do
    wait "$pid" || echo "WARNING: a frontend build failed." >&2
done

echo "Installing the shared Playwright browser when required..."
PLAYWRIGHT_INSTALLED=0
if [ "$DEPENDENCY_ISOLATION" = "true" ]; then
    for project in "${ACTIVE_PROJECTS[@]}"; do
        candidate="$VENV_ROOT/$PROFILE/$project/bin/playwright"
        if [ -x "$candidate" ]; then
            "$candidate" install chromium
            PLAYWRIGHT_INSTALLED=1
            break
        fi
    done
elif command -v playwright >/dev/null 2>&1; then
    playwright install chromium
    PLAYWRIGHT_INSTALLED=1
fi

if [ "$PLAYWRIGHT_INSTALLED" -eq 0 ]; then
    echo "Playwright is not required by active projects."
fi
