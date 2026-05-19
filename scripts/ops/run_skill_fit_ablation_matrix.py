#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_ablation import (
    build_skill_fit_catalog,
    classify_skill_fit_failure,
    evaluate_skill_fit_ablation_rows,
    select_skill_discovery_replay_row_ids,
)


DEFAULT_MATRIX = Path("docs/reports/NEXUS_SKILL_FIT_EXECUTION_MATRIX_REPAIR_AND_CODING_FLASH30_2026-05-15.json")
DEFAULT_OUTPUT_ROOT = Path(".nexus/reports/skill_fit_ablation_flash30_2026-05-15")


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")[:160] or "row"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _find_with_nexus_rows(output_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(output_dir.glob("with_nexus_*.jsonl")):
        rows.extend(_load_jsonl(path))
    return rows


def _matrix_rows(
    matrix: Mapping[str, Any],
    *,
    row_id_filter: str = "",
    arm_type_filter: str = "",
    max_rows: int = 0,
) -> list[Mapping[str, Any]]:
    rows = [row for row in matrix.get("rows", []) if isinstance(row, Mapping)]
    allowed_row_ids = {part.strip() for part in row_id_filter.split(",") if part.strip()}
    if allowed_row_ids:
        rows = [row for row in rows if str(row.get("row_id") or "") in allowed_row_ids]
    allowed_arm_types = {part.strip() for part in arm_type_filter.split(",") if part.strip()}
    if allowed_arm_types:
        rows = [row for row in rows if str(row.get("arm_type") or "") in allowed_arm_types]
    if max_rows > 0:
        rows = rows[:max_rows]
    return rows


def _row_has_with_nexus_artifact(output_root: Path, row: Mapping[str, Any]) -> bool:
    row_id = str(row.get("row_id") or "")
    output_dir = output_root / _safe_name(row_id)
    return any(output_dir.glob("with_nexus_*.jsonl"))


def _row_status(row: Mapping[str, Any]) -> str:
    return str(row.get("status") or row.get("semantic_status") or "").upper()


def _ablation_gate_row(matrix_row: Mapping[str, Any], bench_row: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    arm_type = str(matrix_row.get("arm_type") or "")
    skill_status = str(bench_row.get("skill_mount_contract_status") or "").upper()
    trust_mismatch = bool(bench_row.get("report_trust_mismatch") or bench_row.get("trust_mismatch"))
    skill_contracts = [item for item in (bench_row.get("skill_mount_contract") or []) if isinstance(item, dict)]
    skill_effective = bool(skill_contracts and skill_status == "PASS")
    if arm_type == "capability_only":
        selected = injected = used = evidence_present = gate_passed = outcome_contributed = True
        status = "PASS" if _row_status(bench_row) in {"SUCCESS", "VERIFIED", "PASS"} else _row_status(bench_row)
    elif arm_type == "wrong_or_quarantined_skill":
        selected = injected = used = evidence_present = gate_passed = outcome_contributed = False
        status = "BLOCK" if skill_status in {"RETURN", "EMPTY"} else skill_status or _row_status(bench_row)
    else:
        selected = injected = used = evidence_present = gate_passed = outcome_contributed = skill_effective
        status = "KEEP" if skill_effective else skill_status or "RETURN"
    return {
        "arm_id": str(matrix_row.get("arm_id") or ""),
        "arm_type": arm_type,
        "status": status,
        "selected": selected,
        "injected": injected,
        "used": used,
        "evidence_present": evidence_present,
        "gate_passed": gate_passed,
        "outcome_contributed": outcome_contributed,
        "evidence_path": str(output_dir / "evidence_bundle.json"),
        "receipt_path": str(output_dir),
        "trust_mismatch": trust_mismatch,
        "benchmark_status": _row_status(bench_row),
        "skill_mount_contract_status": skill_status,
    }


def _with_failure_classification(result: dict[str, Any]) -> dict[str, Any]:
    classification = classify_skill_fit_failure(result)
    result["failure_classification"] = classification
    result["failure_action"] = classification.get("action", "")
    return result


def _bench_row_disqualifying_reason(bench_row: Mapping[str, Any]) -> str:
    infra_reason = str(bench_row.get("infra_invalid_reason") or "").strip()
    if infra_reason:
        return infra_reason
    if bench_row.get("run_eligible") is False:
        return "run_ineligible"
    model_calls = int(bench_row.get("model_calls") or 0)
    total_tokens = int(bench_row.get("total_tokens") or bench_row.get("model_total_tokens") or 0)
    if model_calls > 0 and total_tokens <= 0 and not bool(bench_row.get("token_measured")):
        return "model_call_without_tokens"
    return ""


def _result_status_from_gate(matrix_row: Mapping[str, Any], bench_row: Mapping[str, Any], gate: Mapping[str, Any]) -> str:
    if _bench_row_disqualifying_reason(bench_row):
        return "RETURN"
    if gate.get("status") != "PASS":
        return "RETURN"
    if str(matrix_row.get("arm_type") or "") == "wrong_or_quarantined_skill":
        return "PASS"
    return "PASS" if _row_status(bench_row) in {"SUCCESS", "VERIFIED", "PASS"} else "RETURN"


def _result_from_existing_artifact(matrix_row: Mapping[str, Any], *, output_root: Path) -> dict[str, Any]:
    row_id = str(matrix_row.get("row_id") or "")
    output_dir = output_root / _safe_name(row_id)
    result: dict[str, Any] = {
        "row_id": row_id,
        "capability": matrix_row.get("capability", ""),
        "arm_id": matrix_row.get("arm_id", ""),
        "arm_type": matrix_row.get("arm_type", ""),
        "anonymous_label": matrix_row.get("anonymous_label", ""),
        "skill_id": matrix_row.get("skill_id", ""),
        "source_root": matrix_row.get("source_root", ""),
        "runtime_eligible": bool(matrix_row.get("runtime_eligible")),
        "skill_mount_requests": matrix_row.get("skill_mount_requests", []),
        "task_ref": matrix_row.get("task_ref", {}),
        "output_dir": str(output_dir),
        "resumed_from_existing_artifact": True,
    }
    bench_rows = _find_with_nexus_rows(output_dir)
    if not bench_rows:
        result.update({"status": "RETURN", "reason": "missing_existing_with_nexus_artifact"})
        return _with_failure_classification(result)
    bench_row = bench_rows[-1]
    gate_row = _ablation_gate_row(matrix_row, bench_row, output_dir)
    gate = evaluate_skill_fit_ablation_rows([gate_row])
    disqualifying_reason = _bench_row_disqualifying_reason(bench_row)
    result.update(
        {
            "status": _result_status_from_gate(matrix_row, bench_row, gate),
            "benchmark_row": bench_row,
            "ablation_gate": gate,
            "ablation_gate_row": gate_row,
        }
    )
    if result["status"] != "PASS":
        result["reason"] = disqualifying_reason or "existing_artifact_delivery_or_ablation_gate_return"
        _with_failure_classification(result)
    return result


def _run_one(matrix_row: Mapping[str, Any], *, output_root: Path, preflight_only: bool, row_timeout_sec: int) -> dict[str, Any]:
    row_id = str(matrix_row.get("row_id") or "")
    output_dir = output_root / _safe_name(row_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({str(key): str(value) for key, value in (matrix_row.get("runner_env") or {}).items()})
    args = [str(item) for item in matrix_row.get("runner_args", [])]
    result: dict[str, Any] = {
        "row_id": row_id,
        "capability": matrix_row.get("capability", ""),
        "arm_id": matrix_row.get("arm_id", ""),
        "arm_type": matrix_row.get("arm_type", ""),
        "anonymous_label": matrix_row.get("anonymous_label", ""),
        "skill_id": matrix_row.get("skill_id", ""),
        "source_root": matrix_row.get("source_root", ""),
        "runtime_eligible": bool(matrix_row.get("runtime_eligible")),
        "skill_mount_requests": matrix_row.get("skill_mount_requests", []),
        "task_ref": matrix_row.get("task_ref", {}),
        "output_dir": str(output_dir),
    }
    if not args:
        result.update({"status": "RETURN", "reason": "missing_runner_args"})
        return _with_failure_classification(result)
    args = [*args, "--output-dir", str(output_dir)]
    if preflight_only:
        args.append("--preflight-only")
    try:
        proc = subprocess.run(args, cwd=PROJECT_ROOT, env=env, text=True, capture_output=True, timeout=row_timeout_sec)
    except subprocess.TimeoutExpired as exc:
        result.update(
            {
                "status": "RETURN",
                "reason": "runner_timeout",
                "returncode": None,
                "stdout_tail": str(exc.stdout or "")[-2000:],
                "stderr_tail": str(exc.stderr or "")[-2000:],
            }
        )
        return _with_failure_classification(result)
    result.update(
        {
            "returncode": proc.returncode,
            "stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-2000:],
        }
    )
    if preflight_only:
        report_path = output_dir / "benchmark_preflight.json"
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
        result["status"] = str(report.get("status") or "RETURN")
        result["preflight_report"] = str(report_path)
        result["failures"] = report.get("failures", [])
        if result["status"] != "PASS":
            result["reason"] = "preflight_return"
            _with_failure_classification(result)
        return result

    bench_rows = _find_with_nexus_rows(output_dir)
    if proc.returncode != 0 or not bench_rows:
        result["status"] = "RETURN"
        result["reason"] = "runner_failed_or_missing_rows"
        return _with_failure_classification(result)
    bench_row = bench_rows[-1]
    gate_row = _ablation_gate_row(matrix_row, bench_row, output_dir)
    gate = evaluate_skill_fit_ablation_rows([gate_row])
    disqualifying_reason = _bench_row_disqualifying_reason(bench_row)
    result.update(
        {
            "status": _result_status_from_gate(matrix_row, bench_row, gate),
            "benchmark_row": bench_row,
            "ablation_gate": gate,
            "ablation_gate_row": gate_row,
        }
    )
    if result["status"] != "PASS":
        result["reason"] = disqualifying_reason or "delivery_or_ablation_gate_return"
        _with_failure_classification(result)
    return result


def run_matrix(
    *,
    matrix_path: str | Path,
    output_root: str | Path,
    preflight_only: bool = False,
    max_rows: int = 0,
    docs_catalog_path: str | Path | None = None,
    row_timeout_sec: int = 900,
    row_id_filter: str = "",
    arm_type_filter: str = "",
) -> dict[str, Any]:
    matrix = json.loads(Path(matrix_path).read_text(encoding="utf-8"))
    rows = _matrix_rows(matrix, row_id_filter=row_id_filter, arm_type_filter=arm_type_filter, max_rows=max_rows)
    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=True)
    results = []
    status = "PASS" if rows else "RETURN"
    checkpoint_path = output / "checkpoint_summary.json"
    for row in rows:
        result = _run_one(row, output_root=output, preflight_only=preflight_only, row_timeout_sec=row_timeout_sec)
        results.append(result)
        checkpoint_path.write_text(
            json.dumps(
                {
                    "schema": "nexus.skill_fit_ablation_matrix_checkpoint.v1",
                    "status": "RUNNING" if result.get("status") == "PASS" else "RETURN",
                    "mode": "preflight" if preflight_only else "live",
                    "matrix_path": str(matrix_path),
                    "output_root": str(output),
                    "summary": {
                        "planned_rows": len(rows),
                        "completed_rows": len(results),
                        "pass_count": sum(1 for item in results if item.get("status") == "PASS"),
                        "return_count": sum(1 for item in results if item.get("status") != "PASS"),
                    },
                    "last_result": result,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        if result.get("status") != "PASS":
            status = "RETURN"
            break
    summary = {
        "schema": "nexus.skill_fit_ablation_matrix_run.v1",
        "status": status,
        "mode": "preflight" if preflight_only else "live",
        "matrix_path": str(matrix_path),
        "output_root": str(output),
        "summary": {
            "planned_rows": len(rows),
            "completed_rows": len(results),
            "pass_count": sum(1 for item in results if item.get("status") == "PASS"),
            "return_count": sum(1 for item in results if item.get("status") != "PASS"),
        },
        "results": results,
    }
    if not rows:
        summary["failure_action"] = "inspect_matrix_filter_before_rerun"
        summary["failure_classification"] = {
            "kind": "empty_matrix_selection",
            "action": "inspect_matrix_filter_before_rerun",
            "reason": "no_rows_selected",
        }
    summary_path = output / ("preflight_summary.json" if preflight_only else "live_summary.json")
    if not preflight_only:
        catalog = build_skill_fit_catalog(summary)
        catalog_path = output / "skill_fit_catalog.json"
        catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
        docs_catalog = Path(docs_catalog_path) if docs_catalog_path is not None else PROJECT_ROOT / "docs/reports/NEXUS_SKILL_FIT_CATALOG_REPAIR_AND_CODING_2026-05-15.json"
        docs_catalog.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
        summary["skill_fit_catalog_path"] = str(catalog_path)
        summary["docs_skill_fit_catalog_path"] = str(docs_catalog)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def build_resume_manifest(
    *,
    matrix_path: str | Path,
    output_root: str | Path,
    max_rows: int = 0,
    row_id_filter: str = "",
    arm_type_filter: str = "",
    abort_reason: str = "",
) -> dict[str, Any]:
    matrix = json.loads(Path(matrix_path).read_text(encoding="utf-8"))
    rows = _matrix_rows(matrix, row_id_filter=row_id_filter, arm_type_filter=arm_type_filter, max_rows=max_rows)
    output = Path(output_root)
    completed = [row for row in rows if _row_has_with_nexus_artifact(output, row)]
    remaining = [row for row in rows if not _row_has_with_nexus_artifact(output, row)]
    return {
        "schema": "nexus.skill_fit_resume_manifest.v1",
        "status": "PASS" if not remaining and rows else "RESUME_REQUIRED",
        "matrix_path": str(matrix_path),
        "output_root": str(output),
        "abort_reason": abort_reason,
        "summary": {
            "planned_rows": len(rows),
            "completed_rows": len(completed),
            "remaining_rows": len(remaining),
        },
        "last_completed_row_id": str(completed[-1].get("row_id") or "") if completed else "",
        "next_row_id": str(remaining[0].get("row_id") or "") if remaining else "",
        "completed_row_ids": [str(row.get("row_id") or "") for row in completed],
        "remaining_row_ids": [str(row.get("row_id") or "") for row in remaining],
        "claim_boundary": [
            "This manifest resumes execution only; it is not a sealed live summary.",
            "Completed rows remain diagnostic until a full live seal emits catalog evidence.",
        ],
    }


def run_resume_manifest(
    *,
    resume_manifest_path: str | Path,
    docs_catalog_path: str | Path | None = None,
    row_timeout_sec: int = 900,
) -> dict[str, Any]:
    resume = json.loads(Path(resume_manifest_path).read_text(encoding="utf-8"))
    matrix_path = Path(str(resume.get("matrix_path") or ""))
    output_root = Path(str(resume.get("output_root") or ""))
    manifest_row_ids = [
        str(row_id)
        for row_id in [
            *(resume.get("completed_row_ids", []) or []),
            *(resume.get("remaining_row_ids", []) or []),
        ]
        if str(row_id)
    ]
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    requested_rows = _matrix_rows(matrix, row_id_filter=",".join(manifest_row_ids))
    remaining_row_ids = [
        str(row.get("row_id") or "")
        for row in requested_rows
        if not _row_has_with_nexus_artifact(output_root, row)
    ]
    if remaining_row_ids:
        run_matrix(
            matrix_path=matrix_path,
            output_root=output_root,
            row_timeout_sec=row_timeout_sec,
            row_id_filter=",".join(remaining_row_ids),
            docs_catalog_path=docs_catalog_path,
        )
    all_rows = requested_rows
    results = []
    status = "PASS" if all_rows else "RETURN"
    for row in all_rows:
        result = _result_from_existing_artifact(row, output_root=output_root)
        results.append(result)
        if result.get("status") != "PASS":
            status = "RETURN"
            break
    summary = {
        "schema": "nexus.skill_fit_ablation_matrix_run.v1",
        "status": status,
        "mode": "live",
        "matrix_path": str(matrix_path),
        "output_root": str(output_root),
        "resume_manifest_path": str(resume_manifest_path),
        "summary": {
            "planned_rows": len(all_rows),
            "completed_rows": len(results),
            "pass_count": sum(1 for item in results if item.get("status") == "PASS"),
            "return_count": sum(1 for item in results if item.get("status") != "PASS"),
        },
        "results": results,
    }
    catalog = build_skill_fit_catalog(summary)
    catalog_path = output_root / "skill_fit_catalog.json"
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    if docs_catalog_path is not None:
        docs_catalog = Path(docs_catalog_path)
        docs_catalog.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
        summary["docs_skill_fit_catalog_path"] = str(docs_catalog)
    summary["skill_fit_catalog_path"] = str(catalog_path)
    (output_root / "live_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def run_discovery_controller(
    *,
    phase: str,
    matrix_path: str | Path,
    output_root: str | Path,
    preflight_only: bool = False,
    max_rows: int = 0,
    docs_catalog_path: str | Path | None = None,
    row_timeout_sec: int = 900,
    rerun_queue_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run stable discovery phases without hand-built row filters."""

    matrix = json.loads(Path(matrix_path).read_text(encoding="utf-8"))
    row_id_filter = ""
    arm_type_filter = ""
    if phase == "capability_sweep":
        arm_type_filter = "capability_only"
    elif phase == "targeted_replay":
        if rerun_queue_path is None:
            raise ValueError("rerun_queue_path is required for targeted_replay")
        queue = json.loads(Path(rerun_queue_path).read_text(encoding="utf-8"))
        row_ids = select_skill_discovery_replay_row_ids(matrix, queue)
        row_id_filter = ",".join(row_ids)
    elif phase == "full_seal":
        pass
    else:
        raise ValueError(f"unknown discovery controller phase: {phase}")
    summary = run_matrix(
        matrix_path=matrix_path,
        output_root=output_root,
        preflight_only=preflight_only,
        max_rows=max_rows,
        docs_catalog_path=docs_catalog_path,
        row_timeout_sec=row_timeout_sec,
        row_id_filter=row_id_filter,
        arm_type_filter=arm_type_filter,
    )
    summary["controller"] = {
        "phase": phase,
        "row_id_filter": row_id_filter,
        "arm_type_filter": arm_type_filter,
        "rerun_queue_path": str(rerun_queue_path or ""),
    }
    summary_path = Path(output_root) / ("preflight_summary.json" if preflight_only else "live_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a skill-fit ablation execution matrix with fail-fast gates.")
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--max-rows", type=int, default=0)
    parser.add_argument("--docs-catalog-path", default=None)
    parser.add_argument("--row-timeout-sec", type=int, default=900)
    parser.add_argument("--row-id-filter", default="")
    parser.add_argument("--arm-type-filter", default="")
    parser.add_argument("--controller-phase", choices=["", "capability_sweep", "targeted_replay", "full_seal"], default="")
    parser.add_argument("--rerun-queue", default=None)
    parser.add_argument("--emit-resume-manifest", action="store_true")
    parser.add_argument("--resume-manifest", default="")
    parser.add_argument("--resume-manifest-output", default="")
    parser.add_argument("--abort-reason", default="")
    args = parser.parse_args(argv)
    if args.resume_manifest:
        summary = run_resume_manifest(
            resume_manifest_path=args.resume_manifest,
            docs_catalog_path=args.docs_catalog_path,
            row_timeout_sec=args.row_timeout_sec,
        )
        print(json.dumps({"status": summary["status"], **summary["summary"], "output_root": summary["output_root"]}, sort_keys=True))
        return 0 if summary["status"] == "PASS" else 1
    if args.emit_resume_manifest:
        manifest = build_resume_manifest(
            matrix_path=args.matrix,
            output_root=args.output_root,
            max_rows=args.max_rows,
            row_id_filter=args.row_id_filter,
            arm_type_filter=args.arm_type_filter,
            abort_reason=args.abort_reason,
        )
        output_path = Path(args.resume_manifest_output) if args.resume_manifest_output else Path(args.output_root) / "resume_manifest.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"status": manifest["status"], **manifest["summary"], "output": str(output_path)}, sort_keys=True))
        return 0
    if args.controller_phase:
        summary = run_discovery_controller(
            phase=args.controller_phase,
            matrix_path=args.matrix,
            output_root=args.output_root,
            preflight_only=args.preflight_only,
            max_rows=args.max_rows,
            docs_catalog_path=args.docs_catalog_path,
            row_timeout_sec=args.row_timeout_sec,
            rerun_queue_path=args.rerun_queue,
        )
    else:
        summary = run_matrix(
            matrix_path=args.matrix,
            output_root=args.output_root,
            preflight_only=args.preflight_only,
            max_rows=args.max_rows,
            docs_catalog_path=args.docs_catalog_path,
            row_timeout_sec=args.row_timeout_sec,
            row_id_filter=args.row_id_filter,
            arm_type_filter=args.arm_type_filter,
        )
    print(json.dumps({"status": summary["status"], **summary["summary"], "output_root": summary["output_root"]}, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
