from __future__ import annotations

import json
import tempfile
from pathlib import Path
import pytest

from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
from nexus.services.local_heal.learning_closure_bridge import (
    LearningClosureBridge,
    write_candidate_learning_closures,
)


def test_write_candidate_learning_closures_writes_all_models() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "learning_closure.jsonl"
        bridge = LearningClosureBridge(path=path, enable_findings=False)

        c_judge = CandidateEnvelope(
            candidate_id="cand-judge",
            task_id="task-1",
            source="local",
            model="qwen-3b",
            role="judge",
            patch_protocol="none",
            target_file="app.py",
            target_symbol="run",
            source_anchor_hash="hash-1",
            candidate_patch_hash="hash-empty",
            evidence_refs=("ref-1",),
            candidate_patch="",
        )

        c_primary = CandidateEnvelope(
            candidate_id="cand-primary",
            task_id="task-1",
            source="local",
            model="qwen-7b",
            role="primary_proposer",
            patch_protocol="anchored_edit",
            target_file="app.py",
            target_symbol="run",
            source_anchor_hash="hash-1",
            candidate_patch_hash="hash-2",
            evidence_refs=("ref-1",),
            candidate_patch="print('hello')",
        )

        c_secondary = CandidateEnvelope(
            candidate_id="cand-secondary",
            task_id="task-1",
            source="local",
            model="ds-6.7b",
            role="secondary_proposer",
            patch_protocol="anchored_edit",
            target_file="app.py",
            target_symbol="run",
            source_anchor_hash="hash-1",
            candidate_patch_hash="hash-3",
            evidence_refs=("ref-1",),
            candidate_patch="print('world')",
        )

        ctx = {"task_id": "task-1", "instance_id": "task-1"}

        lessons = write_candidate_learning_closures(
            ctx=ctx,
            envelopes=[c_judge, c_primary, c_secondary],
            selected_id="cand-primary",
            selected_by="candidate_policy",
            verifier_result="pass",
            bridge=bridge,
        )

        assert len(lessons) == 3

        # Read back jsonl file
        with path.open("r", encoding="utf-8") as handle:
            lines = [json.loads(line) for line in handle]

        assert len(lines) == 3

        # 3B judge check
        judge_line = next(line for line in lines if line["model"] == "qwen-3b")
        assert judge_line["selected"] is False
        assert judge_line["selected_by"] == "none"
        assert judge_line["verifier_result"] == "not_run"
        assert judge_line["failure_class"] == "not_selected"

        # Primary proposer check
        primary_line = next(line for line in lines if line["model"] == "qwen-7b")
        assert primary_line["selected"] is True
        assert primary_line["selected_by"] == "candidate_policy"
        assert primary_line["verifier_result"] == "pass"
        assert primary_line["failure_class"] == "none"
        assert primary_line["future_weight_delta"] == 1.0
