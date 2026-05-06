from __future__ import annotations

from nexus.contracts.s2t_export import redact_s2t_event
from nexus.contracts.s2t_policy import S2TCandidate
from nexus.contracts.s2t_trace import S2TTraceEvent


def test_s2t_redaction_removes_secret_values_and_private_paths() -> None:
    event = S2TTraceEvent(
        task_id="task-1",
        run_id="run-1",
        model="gemini-3-flash-preview",
        mode="shadow",
        phase="R",
        risk_tier="high",
        candidate_set_id="candset-1",
        candidates=[
            S2TCandidate(
                candidate_id="A",
                source="repair_pass",
                content_ref=".nexus/reports/s2t/candidates/A.json",
                verifier_result="pass",
                evidence_refs=["tests/test_target.py"],
            )
        ],
        selected_candidate_id="A",
        verifier_result="pass",
        secret_values={"api_token": "secret-token"},
        private_paths=["/Users/jameschen/private.txt"],
    )

    redacted = redact_s2t_event(event)

    assert redacted["secret_values"] == {}
    assert redacted["private_paths"] == ["<redacted-path>"]
    assert redacted["candidates"][0]["content_ref"] == ".nexus/reports/s2t/candidates/A.json"
