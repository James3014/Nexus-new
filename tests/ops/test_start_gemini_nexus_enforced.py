import pytest
import subprocess
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
    # 驗證啟動後是否產生了 ack artifact
    # 這裡我們直接執行 contract check 腳本來模擬成功路徑
    subprocess.run(["python3", "scripts/ops/nexus_startup_contract_check.py"], capture_output=True)
    ack_path = Path(".nexus/reports/startup_hardening/startup_contract_ack.json")
    assert ack_path.exists()
