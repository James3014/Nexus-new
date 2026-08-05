import json
from pathlib import Path

from scripts.ops.agent_protocol_check import check_protocol

ROOT = Path(__file__).resolve().parents[2]
CURRENT_REQUIRED_TERMS = (
    "Direct execution authority",
    "Governed execution authority",
    "Completion requires behavioral evidence",
    "Report evidence in the final response",
    "docs/agents/TASK_EXECUTION_CONTRACT.md",
    "docs/agents/LEARNING_WRITEBACK_OVERLAY.md",
    "CapabilityPlanner",
)


def _write_agents(path: Path, terms=CURRENT_REQUIRED_TERMS):
    path.write_text("\n".join(terms), encoding="utf-8")


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


def _write_overlay_card(path: Path, *, forbidden=None, allowed=None, max_files=10):
    forbidden = forbidden or []
    allowed = allowed or ["scripts/"]
    path.write_text(
        "## Machine policy overlay\n\n```json\n"
        + json.dumps(
            {
                "allowed_paths": allowed,
                "forbidden_paths": forbidden,
                "max_files_touched": max_files,
            }
        )
        + "\n```\n",
        encoding="utf-8",
    )


def test_repository_contract_accepts_current_compact_agents(monkeypatch):
    monkeypatch.chdir(ROOT)

    assert check_protocol(contract_path=ROOT / "scripts/ops/agent_protocol_contract.json") == 0


def test_protocol_missing_agents_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert check_protocol(contract_path=tmp_path / "contract.json") == 1

def test_protocol_missing_terms(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_agents(tmp_path / "AGENTS.md", CURRENT_REQUIRED_TERMS[:1])
    _write_contract(tmp_path / "contract.json")
    assert check_protocol(contract_path=tmp_path / "contract.json") == 1

def test_protocol_check_files_forbidden(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_agents(tmp_path / "AGENTS.md")
    _write_contract(tmp_path / "contract.json", forbidden=[".obsidian/", "secret/"])
    # Hit forbidden
    assert check_protocol(check_files=[".obsidian/config"], contract_path=tmp_path / "contract.json") == 1
    assert check_protocol(check_files=["secret/key"], contract_path=tmp_path / "contract.json") == 1

def test_protocol_check_files_too_many(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_agents(tmp_path / "AGENTS.md")
    _write_contract(tmp_path / "contract.json", max_files=2)
    assert check_protocol(check_files=["a.txt", "b.txt", "c.txt"], contract_path=tmp_path / "contract.json") == 1

def test_protocol_check_files_pass(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_agents(tmp_path / "AGENTS.md")
    _write_contract(tmp_path / "contract.json")
    assert check_protocol(check_files=["a.txt", "b.txt"], contract_path=tmp_path / "contract.json") == 0


def test_protocol_check_files_strict_boundary_fail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_agents(tmp_path / "AGENTS.md")
    _write_contract(tmp_path / "contract.json", allowed=["scripts/ops/"])
    assert (
        check_protocol(
            check_files=["nexus_wiki_vault/00_Home/System Overview.md"],
            strict=True,
            contract_path=tmp_path / "contract.json",
        )
        == 1
    )


def test_protocol_missing_baseline_fails_closed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_agents(tmp_path / "AGENTS.md")
    assert check_protocol(contract_path=tmp_path / "missing.json") == 1


def test_protocol_malformed_baseline_fails_closed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_agents(tmp_path / "AGENTS.md")
    contract = tmp_path / "contract.json"
    contract.write_text("{not-json")
    assert check_protocol(contract_path=contract) == 1


def test_protocol_task_card_overlay_narrows_baseline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_agents(tmp_path / "AGENTS.md")
    contract = tmp_path / "contract.json"
    _write_contract(contract, allowed=["."], forbidden=["packages/"], max_files=5)
    card = tmp_path / "card.md"
    _write_overlay_card(card, allowed=["scripts/"], forbidden=["scripts/private/"], max_files=2)

    assert check_protocol(
        check_files=["scripts/ops/check.py"],
        strict=True,
        contract_path=contract,
        task_card_path=card,
    ) == 0
    assert check_protocol(
        check_files=["docs/plan.md"],
        strict=True,
        contract_path=contract,
        task_card_path=card,
    ) == 1
    assert check_protocol(
        check_files=["scripts/private/key.txt"],
        contract_path=contract,
        task_card_path=card,
    ) == 1
    assert check_protocol(
        check_files=["scripts/a.py", "scripts/b.py", "scripts/c.py"],
        contract_path=contract,
        task_card_path=card,
    ) == 1
