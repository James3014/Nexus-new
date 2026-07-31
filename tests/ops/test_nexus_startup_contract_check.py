import pytest
import os
import json
import subprocess
from pathlib import Path
from scripts.ops.nexus_startup_contract_check import run_check, REQUIRED_FILES
import scripts.ops.nexus_startup_contract_check as startup

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


def _pass_freshness(index_path):
    return {
        "decision": "PASS",
        "index_commit": "a" * 40,
        "current_frontier": "task-one",
        "task_cards": [{"task_id": "task-one", "sha256": "b" * 64}],
    }


def test_startup_freshness_block_does_not_issue_ack(mock_project_root, monkeypatch):
    monkeypatch.setattr(
        startup,
        "check_worktree",
        lambda root: {
            "root_match": True,
            "branch": "main",
            "head": "c" * 40,
            "clean": True,
        },
    )
    monkeypatch.setattr(startup, "check_cli", lambda root: {cmd: True for cmd in startup.REQUIRED_SURFACES})
    monkeypatch.setattr(startup, "validate_task_authority", lambda *args, **kwargs: {"decision": "BLOCK", "findings": [{"code": "INDEX_MISSING"}], "task_cards": []})
    contract = mock_project_root / "contract.json"
    contract.write_text("policy")
    report_dir = mock_project_root / "reports"

    result = run_check(
        mock_project_root,
        index_path=mock_project_root / "missing-index.md",
        contract_path=contract,
        report_dir=report_dir,
    )

    assert result == 1
    assert not (report_dir / "startup_contract_ack.json").exists()
    report = json.loads((report_dir / "startup_contract_check_report.json").read_text())
    assert report["task_authority"]["decision"] == "BLOCK"


def test_startup_ack_binds_freshness_inputs(mock_project_root, monkeypatch):
    monkeypatch.setattr(
        startup,
        "check_worktree",
        lambda root: {
            "root_match": True,
            "branch": "main",
            "head": "c" * 40,
            "clean": True,
        },
    )
    monkeypatch.setattr(startup, "check_cli", lambda root: {cmd: True for cmd in startup.REQUIRED_SURFACES})
    monkeypatch.setattr(startup, "validate_task_authority", lambda *args, **kwargs: _pass_freshness(args[1]))
    contract = mock_project_root / "contract.json"
    contract.write_text("policy")
    report_dir = mock_project_root / "reports"

    result = run_check(
        mock_project_root,
        index_path=mock_project_root / "index.md",
        contract_path=contract,
        report_dir=report_dir,
    )

    assert result == 0
    ack = json.loads((report_dir / "startup_contract_ack.json").read_text())
    assert ack["head"] == "c" * 40
    assert ack["index_path"].endswith("index.md")
    assert ack["task_card_hash"] == "b" * 64
    assert ack["policy_contract_sha256"] == startup._sha256(contract)


def test_default_report_dir_is_external_to_source_checkout(mock_project_root, monkeypatch, tmp_path):
    monkeypatch.delenv("NEXUS_STARTUP_REPORT_DIR", raising=False)
    monkeypatch.delenv("NEXUS_MACHINE_STATE_DIR", raising=False)
    monkeypatch.delenv("NEXUS_STATE_DIR", raising=False)
    resolved = startup._default_report_dir(mock_project_root)
    assert resolved.is_absolute()
    assert mock_project_root not in resolved.parents
    assert resolved.parts[-2:] == ("nexus-startup-contract", "startup_hardening") or resolved.name == "startup_hardening"


def test_machine_state_dir_controls_default_report_dir(mock_project_root, monkeypatch, tmp_path):
    machine_state = tmp_path / "machine-state"
    monkeypatch.delenv("NEXUS_STARTUP_REPORT_DIR", raising=False)
    monkeypatch.setenv("NEXUS_MACHINE_STATE_DIR", str(machine_state))
    assert startup._default_report_dir(mock_project_root) == machine_state / "startup_hardening"
