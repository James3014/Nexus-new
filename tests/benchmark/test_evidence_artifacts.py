from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.bench.evidence_artifacts import write_trial_evidence


def test_write_trial_evidence_writes_sanitized_files_and_hashes(tmp_path: Path):
    row = {"task_id": "task/with spaces", "mode": "with:nexus", "trial_index": "1", "ok": True}

    result = write_trial_evidence(
        evidence_root=tmp_path,
        row=row,
        target_before="old\n",
        target_after="new\n",
    )

    row_path = Path(result["evidence_record_file"])
    diff_path = Path(result["evidence_diff_file"])

    assert row_path.name == "with_nexus__task_with_spaces__trial_1.row.json"
    assert diff_path.name == "with_nexus__task_with_spaces__trial_1.target.diff"
    assert json.loads(row_path.read_text(encoding="utf-8")) == row
    assert "--- target.before" in diff_path.read_text(encoding="utf-8")
    assert "+++ target.after" in diff_path.read_text(encoding="utf-8")
    assert result["target_before_sha256"] == hashlib.sha256(b"old\n").hexdigest()
    assert result["target_after_sha256"] == hashlib.sha256(b"new\n").hexdigest()
    assert result["target_diff_sha256"] == hashlib.sha256(diff_path.read_bytes()).hexdigest()


def test_write_trial_evidence_treats_missing_targets_as_empty(tmp_path: Path):
    result = write_trial_evidence(
        evidence_root=tmp_path,
        row={"task_id": "task", "mode": "with_nexus"},
        target_before=None,
        target_after=None,
    )

    diff_path = Path(result["evidence_diff_file"])

    assert diff_path.read_text(encoding="utf-8") == ""
    assert result["target_before_sha256"] == hashlib.sha256(b"").hexdigest()
    assert result["target_after_sha256"] == hashlib.sha256(b"").hexdigest()
