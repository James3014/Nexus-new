#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.bench.ab_eval import compare_datasets, load_runs
from scripts.bench.gemini_nexus_report import (
    _per_capability_public_gate,
    _route_quality_gate_from_rows,
    _route_quality_metrics,
)


def _latest_jsonl(root: Path, prefix: str) -> Path:
    matches = sorted(root.glob(f"{prefix}_*.jsonl"), key=lambda path: path.stat().st_mtime)
    if not matches:
        raise FileNotFoundError(f"{prefix}_*.jsonl not found in {root}")
    return matches[-1]


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _infra_invalid(rows: list[dict[str, Any]]) -> dict[str, Any]:
    reasons = [
        str(row.get("infra_invalid_reason") or "").strip()
        for row in rows
        if row.get("run_eligible") is False or str(row.get("infra_invalid_reason") or "").strip()
    ]
    reasons = [reason or "unknown" for reason in reasons]
    return {"count": len(reasons), "reasons": sorted(set(reasons))}


def _promotion_status(*, gate_valid: bool, infra_invalid: bool, semantic_delta: float) -> str:
    if infra_invalid or not gate_valid:
        return "INFRA_INVALID"
    if semantic_delta > 0:
        return "PASS"
    if semantic_delta < 0:
        return "REGRESSION"
    return "NO_UPLIFT"


def _runtime_pruning_summary(summary_without: dict[str, Any], summary_with: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    with_rate = float(summary_with.get("runtime_pruned_capability_rate", 0.0) or 0.0)
    warnings = []
    target_failures = []
    if with_rate > 0.30:
        warnings.append("runtime_pruning_above_warning_threshold")
    if with_rate > 0.15:
        target_failures.append("runtime_pruning_above_target_threshold")
    return {
        "without_nexus": summary_without.get("runtime_pruned_capability_rate", 0.0),
        "with_nexus": with_rate,
        "delta": delta.get("runtime_pruned_capability_rate_delta", 0.0),
        "avg_without_nexus": summary_without.get("avg_runtime_pruned_capability_count", 0.0),
        "avg_with_nexus": summary_with.get("avg_runtime_pruned_capability_count", 0.0),
        "avg_delta": delta.get("avg_runtime_pruned_capability_count_delta", 0.0),
        "warning_threshold": 0.30,
        "target_threshold": 0.15,
        "warnings": warnings,
        "target_failures": target_failures,
    }


def build_summary(*, output_dir: Path, scope: str = "") -> dict[str, Any]:
    without_path = _latest_jsonl(output_dir, "without_nexus")
    with_path = _latest_jsonl(output_dir, "with_nexus")
    rows_without = load_runs(without_path)
    rows_with = load_runs(with_path)
    report = compare_datasets("without_nexus", rows_without, "with_nexus", rows_with)
    public_safe = _per_capability_public_gate(report)
    route_quality = _route_quality_metrics(report, "b")
    route_quality["gate_failures"] = _route_quality_gate_from_rows(rows_with)
    evidence_bundle = _load_optional_json(output_dir / "evidence_bundle.json")
    model_names = sorted(
        {
            str(row.get("model_name") or "").strip()
            for row in [*rows_without, *rows_with]
            if str(row.get("model_name") or "").strip()
        }
    )
    summary_without = report["a"]["summary"]
    summary_with = report["b"]["summary"]
    infra_without = _infra_invalid(rows_without)
    infra_with = _infra_invalid(rows_with)
    infra_reasons = sorted(set(infra_without["reasons"]) | set(infra_with["reasons"]))
    semantic_delta = float(report["delta"].get("semantic_verified_rate_delta", 0.0) or 0.0)
    gate_valid = bool(not route_quality["gate_failures"] and public_safe.get("verdict") == "PASS")
    has_infra_invalid = bool(infra_without["count"] or infra_with["count"])
    status = _promotion_status(
        gate_valid=gate_valid,
        infra_invalid=has_infra_invalid,
        semantic_delta=semantic_delta,
    )
    return {
        "schema": "nexus_flash_baseline_summary_v1",
        "status": status,
        "promotion_status": status,
        "model": model_names[0] if len(model_names) == 1 else ",".join(model_names),
        "scope": scope or f"{len(rows_with)}x1",
        "files": {
            "without_nexus": str(without_path),
            "with_nexus": str(with_path),
            "evidence_bundle": str(output_dir / "evidence_bundle.json") if evidence_bundle else "",
        },
        "solve_rate": {
            "without_nexus": summary_without.get("solve_rate", 0.0),
            "with_nexus": summary_with.get("solve_rate", 0.0),
            "delta": report["delta"].get("solve_rate_delta", 0.0),
        },
        "semantic_verified_rate": {
            "without_nexus": summary_without.get("semantic_verified_rate", 0.0),
            "with_nexus": summary_with.get("semantic_verified_rate", 0.0),
            "delta": semantic_delta,
        },
        "route_quality": route_quality,
        "runtime_pruning": _runtime_pruning_summary(summary_without, summary_with, report["delta"]),
        "public_safe": public_safe,
        "infra_invalid": {
            "without_nexus": infra_without["count"],
            "with_nexus": infra_with["count"],
            "reasons": infra_reasons,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a Flash A/B baseline lock output directory.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--scope", default="")
    parser.add_argument("--write-json", default="")
    args = parser.parse_args()
    summary = build_summary(output_dir=Path(args.output_dir), scope=args.scope)
    text = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
    if args.write_json:
        out = Path(args.write_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
