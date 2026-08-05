from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.engine.capability_planner import CapabilityPlanner
from nexus.services.local_assist_service import LocalAssistService
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider
from scripts.ops import unified_runtime_scenarios as scenarios
from scripts.ops.unified_runtime_scenarios import run_scenario, run_scenario_matrix


_PATCH = (
    "--- a/scenario_task.py\n"
    "+++ b/scenario_task.py\n"
    "@@ -1,2 +1,2 @@\n"
    " def scenario_response():\n"
    "-    return 'NOT_COMPLETED'\n"
    "+    return 'NEXUS_RUNTIME_VERIFIED'\n"
)


def _args(scenario: str, *, live: bool = False) -> Namespace:
    # Deliberately omit run_root: old programmatic Namespace callers remain valid.
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


def _enable_local_fixture(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_NAME", "qwen2.5-coder:7b-instruct")
    monkeypatch.setattr(scenarios, "_ollama_endpoint_available", lambda: True)
    monkeypatch.setattr(
        scenarios,
        "_build_local_service",
        lambda run_root: LocalAssistService(
            provider=InjectedLocalModelProvider(
                lambda _: _PATCH,
                provider_identity="ollama",
                model_identity="qwen2.5-coder:7b-instruct",
            ),
            apply_runner=scenarios._isolated_apply_runner(run_root),
        ),
    )


def _tracked_nexus_hashes(repo_root: Path) -> dict[str, str]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z", "--", ".nexus"],
        cwd=repo_root,
    )
    paths = [item.decode("utf-8") for item in output.split(b"\0") if item]
    return {
        path: hashlib.sha256((repo_root / path).read_bytes()).hexdigest()
        for path in paths
        if (repo_root / path).is_file()
    }


def test_agy_invoker_passes_dynamic_prompt_as_print_argument(monkeypatch, tmp_path) -> None:
    agy = tmp_path / "agy"
    agy.write_text("fixture", encoding="utf-8")
    agy.chmod(0o755)
    monkeypatch.setenv("NEXUS_AGY_BIN", str(agy))
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="NEXUS_V3_ONLINE_OK\n", stderr="")

    invoker = scenarios._build_agy_online_invoker(
        timeout_sec=5,
        include_local_context=False,
        runner=runner,
    )
    response = invoker(
        {
            "task_id": "agy-bounded",
            "online_prompt": "Reply with exactly: NEXUS_V3_ONLINE_OK",
        }
    )

    assert calls[0][0] == [
        str(agy),
        "--dangerously-skip-permissions",
        "--print",
        "Reply with exactly: NEXUS_V3_ONLINE_OK",
    ]
    assert calls[0][1]["input"] is None
    assert response["gate_passed"] is True


@pytest.mark.parametrize(
    ("case", "expected_blocker"),
    (
        ("unavailable", "online_provider_call_missing"),
        ("timeout", "online_output_not_delivered"),
        ("wrong_answer", "online_response_not_exact"),
    ),
)
def test_agy_negative_controls_fail_closed(
    monkeypatch,
    tmp_path,
    case,
    expected_blocker,
) -> None:
    agy = tmp_path / "agy"
    if case != "unavailable":
        agy.write_text("fixture", encoding="utf-8")
        agy.chmod(0o755)
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setenv("NEXUS_AGY_BIN", str(agy))

    def runner(_argv, **_kwargs):
        if case == "timeout":
            raise subprocess.TimeoutExpired(cmd="agy", timeout=1)
        return SimpleNamespace(returncode=0, stdout="WRONG_ANSWER\n", stderr="")

    invoker = scenarios._build_agy_online_invoker(
        timeout_sec=1,
        include_local_context=False,
        runner=runner,
    )
    monkeypatch.setattr(
        scenarios,
        "_build_agy_online_invoker",
        lambda **_kwargs: invoker,
    )
    args = _args("D", live=True)
    args.provider = "agy"
    args.project_root = str(tmp_path)
    args.run_root = str(tmp_path / "runs")
    args.task_statement = "Reply with exactly: EXPECTED_ANSWER"

    report = run_scenario(args)

    assert report["terminal_status"] == "INCOMPLETE"
    assert report["receipt_complete"] is False
    verifier = report["unified_receipt"]["verifier"]["response"]
    assert expected_blocker in verifier["blockers"]
    assert Path(verifier["verifier_artifact_path"]).is_file()
    for gate_name in ("artifact_gate", "claim_gate", "delivery_gate"):
        assert report["unified_receipt"]["capability_results"][gate_name]["status"] == "FAILED"


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
    args.run_root = str(tmp_path / "runs")

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
    receipt_path = Path(report["unified_receipt_path"])
    artifact_path = Path(
        report["unified_receipt"]["verifier"]["response"]["verifier_artifact_path"]
    )
    assert receipt_path.is_file()
    assert artifact_path.is_file()
    assert receipt_path.is_relative_to(Path(report["run_root"]))
    assert artifact_path.is_relative_to(Path(report["run_root"]))
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    for key in ("online_request_path", "online_stdout_path", "online_stderr_path"):
        evidence_path = Path(artifact[key])
        assert evidence_path.is_file()
        assert evidence_path.is_relative_to(Path(report["run_root"]))
    assert artifact["online_provider"] == "agy"
    assert (
        report["unified_receipt"]["gateway_invocation_authority"]["resolved_provider"]
        == "agy"
    )
    assert artifact["online_response_hash"] == hashlib.sha256(
        Path(artifact["online_stdout_path"]).read_bytes()
    ).hexdigest()


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


def test_hybrid_harness_executes_verified_subtask_before_online(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    _enable_local_fixture(monkeypatch)

    args = _args("B", live=True)
    args.command = (sys.executable, "-c", "print('ONLINE_FIXTURE_OK')")
    args.project_root = str(Path(__file__).resolve().parents[2])
    args.run_root = str(tmp_path / "runs")
    report = run_scenario(args)

    assert report["terminal_status"] == "SUCCEEDED"
    assert report["receipt_complete"] is True
    receipt = report["unified_receipt"]
    local = receipt["local"]["response"]
    assert local["action"] == "verified-subtask"
    assert local["physical_callable"] == "LocalModelExecutor.run"
    assert local["executor_invoked"] is True
    assert local["candidate_summary"]["isolation_status"] == "isolated"
    assert local["candidate_summary"]["selected_candidate_hash_matches_applied"] is True
    assert local["verifier_summary"]["verifier_status"] == "pass"
    assert local["verifier_summary"]["exit_code"] == 0
    assert Path(local["receipt_path"]).is_file()
    assert Path(local["receipt_path"]).is_relative_to(Path(report["run_root"]))
    assert (Path(report["task_workspace"]) / "scenario_task.py").read_text(
        encoding="utf-8"
    ) == "def scenario_response():\n    return 'NOT_COMPLETED'\n"
    capability_results = receipt["capability_results"]
    # Only CapabilityPlanner-selected capabilities execute. The scenario's
    # old caller-supplied route_decision no longer forces extra local edges.
    expected_local_capabilities = {"memory", "repair_loop"}
    assert expected_local_capabilities.issubset(capability_results), ",".join(
        sorted(capability_results)
    )
    assert all(
        capability_results[name]["status"] == "SUCCEEDED"
        for name in expected_local_capabilities
    )
    assert report["capability_runtime_complete"] is True
    assert report["capability_online_forwarded"] is True
    selected_edges = [
        edge for edge in report["capability_edges"].values() if edge["selected"]
    ]
    assert selected_edges
    assert all(edge["delegated_to"] == "Local" for edge in selected_edges)
    assert receipt["context_trace"]["task_id"] == report["task_id"]
    assert receipt["context_trace"]["online_received_context"]["capability_context_forwarded"] is True
    assert receipt["context_trace"]["online_received_context"]["compressed_context_applied"] is False
    assert (
        "online:agy:scenario-test-b:capability_context_forwarded"
        in receipt["online"]["evidence_refs"]
    )

    verifier = receipt["verifier"]["response"]
    artifact_path = Path(verifier["verifier_artifact_path"])
    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact_payload["status"] == "PASS"
    assert verifier["verifier_artifact"] == (
        "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    )
    assert verifier["candidate_hash"] == local["candidate_summary"]["selected_candidate_hash"]
    assert verifier["source_hash"] == receipt["capability_evidence_bundle"]["source_hash"]
    for gate_name in ("artifact_gate", "claim_gate", "delivery_gate"):
        gate = capability_results[gate_name]
        proof = gate["response"]["response"]["proof"]
        assert gate["status"] == "SUCCEEDED"
        assert proof["verifier_status"] == "pass"
        assert proof["source_hash"] == verifier["source_hash"]
        assert proof["verifier_artifact"] == verifier["verifier_artifact"]
        assert proof["candidate_hash"] == verifier["candidate_hash"]

    learning = receipt["learning"]["response"]
    assert learning["readback"]["phases"] == ["A", "C", "D", "P", "R", "X"]
    assert Path(learning["evidence_refs"][1]).is_file()
    assert Path(learning["evidence_refs"][2]).is_file()


def test_declarative_local_success_without_physical_evidence_fails_closed(
    monkeypatch, tmp_path
) -> None:
    class _DeclarativeLocalAssist:
        def handle(self, request):
            return {
                "task_id": request.task_id,
                "action": "verified-subtask",
                "local_model_invoked": True,
                "executor_invoked": True,
                "physical_callable": "LocalModelExecutor.run",
                "output_delivered": True,
                "candidate_summary": {
                    "isolation_status": "isolated",
                    "selected_candidate_hash": "a" * 64,
                    "applied_patch_hash": "a" * 64,
                    "selected_candidate_hash_matches_applied": True,
                },
                "verifier_summary": {
                    "verifier_reached": True,
                    "verifier_status": "pass",
                    "exit_code": 0,
                },
                "receipt_path": "",
                "evidence_refs": [f"local:{request.task_id}:declarative"],
            }

    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    _enable_local_fixture(monkeypatch)
    monkeypatch.setattr(
        scenarios,
        "_build_local_service",
        lambda _run_root: _DeclarativeLocalAssist(),
    )
    args = _args("B", live=True)
    args.command = (sys.executable, "-c", "print('ONLINE_FIXTURE_OK')")
    args.project_root = str(Path(__file__).resolve().parents[2])
    args.run_root = str(tmp_path / "runs")

    report = run_scenario(args)

    assert report["terminal_status"] == "INCOMPLETE"
    verifier = report["unified_receipt"]["verifier"]["response"]
    assert verifier["gate_passed"] is False
    assert "local_receipt_outside_run_root" in verifier["blockers"]
    assert "local_disk_receipt_incomplete" in verifier["blockers"]
    assert "candidate_not_isolated_in_run_root" in verifier["blockers"]
    for gate_name in ("artifact_gate", "claim_gate", "delivery_gate"):
        assert report["unified_receipt"]["capability_results"][gate_name]["status"] == "FAILED"


def test_run_root_prevents_tracked_nexus_artifact_pollution(monkeypatch, tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    before = _tracked_nexus_hashes(repo_root)
    _enable_local_fixture(monkeypatch)
    args = _args("C", live=True)
    args.project_root = str(repo_root)
    args.run_root = str(tmp_path / "runs")

    report = run_scenario(args)

    assert report["terminal_status"] == "SUCCEEDED"
    assert report["provider_call_count"] == 1
    assert report["online_provider_call_count"] == 0
    assert report["local_provider_call_count"] == 1
    assert _tracked_nexus_hashes(repo_root) == before
    run_root = Path(report["run_root"])
    isolated = Path(
        report["unified_receipt"]["local"]["response"]["candidate_summary"][
            "isolated_workspace"
        ]
    )
    assert isolated.is_relative_to(run_root)
    assert Path(report["unified_receipt_path"]).is_relative_to(run_root)


def test_cli_accepts_run_root_without_invoking_provider(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", raising=False)
    receipt_path = tmp_path / "authorization-receipt.json"
    run_root = tmp_path / "runs"

    exit_code = scenarios.main(
        [
            "--scenario",
            "C",
            "--project-root",
            str(tmp_path),
            "--run-root",
            str(run_root),
            "--receipt-path",
            str(receipt_path),
        ]
    )

    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["terminal_status"] == "AUTHORIZATION_REQUIRED_NOT_RUN"


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
