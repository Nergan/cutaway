#!/bin/bash
set -e # Exit immediately on core failure

echo "Installing Tier 1 (Core) dependencies..."
pip install --no-cache-dir -r requirements.txt

echo "Scanning for Tier 2 (Plugin) dependencies..."
# Iterate over all directories in the base path
for dir in */; do
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