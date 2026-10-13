"""Online A/B 20261013b finding 4: an ESCALATEd Workforce admission is not a model call.

On oabh-conflict/ledger/ruleset the planner asked for role ``independent_review``, admission
returned ESCALATE, no provider process started, yet the row reported ``model_calls=1``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus.research.sprint_service import LLMCandidateError, LLMCandidateGenerator

_BLOCKED_AUTHORITY = {
    "schema": "nexus.gateway_invocation_authority.v1",
    "status": "BLOCKED",
    "gate_passed": False,
    "failure_reason": "workforce_admission_overall_decision_not_allow",
    "admission_overall_decision": "ESCALATE",
}

# Shape of saved receipt sprint-e5d69e0e3653-s0-a1 (run 20261013b, _diag/).
ESCALATED_RECEIPT = {
    "online": {
        "name": "online",
        "status": "FAILED",
        "invoked": False,
        "provider_call_count": 0,
        "reason": "workforce_admission_overall_decision_not_allow",
        "context_trace": {"gateway_invocation_authority": dict(_BLOCKED_AUTHORITY)},
        "response": {
            "provider": "",
            "invoked": False,
            "output_delivered": False,
            "provider_call_count": 0,
            "response": "",
            "raw_response": "",
            "error": "workforce_admission_overall_decision_not_allow",
        },
    }
}


def _generator(monkeypatch, tmp_path: Path, receipt: dict) -> LLMCandidateGenerator:
    generator = LLMCandidateGenerator(tmp_path, safe_mode=True)
    monkeypatch.setattr(generator, "_workspace_revision", lambda: "revision-escalate-001")
    monkeypatch.setattr(generator, "model_chain", ["gemini-3.8-flash-medium"])
    monkeypatch.setattr(generator.gateway, "ask_unified", lambda *_a, **_k: receipt, raising=False)
    return generator


def test_escalated_admission_reports_zero_model_calls(monkeypatch, tmp_path: Path):
    generator = _generator(monkeypatch, tmp_path, ESCALATED_RECEIPT)

    with pytest.raises(LLMCandidateError) as excinfo:
        generator.generate(source_code="x = 1\n", task="t", mutation_hint="", seed=0)

    assert excinfo.value.metadata["model_calls"] == 0
    assert excinfo.value.metadata["model_call_skipped_reason"] == "admission_escalated"


def test_invoked_online_stage_still_counts_one_call(monkeypatch, tmp_path: Path):
    receipt = {
        "online": {
            "status": "SUCCEEDED",
            "invoked": True,
            "response": {"invoked": True, "provider_call_count": 1, "response": "x = 2\n"},
        }
    }
    generator = _generator(monkeypatch, tmp_path, receipt)

    _code, metadata = generator.generate(source_code="x = 1\n", task="t", mutation_hint="", seed=0)

    assert metadata["model_calls"] == 1
    assert metadata["model_call_skipped_reason"] == ""
