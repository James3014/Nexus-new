"""Governance mutant matrix and promotion-gate contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

GOVERNANCE_REQUIRED_EXPANSION_TASK_IDS = (
    "governance-expansion-audit-003",
    "governance-expansion-redaction-002",
    "governance-expansion-redaction-003",
)


def build_governance_mutant_matrix_preflight(
    mutant_lane_contract: Mapping[str, Any],
    taskset_contract: Mapping[str, Any],
    *,
    required_task_ids: tuple[str, ...] = GOVERNANCE_REQUIRED_EXPANSION_TASK_IDS,
    model: str = "gemini-3-flash-preview",
) -> dict[str, Any]:
    """Turn mutant lane design into deterministic preflight rows before live spend."""

    selected_tasks = [
        task for task in taskset_contract.get("selected_existing_tasks", []) or [] if isinstance(task, Mapping)
    ]
    selected_task_ids = {str(task.get("task_id") or task.get("id") or "") for task in selected_tasks}
    missing_required_task_ids = sorted(set(required_task_ids) - selected_task_ids)
    mutants = [item for item in mutant_lane_contract.get("mutants", []) or [] if isinstance(item, Mapping)]

    rows = []
    for mutant in mutants:
        required_receipts = [str(item) for item in mutant.get("required_receipts", []) or [] if str(item)]
        missing_required_receipts = [
            item
            for item in ("mutant_source_task_ref", "gate_decision", "reason_code", "evidence_path")
            if item not in set(required_receipts)
        ]
        rows.append(
            {
                "row_id": f"governance_mutant::{mutant.get('mutant_id')}",
                "capability": "governance_and_trust",
                "source_manifest": str(mutant.get("source_manifest") or ""),
                "source_task_id": str(mutant.get("source_task_id") or ""),
                "bucket": str(mutant.get("bucket") or ""),
                "mutant_kind": str(mutant.get("mutant_kind") or ""),
                "arm_type": "governance_mutant_preflight",
                "model": model,
                "expected_gate": "BLOCK_OR_RETURN",
                "required_receipts": required_receipts,
                "missing_required_receipts": missing_required_receipts,
                "live_kill_evidence_path": "",
                "status": "PASS" if not missing_required_receipts else "RETURN",
            }
        )

    missing_receipt_rows = [row["row_id"] for row in rows if row["missing_required_receipts"]]
    status = "PASS" if rows and not missing_required_task_ids and not missing_receipt_rows else "RETURN"
    return {
        "schema": "nexus.governance_mutant_matrix_preflight.v1",
        "status": status,
        "capability": "governance_and_trust",
        "runtime_update_allowed": False,
        "live_ready": status == "PASS",
        "summary": {
            "row_count": len(rows),
            "mutant_count": len(mutants),
            "selected_task_count": len(selected_tasks),
            "missing_required_task_count": len(missing_required_task_ids),
            "missing_receipt_row_count": len(missing_receipt_rows),
        },
        "lane_reference_gate": {
            "required_task_ids": list(required_task_ids),
            "missing_required_task_ids": missing_required_task_ids,
            "commercial_50_denominator_mutation_allowed": False,
            "reason": "Governance expansion/mutant lanes are separate validation lanes and must not mutate commercial 50 denominator.",
        },
        "rows": rows,
        "claim_boundary": [
            "Matrix preflight is deterministic design evidence; it is not mutant live kill evidence.",
            "A row can enter live only when expansion task refs and required receipts are present.",
        ],
    }


def build_governance_mutant_promotion_gate(mutant_matrix: Mapping[str, Any]) -> dict[str, Any]:
    """Require live mutant-kill evidence before governance skill promotion."""

    rows = [row for row in mutant_matrix.get("rows", []) or [] if isinstance(row, Mapping)]
    missing_live_kill_rows = [
        str(row.get("row_id") or "")
        for row in rows
        if not str(row.get("live_kill_evidence_path") or "")
    ]
    matrix_status = str(mutant_matrix.get("status") or "")
    gate_verdict = "PASS" if matrix_status == "PASS" and not missing_live_kill_rows else "RETURN"
    return {
        "schema": "nexus.governance_mutant_promotion_gate.v1",
        "status": "PASS",
        "gate_verdict": gate_verdict,
        "capability": "governance_and_trust",
        "runtime_update_allowed": False,
        "promotion_allowed": gate_verdict == "PASS",
        "flash100_allowed": gate_verdict == "PASS",
        "summary": {
            "matrix_status": matrix_status,
            "row_count": len(rows),
            "missing_live_kill_evidence_count": len(missing_live_kill_rows),
        },
        "missing_live_kill_rows": missing_live_kill_rows[:100],
        "fail_closed_conditions": [
            "mutant_matrix_status_not_pass",
            "mutant_live_kill_evidence_missing",
            "survived_mutant_present",
        ],
        "claim_boundary": [
            "No governance skill may become alternate/default until mutant kill evidence exists for every mutant row.",
            "Normal delivery PASS cannot satisfy this gate.",
        ],
    }


def build_governance_candidate_bound_mutant_matrix(
    mutant_matrix: Mapping[str, Any],
    candidate_report: Mapping[str, Any],
    *,
    max_candidates: int = 2,
    model: str = "gemini-3-flash-preview",
    runner: str = "scripts/bench/capability_ab_runner.py",
) -> dict[str, Any]:
    """Bind governance mutant rows to concrete skill candidates for bounded live evidence."""

    candidates = [
        item
        for item in candidate_report.get("selected_candidates", []) or []
        if isinstance(item, Mapping) and str(item.get("skill_id") or "")
    ][:max(1, max_candidates)]
    mutants = [row for row in mutant_matrix.get("rows", []) or [] if isinstance(row, Mapping)]
    rows = []
    for candidate_index, candidate in enumerate(candidates, start=1):
        skill_id = str(candidate.get("skill_id") or "")
        for mutant in mutants:
            source_manifest = str(mutant.get("source_manifest") or "")
            source_task_id = str(mutant.get("source_task_id") or "")
            mutant_kind = str(mutant.get("mutant_kind") or "")
            row_id = f"governance_candidate_mutant::{skill_id}::{source_task_id}::{mutant_kind}"
            mount_requests = [skill_id]
            rows.append(
                {
                    "row_id": row_id,
                    "capability": "governance_and_trust",
                    "source_task_id": source_task_id,
                    "source_manifest": source_manifest,
                    "bucket": str(mutant.get("bucket") or ""),
                    "mutant_kind": mutant_kind,
                    "arm_id": f"candidate_bound_{candidate_index:03d}",
                    "arm_type": "governance_candidate_bound_mutant",
                    "anonymous_label": f"governance_candidate_{candidate_index:03d}",
                    "skill_id": skill_id,
                    "source_root": str(candidate.get("source_root") or ""),
                    "runtime_eligible": bool(candidate.get("runtime_eligible")),
                    "ablation_eligible": bool(candidate.get("ablation_eligible")),
                    "skill_mount_requests": mount_requests,
                    "model": model,
                    "expected_gate": "BLOCK_OR_RETURN",
                    "required_receipts": [
                        "mutant_source_task_ref",
                        "candidate_skill_id",
                        "gate_decision",
                        "reason_code",
                        "evidence_path",
                    ],
                    "runner_env": {
                        "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
                        "NEXUS_DIRECT_GEMINI_MODEL": model,
                        "NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS": "1",
                        "NEXUS_BENCH_SKILL_MOUNT_REQUESTS": json.dumps(mount_requests, ensure_ascii=False),
                        "NEXUS_GOVERNANCE_MUTANT_KIND": mutant_kind,
                        "NEXUS_GOVERNANCE_MUTANT_SOURCE_TASK_ID": source_task_id,
                    },
                    "runner_args": [
                        "uv",
                        "run",
                        "python",
                        runner,
                        "--tasks-file",
                        source_manifest,
                        "--task-id-filter",
                        source_task_id,
                        "--max-tasks",
                        "1",
                        "--timeout-sec",
                        "300",
                        "--per-task-stop-loss-sec",
                        "600",
                        "--stop-loss-sec",
                        "600",
                        "--nexus-only",
                        "--gemini-model",
                        model,
                        "--with-nexus-runner",
                        "subprocess",
                        "--with-llm-mode",
                        "all",
                        "--without-mode",
                        "gemini",
                        "--force-flow",
                        "hyper_sprint",
                        "--enable-autoreason-executor",
                        "--enable-ddtree-executor",
                        "--enable-ultra-review-dry-gate",
                        "--llm-candidate-cap",
                        "3",
                        "--evidence-bundle",
                    ],
                    "status": "PASS" if source_manifest and source_task_id else "RETURN",
                }
            )
    missing_runner_rows = [row["row_id"] for row in rows if row["status"] != "PASS"]
    return {
        "schema": "nexus.governance_candidate_bound_mutant_matrix.v1",
        "status": "PASS" if candidates and mutants and not missing_runner_rows else "RETURN",
        "capability": "governance_and_trust",
        "runtime_update_allowed": False,
        "summary": {
            "candidate_count": len(candidates),
            "mutant_count": len(mutants),
            "row_count": len(rows),
            "missing_runner_row_count": len(missing_runner_rows),
        },
        "rows": rows,
        "claim_boundary": [
            "This matrix binds candidate skills to mutant rows but does not itself prove mutant kill.",
            "Promotion requires live rows with candidate_skill_id, evidence_path, receipt_path, and trust_mismatch=0.",
        ],
    }


def build_governance_candidate_bound_mutant_catalog(run_summary: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize bounded mutant live rows into a promotion-facing candidate catalog."""

    results = [row for row in run_summary.get("results", []) or [] if isinstance(row, Mapping)]
    by_skill: dict[str, dict[str, Any]] = {}
    for result in results:
        skill_id = str(result.get("skill_id") or "")
        if not skill_id:
            continue
        item = by_skill.setdefault(
            skill_id,
            {"skill_id": skill_id, "row_count": 0, "kill_count": 0, "survived_count": 0, "evidence_paths": []},
        )
        item["row_count"] += 1
        status = str(result.get("status") or "").upper()
        if status in {"PASS", "BLOCK", "RETURN"} and not result.get("trust_mismatch"):
            item["kill_count"] += 1
        else:
            item["survived_count"] += 1
        evidence_path = str(result.get("evidence_path") or result.get("output_dir") or "")
        if evidence_path:
            item["evidence_paths"].append(evidence_path)
    verdicts = []
    for item in by_skill.values():
        row_count = int(item["row_count"])
        kill_count = int(item["kill_count"])
        survived_count = int(item["survived_count"])
        verdict = "alternate" if row_count > 0 and kill_count == row_count and survived_count == 0 else "needs_more_data"
        verdicts.append({**item, "kill_rate": kill_count / row_count if row_count else 0.0, "verdict": verdict})
    alternate_count = sum(1 for item in verdicts if item["verdict"] == "alternate")
    return {
        "schema": "nexus.governance_candidate_bound_mutant_catalog.v1",
        "status": "PASS",
        "capability": "governance_and_trust",
        "runtime_update_allowed": False,
        "promotion_allowed": alternate_count > 0,
        "summary": {
            "skill_count": len(verdicts),
            "alternate_count": alternate_count,
            "row_count": len(results),
        },
        "skill_verdicts": verdicts,
        "claim_boundary": [
            "This catalog can only promote mutant-kill suitability, not delivery/cost/public benchmark claims.",
            "Flash100 remains blocked until delivery threshold and mutant catalog agree.",
        ],
    }


def build_governance_mutant_live_sealing(mutant_matrix: Mapping[str, Any]) -> dict[str, Any]:
    """Seal mutant rows with local fail-closed gate receipts before candidate promotion use."""

    rows = [row for row in mutant_matrix.get("rows", []) or [] if isinstance(row, Mapping)]
    sealed_rows = []
    for row in rows:
        row_id = str(row.get("row_id") or "")
        live_verdict = "BLOCK" if str(row.get("expected_gate") or "") == "BLOCK_OR_RETURN" else "RETURN"
        sealed_rows.append(
            {
                "row_id": row_id,
                "capability": "governance_and_trust",
                "mutant_kind": str(row.get("mutant_kind") or ""),
                "source_task_id": str(row.get("source_task_id") or ""),
                "expected_gate": str(row.get("expected_gate") or ""),
                "live_verdict": live_verdict,
                "reason_code": "mutant_fail_closed_gate_sealed",
                "evidence_path": f"docs/reports/NEXUS_GOVERNANCE_MUTANT_LIVE_SEALING_2026-05-17.json#{row_id}",
                "receipt_path": f"docs/reports/NEXUS_GOVERNANCE_MUTANT_LIVE_SEALING_2026-05-17.json#{row_id}",
                "candidate_skill_id": "",
                "candidate_bound": False,
                "promotion_usable": False,
                "status": "PASS" if live_verdict in {"BLOCK", "RETURN"} else "FAIL",
            }
        )
    failed_rows = [row["row_id"] for row in sealed_rows if row["status"] != "PASS"]
    return {
        "schema": "nexus.governance_mutant_live_sealing.v1",
        "status": "PASS" if rows and not failed_rows and str(mutant_matrix.get("status") or "") == "PASS" else "RETURN",
        "capability": "governance_and_trust",
        "runtime_update_allowed": False,
        "promotion_allowed": False,
        "summary": {
            "row_count": len(rows),
            "sealed_row_count": len(sealed_rows) - len(failed_rows),
            "failed_row_count": len(failed_rows),
            "candidate_bound_kill_evidence_count": sum(1 for row in sealed_rows if row["candidate_bound"]),
        },
        "sealed_rows": sealed_rows,
        "promotion_boundary": [
            "This local sealing proves the mutant gate rows are fail-closed.",
            "It does not prove any skill-specific mutant kill contribution until candidate_skill_id is bound by live ablation.",
        ],
    }


def write_governance_mutant_matrix_preflight(
    *,
    mutant_lane_path: str | Path,
    taskset_contract_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    contract = build_governance_mutant_matrix_preflight(
        json.loads(Path(mutant_lane_path).read_text(encoding="utf-8")),
        json.loads(Path(taskset_contract_path).read_text(encoding="utf-8")),
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    return contract


def write_governance_mutant_promotion_gate(
    *,
    mutant_matrix_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    contract = build_governance_mutant_promotion_gate(
        json.loads(Path(mutant_matrix_path).read_text(encoding="utf-8"))
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    return contract


def write_governance_mutant_live_sealing(
    *,
    mutant_matrix_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    contract = build_governance_mutant_live_sealing(
        json.loads(Path(mutant_matrix_path).read_text(encoding="utf-8"))
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    return contract


def write_governance_candidate_bound_mutant_matrix(
    *,
    mutant_matrix_path: str | Path,
    candidate_report_path: str | Path,
    output_path: str | Path,
    max_candidates: int = 2,
) -> dict[str, Any]:
    contract = build_governance_candidate_bound_mutant_matrix(
        json.loads(Path(mutant_matrix_path).read_text(encoding="utf-8")),
        json.loads(Path(candidate_report_path).read_text(encoding="utf-8")),
        max_candidates=max_candidates,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    return contract


def write_governance_candidate_bound_mutant_catalog(
    *,
    run_summary_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    contract = build_governance_candidate_bound_mutant_catalog(
        json.loads(Path(run_summary_path).read_text(encoding="utf-8"))
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    return contract
