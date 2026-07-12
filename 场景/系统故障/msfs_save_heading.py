#!/usr/bin/env python3
"""用当前机头方向更新系统故障起始点航向。"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "msfs_failure.py"

if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, str(SCRIPT), "save-heading"]))
