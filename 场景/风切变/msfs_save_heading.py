#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "msfs_windshear.py"
sys.exit(subprocess.call([sys.executable, str(SCRIPT), "save-heading"]))
