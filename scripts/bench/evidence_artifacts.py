from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
from typing import Any


def _safe_artifact_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_trial_evidence(
    *,
    evidence_root: Path,
    row: dict[str, Any],
    target_before: str | None,
    target_after: str | None,
) -> dict[str, str]:
    evidence_root.mkdir(parents=True, exist_ok=True)
    task_id = _safe_artifact_name(str(row.get("task_id", "task")))
    mode = _safe_artifact_name(str(row.get("mode", "mode")))
    trial = _safe_artifact_name(str(row.get("trial_index", "1")))
    stem = f"{mode}__{task_id}__trial_{trial}"
    row_path = evidence_root / f"{stem}.row.json"
    diff_path = evidence_root / f"{stem}.target.diff"

    row_path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
    before = target_before or ""
    after = target_after or ""
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="target.before",
            tofile="target.after",
        )
    )
    diff_path.write_text(diff, encoding="utf-8")
    return {
        "evidence_record_file": str(row_path),
        "evidence_diff_file": str(diff_path),
        "target_before_sha256": _sha256_text(before),
        "target_after_sha256": _sha256_text(after),
        "target_diff_sha256": _sha256_file(diff_path),
    }
