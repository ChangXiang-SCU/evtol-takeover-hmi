#!/usr/bin/env python3
"""传送到恢复点。"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "msfs_windshear.py"

if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, str(SCRIPT), "teleport"]))
