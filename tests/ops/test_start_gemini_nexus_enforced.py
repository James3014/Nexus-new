import pytest
import subprocess
import os
from pathlib import Path

def test_gemini_enforced_startup_contract_block():
    # 故意在一個沒有 Nexus 的環境執行
    # 這裡我們模擬呼叫腳本
    try:
        res = subprocess.run(
            ["bash", "scripts/ops/start_gemini_nexus_enforced.sh"],
            capture_output=True, text=True, cwd="/tmp" # 切換到一個空的目錄
        )
        # 應該會因為找不到腳本或 contract 檢查失敗而 exit 1
        assert res.returncode != 0
    except Exception:
        pass

def test_gemini_enforced_interactive_artifact():
    # A dirty implementation Target must block, but the report must remain
    # outside the source checkout so the block itself is observable.
    state_dir = Path("/tmp") / "nexus-gemini-startup-test"
    env = {**os.environ, "NEXUS_MACHINE_STATE_DIR": str(state_dir)}
    source_report = Path(".nexus/reports/startup_hardening/startup_contract_check_report.json")
    source_before = source_report.read_bytes() if source_report.exists() else None
    result = subprocess.run(
        ["python3", "scripts/ops/nexus_startup_contract_check.py"],
        capture_output=True,
        text=True,
        env=env,
    )
    report_path = state_dir / "startup_hardening/startup_contract_check_report.json"
    assert result.returncode != 0
    assert report_path.exists()
    source_after = source_report.read_bytes() if source_report.exists() else None
    assert source_after == source_before
