#!/usr/bin/env python3
"""记录当前位置为恢复点。"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "msfs_obstacle.py"

if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, str(SCRIPT), "save"]))
