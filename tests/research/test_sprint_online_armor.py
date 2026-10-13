"""Online A/B gap A: the sprint online candidate runs run_mainchain with Nexus armor on."""

from __future__ import annotations

from pathlib import Path

from nexus.research.sprint_service import LLMCandidateGenerator


def _approved(*_args, **_kwargs):
    return (
        {
            "status": "APPROVED",
            "operation": "replace",
            "target_snippet": "return text",
            "replacement": "return text.strip()",
        },
        "raw-candidate",
    )


def test_llm_generator_runs_mainchain_with_nexus_armor_and_task_signals(
    monkeypatch, tmp_path: Path
):
    generator = LLMCandidateGenerator(
        tmp_path,
        safe_mode=True,
        route_signals={
            "should_research": True,
            "route_features": {"risk_score": 64, "local_reflex_provider": "ollama"},
            "recommended_flow": "hyper_sprint",
        },
    )
    monkeypatch.setattr(generator, "_workspace_revision", lambda: "revision-armor-001")
    monkeypatch.setattr(generator.gateway, "ask_structured", _approved)

    # Online admission may block in a hermetic test env; the route/plan facts are recorded
    # before the provider call either way.
    _out, _raw, receipt = generator._ask_unified_candidate(
        prompt="p", payload="x", task="fix normalize", seed=3, attempt=1, model="m"
    )

    route = receipt["context_trace"]["route"]
    assert route["with_nexus_armor"] is True
    assert route["mainchain_entry"] is True
    # forwarded route_features reach the executing CapabilityPlanner (forbidden keys dropped)
    assert receipt["plan_payload"]["signal_snapshot"]["risk_score_0_100"] == 64
