"""Compatibility shims for ops modules with lightweight public contracts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType


def _count_changed_files(project_root: Path) -> int:
    result = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 0
    return len([line for line in result.stdout.splitlines() if line.strip()])


def _run_anti_drift_gate(project_root: Path, policy: dict, report_path: Path) -> dict:
    historical_tests = policy.get("historical_tests", [])
    passed = 0
    results = []
    for test in historical_tests:
        command = str(test.get("command", "")).strip()
        result = subprocess.run(command, cwd=project_root, shell=True, capture_output=True, text=True)
        ok = result.returncode == 0
        passed += int(ok)
        results.append({"name": test.get("name", command), "passed": ok})

    total = len(historical_tests)
    pass_rate = passed / total if total else 1.0
    min_pass_rate = float(policy.get("min_pass_rate", 1.0))
    invariance_min = float((policy.get("invariance_assertions", {}) or {}).get("min_historical_pass_rate", min_pass_rate))
    gate_passed = pass_rate >= min_pass_rate and pass_rate >= invariance_min

    belief_guard = {"enabled": False}
    guard_policy = policy.get("belief_jump_guard", {}) or {}
    if guard_policy.get("enabled"):
        changed_files = _count_changed_files(project_root)
        max_delta = float(guard_policy.get("max_score_delta", 1.0))
        small_change_max = int(guard_policy.get("small_change_max_files", 0))
        previous_score = None
        if report_path.exists():
            try:
                previous_score = float(json.loads(report_path.read_text(encoding="utf-8")).get("invariance_score", pass_rate))
            except Exception:
                previous_score = None
        delta = abs(pass_rate - previous_score) if previous_score is not None else 0.0
        belief_guard = {"enabled": True, "changed_files": changed_files, "score_delta": delta}
        if changed_files <= small_change_max and delta > max_delta:
            gate_passed = False
            belief_guard["reason"] = "score_jump_too_large_for_small_change"

    report = {
        "gate_passed": gate_passed,
        "historical_pass_rate": pass_rate,
        "invariance_score": pass_rate,
        "drift_index": 1.0 - pass_rate,
        "historical_results": results,
        "belief_jump_guard": belief_guard,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _build_vault_record(receipt_path: Path, output_dir: Path) -> tuple[dict, bool]:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    artifacts_ok = True
    for artifact in (receipt.get("artifacts", {}) or {}).values():
        artifact_path = Path(artifact.get("path", ""))
        expected_sha = artifact.get("sha256")
        if not artifact_path.exists() or not expected_sha:
            artifacts_ok = False
            continue
        actual_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if actual_sha != expected_sha:
            artifacts_ok = False

    trace_ok = all(int(step.get("exit_code", 1)) == 0 for step in receipt.get("steps", []))
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "branch": receipt.get("branch"),
        "head": receipt.get("head"),
        "verification": {"artifacts_ok": artifacts_ok, "trace_ok": trace_ok},
    }
    record_path = output_dir / "soul_artifact_record.json"
    record_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    checksum_path = output_dir / "soul_artifact_record.sha256"
    checksum_path.write_text(hashlib.sha256(record_path.read_bytes()).hexdigest(), encoding="utf-8")
    payload["record_path"] = str(record_path)
    payload["checksum_path"] = str(checksum_path)
    return payload, artifacts_ok and trace_ok


anti_drift_gate = ModuleType("scripts.ops.anti_drift_gate")
anti_drift_gate.subprocess = subprocess
anti_drift_gate._count_changed_files = _count_changed_files
anti_drift_gate.run_anti_drift_gate = _run_anti_drift_gate
sys.modules[anti_drift_gate.__name__] = anti_drift_gate

soul_artifact_vault = ModuleType("scripts.ops.soul_artifact_vault")
soul_artifact_vault.build_vault_record = _build_vault_record
sys.modules[soul_artifact_vault.__name__] = soul_artifact_vault
