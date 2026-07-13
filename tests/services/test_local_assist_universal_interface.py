from __future__ import annotations

import json

import pytest

from nexus.services.local_assist_universal_interface import (
    AGENT_INTERFACE_SCHEMA,
    build_universal_agent_interface,
    load_universal_agent_task,
    render_machine_readable_interface,
)


def _task() -> dict[str, object]:
    return {
        "task_id": "m6-a-001",
        "workspace_revision": "rev-1",
        "task_statement": "implement a bounded bug fix in one file",
        "task_type": "bugfix",
        "route": {"route_features": {"risk_score": 20, "adjusted_root_cause_confidence": 0.9}},
        "allowed_files": ["target.py"],
        "target_file": "target.py",
        "target_symbol": "target",
        "evidence_refs": ["tests/services/test_local_assist_universal_interface.py"],
    }


def test_universal_interface_exposes_provider_neutral_contract() -> None:
    envelope = build_universal_agent_interface(_task())
    assert envelope["schema"] == AGENT_INTERFACE_SCHEMA
    assert envelope["task_identity"]["task_id"] == "m6-a-001"
    assert envelope["planner_recommendation"]["action"] == "candidate"
    assert envelope["available_actions"] == ["skip", "advisor", "candidate", "verified-subtask"]
    assert envelope["assist_envelope"]["receipt_paths"] == []
    assert envelope["consumption_contract"]["receipt_only_insufficient"] is True
    assert envelope["contribution_contract"]["outcome_contributed"] is False
    assert envelope["claim_boundary"]["public_claim_allowed"] is False
    assert envelope["provider_neutral"] is True


def test_task_file_and_machine_stdout_are_round_trippable(tmp_path) -> None:
    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps(_task()), encoding="utf-8")
    loaded = load_universal_agent_task(task_file)
    rendered = render_machine_readable_interface(loaded)
    assert json.loads(rendered)["schema"] == AGENT_INTERFACE_SCHEMA


def test_missing_identity_or_task_statement_fails_closed() -> None:
    with pytest.raises(ValueError, match="task_id_missing"):
        build_universal_agent_interface({**_task(), "task_id": ""})
    with pytest.raises(ValueError, match="task_statement_missing"):
        build_universal_agent_interface({**_task(), "task_statement": ""})
