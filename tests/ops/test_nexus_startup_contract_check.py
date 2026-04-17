import pytest
import os
import json
import subprocess
from pathlib import Path
from scripts.ops.nexus_startup_contract_check import run_check, REQUIRED_FILES

@pytest.fixture
def mock_project_root(tmp_path):
    # 模擬一個乾淨的專案根目錄
    for f in REQUIRED_FILES:
        path = tmp_path / f
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("dummy")
    
    # 模擬 nexus_cli.py --help
    cli_dir = tmp_path / "scripts/engine"
    cli_dir.mkdir(parents=True, exist_ok=True)
    cli_file = cli_dir / "nexus_cli.py"
    cli_file.write_text("""
import sys
if 'nexus' in sys.argv and '--help' in sys.argv:
    print('Usage: nexus [OPTIONS] COMMAND')
    print('acceptance-check')
    print('contract-check')
""")
    return tmp_path

def test_startup_contract_check_success(mock_project_root, monkeypatch):
    # 透過 monkeypatch 修改 scripts/ops/中的路徑邏輯，或直接執行
    monkeypatch.chdir(mock_project_root)
    # 我們需要讓腳本讀到 mock 的根目錄
    # 這裡直接測試內部的 check_files 邏輯 (匯入方式測試)
    from scripts.ops.nexus_startup_contract_check import check_files, check_cli
    
    f_res = check_files(mock_project_root)
    assert all(f_res.values())
    
    # 模擬 subprocess 呼叫
    monkeypatch.setattr(subprocess, "check_output", lambda cmd, **kwargs: "acceptance-check\ncontract-check")
    c_res = check_cli(mock_project_root)
    assert all(c_res.values())

def test_startup_contract_check_failure(mock_project_root, monkeypatch):
    monkeypatch.chdir(mock_project_root)
    # 故意刪除一個檔案
    (mock_project_root / "AGENTS.md").unlink()
    
    from scripts.ops.nexus_startup_contract_check import check_files
    f_res = check_files(mock_project_root)
    assert f_res["AGENTS.md"] is False
