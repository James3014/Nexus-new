from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nexus.engine.completion_enforcer import enforce_completion


def build_completion_envelope(
    *,
    command_name: str,
    task_name: str,
    runtime_ok: bool,
    execution_path: str,
    artifact_paths: list[str] | None = None,
    evidence_paths: list[str] | None = None,
    gate_verdict: dict[str, Any] | None = None,
    tests_run: list[dict[str, Any]] | None = None,
    rollback_triggered: bool = False,
    rollback_evidence: list[str] | None = None,
    semantic_failures: list[str] | None = None,
    semantic_status: str | None = None,
    runtime_classification: str | None = None,
    retryable: bool | None = None,
    blocker_type: str | None = None,
    next_action: str | None = None,
) -> dict[str, Any]:
    artifacts = [str(path) for path in (artifact_paths or [])]
    evidence = [str(path) for path in (evidence_paths or [])]
    tests = list(tests_run or [])
    failures = list(semantic_failures or [])

    if not runtime_ok and "runtime_execution_failed" not in failures:
        failures.append("runtime_execution_failed")

    if semantic_status is None:
        if not failures:
            semantic_status = "VERIFIED"
        elif retryable is False:
            semantic_status = "BLOCKED"
        else:
            semantic_status = "UNVERIFIED"

    if blocker_type is None:
        if semantic_status == "VERIFIED":
            blocker_type = "none"
        elif not runtime_ok:
            blocker_type = "runtime_defect"
        else:
            blocker_type = "semantic_incomplete"

    if retryable is None:
        retryable = semantic_status not in {"VERIFIED", "BLOCKED", "REJECTED"}

    if next_action is None:
        if semantic_status == "VERIFIED":
            next_action = "none"
        elif retryable:
            next_action = "retry_repair"
        elif blocker_type == "governance":
            next_action = "stop"
        else:
            next_action = "escalate_to_human"

    if runtime_classification is None:
        if semantic_status == "VERIFIED":
            runtime_classification = "verified_pass"
        elif blocker_type == "governance":
            runtime_classification = "governance_state_block"
        elif not runtime_ok:
            runtime_classification = "runtime_defect"
        else:
            runtime_classification = "semantic_incomplete"

    return {
        "command_name": command_name,
        "task_name": task_name,
        "status": "SUCCESS" if runtime_ok else "FAILED",
        "runtime_classification": runtime_classification,
        "semantic_status": semantic_status,
        "semantic_failures": failures,
        "retryable": retryable,
        "blocker_type": blocker_type,
        "next_action": next_action,
        "gate_verdict": dict(gate_verdict or {}),
        "artifact_paths": artifacts,
        "evidence_paths": evidence,
        "rollback_triggered": bool(rollback_triggered),
        "rollback_evidence": list(rollback_evidence or []),
        "execution_path": execution_path,
        "tests_run": tests,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def write_completion_envelope(project_root: Path, output_path: str | Path, payload: dict[str, Any]) -> Path:
    out = Path(output_path)
    if not out.is_absolute():
        out = (project_root / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    import json

    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def ensure_verified_completion(payload: dict[str, Any], *, context: str) -> None:
    enforce_completion(payload, context=context)
