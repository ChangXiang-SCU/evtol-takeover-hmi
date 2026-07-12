#!/usr/bin/env python3
"""记录系统故障存档点。"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "msfs_failure.py"

if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, str(SCRIPT), "save"]))
