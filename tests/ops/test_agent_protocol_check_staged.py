import json
from pathlib import Path

import scripts.ops.agent_protocol_check as apc
from scripts.ops.agent_protocol_check import check_protocol

CURRENT_REQUIRED_TERMS = (
    "Direct execution authority",
    "Governed execution authority",
    "Completion requires behavioral evidence",
    "Report evidence in the final response",
    "docs/agents/TASK_EXECUTION_CONTRACT.md",
    "docs/agents/LEARNING_WRITEBACK_OVERLAY.md",
    "CapabilityPlanner",
)


def _write_contract(path: Path, *, forbidden=None, allowed=None, max_files=10):
    forbidden = forbidden or [".obsidian/"]
    allowed = allowed or ["."]
    path.write_text(json.dumps({
        "required_terms": list(CURRENT_REQUIRED_TERMS),
        "boundaries": {
            "allowed_paths": allowed,
            "forbidden_paths": forbidden,
            "max_files_touched": max_files,
        },
    }), encoding="utf-8")

def _setup_agents_md(tmp_path):
    (tmp_path / "AGENTS.md").write_text("\n".join(CURRENT_REQUIRED_TERMS), encoding="utf-8")

def test_protocol_check_staged_pass(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _setup_agents_md(tmp_path)
    _write_contract(tmp_path / "contract.json")
    
    monkeypatch.setattr(apc, "_get_staged_files", lambda: ["a.txt", "b.txt"])
    
    assert check_protocol(check_staged=True, contract_path=tmp_path / "contract.json") == 0

def test_protocol_check_staged_forbidden(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _setup_agents_md(tmp_path)
    _write_contract(tmp_path / "contract.json", forbidden=["secret/"])
    
    monkeypatch.setattr(apc, "_get_staged_files", lambda: ["secret/key.txt"])
    
    assert check_protocol(check_staged=True, contract_path=tmp_path / "contract.json") == 1

def test_protocol_check_staged_strict_fail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _setup_agents_md(tmp_path)
    _write_contract(tmp_path / "contract.json", allowed=["scripts/"])
    
    monkeypatch.setattr(apc, "_get_staged_files", lambda: ["other/file.txt"])
    
    assert check_protocol(check_staged=True, strict=True, contract_path=tmp_path / "contract.json") == 1

def test_protocol_check_staged_too_many(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _setup_agents_md(tmp_path)
    _write_contract(tmp_path / "contract.json", max_files=2)
    
    monkeypatch.setattr(apc, "_get_staged_files", lambda: ["a.txt", "b.txt", "c.txt"])
    
    assert check_protocol(check_staged=True, contract_path=tmp_path / "contract.json") == 1
