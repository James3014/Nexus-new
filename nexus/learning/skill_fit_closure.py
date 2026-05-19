"""SF capability-local matrix, evidence gate, and final skill pairing catalog."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from nexus.learning.skill_route_taxonomy import CAPABILITY_BY_ID


EVIDENCE_WORDS = {
    "acceptance",
    "audit",
    "block",
    "claim",
    "contract",
    "evidence",
    "gate",
    "outcome",
    "receipt",
    "verify",
    "verification",
}


def _tokens(text: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9_]+", text.lower()) if len(part) >= 3}


def _read_skill_text(path: str) -> str:
    if not path:
        return ""
    source = Path(path)
    if not source.exists():
        return ""
    return source.read_text(encoding="utf-8", errors="replace")


def _capability_terms(capability_id: str) -> set[str]:
    capability = CAPABILITY_BY_ID.get(capability_id)
    if capability is None:
        return _tokens(capability_id)
    raw = " ".join(
        [
            capability.capability_id,
            capability.group,
            capability.pillar,
            " ".join(capability.phases),
            capability.role,
            " ".join(capability.keywords),
            " ".join(capability.legacy_hints),
        ]
    )
    return _tokens(raw)


def _unique_candidates(*groups: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for group in groups:
        for item in group:
            identity_id = str(item.get("identity_id") or item.get("current_pairing_identity_id") or item.get("canonical_top_identity_id") or "")
            if not identity_id or identity_id in seen:
                continue
            seen.add(identity_id)
            candidates.append(dict(item))
    return candidates


def build_capability_local_test_matrix(
    *,
    final_pairing: Mapping[str, Any],
    capability_buckets: Mapping[str, Any],
    max_alternates_per_capability: int = 3,
) -> dict[str, Any]:
    buckets_by_capability = {
        str(item.get("capability_id") or ""): item
        for item in capability_buckets.get("capability_buckets", []) or []
        if isinstance(item, Mapping)
    }
    matrix = []
    rows = []
    blockers = []
    for pairing in final_pairing.get("pairings", []) or []:
        if not isinstance(pairing, Mapping):
            continue
        capability_id = str(pairing.get("capability_id") or "")
        bucket = buckets_by_capability.get(capability_id, {})
        top_candidates = [item for item in bucket.get("top_candidates", []) or [] if isinstance(item, Mapping)]
        current = {
            "skill_id": pairing.get("current_pairing_skill_id", ""),
            "identity_id": pairing.get("current_pairing_identity_id", ""),
            "skill_path": pairing.get("current_pairing_skill_path")
            or next(
                (
                    item.get("skill_path", "")
                    for item in top_candidates
                    if item.get("identity_id") == pairing.get("current_pairing_identity_id")
                ),
                "",
            ),
            "sha256": pairing.get("current_pairing_sha256", ""),
            "source_status": pairing.get("current_pairing_source_status", ""),
            "candidate_score": pairing.get("current_pairing_score", 0),
            "runtime_eligible": pairing.get("current_pairing_runtime_eligible", False),
            "ablation_eligible": pairing.get("current_pairing_ablation_eligible", True),
            "candidate_role": "current_pairing",
        }
        if not current["skill_path"]:
            current["skill_path"] = next(
                (
                    item.get("skill_path", "")
                    for item in top_candidates
                    if item.get("skill_id") == pairing.get("current_pairing_skill_id")
                ),
                "",
            )
        canonical_top = {
            "skill_id": pairing.get("canonical_top_skill_id", ""),
            "identity_id": pairing.get("canonical_top_identity_id", ""),
            "skill_path": pairing.get("canonical_top_skill_path")
            or next(
                (
                    item.get("skill_path", "")
                    for item in top_candidates
                    if item.get("identity_id") == pairing.get("canonical_top_identity_id")
                ),
                "",
            ),
            "sha256": pairing.get("canonical_top_sha256", ""),
            "source_status": pairing.get("canonical_top_source_status", ""),
            "candidate_score": pairing.get("canonical_top_score", 0),
            "runtime_eligible": pairing.get("canonical_top_runtime_eligible", False),
            "ablation_eligible": pairing.get("canonical_top_ablation_eligible", True),
            "candidate_role": "canonical_top",
        }
        alternates = [
            {
                **dict(item),
                "candidate_role": "alternate_candidate",
            }
            for item in top_candidates
            if item.get("identity_id") not in {current.get("identity_id"), canonical_top.get("identity_id")}
        ][:max_alternates_per_capability]
        skill_candidates = _unique_candidates([current], [canonical_top], alternates)
        if not skill_candidates:
            blockers.append(f"{capability_id}:missing_skill_candidate")
        capability_rows = [
            {
                "row_id": f"{capability_id}::capability_only",
                "capability_id": capability_id,
                "arm_type": "capability_only",
                "expected": "baseline",
            }
        ]
        for index, candidate in enumerate(skill_candidates, start=1):
            row = {
                "row_id": f"{capability_id}::skill_arm_{index:03d}::{candidate.get('skill_id')}",
                "capability_id": capability_id,
                "arm_type": "skill_arm",
                "expected": "measure_skill_fit",
                "skill_id": candidate.get("skill_id", ""),
                "identity_id": candidate.get("identity_id", ""),
                "skill_path": candidate.get("skill_path", ""),
                "source_status": candidate.get("source_status", ""),
                "candidate_role": candidate.get("candidate_role", ""),
                "candidate_score": int(candidate.get("candidate_score") or candidate.get("score") or 0),
                "runtime_eligible": bool(candidate.get("runtime_eligible")),
                "ablation_eligible": bool(candidate.get("ablation_eligible")),
            }
            capability_rows.append(row)
        capability_rows.append(
            {
                "row_id": f"{capability_id}::negative_control",
                "capability_id": capability_id,
                "arm_type": "negative_control",
                "expected": "BLOCK_OR_RETURN",
                "skill_id": "wrong_or_quarantined_skill",
            }
        )
        rows.extend(capability_rows)
        matrix.append(
            {
                "capability_id": capability_id,
                "status": "READY" if skill_candidates else "BLOCKED",
                "candidate_count": len(skill_candidates),
                "row_count": len(capability_rows),
                "rows": capability_rows,
            }
        )
    return {
        "schema": "nexus.sf_capability_local_test_matrix.v1",
        "status": "PASS" if not blockers else "BLOCKED",
        "summary": {
            "capability_count": len(matrix),
            "ready_capability_count": sum(1 for item in matrix if item["status"] == "READY"),
            "blocked_capability_count": len(blockers),
            "row_count": len(rows),
            "skill_arm_count": sum(1 for row in rows if row["arm_type"] == "skill_arm"),
            "negative_control_count": sum(1 for row in rows if row["arm_type"] == "negative_control"),
            "public_benchmark_allowed": False,
        },
        "blockers": blockers,
        "capabilities": matrix,
        "rows": rows,
        "claim_boundary": [
            "This is a capability-local SF test matrix, not a public benchmark.",
            "One capability may have a primary skill plus alternates; runtime may still load only the policy-approved default unless combo support is explicitly gated.",
        ],
    }


def build_sf_evidence_gate_schema() -> dict[str, Any]:
    return {
        "schema": "nexus.sf_evidence_gate_schema.v1",
        "status": "PASS",
        "required_fields": [
            "selected",
            "injected",
            "used",
            "evidence_present",
            "gate_passed",
            "outcome_contributed",
            "trust_mismatch",
            "cost_delta_status",
        ],
        "hard_gates": {
            "selected_only_is_invalid": True,
            "delivery_success_without_skill_evidence_is_invalid": True,
            "negative_control_must_block_or_return": True,
            "trust_mismatch_required": 0,
        },
        "verdict_rules": {
            "primary_candidate": "skill arm passes full evidence chain and is strongest among capability-local candidates",
            "alternate_candidate": "skill arm passes full evidence chain but is not strongest or is candidate-only",
            "needs_flash_compare": "bounded probe cannot distinguish top candidates or receipt chain is synthetic/weak",
            "reject": "missing used/evidence/gate/outcome or negative safety signal",
        },
        "public_benchmark_allowed": False,
    }


def evaluate_bounded_probe_row(row: Mapping[str, Any]) -> dict[str, Any]:
    arm_type = str(row.get("arm_type") or "")
    capability_id = str(row.get("capability_id") or "")
    base = {
        "row_id": str(row.get("row_id") or ""),
        "capability_id": capability_id,
        "arm_type": arm_type,
        "skill_id": str(row.get("skill_id") or ""),
        "identity_id": str(row.get("identity_id") or ""),
        "selected": False,
        "injected": False,
        "used": False,
        "evidence_present": False,
        "gate_passed": False,
        "outcome_contributed": False,
        "trust_mismatch": 0,
        "cost_delta_status": "not_measured_in_bounded_probe",
    }
    if arm_type == "capability_only":
        return {
            **base,
            "status": "PASS",
            "selected": True,
            "injected": True,
            "used": True,
            "evidence_present": True,
            "gate_passed": True,
            "reason": "capability_baseline_ready",
        }
    if arm_type == "negative_control":
        return {
            **base,
            "status": "PASS",
            "reason": "negative_control_blocked",
        }
    if arm_type != "skill_arm":
        return {**base, "status": "RETURN", "reason": "unsupported_arm_type"}

    skill_text = _read_skill_text(str(row.get("skill_path") or ""))
    capability_overlap = sorted(_tokens(skill_text) & _capability_terms(capability_id))
    evidence_overlap = sorted(_tokens(skill_text) & EVIDENCE_WORDS)
    selected = bool(row.get("skill_id"))
    injected = bool(skill_text)
    used = bool(capability_overlap)
    evidence_present = bool(evidence_overlap)
    gate_passed = selected and injected and used and evidence_present
    outcome_contributed = gate_passed
    status = "PASS" if outcome_contributed else "RETURN"
    reason = "bounded_probe_evidence_chain_pass" if status == "PASS" else "bounded_probe_evidence_chain_incomplete"
    return {
        **base,
        "status": status,
        "reason": reason,
        "selected": selected,
        "injected": injected,
        "used": used,
        "evidence_present": evidence_present,
        "gate_passed": gate_passed,
        "outcome_contributed": outcome_contributed,
        "capability_overlap": capability_overlap[:20],
        "evidence_overlap": evidence_overlap[:20],
        "skill_path": str(row.get("skill_path") or ""),
        "candidate_role": str(row.get("candidate_role") or ""),
        "candidate_score": int(row.get("candidate_score") or 0),
        "runtime_eligible": bool(row.get("runtime_eligible")),
        "ablation_eligible": bool(row.get("ablation_eligible")),
    }


def run_sf_bounded_probe(matrix: Mapping[str, Any]) -> dict[str, Any]:
    results = [evaluate_bounded_probe_row(row) for row in matrix.get("rows", []) or [] if isinstance(row, Mapping)]
    by_capability: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        by_capability.setdefault(result["capability_id"], []).append(result)
    capability_results = []
    flash_required = []
    for capability_id, rows in sorted(by_capability.items()):
        skill_rows = [row for row in rows if row["arm_type"] == "skill_arm"]
        passed = [row for row in skill_rows if row.get("outcome_contributed")]
        for row in passed:
            row["fit_score"] = (
                len(row.get("capability_overlap") or []) * 4
                + len(row.get("evidence_overlap") or []) * 2
                + int(row.get("candidate_score") or 0)
                + (3 if row.get("runtime_eligible") else 0)
                + (1 if row.get("candidate_role") == "canonical_top" else 0)
            )
        ranked = sorted(
            passed,
            key=lambda row: (
                -int(row.get("fit_score") or 0),
                row.get("candidate_role") != "current_pairing",
                row.get("skill_id", ""),
            ),
        )
        primary = ranked[0] if ranked else {}
        alternates = ranked[1:]
        rejected = [row for row in skill_rows if not row.get("outcome_contributed")]
        needs_flash = bool(
            len(ranked) > 1
            and ranked[0].get("fit_score") == ranked[1].get("fit_score")
            and ranked[0].get("candidate_role") != "current_pairing"
        )
        if needs_flash:
            flash_required.append(capability_id)
        capability_results.append(
            {
                "capability_id": capability_id,
                "status": "PASS" if primary else "NEEDS_FLASH_OR_SUPPLY_FIX",
                "primary_skill_id": primary.get("skill_id", ""),
                "primary_identity_id": primary.get("identity_id", ""),
                "alternate_skill_ids": [row.get("skill_id", "") for row in alternates],
                "reject_skill_ids": [row.get("skill_id", "") for row in rejected],
                "needs_flash_compare": needs_flash or not primary,
                "skill_arm_count": len(skill_rows),
                "passing_skill_arm_count": len(passed),
            }
        )
    status_counts = Counter(item["status"] for item in capability_results)
    return {
        "schema": "nexus.sf_bounded_probe_result.v1",
        "status": "PASS" if status_counts.get("NEEDS_FLASH_OR_SUPPLY_FIX", 0) == 0 else "PARTIAL",
        "summary": {
            "capability_count": len(capability_results),
            "capability_pass_count": status_counts.get("PASS", 0),
            "capability_needs_flash_or_supply_fix_count": status_counts.get("NEEDS_FLASH_OR_SUPPLY_FIX", 0),
            "row_count": len(results),
            "pass_row_count": sum(1 for row in results if row["status"] == "PASS"),
            "return_row_count": sum(1 for row in results if row["status"] != "PASS"),
            "flash_compare_required_count": len(flash_required),
            "public_benchmark_allowed": False,
        },
        "flash_compare_required_capabilities": sorted(flash_required),
        "capabilities": capability_results,
        "rows": results,
    }


def build_final_capability_skill_catalog(
    *,
    bounded_probe: Mapping[str, Any],
    evidence_gate: Mapping[str, Any],
) -> dict[str, Any]:
    entries = []
    blockers = []
    for item in bounded_probe.get("capabilities", []) or []:
        if not isinstance(item, Mapping):
            continue
        capability_id = str(item.get("capability_id") or "")
        primary = str(item.get("primary_skill_id") or "")
        needs_flash = bool(item.get("needs_flash_compare"))
        if not primary:
            blockers.append(f"{capability_id}:missing_primary_skill")
        entries.append(
            {
                "capability_id": capability_id,
                "primary_default": primary,
                "primary_identity_id": str(item.get("primary_identity_id") or ""),
                "alternate": list(item.get("alternate_skill_ids", []) or []),
                "combo_support": [],
                "reject": list(item.get("reject_skill_ids", []) or []),
                "evidence_level": "bounded_probe_pass" if primary else "needs_flash_or_supply_fix",
                "needs_flash_compare": needs_flash,
                "next_review_trigger": "new_skill_ingest_or_primary_regression",
            }
        )
    return {
        "schema": "nexus.sf_final_capability_skill_catalog_v2.v1",
        "status": "PASS" if not blockers else "PARTIAL",
        "summary": {
            "capability_count": len(entries),
            "capability_with_primary_count": sum(1 for item in entries if item["primary_default"]),
            "blocker_count": len(blockers),
            "flash_compare_required_count": sum(1 for item in entries if item["needs_flash_compare"]),
            "public_benchmark_allowed": False,
            "evidence_gate_schema": evidence_gate.get("schema", ""),
        },
        "blockers": blockers,
        "capability_skill_catalog": entries,
        "future_replacement_flow": [
            "ingest_new_skill",
            "dedup_by_root_relative_path_skill_id_sha256",
            "classify_into_route_capability_buckets",
            "run_capability_local_bounded_probe_against_current_primary",
            "promote_to_primary_only_when_evidence_chain_and_delta_pass",
            "otherwise_mark_alternate_reject_or_quarantine",
        ],
        "claim_boundary": [
            "This catalog completes SF pairing selection for bounded-probe evidence.",
            "It does not allow public benchmark until live route/policy gates explicitly pass.",
        ],
    }


def build_sf_paired_delta_report(
    *,
    matrix: Mapping[str, Any],
    bounded_probe: Mapping[str, Any],
    catalog: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare capability-only baseline with the chosen primary skill arm.

    This is an SF bounded-pair test, not a public benchmark. It proves the
    selected primary has a complete skill evidence chain for the capability; it
    does not claim a live solve-rate or cost delta.
    """

    rows_by_id = {
        str(row.get("row_id") or ""): row
        for row in bounded_probe.get("rows", []) or []
        if isinstance(row, Mapping)
    }
    matrix_by_capability: dict[str, list[Mapping[str, Any]]] = {}
    for row in matrix.get("rows", []) or []:
        if isinstance(row, Mapping):
            matrix_by_capability.setdefault(str(row.get("capability_id") or ""), []).append(row)

    deltas = []
    blockers = []
    for entry in catalog.get("capability_skill_catalog", []) or []:
        if not isinstance(entry, Mapping):
            continue
        capability_id = str(entry.get("capability_id") or "")
        primary_skill = str(entry.get("primary_default") or "")
        baseline_result = rows_by_id.get(f"{capability_id}::capability_only", {})
        primary_matrix_row = next(
            (
                row
                for row in matrix_by_capability.get(capability_id, [])
                if str(row.get("arm_type") or "") == "skill_arm"
                and str(row.get("skill_id") or "") == primary_skill
            ),
            {},
        )
        primary_result = rows_by_id.get(str(primary_matrix_row.get("row_id") or ""), {})
        skill_chain_pass = bool(
            primary_result.get("selected")
            and primary_result.get("injected")
            and primary_result.get("used")
            and primary_result.get("evidence_present")
            and primary_result.get("gate_passed")
            and primary_result.get("outcome_contributed")
        )
        baseline_pass = baseline_result.get("status") == "PASS"
        if not baseline_pass:
            blockers.append(f"{capability_id}:capability_only_not_pass")
        if not skill_chain_pass:
            blockers.append(f"{capability_id}:primary_skill_chain_not_pass")
        capability_terms_added = len(primary_result.get("capability_overlap") or [])
        evidence_terms_added = len(primary_result.get("evidence_overlap") or [])
        fit_score = int(primary_result.get("fit_score") or 0)
        bounded_delta = capability_terms_added + evidence_terms_added + fit_score
        deltas.append(
            {
                "capability_id": capability_id,
                "baseline_arm": "capability_only",
                "primary_skill_id": primary_skill,
                "baseline_status": baseline_result.get("status", ""),
                "with_skill_status": primary_result.get("status", ""),
                "selected": bool(primary_result.get("selected")),
                "injected": bool(primary_result.get("injected")),
                "used": bool(primary_result.get("used")),
                "evidence_present": bool(primary_result.get("evidence_present")),
                "gate_passed": bool(primary_result.get("gate_passed")),
                "outcome_contributed": bool(primary_result.get("outcome_contributed")),
                "capability_terms_added": capability_terms_added,
                "evidence_terms_added": evidence_terms_added,
                "bounded_fit_score_delta": bounded_delta,
                "live_solve_rate_delta": "not_measured_in_sf_bounded_delta",
                "cost_delta": "not_measured_in_sf_bounded_delta",
                "delta_status": "BOUNDED_POSITIVE" if baseline_pass and skill_chain_pass else "RETURN",
                "evidence_level": "bounded_paired_delta",
                "claim_boundary": "Do not use as public benchmark or live solve-rate claim.",
            }
        )

    return {
        "schema": "nexus.sf_paired_delta_report.v1",
        "status": "PASS" if not blockers else "PARTIAL",
        "summary": {
            "capability_count": len(deltas),
            "bounded_positive_delta_count": sum(1 for item in deltas if item["delta_status"] == "BOUNDED_POSITIVE"),
            "return_count": sum(1 for item in deltas if item["delta_status"] != "BOUNDED_POSITIVE"),
            "blocker_count": len(blockers),
            "live_delta_measured_count": 0,
            "public_benchmark_allowed": False,
        },
        "blockers": blockers,
        "deltas": deltas,
        "future_live_compare_flow": [
            "select_capability_or_changed_skill",
            "freeze_taskset_hidden_verifier_and_model",
            "run_capability_only_vs_primary_skill_paired_rows",
            "require_delivery_trust_receipt_and_cost_gates",
            "update_catalog_only_when_live_delta_confirms_bounded_delta",
        ],
    }


def build_sf_live_pair_compare_report(
    *,
    paired_delta: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the SF internal live-pair comparison report.

    The comparison is intentionally scoped to skill-fit receipts. It compares
    no-skill capability execution against the primary skill's mounted evidence
    chain and says whether a heavier Flash/Nexus run is still needed.
    """

    rows = []
    blockers = []
    flash_required = []
    for item in paired_delta.get("deltas", []) or []:
        if not isinstance(item, Mapping):
            continue
        capability_id = str(item.get("capability_id") or "")
        primary_skill_id = str(item.get("primary_skill_id") or "")
        bounded_delta = int(item.get("bounded_fit_score_delta") or 0)
        chain_pass = item.get("delta_status") == "BOUNDED_POSITIVE"
        needs_flash = not chain_pass
        if needs_flash:
            blockers.append(f"{capability_id}:live_pair_chain_not_positive")
            flash_required.append(capability_id)
        rows.append(
            {
                "capability_id": capability_id,
                "primary_skill_id": primary_skill_id,
                "no_skill_arm": {
                    "arm_type": "capability_only",
                    "status": str(item.get("baseline_status") or ""),
                    "skill_receipt_chain": False,
                    "outcome_contributed_by_skill": False,
                },
                "with_skill_arm": {
                    "arm_type": "with_primary_skill",
                    "status": str(item.get("with_skill_status") or ""),
                    "selected": bool(item.get("selected")),
                    "injected": bool(item.get("injected")),
                    "used": bool(item.get("used")),
                    "evidence_present": bool(item.get("evidence_present")),
                    "gate_passed": bool(item.get("gate_passed")),
                    "outcome_contributed_by_skill": bool(item.get("outcome_contributed")),
                },
                "difference": {
                    "skill_receipt_chain_added": chain_pass,
                    "bounded_fit_score_delta": bounded_delta,
                    "live_solve_rate_delta": "not_measured_by_internal_sf_pair_probe",
                    "cost_delta": "not_measured_by_internal_sf_pair_probe",
                    "trust_delta": "no_mismatch_observed_in_internal_sf_pair_probe" if chain_pass else "not_claimed",
                },
                "sf_live_pair_status": "PASS" if chain_pass else "RETURN",
                "needs_flash_nexus_compare": needs_flash,
                "flash_nexus_compare_reason": ""
                if not needs_flash
                else "internal_sf_pair_probe_cannot_establish_skill_receipt_delta",
            }
        )

    return {
        "schema": "nexus.sf_live_pair_compare_report.v1",
        "status": "PASS" if not blockers else "PARTIAL",
        "summary": {
            "capability_count": len(rows),
            "live_pair_pass_count": sum(1 for row in rows if row["sf_live_pair_status"] == "PASS"),
            "live_pair_return_count": sum(1 for row in rows if row["sf_live_pair_status"] != "PASS"),
            "flash_nexus_compare_required_count": len(flash_required),
            "live_solve_rate_delta_measured_count": 0,
            "cost_delta_measured_count": 0,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "blockers": blockers,
        "flash_nexus_compare_required_capabilities": sorted(flash_required),
        "comparisons": rows,
        "claim_boundary": [
            "This is an SF internal live-pair comparison of receipt chains.",
            "It shows what the primary skill adds over no-skill execution for SF evidence.",
            "It does not claim public solve-rate or provider-cost improvement.",
        ],
    }


def _metric_number(row: Mapping[str, Any], key: str) -> float | int | None:
    value = row.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _artifact_exists(output_dir: str | Path, pattern: str) -> bool:
    if not output_dir:
        return False
    root = Path(output_dir)
    return root.exists() and any(root.glob(pattern))


def build_sf_flash_pair_live_report(*, live_summary: Mapping[str, Any]) -> dict[str, Any]:
    """Compare Flash+Nexus rows with their Flash+Nexus+skill paired arm."""

    results = [row for row in live_summary.get("results", []) or [] if isinstance(row, Mapping)]
    by_key: dict[tuple[str, str], dict[str, Mapping[str, Any]]] = {}
    for row in results:
        capability_id = str(row.get("capability") or "")
        task_ref = row.get("task_ref") if isinstance(row.get("task_ref"), Mapping) else {}
        task_id = str(task_ref.get("task_id") or "")
        arm_id = str(row.get("arm_id") or "")
        if not capability_id or not task_id or not arm_id:
            continue
        by_key.setdefault((capability_id, task_id), {})[arm_id] = row

    comparisons: list[dict[str, Any]] = []
    blockers: list[str] = []
    for (capability_id, task_id), arms in sorted(by_key.items()):
        baseline = arms.get("flash_nexus")
        with_skill = arms.get("flash_nexus_with_skill")
        if baseline is None or with_skill is None:
            blockers.append(f"{capability_id}:{task_id}:missing_paired_arm")
            continue
        base_bench = baseline.get("benchmark_row") if isinstance(baseline.get("benchmark_row"), Mapping) else {}
        skill_bench = with_skill.get("benchmark_row") if isinstance(with_skill.get("benchmark_row"), Mapping) else {}
        skill_gate = with_skill.get("ablation_gate_row") if isinstance(with_skill.get("ablation_gate_row"), Mapping) else {}
        baseline_dir = str(baseline.get("output_dir") or "")
        skill_dir = str(with_skill.get("output_dir") or "")
        baseline_tokens = _metric_number(base_bench, "total_tokens")
        skill_tokens = _metric_number(skill_bench, "total_tokens")
        baseline_wall = _metric_number(base_bench, "phase_wall_total_sec")
        skill_wall = _metric_number(skill_bench, "phase_wall_total_sec")
        skill_chain_pass = all(
            bool(skill_gate.get(key))
            for key in ("selected", "injected", "used", "evidence_present", "gate_passed", "outcome_contributed")
        )
        baseline_pass = baseline.get("status") == "PASS" and base_bench.get("status") == "SUCCESS"
        skill_pass = with_skill.get("status") == "PASS" and skill_bench.get("status") == "SUCCESS"
        session_worker_clean = (
            base_bench.get("session_worker_enabled") is False
            and skill_bench.get("session_worker_enabled") is False
        )
        artifacts_present = all(
            [
                _artifact_exists(baseline_dir, "with_nexus_*.jsonl"),
                _artifact_exists(baseline_dir, "without_nexus_*.jsonl"),
                _artifact_exists(skill_dir, "with_nexus_*.jsonl"),
                _artifact_exists(skill_dir, "without_nexus_*.jsonl"),
                _artifact_exists(baseline_dir, "evidence_bundle.json"),
                _artifact_exists(skill_dir, "evidence_bundle.json"),
            ]
        )
        status = "KEEP" if baseline_pass and skill_pass and skill_chain_pass and session_worker_clean and artifacts_present else "RETURN"
        if status != "KEEP":
            blockers.append(f"{capability_id}:{task_id}:flash_pair_not_keep")
        comparisons.append(
            {
                "capability_id": capability_id,
                "task_id": task_id,
                "baseline_row_id": baseline.get("row_id", ""),
                "with_skill_row_id": with_skill.get("row_id", ""),
                "skill_id": with_skill.get("skill_id", ""),
                "same_runner_pair_artifacts": artifacts_present,
                "session_worker_clean": session_worker_clean,
                "baseline": {
                    "status": baseline.get("status", ""),
                    "benchmark_status": base_bench.get("status", ""),
                    "semantic_status": base_bench.get("semantic_status", ""),
                    "trust_mismatch": bool(base_bench.get("report_trust_mismatch")),
                    "model_calls": base_bench.get("model_calls", 0),
                    "total_tokens": baseline_tokens,
                    "phase_wall_total_sec": baseline_wall,
                    "output_dir": baseline_dir,
                },
                "with_skill": {
                    "status": with_skill.get("status", ""),
                    "benchmark_status": skill_bench.get("status", ""),
                    "semantic_status": skill_bench.get("semantic_status", ""),
                    "trust_mismatch": bool(skill_bench.get("report_trust_mismatch")),
                    "model_calls": skill_bench.get("model_calls", 0),
                    "total_tokens": skill_tokens,
                    "phase_wall_total_sec": skill_wall,
                    "output_dir": skill_dir,
                    "skill_mount_contract_status": skill_gate.get("skill_mount_contract_status", ""),
                    "selected": bool(skill_gate.get("selected")),
                    "injected": bool(skill_gate.get("injected")),
                    "used": bool(skill_gate.get("used")),
                    "evidence_present": bool(skill_gate.get("evidence_present")),
                    "gate_passed": bool(skill_gate.get("gate_passed")),
                    "outcome_contributed": bool(skill_gate.get("outcome_contributed")),
                },
                "delta": {
                    "token_delta": None
                    if baseline_tokens is None or skill_tokens is None
                    else skill_tokens - baseline_tokens,
                    "phase_wall_total_delta_sec": None
                    if baseline_wall is None or skill_wall is None
                    else round(float(skill_wall) - float(baseline_wall), 4),
                    "skill_causality_delta": "receipt_backed_skill_chain_present" if skill_chain_pass else "missing_skill_chain",
                    "delivery_delta": "paired_delivery_equal_or_clean" if baseline_pass and skill_pass else "delivery_not_comparable",
                    "cost_delta_status": "observation_only_not_promotion_gate",
                },
                "verdict": status,
            }
        )

    return {
        "schema": "nexus.sf_flash_pair_live_report.v1",
        "status": "PASS" if not blockers else "RETURN",
        "summary": {
            "comparison_count": len(comparisons),
            "keep_count": sum(1 for item in comparisons if item["verdict"] == "KEEP"),
            "return_count": sum(1 for item in comparisons if item["verdict"] != "KEEP"),
            "same_runner_pair_artifact_count": sum(1 for item in comparisons if item["same_runner_pair_artifacts"]),
            "session_worker_clean_count": sum(1 for item in comparisons if item["session_worker_clean"]),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "blockers": blockers,
        "comparisons": comparisons,
        "claim_boundary": [
            "This is SF live evidence for Flash+Nexus versus Flash+Nexus+skill.",
            "Rows are paired by capability and task in the same runner artifact shape.",
            "Token and wall deltas are observation-only and do not unlock public benchmark claims.",
        ],
    }


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
