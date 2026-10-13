from __future__ import annotations

from nexus.app.research_receipt_runtime import build_capability_receipt_payloads, runtime_receipt_plan_payload


def test_runtime_receipt_plan_prunes_unexecuted_autoreason_and_judge_panel():
    capabilities = {}
    plan = runtime_receipt_plan_payload(
        {"selected_capabilities": ["hyper_sprint", "autoreason", "judge_panel", "llm_judge_panel", "formal_report"]},
        {
            "capabilities": capabilities,
            "autoreason": {"status": "SKIPPED", "stop_reason": "candidate_factory_skipped", "judge_votes": []},
        },
    )

    assert plan["selected_capabilities"] == ["hyper_sprint", "formal_report"]
    assert capabilities["runtime_pruned_capabilities"] == {
        "autoreason": "candidate_factory_skipped",
        "judge_panel": "candidate_factory_skipped",
        "llm_judge_panel": "candidate_factory_skipped",
    }


def test_runtime_receipt_plan_adds_runtime_autoreason_success():
    plan = runtime_receipt_plan_payload(
        {"selected_capabilities": ["hyper"]},
        {
            "capabilities": {"claim_verified": True},
            "autoreason": {
                "enabled": True,
                "status": "SUCCESS",
                "winner": "AB",
                "judge_votes": [{"judge": "deterministic", "ranking": ["AB", "B", "A"]}],
            },
        },
    )

    assert "autoreason" in plan["selected_capabilities"]


def test_build_capability_receipt_payloads_marks_runtime_autoreason_safe(tmp_path):
    """Contract: the runtime autoreason receipt is added and evidenced, but stays fail-closed (#453)."""
    evidence = _real_verifier_evidence(tmp_path)
    receipts = build_capability_receipt_payloads(
        {"selected_capabilities": ["hyper"]},
        {
            "capabilities": {"claim_verified": True, **evidence},
            "autoreason": {
                "enabled": True,
                "status": "SUCCESS",
                "winner": "AB",
                "judge_votes": [{"judge": "deterministic", "ranking": ["AB", "B", "A"]}],
                **evidence,
            },
            "ddtree": {},
            "ultra_review": {},
            "codeintel": {},
        },
    )

    by_name = {item["name"]: item for item in receipts}
    _assert_receipt_held_fail_closed(by_name["autoreason"])
    assert by_name["autoreason"]["telemetries"]["telemetry_source"] == "measured"
    assert by_name["autoreason"]["evidence_refs"]


def test_build_capability_receipt_payloads_preserves_runtime_repair_loop_receipt(tmp_path):
    """Contract: the runtime repair_loop receipt keeps its trace evidence and stays fail-closed (#453)."""
    receipts = build_capability_receipt_payloads(
        {"selected_capabilities": ["repair_loop"]},
        {
            "capabilities": {
                "claim_verified": True,
                "rlm_trace_present": True,
                "rlm_trace_path": ".nexus/reports/rlm/trace.jsonl",
                **_real_verifier_evidence(tmp_path),
            },
        },
    )

    by_name = {item["name"]: item for item in receipts}
    _assert_receipt_held_fail_closed(by_name["repair_loop"])
    assert by_name["repair_loop"]["evidence_refs"] == [".nexus/reports/rlm/trace.jsonl"]


def test_hyper_runtime_usage_backfill_is_marked_as_supporting_flow(tmp_path):
    """Contract: runtime hyper usage is backfilled as a supporting flow and stays fail-closed (#453)."""
    capabilities = {
        "claim_verified": True,
        "hyper_used": True,
        "winner_source": "hyper_sprint",
        "attempt_count": 1,
        **_real_verifier_evidence(tmp_path),
    }
    receipts = build_capability_receipt_payloads(
        {"selected_capabilities": ["delivery_gate"]},
        {"capabilities": capabilities},
    )

    by_name = {item["name"]: item for item in receipts}
    assert by_name["hyper"]["invoked"] is True
    _assert_receipt_held_fail_closed(by_name["hyper"])
    assert by_name["hyper"]["selection_source"] == "supporting_flow_forced_hyper_sprint"
    assert capabilities["runtime_supporting_capabilities"] == {
        "hyper": "runtime_flow_used_without_route_oracle_expectation"
    }


def _real_verifier_evidence(tmp_path) -> dict:
    """Evidence the current receipt contract asks for (#453, #1757).

    Runs a real verifier over a real source file and returns its result, the sha256 of the
    verifier artifact, the source hash and telemetry measured around the run.
    """
    import hashlib
    import subprocess
    import sys
    import time

    source = tmp_path / "target_under_verifier.py"
    source.write_text("VALUE = 2\n", encoding="utf-8")
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-c", "import ast, sys; ast.parse(open(sys.argv[1]).read())", str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    wall_time_ms = max(1, int((time.perf_counter() - started) * 1000))
    artifact = tmp_path / "verifier.log"
    artifact.write_text(f"returncode={proc.returncode}\n{proc.stdout}{proc.stderr}", encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return {
        "verifier_status": "pass",
        "verifier_artifact": "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "source_hash": "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest(),
        "telemetries": {
            "telemetry_source": "measured",
            "wall_time_ms": wall_time_ms,
            "token_usage": 0,
            "provider_costs": 0.0,
            "overhead_ms": 0,
            "model_calls": 0,
        },
    }


def _assert_receipt_held_fail_closed(receipt: dict) -> None:
    """Contract (#453 ADVISORY_ONLY_FAIL_CLOSED): a generic adapter payload cannot mint verifier
    authority. The receipt keeps its invocation, evidence and gate pass, but it never contributes
    an outcome and is never public_claim_safe until an authenticated upstream verifier authority
    is bound."""
    assert receipt["selected"] is True
    assert receipt["invoked"] is True
    assert receipt["evidence_present"] is True
    assert receipt["gate_passed"] is True
    assert receipt["failure_reason"] == ""
    assert receipt["outcome_contributed"] is False
    assert receipt["public_claim_safe"] is False
