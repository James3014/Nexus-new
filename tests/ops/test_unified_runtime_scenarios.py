from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

from nexus.engine.capability_planner import CapabilityPlanner
from scripts.ops.unified_runtime_scenarios import run_scenario, run_scenario_matrix


def _args(scenario: str, *, live: bool = False) -> Namespace:
    return Namespace(
        scenario=scenario,
        task_group_id="scenario-test",
        task_statement="Reply exactly OK",
        workspace_revision="revision-test",
        provider="grok",
        command=None,
        project_root=".",
        timeout_sec=1.0,
        receipt_path=None,
        live=live,
    )


def test_scenarios_fail_closed_without_live_flag(monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    monkeypatch.delenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", raising=False)

    for scenario in ("A", "B", "C", "D"):
        report = run_scenario(_args(scenario))
        assert report["terminal_status"] == "AUTHORIZATION_REQUIRED_NOT_RUN"
        assert report["receipt_complete"] is False
        assert report["provider_call_count"] == 0


def test_external_scenarios_require_both_live_and_external_authorization(monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    monkeypatch.delenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", raising=False)

    report = run_scenario(_args("A", live=True))
    assert report["terminal_status"] == "AUTHORIZATION_REQUIRED_NOT_RUN"
    assert "NEXUS_EXTERNAL_RUNTIME_AUTHORIZED" in report["reason"]

    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    args = _args("B", live=True)
    args.command = (sys.executable, "-c", "print('bounded provider output')")
    hybrid = run_scenario(args)
    assert hybrid["terminal_status"] == "AUTHORIZATION_REQUIRED_NOT_RUN"
    assert "NEXUS_LOCAL_MODEL_CALL_ALLOWED" in hybrid["reason"]

    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    control = run_scenario(_args("D", live=True))
    assert control["terminal_status"] == "AUTHORIZATION_REQUIRED_NOT_RUN"
    assert "NEXUS_EXTERNAL_RUNTIME_AUTHORIZED" in control["reason"]


def test_all_scenario_matrix_preserves_fail_closed_rows(monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    monkeypatch.delenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", raising=False)

    matrix = run_scenario_matrix(_args("ALL"))

    assert matrix["schema"] == "nexus.unified_runtime.scenario_matrix.v1"
    assert [row["scenario"] for row in matrix["comparison"]] == ["A", "B", "C", "D"]
    assert matrix["terminal_status"] == "INCOMPLETE"
    assert matrix["receipt_complete"] is False
    assert matrix["claim_boundary"]["same_task_group"] is True
    assert matrix["claim_boundary"]["same_task_statement"] is True
    assert matrix["claim_boundary"]["same_workspace_revision"] is True
    assert matrix["capability_gate"]["status"] == "CAPABILITY_LIVE_GATE_OPEN"
    assert matrix["capability_gate"]["live_provider_evidence"] == "UNVERIFIED"
    assert all(row["provider_call_count"] == 0 for row in matrix["comparison"])


def test_nexus_online_control_uses_canonical_receipt_with_injected_command(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    args = _args("D", live=True)
    args.command = (sys.executable, "-c", "print('D_CONTROL_OK')")
    args.project_root = str(tmp_path)

    report = run_scenario(args)

    assert report["terminal_status"] == "SUCCEEDED"
    assert report["receipt_complete"] is True
    assert report["claim_boundary"]["value_measured"] is True
    assert report["provider_call_count"] == 1
    assert report["unified_receipt"]["local"]["status"] == "NOT_REQUESTED"
    assert report["unified_receipt"]["online"]["task_id"] == report["task_id"]
    online_delegations = [
        item for item in report["unified_receipt"]["capabilities"]
        if item["delegated_to"] == "Online"
    ]
    assert online_delegations
    assert all(item["task_id"] == report["task_id"] for item in online_delegations)


def test_hybrid_route_authorizes_local_capability_edges() -> None:
    route = {
        "recommended_flow": "hybrid",
        "route_decision": {
            "selected_capabilities": ["memory", "semantic_searcher", "codeintel", "prompt_compression"],
        },
        "prompt_compression": True,
        "target_file": "nexus/services/unified_runtime.py",
        "route_features": {"memory_hits": 1, "findings_hits": 1},
    }
    plan = CapabilityPlanner().plan(
        task_desc="Reply exactly OK",
        task_type="repair",
        route=route,
    )

    assert set(("memory", "semantic_searcher", "codeintel", "prompt_compression")) <= set(plan.selected_capabilities)


def test_hybrid_harness_executes_local_capabilities_before_online(monkeypatch) -> None:
    class _FakeLocalAssist:
        def handle(self, request):
            return {
                "task_id": request.task_id,
                "local_model_invoked": True,
                "output_delivered": True,
                "evidence_refs": [f"local:{request.task_id}:fixture"],
                "response": {"local_outputs": {"answer": "LOCAL_FIXTURE_OK"}},
            }

    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_NAME", "qwen2.5-coder:7b")
    monkeypatch.setattr("scripts.ops.unified_runtime_scenarios._ollama_endpoint_available", lambda: True)
    monkeypatch.setattr("nexus.services.local_assist_service.LocalAssistService", _FakeLocalAssist)

    args = _args("B", live=True)
    args.command = (sys.executable, "-c", "print('ONLINE_FIXTURE_OK')")
    args.project_root = str(Path(__file__).resolve().parents[2])
    report = run_scenario(args)

    assert report["terminal_status"] == "SUCCEEDED"
    assert report["receipt_complete"] is True
    receipt = report["unified_receipt"]
    capability_results = receipt["capability_results"]
    assert all(capability_results[name]["status"] == "SUCCEEDED" for name in (
        "memory", "semantic_searcher", "codeintel", "prompt_compression",
    ))
    assert report["capability_runtime_complete"] is True
    assert report["capability_online_forwarded"] is True
    assert all(report["capability_edges"][name]["delegated_to"] == "Local" for name in (
        "memory", "semantic_searcher", "codeintel", "prompt_compression",
    ))
    assert receipt["context_trace"]["task_id"] == report["task_id"]
    assert receipt["context_trace"]["online_received_context"]["capability_context_forwarded"] is True
    assert receipt["context_trace"]["online_received_context"]["compressed_context_applied"] is True
    assert "online:grok:scenario-test-b:compressed_context_applied" in receipt["online"]["evidence_refs"]


def test_nexus_scenario_fails_closed_without_revision_in_non_git_root(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    args = _args("D", live=True)
    args.command = (sys.executable, "-c", "print('should not run')")
    args.project_root = str(tmp_path)
    args.workspace_revision = "live-revision-unrecorded"

    report = run_scenario(args)

    assert report["terminal_status"] == "EVIDENCE_PRECONDITION_NOT_MET"
    assert report["reason"] == "workspace_revision_required"
    assert report["provider_call_count"] == 0


def test_hybrid_scenario_requires_explicit_ollama_model_configuration(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.delenv("NEXUS_LOCAL_MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER", raising=False)
    monkeypatch.delenv("NEXUS_LOCAL_MODEL_NAME", raising=False)

    report = run_scenario(_args("B", live=True))

    assert report["terminal_status"] == "EVIDENCE_PRECONDITION_NOT_MET"
    assert report["reason"] == "local_provider_ollama_required"
    assert report["provider_call_count"] == 0

    monkeypatch.setenv("NEXUS_LOCAL_MODEL_PROVIDER", "ollama")
    report = run_scenario(_args("B", live=True))
    assert report["terminal_status"] == "EVIDENCE_PRECONDITION_NOT_MET"
    assert report["reason"] == "local_model_name_required"
    assert report["provider_call_count"] == 0


def test_hybrid_scenario_fails_closed_when_ollama_endpoint_is_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_NAME", "qwen2.5-coder:7b")
    monkeypatch.setattr(
        "scripts.ops.unified_runtime_scenarios.urllib.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("endpoint unavailable")),
    )

    report = run_scenario(_args("C", live=True))

    assert report["terminal_status"] == "EVIDENCE_PRECONDITION_NOT_MET"
    assert report["reason"] == "ollama_endpoint_unavailable"
    assert report["provider_call_count"] == 0
