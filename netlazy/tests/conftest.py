import sys
from pathlib import Path

# Ensure the monorepo root and netlazy directory are in sys.path
NETLAZY_DIR = Path(__file__).resolve().parent.parent
CUTAWAY_DIR = NETLAZY_DIR.parent

for path in (str(CUTAWAY_DIR), str(NETLAZY_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)