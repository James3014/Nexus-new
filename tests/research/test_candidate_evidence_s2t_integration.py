from __future__ import annotations

import json
import subprocess
from pathlib import Path

from nexus.contracts.s2t_policy import S2TCandidate
from nexus.contracts.s2t_trace import S2TTraceEvent, S2TTraceWriter


def test_repository_s2t_trace_mirrors_candidates_as_trace_only(tmp_path: Path, monkeypatch) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    trace_path = tmp_path / ".nexus" / "reports" / "s2t" / "trace.jsonl"
    evidence_root = tmp_path / "candidate-evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(evidence_root))
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ENABLED", "1")
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_RATE_PERCENT", "100")
    event = S2TTraceEvent(
        task_id="s2t-task",
        run_id="run-1",
        model="advisor",
        mode="shadow",
        phase="R",
        risk_tier="high",
        candidate_set_id="set-1",
        candidates=[
            S2TCandidate(
                candidate_id="A",
                source="repair",
                content_ref="candidate:A",
                claimed_outcome="fix A",
                verifier_result="pass",
                evidence_refs=["tests/a.py"],
            ),
            S2TCandidate(
                candidate_id="B",
                source="repair",
                content_ref="candidate:B",
                claimed_outcome="fix B",
                verifier_result="fail",
            ),
        ],
        selected_candidate_id="A",
        verifier_name="existing-s2t-verifier",
        verifier_result="pass",
        verifier_evidence_ref="tests/a.py",
    )
    S2TTraceWriter(trace_path).append(event)

    assert trace_path.exists()
    group_dirs = list((evidence_root / "groups").glob("*"))
    assert len(group_dirs) == 1
    rows = [json.loads(path.read_text(encoding="utf-8")) for path in group_dirs[0].glob("*.json")]
    assert len(rows) == 2
    assert {row["label_quality"] for row in rows} == {"TRACE_ONLY"}
    assert all(row["dataset_eligible"] is False for row in rows)
    assert {row["verifier_status"] for row in rows} == {"PASS", "FAIL"}
