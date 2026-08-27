import os
from pathlib import Path

# Windows CI/dev accounts sometimes cannot write to %TEMP%/pytest-of-*.
# Keep pytest scratch files inside the already-ignored workspace tree.
_TMP = Path(__file__).resolve().parents[1] / ".pytest-tmp"
_TMP.mkdir(exist_ok=True)
os.environ["TMP"] = str(_TMP)
os.environ["TEMP"] = str(_TMP)
os.environ["TMPDIR"] = str(_TMP)
