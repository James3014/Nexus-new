from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Iterable


def _bucket_for_row(row: dict[str, Any]) -> str:
    if row.get("preflight_ready") is True:
        return "preflight_ready"
    if row.get("solve_eligible"):
        return "solved"

    reason = str(row.get("failure_reason") or "")
    if (
        "VERSION_PARITY" in reason
        or "DEPENDENCY_MISSING" in reason
        or "ENVIRONMENT" in reason
        or "ABI_FAILURE" in reason
    ):
        return "env_blocked"
    if reason.startswith("REPRO_NOT_REPRODUCED") or reason == "NO_REPRO_SCRIPT":
        return "no_repro"
    if reason.startswith("MODEL_"):
        return "model_blocked"
    if "LOCALIZATION" in reason:
        return "localization_blocked"
    if "VERIFICATION" in reason:
        return "verification_blocked"
    return "other_blocked"


def _failure_reason_for_row(row: dict[str, Any]) -> str:
    reason = str(row.get("failure_reason") or "")
    if reason:
        return reason
    if row.get("preflight_ready") is True:
        return "PREFLIGHT_READY"
    if row.get("solve_eligible"):
        return "SOLVED"
    return "UNCLASSIFIED"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def summarize_records(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    by_bucket = Counter(_bucket_for_row(row) for row in materialized)
    by_failure_reason = Counter(_failure_reason_for_row(row) for row in materialized)
    
    by_stop_layer = Counter()
    layer_reason_matrix = {}
    
    probes_passed = 0
    probes_total = 0
    
    for row in materialized:
        receipt_path = row.get("receipt_path")
        if receipt_path and Path(receipt_path).exists():
            try:
                receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
                metrics = receipt.get("eval_metrics", {})
                
                gate_exit = metrics.get("gate_exit", "unknown")
                failure_class = metrics.get("failure_class", "unknown")
                
                by_stop_layer[gate_exit] += 1
                
                if gate_exit not in layer_reason_matrix:
                    layer_reason_matrix[gate_exit] = Counter()
                layer_reason_matrix[gate_exit][failure_class] += 1
                
                if metrics.get("stop_layer_matched"):
                    probes_passed += 1
                probes_total += 1
            except Exception:
                pass

    solved = by_bucket.get("solved", 0)
    preflight_ready = by_bucket.get("preflight_ready", 0)
    total = len(materialized)

    return {
        "schema": "nexus.local_heal.manifest_summary.v2",
        "total": total,
        "solved": solved,
        "preflight_ready": preflight_ready,
        "probe_pass_rate": probes_passed / probes_total if probes_total > 0 else 0.0,
        "probes_matched": f"{probes_passed}/{probes_total}",
        "by_stop_layer": dict(sorted(by_stop_layer.items())),
        "layer_reason_matrix": {k: dict(sorted(v.items())) for k, v in sorted(layer_reason_matrix.items())},
        "preflight_gate": "PASS" if total > 0 and preflight_ready == total else "NOT_MET",
        "completion_gate": "PASS" if total > 0 and solved == total else "NOT_MET",
        "by_bucket": dict(sorted(by_bucket.items())),
        "by_failure_reason": dict(sorted(by_failure_reason.items())),
        "receipts": [str(row.get("receipt_path") or "") for row in materialized if row.get("receipt_path")],
    }


def summarize_manifest_results(path: str | Path) -> dict[str, Any]:
    return summarize_records(_read_jsonl(Path(path)))
