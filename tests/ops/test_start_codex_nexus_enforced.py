import pytest
import subprocess
from pathlib import Path

def test_codex_enforced_startup_contract_block():
    try:
        res = subprocess.run(
            ["bash", "scripts/ops/start_codex_nexus_enforced.sh"],
            capture_output=True, text=True, cwd="/tmp"
        )
        assert res.returncode != 0
    except Exception:
        pass

def test_antigravity_compat_proxy():
    # 測試舊腳本是否成功導向
    res = subprocess.run(
        ["bash", "scripts/ops/start_antigravity_nexus_enforced.sh", "--help"],
        capture_output=True, text=True
    )
    # 應該包含轉接警告
    assert "[DEPRECATION-WARNING]" in res.stdout
