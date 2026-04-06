import pytest
from pathlib import Path
import json
from scripts.ops.agent_protocol_check import check_protocol
import scripts.ops.agent_protocol_check as apc


def _write_contract(path: Path, *, forbidden=None, allowed=None, max_files=10):
    forbidden = forbidden or [".obsidian/"]
    allowed = allowed or ["."]
    path.write_text(
        f"""
{{
  "required_terms": [
    "allowed_paths",
    "forbidden_paths",
    "max_files_touched",
    "Semantic Completion Criteria",
    "Evidence Reporting Format",
    "Failure-to-Lesson Writeback"
  ],
  "boundaries": {{
    "allowed_paths": {json.dumps(allowed)},
    "forbidden_paths": {json.dumps(forbidden)},
    "max_files_touched": {max_files}
  }}
}}
""".strip()
    )

def _setup_agents_md(tmp_path):
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("""
- **allowed_paths**: Project root
- **forbidden_paths**: .obsidian/, secret/
- **max_files_touched**: 5
- Semantic Completion Criteria
- Evidence Reporting Format
- Failure-to-Lesson Writeback
""")

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
