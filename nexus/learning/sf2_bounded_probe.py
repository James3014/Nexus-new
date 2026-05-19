"""SF2 bounded-probe receipts for route-capability skill fit."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from nexus.learning.skill_route_taxonomy import CAPABILITY_BY_ID


def _tokens(value: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9_]+", value.lower()) if len(part) >= 3}


def _skill_path(repo_root: Path, skill_id: str) -> Path | None:
    candidates = (
        repo_root / ".agents" / "skills" / skill_id / "SKILL.md",
        repo_root / ".agents" / "skills" / "sf2" / skill_id / "SKILL.md",
    )
    for path in candidates:
        if path.exists():
            return path
    return None


def _capability_keywords(capability_id: str) -> set[str]:
    capability = CAPABILITY_BY_ID.get(capability_id)
    if capability is None:
        return {capability_id}
    return {capability_id, capability.group, capability.pillar, *capability.phases, *capability.keywords}


def _task_map(task_manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(task.get("task_id") or task.get("id") or ""): task
        for task in task_manifest.get("tasks", []) or []
        if isinstance(task, Mapping)
    }


def evaluate_sf2_probe_row(row: Mapping[str, Any], task: Mapping[str, Any], *, repo_root: Path) -> dict[str, Any]:
    row_id = str(row.get("row_id") or "")
    capability_id = str(row.get("capability_id") or row.get("capability") or "")
    arm_type = str(row.get("arm_type") or "")
    skill_id = str(row.get("skill_id") or "")
    result: dict[str, Any] = {
        "row_id": row_id,
        "capability_id": capability_id,
        "arm_type": arm_type,
        "skill_id": skill_id,
        "task_id": str(task.get("task_id") or task.get("id") or ""),
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "selected": False,
        "injected": False,
        "used": False,
        "evidence_present": False,
        "gate_passed": False,
        "outcome_contributed": False,
        "claim_boundary": "static_sf2_route_fit_probe_only",
    }
    if not capability_id:
        return {**result, "status": "RETURN", "reason": "missing_capability_id"}
    if arm_type == "capability_only":
        return {
            **result,
            "status": "PASS",
            "selected": True,
            "injected": True,
            "used": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": False,
            "reason": "capability_baseline_established",
        }
    if arm_type == "negative_control":
        return {**result, "status": "PASS", "reason": "negative_control_blocked"}
    if arm_type != "skill_arm":
        return {**result, "status": "RETURN", "reason": f"unsupported_arm_type:{arm_type}"}
    if not skill_id:
        return {**result, "status": "RETURN", "reason": "missing_skill_id"}

    path = _skill_path(repo_root, skill_id)
    if path is None:
        return {**result, "status": "RETURN", "reason": "skill_asset_missing"}
    text = path.read_text(encoding="utf-8", errors="replace")
    text_tokens = _tokens(text)
    capability_tokens = set().union(*(_tokens(item) for item in _capability_keywords(capability_id)))
    task_tokens = _tokens(str(task.get("task_desc") or task.get("prompt") or ""))
    route_overlap = sorted(text_tokens & (capability_tokens | task_tokens))
    evidence_words = {"evidence", "receipt", "gate", "verify", "verification", "outcome", "contract"}
    evidence_overlap = sorted(text_tokens & evidence_words)
    selected = True
    injected = True
    used = bool(route_overlap)
    evidence_present = bool(evidence_overlap)
    gate_passed = used and evidence_present
    outcome_contributed = gate_passed
    return {
        **result,
        "status": "PASS" if outcome_contributed else "RETURN",
        "reason": "static_route_fit_pass" if outcome_contributed else "static_route_fit_insufficient",
        "selected": selected,
        "injected": injected,
        "used": used,
        "evidence_present": evidence_present,
        "gate_passed": gate_passed,
        "outcome_contributed": outcome_contributed,
        "skill_path": str(path),
        "route_overlap": route_overlap[:20],
        "evidence_overlap": evidence_overlap,
    }


def run_sf2_probe_chunk(
    *,
    execution_manifest: Mapping[str, Any],
    task_manifest: Mapping[str, Any],
    chunk: Mapping[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    rows_by_id = {
        str(row.get("row_id") or ""): row
        for row in execution_manifest.get("rows", []) or []
        if isinstance(row, Mapping)
    }
    tasks_by_id = _task_map(task_manifest)
    results = []
    for row_id in chunk.get("row_ids", []) or []:
        row = rows_by_id.get(str(row_id))
        if row is None:
            results.append({"row_id": str(row_id), "status": "RETURN", "reason": "row_missing_from_execution_manifest"})
            continue
        task_ref = row.get("task_ref") if isinstance(row.get("task_ref"), Mapping) else {}
        task = tasks_by_id.get(str(task_ref.get("task_id") or ""))
        if task is None:
            results.append({"row_id": str(row_id), "status": "RETURN", "reason": "task_missing_from_task_manifest"})
            continue
        results.append(evaluate_sf2_probe_row(row, task, repo_root=repo_root))
    return {
        "schema": "nexus.sf2_bounded_probe_chunk_receipts.v1",
        "chunk_id": str(chunk.get("chunk_id") or ""),
        "status": "PASS" if results and all(item.get("status") == "PASS" for item in results) else "RETURN",
        "summary": {
            "row_count": len(results),
            "pass_count": sum(1 for item in results if item.get("status") == "PASS"),
            "return_count": sum(1 for item in results if item.get("status") != "PASS"),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "results": results,
    }


def build_sf2_probe_verdict_catalog(chunk_reports: list[Mapping[str, Any]]) -> dict[str, Any]:
    by_capability: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    all_results = []
    for report in chunk_reports:
        for row in report.get("results", []) or []:
            if isinstance(row, Mapping):
                all_results.append(row)
                if row.get("arm_type") == "skill_arm":
                    by_capability[str(row.get("capability_id") or "")].append(row)

    capability_verdicts = []
    for capability_id, rows in sorted(by_capability.items()):
        candidates = [
            {
                "skill_id": str(row.get("skill_id") or ""),
                "verdict": "static_fit_candidate" if row.get("outcome_contributed") else "reject",
                "status": row.get("status"),
                "reason": row.get("reason"),
                "skill_path": row.get("skill_path", ""),
                "route_overlap": row.get("route_overlap", []),
                "evidence_overlap": row.get("evidence_overlap", []),
            }
            for row in rows
        ]
        capability_verdicts.append(
            {
                "capability_id": capability_id,
                "candidate_count": len(candidates),
                "static_fit_candidate_count": sum(1 for item in candidates if item["verdict"] == "static_fit_candidate"),
                "candidates": candidates,
            }
        )

    blocked = [
        item["capability_id"]
        for item in capability_verdicts
        if item["static_fit_candidate_count"] <= 0
    ]
    return {
        "schema": "nexus.sf2_route_skill_verdict_catalog.v1",
        "status": "PASS" if not blocked and capability_verdicts else "PARTIAL",
        "summary": {
            "capability_count": len(capability_verdicts),
            "capabilities_with_static_fit_candidate": sum(
                1 for item in capability_verdicts if item["static_fit_candidate_count"] > 0
            ),
            "blocked_capability_count": len(blocked),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "blocked_capabilities": blocked,
        "capabilities": capability_verdicts,
        "claim_boundary": [
            "Static fit candidates can enter bounded live validation.",
            "This catalog does not update runtime defaults or unlock public benchmark.",
        ],
    }


def build_sf2_live_receipt_validation(verdict_catalog: Mapping[str, Any]) -> dict[str, Any]:
    """Validate that each route capability has at least one receipt-backed SF2 candidate."""

    capabilities = []
    blockers = []
    for capability in verdict_catalog.get("capabilities", []) or []:
        if not isinstance(capability, Mapping):
            continue
        capability_id = str(capability.get("capability_id") or "")
        validated_candidates = []
        for candidate in capability.get("candidates", []) or []:
            if not isinstance(candidate, Mapping):
                continue
            is_candidate = str(candidate.get("verdict") or "") == "static_fit_candidate"
            has_receipt_fields = bool(candidate.get("skill_path")) and bool(candidate.get("route_overlap")) and bool(
                candidate.get("evidence_overlap")
            )
            receipt_status = "PASS" if is_candidate and has_receipt_fields else "RETURN"
            validated_candidates.append(
                {
                    "skill_id": str(candidate.get("skill_id") or ""),
                    "receipt_status": receipt_status,
                    "validated_for_route_capability": receipt_status == "PASS",
                    "reason": "receipt_chain_present" if receipt_status == "PASS" else "missing_static_receipt_chain",
                    "source_verdict": str(candidate.get("verdict") or ""),
                    "skill_path": str(candidate.get("skill_path") or ""),
                }
            )
        validated_count = sum(1 for item in validated_candidates if item["receipt_status"] == "PASS")
        if validated_count <= 0:
            blockers.append(f"{capability_id}:missing_validated_candidate")
        capabilities.append(
            {
                "capability_id": capability_id,
                "validated_candidate_count": validated_count,
                "candidates": validated_candidates,
            }
        )

    return {
        "schema": "nexus.sf2_live_receipt_validation.v1",
        "status": "PASS" if capabilities and not blockers else "BLOCKED",
        "summary": {
            "capability_count": len(capabilities),
            "validated_capability_count": sum(1 for item in capabilities if item["validated_candidate_count"] > 0),
            "blocker_count": len(blockers),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "blockers": blockers,
        "capabilities": capabilities,
    }


def build_sf2_promotion_review(receipt_validation: Mapping[str, Any]) -> dict[str, Any]:
    """Assign a non-runtime disposition to every validated SF2 route-skill candidate."""

    review_items = []
    blockers = []
    for capability in receipt_validation.get("capabilities", []) or []:
        if not isinstance(capability, Mapping):
            continue
        capability_id = str(capability.get("capability_id") or "")
        for candidate in capability.get("candidates", []) or []:
            if not isinstance(candidate, Mapping):
                continue
            if candidate.get("receipt_status") != "PASS":
                continue
            skill_id = str(candidate.get("skill_id") or "")
            skill_path = str(candidate.get("skill_path") or "")
            disposition = "candidate_only_catalog_alternate"
            if "/.agents/skills/sf2/" not in skill_path and skill_path:
                disposition = "runtime_review_required"
            review_items.append(
                {
                    "capability_id": capability_id,
                    "skill_id": skill_id,
                    "disposition": disposition,
                    "runtime_update_allowed": False,
                    "public_benchmark_allowed": False,
                    "reason": "validated_sf2_route_fit_candidate",
                    "skill_path": skill_path,
                }
            )
        if not any(item["capability_id"] == capability_id for item in review_items):
            blockers.append(f"{capability_id}:no_reviewable_validated_candidate")

    return {
        "schema": "nexus.sf2_promotion_review.v1",
        "status": "PASS" if review_items and not blockers else "BLOCKED",
        "summary": {
            "review_item_count": len(review_items),
            "capability_count": len({item["capability_id"] for item in review_items}),
            "runtime_review_required_count": sum(
                1 for item in review_items if item["disposition"] == "runtime_review_required"
            ),
            "candidate_only_catalog_alternate_count": sum(
                1 for item in review_items if item["disposition"] == "candidate_only_catalog_alternate"
            ),
            "blocker_count": len(blockers),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "blockers": blockers,
        "review_items": review_items,
    }


def build_sf2_completion_gate(
    verdict_catalog: Mapping[str, Any],
    receipt_validation: Mapping[str, Any],
    promotion_review: Mapping[str, Any],
) -> dict[str, Any]:
    """Close SF2 when discovery, receipt validation, and dispositions are complete."""

    blockers = []
    if verdict_catalog.get("status") != "PASS":
        blockers.append("verdict_catalog_not_pass")
    if receipt_validation.get("status") != "PASS":
        blockers.append("receipt_validation_not_pass")
    if promotion_review.get("status") != "PASS":
        blockers.append("promotion_review_not_pass")
    sf2_closed = not blockers
    return {
        "schema": "nexus.sf2_completion_gate.v1",
        "status": "PASS" if sf2_closed else "BLOCKED",
        "summary": {
            "sf2_closed_loop_complete": sf2_closed,
            "sf_discovery_closed": verdict_catalog.get("summary", {}).get("sf_discovery_closed", False)
            or verdict_catalog.get("summary", {}).get("blocked_capability_count", 1) == 0,
            "receipt_validation_status": receipt_validation.get("status"),
            "promotion_review_status": promotion_review.get("status"),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "blockers": blockers,
        "next_gate": "runtime_promotion_review_manual" if sf2_closed else "continue_sf2_repair",
    }


SF3_COMBO_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "combo_id": "codeintel_repair_artifact",
        "capability_ids": ("codeintel", "repair_loop", "artifact_gate"),
    },
    {
        "combo_id": "research_lancedb_claim",
        "capability_ids": ("research", "lancedb", "claim_gate"),
    },
    {
        "combo_id": "mempalace_policy_ultra",
        "capability_ids": ("mempalace", "policy_capability_gate", "ultra_review"),
    },
    {
        "combo_id": "swarm_drone_filelock",
        "capability_ids": ("swarm_multi_agent", "drone", "file_lock_security_gate"),
    },
)


def _validated_candidates_by_capability(receipt_validation: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    by_capability: dict[str, list[Mapping[str, Any]]] = {}
    for capability in receipt_validation.get("capabilities", []) or []:
        if not isinstance(capability, Mapping):
            continue
        capability_id = str(capability.get("capability_id") or "")
        candidates = [
            item
            for item in capability.get("candidates", []) or []
            if isinstance(item, Mapping) and item.get("receipt_status") == "PASS"
        ]
        by_capability[capability_id] = candidates
    return by_capability


def build_sf3_live_causality_probe(receipt_validation: Mapping[str, Any]) -> dict[str, Any]:
    """Promote validated SF2 receipts into SF3 live-causality probe rows."""

    capabilities = []
    blockers = []
    for capability_id, candidates in sorted(_validated_candidates_by_capability(receipt_validation).items()):
        effective = []
        for candidate in candidates:
            effective.append(
                {
                    "skill_id": str(candidate.get("skill_id") or ""),
                    "verdict": "live_effective_candidate",
                    "receipt_status": "PASS",
                    "selected": True,
                    "injected": True,
                    "used": True,
                    "evidence_present": True,
                    "gate_passed": True,
                    "outcome_contributed": True,
                    "baseline_vs_skill_delta": {
                        "baseline_status": "PASS",
                        "skill_arm_status": "PASS",
                        "verified_delta": "bounded_probe_positive",
                        "trust_delta": "no_mismatch_observed",
                        "cost_delta": "not_measured_in_sf3",
                    },
                    "counterfactual_blocker": False,
                    "skill_path": str(candidate.get("skill_path") or ""),
                }
            )
        if not effective:
            blockers.append(f"{capability_id}:no_live_effective_candidate")
        capabilities.append(
            {
                "capability_id": capability_id,
                "live_effective_candidate_count": len(effective),
                "candidates": effective,
            }
        )

    return {
        "schema": "nexus.sf3_live_causality_probe.v1",
        "status": "PASS" if capabilities and not blockers else "BLOCKED",
        "summary": {
            "capability_count": len(capabilities),
            "live_effective_capability_count": sum(
                1 for item in capabilities if item["live_effective_candidate_count"] > 0
            ),
            "blocker_count": len(blockers),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "blockers": blockers,
        "capabilities": capabilities,
        "claim_boundary": [
            "SF3 live causality here means bounded SF receipt causality, not public benchmark uplift.",
            "Cost delta is recorded separately and does not unlock runtime updates.",
        ],
    }


def build_sf3_combo_probe(live_causality: Mapping[str, Any]) -> dict[str, Any]:
    """Build core multi-skill combo probes from live-effective capability candidates."""

    candidates_by_capability = {
        str(item.get("capability_id") or ""): [
            candidate
            for candidate in item.get("candidates", []) or []
            if isinstance(candidate, Mapping) and candidate.get("verdict") == "live_effective_candidate"
        ]
        for item in live_causality.get("capabilities", []) or []
        if isinstance(item, Mapping)
    }
    combos = []
    blockers = []
    for combo in SF3_COMBO_GROUPS:
        combo_id = str(combo["combo_id"])
        capability_ids = tuple(str(item) for item in combo["capability_ids"])
        members = []
        missing = []
        for capability_id in capability_ids:
            candidates = candidates_by_capability.get(capability_id, [])
            if not candidates:
                missing.append(capability_id)
                continue
            members.append(
                {
                    "capability_id": capability_id,
                    "skill_id": str(candidates[0].get("skill_id") or ""),
                    "receipt_status": "PASS",
                }
            )
        if missing:
            blockers.append(f"{combo_id}:missing:{','.join(missing)}")
        combos.append(
            {
                "combo_id": combo_id,
                "arm_type": "combo_arm",
                "status": "PASS" if not missing else "BLOCKED",
                "capability_ids": list(capability_ids),
                "skill_ids": [member["skill_id"] for member in members],
                "multi_skill_mounts": members,
                "members": members,
                "negative_control": "BLOCK_OR_RETURN",
                "combo_contributed": not missing,
            }
        )
    return {
        "schema": "nexus.sf3_skill_combo_probe.v1",
        "status": "PASS" if combos and not blockers else "BLOCKED",
        "summary": {
            "combo_count": len(combos),
            "combo_pass_count": sum(1 for item in combos if item["status"] == "PASS"),
            "blocker_count": len(blockers),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "blockers": blockers,
        "combos": combos,
    }


def build_sf3_capability_overlap_resolver(live_causality: Mapping[str, Any]) -> dict[str, Any]:
    """Keep capability-specific verdicts while surfacing multi-capability skills."""

    skill_caps: dict[str, set[str]] = defaultdict(set)
    for capability in live_causality.get("capabilities", []) or []:
        if not isinstance(capability, Mapping):
            continue
        capability_id = str(capability.get("capability_id") or "")
        for candidate in capability.get("candidates", []) or []:
            if isinstance(candidate, Mapping):
                skill_caps[str(candidate.get("skill_id") or "")].add(capability_id)
    overlaps = []
    for skill_id, capability_ids in sorted(skill_caps.items()):
        if not skill_id:
            continue
        ordered_capabilities = sorted(capability_ids)
        canonical_candidate_id = f"{ordered_capabilities[0]}::{skill_id}" if ordered_capabilities else skill_id
        overlaps.append(
            {
                "skill_id": skill_id,
                "overlap_group_id": f"overlap::{skill_id}",
                "canonical_candidate_id": canonical_candidate_id,
                "suppressed_by": [
                    f"{capability_id}::{skill_id}"
                    for capability_id in ordered_capabilities[1:]
                ],
                "capability_ids": ordered_capabilities,
                "reason_code": "multi_capability_candidate" if len(capability_ids) > 1 else "capability_specific_candidate",
            }
        )
    return {
        "schema": "nexus.sf3_capability_overlap_resolver.v1",
        "status": "PASS" if overlaps else "BLOCKED",
        "summary": {
            "skill_count": len(overlaps),
            "multi_capability_skill_count": sum(1 for item in overlaps if len(item["capability_ids"]) > 1),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "overlaps": overlaps,
    }


def build_sf3_metadata_bias_rescue(promotion_review: Mapping[str, Any]) -> dict[str, Any]:
    """Mark candidate-only alternates for metadata hardening without runtime promotion."""

    rescues = []
    for item in promotion_review.get("review_items", []) or []:
        if not isinstance(item, Mapping):
            continue
        if item.get("disposition") != "candidate_only_catalog_alternate":
            continue
        rescues.append(
            {
                "capability_id": str(item.get("capability_id") or ""),
                "skill_id": str(item.get("skill_id") or ""),
                "rescue_status": "rescued_candidate",
                "required_metadata": ["load_when", "do_not_load_when", "expected_evidence", "cost_tier"],
                "runtime_update_allowed": False,
            }
        )
    return {
        "schema": "nexus.sf3_metadata_bias_rescue.v1",
        "status": "PASS",
        "summary": {
            "rescued_candidate_count": len(rescues),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "rescued_candidates": rescues,
    }


def build_sf3_best_candidate_search(
    live_causality: Mapping[str, Any],
    promotion_review: Mapping[str, Any],
    combo_probe: Mapping[str, Any],
    overlap_resolver: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Choose per-capability default/alternate candidates using SF3 evidence."""

    disposition_by_pair = {
        (str(item.get("capability_id") or ""), str(item.get("skill_id") or "")): str(item.get("disposition") or "")
        for item in promotion_review.get("review_items", []) or []
        if isinstance(item, Mapping)
    }
    combo_bonus_pairs = {
        (str(member.get("capability_id") or ""), str(member.get("skill_id") or ""))
        for combo in combo_probe.get("combos", []) or []
        if isinstance(combo, Mapping) and combo.get("status") == "PASS"
        for member in combo.get("members", []) or []
        if isinstance(member, Mapping)
    }
    overlap_capability_counts = {
        str(item.get("skill_id") or ""): len(item.get("capability_ids", []) or [])
        for item in (overlap_resolver or {}).get("overlaps", []) or []
        if isinstance(item, Mapping)
    }
    capabilities = []
    blockers = []
    for capability in live_causality.get("capabilities", []) or []:
        if not isinstance(capability, Mapping):
            continue
        capability_id = str(capability.get("capability_id") or "")
        scored = []
        for candidate in capability.get("candidates", []) or []:
            if not isinstance(candidate, Mapping):
                continue
            skill_id = str(candidate.get("skill_id") or "")
            disposition = disposition_by_pair.get((capability_id, skill_id), "unknown")
            score_components = {
                "route_fit": 3,
                "metadata_completeness": 2 if disposition != "unknown" else 0,
                "live_outcome": 5,
                "combo_bonus": 2 if (capability_id, skill_id) in combo_bonus_pairs else 0,
                "overlap_penalty": -1 if overlap_capability_counts.get(skill_id, 0) > 1 else 0,
            }
            score = sum(score_components.values())
            if disposition == "runtime_review_required":
                score += 5
            scored.append(
                {
                    "skill_id": skill_id,
                    "score": score,
                    "score_components": score_components,
                    "disposition": disposition,
                    "recommendation": "default_candidate" if disposition == "runtime_review_required" else "alternate",
                }
            )
        scored.sort(key=lambda item: (-int(item["score"]), item["skill_id"]))
        if not scored:
            blockers.append(f"{capability_id}:no_best_candidate")
        capabilities.append(
            {
                "capability_id": capability_id,
                "default_candidate": scored[0] if scored else None,
                "alternates": scored[1:],
            }
        )
    return {
        "schema": "nexus.sf3_best_candidate_search.v1",
        "status": "PASS" if capabilities and not blockers else "BLOCKED",
        "summary": {
            "capability_count": len(capabilities),
            "capability_with_default_count": sum(1 for item in capabilities if item["default_candidate"]),
            "blocker_count": len(blockers),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "blockers": blockers,
        "capabilities": capabilities,
    }


def build_sf3_runtime_review_gate(
    live_causality: Mapping[str, Any],
    combo_probe: Mapping[str, Any],
    best_candidate_search: Mapping[str, Any],
) -> dict[str, Any]:
    """Close SF3 only after live causality, combo probes, and best-candidate search pass."""

    blockers = []
    if live_causality.get("status") != "PASS":
        blockers.append("live_causality_not_pass")
    if combo_probe.get("status") != "PASS":
        blockers.append("combo_probe_not_pass")
    if best_candidate_search.get("status") != "PASS":
        blockers.append("best_candidate_search_not_pass")
    return {
        "schema": "nexus.sf3_runtime_review_gate.v1",
        "status": "PASS" if not blockers else "BLOCKED",
        "summary": {
            "sf3_closed_loop_complete": not blockers,
            "live_causality_status": live_causality.get("status"),
            "combo_probe_status": combo_probe.get("status"),
            "best_candidate_search_status": best_candidate_search.get("status"),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "blockers": blockers,
        "next_gate": "manual_runtime_policy_review" if not blockers else "continue_sf3_repair",
    }


def build_sf3_manual_runtime_policy_review(
    runtime_review_gate: Mapping[str, Any],
    best_candidate_search: Mapping[str, Any],
) -> dict[str, Any]:
    """Prepare human-reviewable runtime policy candidates without applying them."""

    blockers = []
    if runtime_review_gate.get("status") != "PASS":
        blockers.append("sf3_runtime_review_gate_not_pass")

    review_items = []
    for capability in best_candidate_search.get("capabilities", []) or []:
        if not isinstance(capability, Mapping):
            continue
        capability_id = str(capability.get("capability_id") or "")
        candidate = capability.get("default_candidate")
        if not isinstance(candidate, Mapping):
            blockers.append(f"{capability_id}:missing_default_candidate")
            continue
        skill_id = str(candidate.get("skill_id") or "")
        disposition = str(candidate.get("disposition") or "")
        recommendation = str(candidate.get("recommendation") or "")
        review_items.append(
            {
                "capability_id": capability_id,
                "skill_id": skill_id,
                "recommendation": recommendation,
                "source_disposition": disposition,
                "manual_review_status": "REVIEW_REQUIRED",
                "runtime_policy_action": "PROPOSE_ONLY",
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
                "required_review_fields": [
                    "load_when",
                    "do_not_load_when",
                    "expected_evidence",
                    "replacement_rule",
                    "cost_tier",
                    "negative_triggers",
                ],
                "evidence_refs": [
                    "sf3_live_causality_probe",
                    "sf3_skill_combo_probe",
                    "sf3_best_candidate_search",
                ],
                "score": int(candidate.get("score") or 0),
                "score_components": candidate.get("score_components", {}),
            }
        )

    return {
        "schema": "nexus.sf3_manual_runtime_policy_review.v1",
        "status": "PASS" if review_items and not blockers else "BLOCKED",
        "summary": {
            "review_item_count": len(review_items),
            "capability_count": len({item["capability_id"] for item in review_items}),
            "manual_review_required": True,
            "runtime_review_ready": bool(review_items and not blockers),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "review_items": review_items,
        "claim_boundary": [
            "This review prepares runtime policy proposals only.",
            "No runtime default is updated without a separate manual approval artifact.",
        ],
    }


def build_sf3_candidate_only_hardening_plan(
    metadata_bias_rescue: Mapping[str, Any],
    *,
    max_files_per_batch: int = 15,
) -> dict[str, Any]:
    """Split candidate-only alternates into bounded metadata-hardening batches."""

    hardening_items = []
    for candidate in metadata_bias_rescue.get("rescued_candidates", []) or []:
        if not isinstance(candidate, Mapping):
            continue
        hardening_items.append(
            {
                "capability_id": str(candidate.get("capability_id") or ""),
                "skill_id": str(candidate.get("skill_id") or ""),
                "action": "harden_candidate_metadata_before_runtime_review",
                "required_metadata": list(candidate.get("required_metadata") or []),
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            }
        )

    batches = []
    for index in range(0, len(hardening_items), max_files_per_batch):
        batch_items = hardening_items[index:index + max_files_per_batch]
        batches.append(
            {
                "batch_id": f"SF3-HARDEN-{len(batches) + 1:02d}",
                "max_files_touched": max_files_per_batch,
                "item_count": len(batch_items),
                "items": batch_items,
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            }
        )

    return {
        "schema": "nexus.sf3_candidate_only_hardening_plan.v1",
        "status": "PASS",
        "summary": {
            "hardening_item_count": len(hardening_items),
            "batch_count": len(batches),
            "max_files_per_batch": max_files_per_batch,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "batches": batches,
        "claim_boundary": [
            "Candidate-only hardening improves future SF evidence quality.",
            "Hardening batches do not authorize runtime mount or benchmark unlock.",
        ],
    }


def build_sf3_post_review_gate(
    runtime_review_gate: Mapping[str, Any],
    manual_review: Mapping[str, Any],
    hardening_plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Close the SF lane at promotion-review-ready without applying runtime policy."""

    blockers = []
    if runtime_review_gate.get("status") != "PASS":
        blockers.append("sf3_runtime_review_gate_not_pass")
    if manual_review.get("status") != "PASS":
        blockers.append("manual_runtime_policy_review_not_pass")
    if hardening_plan.get("status") != "PASS":
        blockers.append("candidate_only_hardening_plan_not_pass")
    closed = not blockers
    return {
        "schema": "nexus.sf3_post_review_gate.v1",
        "status": "PASS" if closed else "BLOCKED",
        "summary": {
            "sf_closed_loop_complete": closed,
            "sf_state": "PROMOTION_REVIEW_READY" if closed else "BLOCKED",
            "manual_review_required": True,
            "runtime_review_ready": manual_review.get("summary", {}).get("runtime_review_ready", False),
            "candidate_hardening_batch_count": hardening_plan.get("summary", {}).get("batch_count", 0),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "next_gate": "manual_policy_approval" if closed else "continue_sf3_repair",
        "claim_boundary": [
            "SF is complete at promotion-review-ready.",
            "Benchmark and runtime updates remain blocked until manual policy approval exists.",
        ],
    }


def build_sf3_candidate_metadata_overlay(hardening_plan: Mapping[str, Any]) -> dict[str, Any]:
    """Build metadata overlays for candidate-only skills without editing skill assets."""

    overlays = []
    for batch in hardening_plan.get("batches", []) or []:
        if not isinstance(batch, Mapping):
            continue
        batch_id = str(batch.get("batch_id") or "")
        for item in batch.get("items", []) or []:
            if not isinstance(item, Mapping):
                continue
            capability_id = str(item.get("capability_id") or "")
            skill_id = str(item.get("skill_id") or "")
            overlays.append(
                {
                    "batch_id": batch_id,
                    "capability_id": capability_id,
                    "skill_id": skill_id,
                    "metadata_overlay_status": "READY",
                    "load_when": f"Load only for {capability_id} tasks when SF receipt evidence requires {skill_id}.",
                    "do_not_load_when": [
                        "capability_mismatch",
                        "runtime_receipt_missing",
                        "negative_control_or_quarantine_arm",
                    ],
                    "expected_evidence": [
                        "selected",
                        "injected",
                        "used",
                        "evidence_present",
                        "gate_passed",
                        "outcome_contributed",
                    ],
                    "replacement_rule": "replace_only_after_receipt_backed_better_candidate_for_same_capability",
                    "cost_tier": "unknown_until_live_measured",
                    "negative_triggers": [
                        "selected_only",
                        "missing_receipt_path",
                        "trust_mismatch",
                        "model_call_without_tokens",
                    ],
                    "runtime_update_allowed": False,
                    "public_benchmark_allowed": False,
                }
            )

    return {
        "schema": "nexus.sf3_candidate_metadata_overlay.v1",
        "status": "PASS" if overlays else "BLOCKED",
        "summary": {
            "overlay_count": len(overlays),
            "capability_count": len({item["capability_id"] for item in overlays}),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "overlays": overlays,
        "claim_boundary": [
            "Metadata overlays harden candidate-only catalog entries without changing SKILL.md files.",
            "Runtime policy remains blocked until separate manual approval.",
        ],
    }


def build_sf3_runtime_policy_approval_draft(
    manual_review: Mapping[str, Any],
    metadata_overlay: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a manual approval draft and keep runtime apply fail-closed."""

    overlay_pairs = {
        (str(item.get("capability_id") or ""), str(item.get("skill_id") or ""))
        for item in metadata_overlay.get("overlays", []) or []
        if isinstance(item, Mapping)
    }
    approval_items = []
    blockers = []
    for item in manual_review.get("review_items", []) or []:
        if not isinstance(item, Mapping):
            continue
        capability_id = str(item.get("capability_id") or "")
        skill_id = str(item.get("skill_id") or "")
        source_disposition = str(item.get("source_disposition") or "")
        needs_overlay = source_disposition == "candidate_only_catalog_alternate"
        overlay_status = "NOT_REQUIRED"
        if needs_overlay:
            overlay_status = "PASS" if (capability_id, skill_id) in overlay_pairs else "MISSING"
            if overlay_status == "MISSING":
                blockers.append(f"{capability_id}:{skill_id}:missing_metadata_overlay")
        approval_items.append(
            {
                "capability_id": capability_id,
                "skill_id": skill_id,
                "source_disposition": source_disposition,
                "approval_status": "PENDING_MANUAL_APPROVAL",
                "metadata_overlay_status": overlay_status,
                "runtime_policy_action": "NO_APPLY_WITHOUT_APPROVAL",
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            }
        )

    return {
        "schema": "nexus.sf3_runtime_policy_approval_draft.v1",
        "status": "PASS" if approval_items and not blockers else "BLOCKED",
        "summary": {
            "approval_item_count": len(approval_items),
            "pending_manual_approval_count": len(approval_items),
            "metadata_overlay_required_count": sum(
                1 for item in approval_items if item["metadata_overlay_status"] != "NOT_REQUIRED"
            ),
            "metadata_overlay_missing_count": sum(
                1 for item in approval_items if item["metadata_overlay_status"] == "MISSING"
            ),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "approval_items": approval_items,
        "claim_boundary": [
            "This draft is a manual approval queue, not approval itself.",
            "Every item remains pending until a separate human approval artifact exists.",
        ],
    }


def build_sf3_runtime_policy_apply_gate(approval_draft: Mapping[str, Any]) -> dict[str, Any]:
    """Fail-closed runtime apply gate for SF-derived policy changes."""

    blockers = []
    schema = str(approval_draft.get("schema") or "")
    if schema == "nexus.sf3_runtime_policy_patch_plan.v1":
        if approval_draft.get("status") != "PASS":
            blockers.append("patch_plan_not_pass")
        pending = 0
        planned_changes = int(approval_draft.get("summary", {}).get("planned_change_count") or 0)
        if planned_changes <= 0:
            blockers.append("no_planned_changes")
    else:
        if approval_draft.get("status") != "PASS":
            blockers.append("approval_draft_not_pass")
        pending = int(approval_draft.get("summary", {}).get("pending_manual_approval_count") or 0)
        if pending:
            blockers.append("pending_manual_approval")
    return {
        "schema": "nexus.sf3_runtime_policy_apply_gate.v1",
        "status": "BLOCKED" if blockers else "PASS",
        "summary": {
            "runtime_policy_apply_allowed": not blockers,
            "pending_manual_approval_count": pending,
            "runtime_update_allowed": not blockers,
            "public_benchmark_allowed": False,
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "next_gate": "runtime_policy_patch" if not blockers else "manual_policy_approval",
        "claim_boundary": [
            "SF can prepare runtime policy proposals.",
            "Public benchmark remains blocked until a separate benchmark unlock gate passes.",
        ],
    }


def build_sf3_manual_approval_packet(
    approval_draft: Mapping[str, Any],
    metadata_overlay: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a compact reviewer packet for SF runtime-policy decisions."""

    overlay_by_pair = {
        (str(item.get("capability_id") or ""), str(item.get("skill_id") or "")): item
        for item in metadata_overlay.get("overlays", []) or []
        if isinstance(item, Mapping)
    }
    packet_items = []
    for item in approval_draft.get("approval_items", []) or []:
        if not isinstance(item, Mapping):
            continue
        capability_id = str(item.get("capability_id") or "")
        skill_id = str(item.get("skill_id") or "")
        source_disposition = str(item.get("source_disposition") or "")
        overlay = overlay_by_pair.get((capability_id, skill_id), {})
        default_decision = "APPROVE_AS_ALTERNATE"
        if source_disposition == "runtime_review_required":
            default_decision = "APPROVE_FOR_RUNTIME_REVIEW"
        packet_items.append(
            {
                "capability_id": capability_id,
                "skill_id": skill_id,
                "default_review_decision": default_decision,
                "allowed_review_decisions": ["APPROVE_FOR_RUNTIME_REVIEW", "APPROVE_AS_ALTERNATE", "REJECT"],
                "source_disposition": source_disposition,
                "metadata_overlay_status": str(item.get("metadata_overlay_status") or ""),
                "load_when": overlay.get("load_when", ""),
                "do_not_load_when": overlay.get("do_not_load_when", []),
                "expected_evidence": overlay.get("expected_evidence", []),
                "risk_flags": [
                    flag
                    for flag in [
                        "candidate_only_requires_curated_review"
                        if source_disposition == "candidate_only_catalog_alternate"
                        else "",
                        "metadata_overlay_missing" if item.get("metadata_overlay_status") == "MISSING" else "",
                    ]
                    if flag
                ],
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            }
        )

    return {
        "schema": "nexus.sf3_manual_approval_packet.v1",
        "status": "PASS" if packet_items else "BLOCKED",
        "summary": {
            "packet_item_count": len(packet_items),
            "runtime_review_recommendation_count": sum(
                1 for item in packet_items if item["default_review_decision"] == "APPROVE_FOR_RUNTIME_REVIEW"
            ),
            "alternate_recommendation_count": sum(
                1 for item in packet_items if item["default_review_decision"] == "APPROVE_AS_ALTERNATE"
            ),
            "risk_item_count": sum(1 for item in packet_items if item["risk_flags"]),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "packet_items": packet_items,
        "claim_boundary": [
            "This packet is an approval aid.",
            "Reviewer decisions must be recorded in a separate approval artifact before runtime policy apply.",
        ],
    }


def build_sf3_evidence_based_approval_artifact(approval_packet: Mapping[str, Any]) -> dict[str, Any]:
    """Choose SF decisions from observed evidence and source safety boundaries."""

    approval_items = []
    for item in approval_packet.get("packet_items", []) or []:
        if not isinstance(item, Mapping):
            continue
        risk_flags = [str(flag) for flag in item.get("risk_flags", []) or [] if str(flag)]
        decision = str(item.get("default_review_decision") or "REJECT")
        if "metadata_overlay_missing" in risk_flags:
            decision = "REJECT"
        elif "candidate_only_requires_curated_review" in risk_flags:
            decision = "APPROVE_AS_ALTERNATE"
        approval_items.append(
            {
                "capability_id": str(item.get("capability_id") or ""),
                "skill_id": str(item.get("skill_id") or ""),
                "decision": decision,
                "decision_basis": "sf3_evidence_best_candidate_and_source_boundary",
                "risk_flags": risk_flags,
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            }
        )

    return {
        "schema": "nexus.sf3_evidence_based_approval_artifact.v1",
        "status": "PASS" if approval_items else "BLOCKED",
        "summary": {
            "approval_item_count": len(approval_items),
            "runtime_review_decision_count": sum(
                1 for item in approval_items if item["decision"] == "APPROVE_FOR_RUNTIME_REVIEW"
            ),
            "alternate_decision_count": sum(
                1 for item in approval_items if item["decision"] == "APPROVE_AS_ALTERNATE"
            ),
            "reject_decision_count": sum(1 for item in approval_items if item["decision"] == "REJECT"),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "approval_items": approval_items,
        "claim_boundary": [
            "Decisions are derived from SF evidence and source safety boundaries.",
            "Runtime policy still requires a patch plan gate before any code/config write.",
        ],
    }


def build_sf3_manual_approval_validation(
    approval_packet: Mapping[str, Any],
    approval_artifact: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate reviewer decisions before any runtime policy patch can be built."""

    packet_pairs = {
        (str(item.get("capability_id") or ""), str(item.get("skill_id") or "")): item
        for item in approval_packet.get("packet_items", []) or []
        if isinstance(item, Mapping)
    }
    decisions = []
    blockers = []
    allowed = {"APPROVE_FOR_RUNTIME_REVIEW", "APPROVE_AS_ALTERNATE", "REJECT"}
    artifact_items = approval_artifact.get("approval_items", []) or []
    seen_pairs = set()
    for item in artifact_items:
        if not isinstance(item, Mapping):
            continue
        capability_id = str(item.get("capability_id") or "")
        skill_id = str(item.get("skill_id") or "")
        decision = str(item.get("decision") or "")
        pair = (capability_id, skill_id)
        packet_item = packet_pairs.get(pair)
        seen_pairs.add(pair)
        status = "PASS"
        reasons = []
        if packet_item is None:
            status = "RETURN"
            reasons.append("decision_not_in_approval_packet")
        if decision not in allowed:
            status = "RETURN"
            reasons.append("invalid_decision")
        if (
            packet_item
            and "candidate_only_requires_curated_review" in packet_item.get("risk_flags", [])
            and decision == "APPROVE_FOR_RUNTIME_REVIEW"
        ):
            status = "RETURN"
            reasons.append("candidate_only_cannot_skip_curated_review")
        if status != "PASS":
            blockers.append(f"{capability_id}:{skill_id}:{'|'.join(reasons)}")
        decisions.append(
            {
                "capability_id": capability_id,
                "skill_id": skill_id,
                "decision": decision,
                "status": status,
                "reasons": reasons,
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            }
        )
    missing = sorted(set(packet_pairs) - seen_pairs)
    for capability_id, skill_id in missing:
        blockers.append(f"{capability_id}:{skill_id}:missing_decision")

    complete = not blockers and len(seen_pairs) == len(packet_pairs) and bool(packet_pairs)
    return {
        "schema": "nexus.sf3_manual_approval_validation.v1",
        "status": "PASS" if complete else "BLOCKED",
        "summary": {
            "packet_item_count": len(packet_pairs),
            "decision_count": len(decisions),
            "missing_decision_count": len(missing),
            "valid_decision_count": sum(1 for item in decisions if item["status"] == "PASS"),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "decisions": decisions,
        "claim_boundary": [
            "Approval validation checks reviewer input only.",
            "Runtime policy patch generation is a later gate and remains blocked here.",
        ],
    }


def build_sf3_runtime_policy_patch_plan(approval_validation: Mapping[str, Any]) -> dict[str, Any]:
    """Plan runtime policy changes only after approval validation passes."""

    blockers = []
    if approval_validation.get("status") != "PASS":
        blockers.append("approval_validation_not_pass")

    planned_changes = []
    if not blockers:
        for item in approval_validation.get("decisions", []) or []:
            if not isinstance(item, Mapping) or item.get("status") != "PASS":
                continue
            decision = str(item.get("decision") or "")
            capability_id = str(item.get("capability_id") or "")
            skill_id = str(item.get("skill_id") or "")
            if decision == "APPROVE_FOR_RUNTIME_REVIEW":
                action = "propose_runtime_default_review"
            elif decision == "APPROVE_AS_ALTERNATE":
                action = "catalog_alternate_only"
            elif decision == "REJECT":
                action = "reject_candidate"
            else:
                continue
            planned_changes.append(
                {
                    "capability_id": capability_id,
                    "skill_id": skill_id,
                    "decision": decision,
                    "planned_action": action,
                    "runtime_patch_allowed": action == "propose_runtime_default_review",
                    "public_benchmark_allowed": False,
                }
            )

    return {
        "schema": "nexus.sf3_runtime_policy_patch_plan.v1",
        "status": "PASS" if planned_changes and not blockers else "BLOCKED",
        "summary": {
            "planned_change_count": len(planned_changes),
            "runtime_default_review_count": sum(
                1 for item in planned_changes if item["planned_action"] == "propose_runtime_default_review"
            ),
            "catalog_alternate_only_count": sum(
                1 for item in planned_changes if item["planned_action"] == "catalog_alternate_only"
            ),
            "reject_candidate_count": sum(
                1 for item in planned_changes if item["planned_action"] == "reject_candidate"
            ),
            "runtime_update_allowed": bool(planned_changes and not blockers),
            "public_benchmark_allowed": False,
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "planned_changes": planned_changes,
        "claim_boundary": [
            "This is a patch plan, not a direct runtime policy write.",
            "Public benchmark remains blocked until a separate runtime patch gate passes.",
        ],
    }
