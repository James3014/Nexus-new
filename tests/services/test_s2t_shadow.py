from __future__ import annotations

import json

from nexus.contracts.s2t_policy import S2TCandidate
from nexus.services.s2t_shadow import S2TShadowRecorder


def _candidates() -> list[S2TCandidate]:
    return [
        S2TCandidate(
            candidate_id="A",
            source="model_first_pass",
            content_ref=".nexus/reports/s2t/A.json",
            static_score=0.9,
            selector_score=0.95,
            verifier_result="fail",
            risk_flags=["missing_test_evidence"],
        ),
        S2TCandidate(
            candidate_id="B",
            source="repair_pass",
            content_ref=".nexus/reports/s2t/B.json",
            static_score=0.7,
            selector_score=0.75,
            verifier_result="pass",
            evidence_refs=["tests/test_target.py"],
        ),
    ]


def test_s2t_shadow_records_counterfactual_without_changing_final_delivery(tmp_path) -> None:
    trace_path = tmp_path / "s2t_trace.jsonl"
    recorder = S2TShadowRecorder(trace_path=trace_path)

    result = recorder.record(
        task_id="task-1",
        run_id="run-1",
        model="gemini-3-flash-preview",
        phase="R",
        risk_tier="high",
        candidate_set_id="candset-1",
        candidates=_candidates(),
        original_final_candidate_id="A",
        verifier_name="pytest",
        verifier_result="pass",
        verifier_evidence_ref=".nexus/reports/pytest.json",
    )

    row = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
    assert result.final_candidate_id == "A"
    assert result.counterfactual_candidate_id == "B"
    assert row["mode"] == "shadow"
    assert row["selected_candidate_id"] == "B"


def test_s2t_shadow_disabled_keeps_behavior_and_writes_no_trace(tmp_path) -> None:
    trace_path = tmp_path / "s2t_trace.jsonl"
    recorder = S2TShadowRecorder(trace_path=trace_path, enabled=False)

    result = recorder.record(
        task_id="task-1",
        run_id="run-1",
        model="gemini-3-flash-preview",
        phase="R",
        risk_tier="high",
        candidate_set_id="candset-1",
        candidates=_candidates(),
        original_final_candidate_id="A",
    )

    assert result.final_candidate_id == "A"
    assert result.counterfactual_candidate_id == ""
    assert result.trace_written is False
    assert not trace_path.exists()
