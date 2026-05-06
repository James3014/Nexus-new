from __future__ import annotations

import json

from nexus.contracts.s2t_policy import S2TCandidate
from nexus.contracts.s2t_trace import S2TTraceEvent, S2TTraceWriter


def _event(task_id: str) -> S2TTraceEvent:
    return S2TTraceEvent(
        task_id=task_id,
        run_id="run-1",
        model="gemini-3-flash-preview",
        mode="shadow",
        phase="R",
        risk_tier="high",
        candidate_set_id=f"{task_id}-candidates",
        candidates=[
            S2TCandidate(
                candidate_id="A",
                source="repair_pass",
                content_ref=".nexus/reports/s2t/A.json",
                verifier_result="pass",
                evidence_refs=["tests/test_target.py"],
            )
        ],
        selected_candidate_id="A",
        verifier_result="pass",
    )


def test_s2t_trace_writer_appends_multiple_events(tmp_path) -> None:
    path = tmp_path / "trace.jsonl"
    writer = S2TTraceWriter(path)

    writer.append(_event("task-1"))
    writer.append(_event("task-2"))

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["task_id"] for row in rows] == ["task-1", "task-2"]
