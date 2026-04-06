import pytest
from pathlib import Path
import json
from scripts.ops.agent_protocol_check import check_protocol


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


def test_protocol_missing_agents_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert check_protocol(contract_path=tmp_path / "contract.json") == 1

def test_protocol_missing_terms(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("allowed_paths: /") # Missing others
    _write_contract(tmp_path / "contract.json")
    assert check_protocol(contract_path=tmp_path / "contract.json") == 1

def test_protocol_check_files_forbidden(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("""
- **allowed_paths**: Project root
- **forbidden_paths**: .obsidian/, secret/
- **max_files_touched**: 5
- Semantic Completion Criteria
- Evidence Reporting Format
- Failure-to-Lesson Writeback
""")
    _write_contract(tmp_path / "contract.json", forbidden=[".obsidian/", "secret/"])
    # Hit forbidden
    assert check_protocol(check_files=[".obsidian/config"], contract_path=tmp_path / "contract.json") == 1
    assert check_protocol(check_files=["secret/key"], contract_path=tmp_path / "contract.json") == 1

def test_protocol_check_files_too_many(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("""
- **allowed_paths**: Project root
- **forbidden_paths**: .obsidian/
- **max_files_touched**: 2
- Semantic Completion Criteria
- Evidence Reporting Format
- Failure-to-Lesson Writeback
""")
    _write_contract(tmp_path / "contract.json", max_files=2)
    assert check_protocol(check_files=["a.txt", "b.txt", "c.txt"], contract_path=tmp_path / "contract.json") == 1

def test_protocol_check_files_pass(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("""
- **allowed_paths**: Project root
- **forbidden_paths**: .obsidian/
- **max_files_touched**: 10
- Semantic Completion Criteria
- Evidence Reporting Format
- Failure-to-Lesson Writeback
""")
    _write_contract(tmp_path / "contract.json")
    assert check_protocol(check_files=["a.txt", "b.txt"], contract_path=tmp_path / "contract.json") == 0


def test_protocol_check_files_strict_boundary_fail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text(
        """
- **allowed_paths**: Project root
- **forbidden_paths**: .obsidian/
- **max_files_touched**: 10
- Semantic Completion Criteria
- Evidence Reporting Format
- Failure-to-Lesson Writeback
""".strip()
    )
    _write_contract(tmp_path / "contract.json", allowed=["scripts/ops/"])
    assert (
        check_protocol(
            check_files=["nexus_wiki_vault/00_Home/System Overview.md"],
            strict=True,
            contract_path=tmp_path / "contract.json",
        )
        == 1
    )
