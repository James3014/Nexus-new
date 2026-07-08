from __future__ import annotations

from types import SimpleNamespace

from nexus.engine.capability_receipt_adapters import ClaimGateReceiptAdapter, DeliveryGateReceiptAdapter
from nexus.services.local_heal.claim_delivery_gate import ClaimDeliveryGate
from nexus.services.local_heal.learning_closure_bridge import LearningClosureBridge, write_learning_closure
from nexus.services.local_heal.memory_retrieval_adapter import MemoryRetrievalAdapter
from nexus.services.local_heal.reasoning_advisory_bridge import apply_autoreason_advisory, apply_belief_update
from nexus.services.local_heal.receipt import build_repair_receipt
from nexus.services.local_heal.semantic_anchor_selection import AnchorCandidate, SemanticAnchorScorer


class FakeLessonStore:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *, query_text: str, limit: int):
        return self.rows[:limit]


def candidate(name: str) -> AnchorCandidate:
    return AnchorCandidate(
        anchor_id=name,
        file_path="target.py",
        symbol_name=name,
        span_start=1,
        span_end=3,
        source_hash="abc123",
        candidate_type="target_symbol",
        source_text=f"def {name}():\n    return True\n",
    )


def test_memory_retrieval_rejects_fake_lesson_without_provenance():
    adapter = MemoryRetrievalAdapter(
        FakeLessonStore([{"lesson_id": "fake", "summary": "boost me", "classification": "verifier_pass"}])
    )
    lessons = adapter.retrieve(query_text="format output")
    assert lessons == []
    assert adapter.last_metadata["rejected_without_provenance"] == 1
    assert adapter.last_metadata["no_memory_match"] is True


def test_memory_success_and_failure_lessons_change_anchor_score():
    success = SemanticAnchorScorer(
        memory_adapter=MemoryRetrievalAdapter(
            FakeLessonStore(
                [{"lesson_id": "s1", "classification": "verifier_pass", "provenance": "receipt:s1", "relevance_score": 1.0}]
            )
        )
    ).score_candidate(candidate("format_output"), issue_keywords=["format"])

    failure = SemanticAnchorScorer(
        memory_adapter=MemoryRetrievalAdapter(
            FakeLessonStore(
                [{"lesson_id": "f1", "classification": "verifier_fail", "provenance": "receipt:f1", "relevance_score": 1.0}]
            )
        )
    ).score_candidate(candidate("format_output"), issue_keywords=["format"])

    assert success.score > failure.score
    assert any("memory_success_delta" in reason for reason in success.score_reasons)
    assert any("memory_failure_delta" in reason for reason in failure.score_reasons)


def test_no_memory_match_and_disabling_memory_are_recorded():
    enabled = SemanticAnchorScorer(memory_adapter=MemoryRetrievalAdapter(FakeLessonStore([]))).score_candidate(candidate("plain"))
    disabled_scorer = SemanticAnchorScorer(memory_enabled=False)
    disabled = disabled_scorer.score_candidate(candidate("plain"))
    assert "no_memory_match" in enabled.score_reasons
    assert disabled.memory_contribution["metadata"]["status"] == "disabled"
    assert disabled_scorer.scoring_metadata["plain"]["metadata"]["no_memory_match"] is True


def test_autoreason_advisory_is_recorded_but_cannot_override_verifier_or_owner_gate():
    ctx = SimpleNamespace(
        final_patch="diff --git a/x.py b/x.py",
        failure_reason="VERIFICATION_FAILED",
        problem_statement="repair regression",
        instance_id="C_12481",
        evidence_refs=["verification_report.txt"],
    )
    advisory = apply_autoreason_advisory(ctx)
    assert advisory["invoked"] is True
    assert advisory["receipt_bound"] is True
    assert advisory["cannot_override_verifier"] is True
    assert advisory["cannot_bypass_owner_gate"] is True


class FakeBelief:
    def __init__(self):
        self.saved = None

    def get_confidence(self, task_id, assumption=""):
        return 0.7

    def process_audit_outcome(self, outcome):
        self.saved = outcome
        return {"confidence": outcome.confidence}


def test_belief_trace_changes_after_verifier_pass_and_fail_without_override():
    passed = SimpleNamespace(instance_id="ok", solve_eligible=True, failure_reason="", receipt_path="receipt:ok")
    failed = SimpleNamespace(instance_id="bad", solve_eligible=False, failure_reason="VERIFICATION_FAILED", receipt_path="receipt:bad")
    pass_trace = apply_belief_update(passed, engine=FakeBelief())
    fail_trace = apply_belief_update(failed, engine=FakeBelief())
    assert pass_trace["belief_after"] > pass_trace["belief_before"]
    assert fail_trace["belief_after"] < fail_trace["belief_before"]
    assert fail_trace["cannot_override_verifier"] is True


def test_strict_claim_delivery_gate_rejects_fake_and_receipt_only_payloads():
    gate = ClaimDeliveryGate()
    fake = gate.validate(
        {
            "verifier_status": "pass",
            "patch_applied": True,
            "artifact_refs": ["claim:caller"],
        }
    )
    assert fake.claim_gate_passed is False
    assert "missing_verifier_artifact" in fake.reasons
    assert "missing_source_hash" in fake.reasons

    real = gate.validate(
        {
            "verifier_status": "pass",
            "verifier_artifact": "verification_report.txt",
            "source_hash": "sha256:abc",
            "candidate_target_file": "f.py",
            "patch_applied": True,
            "artifact_refs": ["patch.diff"],
        }
    )
    assert real.claim_gate_passed is True
    assert real.delivery_gate_passed is True


def test_capability_receipt_adapters_cannot_turn_fake_payload_into_success():
    payload = {"claim_refs": ["claim:caller"], "claim_gate_invoked": True, "claim_gate_passed": True}
    claim = ClaimGateReceiptAdapter().build(claim_verified=True, payload=payload)
    delivery = DeliveryGateReceiptAdapter().build(
        claim_verified=True,
        payload={"delivery_refs": ["delivery:caller"], "delivery_gate_passed": True},
    )
    assert claim.gate_passed is False
    assert delivery.gate_passed is False
    assert "missing_verifier_artifact" in claim.failure_reason
    assert "missing_source_hash" in delivery.failure_reason


def test_learning_closure_writeback_internal_only_and_non_blocking(tmp_path):
    ctx = SimpleNamespace(instance_id="C_13453", solve_eligible=False, failure_reason="owner_gated", receipt_path="receipt:1")
    result = write_learning_closure(ctx, bridge=LearningClosureBridge(tmp_path / "learning.jsonl"))
    assert result["writeback_status"] == "ok"
    assert result["lesson"]["classification"] == "owner_gated"
    assert result["lesson"]["training_export_allowed"] is False

    class BrokenBridge:
        def write_lesson(self, ctx):
            raise OSError("disk")

    failed = write_learning_closure(ctx, bridge=BrokenBridge())
    assert failed["writeback_status"] == "failed_non_blocking"
    assert failed["training_export_allowed"] is False


def test_repair_receipt_records_capability_wiring_and_internal_boundaries():
    ctx = SimpleNamespace(
        instance_id="C_12481",
        solve_eligible=True,
        runner_completed=True,
        reproduced=True,
        final_patch="diff --git a/x.py b/x.py",
        evaluation_report="[PASS]",
        hidden_verifier_required=False,
        hidden_verifier_passed=False,
        failure_reason="",
        errors=[],
        repro_script="reproduce_bug.py",
        python_executable="python3",
        env_resolution={"ready": True},
        env_denoise={},
        model_decisions=[],
        wall_time_sec=1.0,
        token_telemetry_status="not_applicable",
        token_total_estimated=0,
        syntax_gate_passed=True,
        expected_stop_layer="verification",
        expected_reason_family="SOLVED",
        _latency_ledger=None,
        _autoreason_advisory={"invoked": True, "no_override": True},
        _belief_trace={"belief_before": 0.7, "belief_after": 0.9, "uncertainty_delta": -0.2},
        _claim_delivery_gate={"claim_gate_passed": True, "delivery_gate_passed": True},
        _learning_closure={"writeback_status": "ok"},
    )
    receipt = build_repair_receipt(ctx)
    assert receipt["claim_eligible"] is True
    assert receipt["public_claim_allowed"] is False
    assert receipt["production_ready"] is False
    assert receipt["training_export_allowed"] is False
    assert receipt["internal_only"] is True
    assert receipt["telemetries"]["autoreason_advisory"]["invoked"] is True
    assert receipt["telemetries"]["belief_trace"]["belief_after"] == 0.9
    assert receipt["telemetries"]["claim_delivery_gate"]["claim_gate_passed"] is True


def test_repair_receipt_without_claim_delivery_gate_is_not_claim_eligible():
    ctx = SimpleNamespace(
        instance_id="C_12481",
        solve_eligible=True,
        runner_completed=True,
        reproduced=True,
        final_patch="diff --git a/x.py b/x.py",
        evaluation_report="[PASS]",
        hidden_verifier_required=False,
        hidden_verifier_passed=False,
        failure_reason="",
        errors=[],
        repro_script="reproduce_bug.py",
        python_executable="python3",
        env_resolution={"ready": True},
        env_denoise={},
        model_decisions=[],
        wall_time_sec=1.0,
        token_telemetry_status="not_applicable",
        token_total_estimated=0,
        syntax_gate_passed=True,
        expected_stop_layer="verification",
        expected_reason_family="SOLVED",
        _latency_ledger=None,
    )
    receipt = build_repair_receipt(ctx)
    assert receipt["claim_eligible"] is False


def test_route_planner_diagnostics_confidence():
    from nexus.research.domain.route_planner import RoutePlanner
    r1 = RoutePlanner.plan_route("C_12481", "using migrations and db_table")
    assert r1.confidence_score == 0.99
    assert r1.diagnose_overcall is False
    assert r1.diagnose_undercall is False

    r2 = RoutePlanner.plan_route("C_12481", "plain test without keywords")
    assert r2.confidence_score == 0.5
    assert r2.diagnose_overcall is True
    assert r2.diagnose_undercall is True


def test_context_guard_noise_filtering():
    from nexus.services.local_heal.context_guard import ContextGuard, LocalizedFile
    guard = ContextGuard()
    files = [
        LocalizedFile(path="a.py", content="too_short"), # len < 15, should be filtered
        LocalizedFile(path="b.py", content="class GoodFile:\n    pass\n"), # len >= 15, keep
    ]
    res = guard.limit_localized_files(files, max_files=3, max_total_chars=1000)
    assert len(res) == 1
    assert res[0].path == "b.py"

