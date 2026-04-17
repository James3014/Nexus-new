import pytest
import subprocess
import sys
from pathlib import Path

def test_legacy_command_blocked():
    # 測試 nexus:acceptance-check 是否被封鎖
    res = subprocess.run(
        [sys.executable, "scripts/engine/nexus_cli.py", "nexus:acceptance-check"],
        capture_output=True, text=True
    )
    assert res.returncode == 2
    assert "[DEPRECATED_BLOCKED]" in res.stdout or "[DEPRECATED_BLOCKED]" in res.stderr
    assert "nexus acceptance-check" in res.stdout or "nexus acceptance-check" in res.stderr

def test_legacy_status_blocked():
    res = subprocess.run(
        [sys.executable, "scripts/engine/nexus_cli.py", "nexus:status"],
        capture_output=True, text=True
    )
    assert res.returncode == 2
    assert "nexus status" in res.stdout or "nexus status" in res.stderr

def test_new_command_available():
    # 測試新入口是否可用 (以 --help 為例)
    res = subprocess.run(
        [sys.executable, "scripts/engine/nexus_cli.py", "nexus", "acceptance-check", "--help"],
        capture_output=True, text=True
    )
    assert res.returncode == 0
    assert "Run full system acceptance check" in res.stdout
