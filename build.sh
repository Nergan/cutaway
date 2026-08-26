#!/bin/bash
set -e # Exit immediately on core failure

echo "Installing Tier 1 (Core) dependencies..."
# Три попытки: на HF builder PyPI иногда отваливается по read timeout.
pip_try() {
    local n=1
    until pip install --no-cache-dir "$@"; do
        n=$((n + 1))
        if [ "$n" -gt 3 ]; then
            echo "pip failed after 3 attempts: $*" >&2
            return 1
        fi
        echo "pip retry $n/3 after failure..."
        sleep 5
    done
}
pip_try -r requirements.txt

echo "Scanning for Tier 2 (Plugin) dependencies..."
# Iterate over all directories in the base path
declare -a build_pids=()

for dir in */; do
    if [ -f "${dir}package.json" ]; then
        echo "Found package.json in ${dir}. Attempting npm build in background..."
        set +e
        # Run npm build concurrently in a background subshell
        (
            cd "${dir}"
            # Fall back to standard npm install if npm ci fails due to an out-of-sync lockfile
            if npm ci || npm install --no-audit --no-fund; then
                if npm run build; then
                    echo "Successfully built frontend for ${dir}"
                else
                    echo "WARNING: Failed to build frontend for ${dir}. Skipping."
                fi
            else
                echo "WARNING: Failed to install frontend dependencies for ${dir}. Skipping."
            fi
        ) &
        build_pids+=($!)
        set -e
    fi

    if [ -f "${dir}requirements.txt" ]; then
        echo "Found requirements in ${dir}. Attempting installation..."
        
        # Disable exit-on-error to provide build-time fault tolerance for plugins
        set +e
        pip install --no-cache-dir -r "${dir}requirements.txt"
        
        if [ $? -eq 0 ]; then
            echo "Successfully installed dependencies for ${dir}"
        else
            echo "WARNING: Failed to install dependencies for ${dir}. Skipping plugin."
        fi
        
        # Re-enable exit-on-error for the core script
        set -e
    fi
done

echo "Waiting for all frontend builds to finish..."
for pid in "${build_pids[@]}"; do
    wait $pid || echo "WARNING: A background build process (PID $pid) failed."
done

echo "Checking for Playwright requirements..."
# If any plugin successfully installed Playwright, the CLI will be available
if command -v playwright >/dev/null 2>&1; then
    echo "Playwright CLI detected. Installing Chromium..."
    # Disable strict exit in case browser dependencies fail to fetch
    set +e 
    playwright install chromium
    set -e
else
    echo "Playwright not required by any active plugins. Skipping browser installation."
fi