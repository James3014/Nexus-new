#!/usr/bin/env python3
"""Compatibility wrapper for legacy auto_linker entrypoint."""
import subprocess
import sys
from pathlib import Path

TARGET = Path(__file__).with_name('link_mapper.py')

if __name__ == '__main__':
    cmd = [sys.executable, str(TARGET), *sys.argv[1:]]
    raise SystemExit(subprocess.call(cmd))
