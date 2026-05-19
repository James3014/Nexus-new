"""Promotion contracts for receipt-backed skill-fit evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping


KNOWN_CAPABILITIES = (
    "repair_and_coding",
    "governance_and_trust",
    "research_and_source_discipline",
)


def _infer_catalog_capability(catalog: Mapping[str, Any], item: Mapping[str, Any]) -> str:
    capability = str(item.get("capability") or catalog.get("capability") or "").strip()
    if capability:
        return capability
    matrix_path = str(catalog.get("matrix_path") or "").lower()
    for known in KNOWN_CAPABILITIES:
        if known in matrix_path:
            return known
    return ""


def build_skill_discovery_rerun_queue(catalog: Mapping[str, Any]) -> dict[str, Any]:
    """Build a conservative discovery queue from catalog verdicts."""

    queue = []
    skipped = []
    for item in catalog.get("skill_verdicts", []) or []:
        if not isinstance(item, Mapping):
            continue
        verdict = str(item.get("verdict") or "")
        entry = {
            "capability": _infer_catalog_capability(catalog, item),
            "skill_id": str(item.get("skill_id") or ""),
            "verdict": verdict,
            "tested_rows": int(item.get("tested_rows") or 0),
            "effective_rows": int(item.get("effective_rows") or 0),
        }
        if verdict == "needs_more_data":
            queue.append({**entry, "reason": "needs_more_data"})
        else:
            skipped.append({**entry, "reason": f"skip_{verdict or 'unknown'}"})
    return {
        "schema": "nexus.skill_discovery_rerun_queue.v1",
        "status": "PASS",
        "queue_count": len(queue),
        "skipped_count": len(skipped),
        "queue": queue,
        "skipped": skipped,
        "claim_boundary": [
            "Discovery queue schedules validation only; it must not update runtime defaults.",
            "Rejected skills are skipped until the taskset or candidate source changes.",
        ],
    }


def select_skill_discovery_replay_row_ids(matrix: Mapping[str, Any], queue: Mapping[str, Any]) -> list[str]:
    """Select skill-ablation row ids for queued capability/skill replays."""

    wanted = {
        (str(item.get("capability") or ""), str(item.get("skill_id") or ""))
        for item in queue.get("queue", []) or []
        if isinstance(item, Mapping)
    }
    selected = []
    seen = set()
    for row in matrix.get("rows", []) or []:
        if not isinstance(row, Mapping):
            continue
        key = (str(row.get("capability") or ""), str(row.get("skill_id") or ""))
        row_id = str(row.get("row_id") or "")
        if str(row.get("arm_type") or "") != "skill_ablation":
            continue
        if key not in wanted or not row_id or row_id in seen:
            continue
        selected.append(row_id)
        seen.add(row_id)
    return selected


def build_capability_skill_promotion_policy(catalog: Mapping[str, Any]) -> dict[str, Any]:
    """Convert receipt-backed catalog verdicts into a non-runtime policy draft."""

    defaults: dict[str, str] = {}
    alternates: dict[str, list[str]] = {}
    replace_candidates: dict[str, list[str]] = {}
    needs_more_data: dict[str, list[str]] = {}
    rejected: dict[str, list[str]] = {}
    failures = list(catalog.get("failures", []) or [])
    capability_sections = catalog.get("capabilities") if isinstance(catalog.get("capabilities"), Mapping) else {}
    for capability, section in capability_sections.items():
        if not isinstance(section, Mapping):
            continue
        capability_id = str(capability)
        default_candidate = str(section.get("default_candidate") or "")
        if default_candidate:
            defaults.setdefault(capability_id, default_candidate)
        alternate_values = [str(item) for item in section.get("alternate_candidates", []) or [] if str(item)]
        if alternate_values:
            alternates.setdefault(capability_id, []).extend(alternate_values)
        replace_values = [str(item) for item in section.get("replace_candidates", []) or [] if str(item)]
        if replace_values:
            replace_candidates.setdefault(capability_id, []).extend(replace_values)
        needs_values = [str(item) for item in section.get("needs_more_data", []) or [] if str(item)]
        needs_values.extend(str(item) for item in section.get("needs_more_data_normal_lane", []) or [] if str(item))
        if needs_values:
            needs_more_data.setdefault(capability_id, []).extend(needs_values)
        rejected_values = [str(item) for item in section.get("rejected", []) or [] if str(item)]
        if rejected_values:
            rejected.setdefault(capability_id, []).extend(rejected_values)
    for item in catalog.get("skill_verdicts", []) or []:
        if not isinstance(item, Mapping):
            continue
        capability = _infer_catalog_capability(catalog, item)
        skill_id = str(item.get("skill_id") or "")
        verdict = str(item.get("verdict") or "")
        evidence_refs = [str(ref) for ref in item.get("evidence_refs", []) or [] if str(ref)]
        receipt_refs = [str(ref) for ref in item.get("receipt_refs", []) or [] if str(ref)]
        if verdict in {"keep", "replace_candidate"} and (not evidence_refs or not receipt_refs):
            failures.append(f"{capability}:{skill_id}:promotion_without_evidence_or_receipt")
            continue
        if verdict == "keep" and capability and skill_id:
            defaults.setdefault(capability, skill_id)
        elif verdict == "replace_candidate" and capability and skill_id:
            alternates.setdefault(capability, []).append(skill_id)
        elif verdict == "needs_more_data" and capability and skill_id:
            needs_more_data.setdefault(capability, []).append(skill_id)
        elif capability and skill_id:
            rejected.setdefault(capability, []).append(skill_id)
    promoted_by_capability: dict[str, set[str]] = {}
    for capability, skill_id in defaults.items():
        promoted_by_capability.setdefault(capability, set()).add(skill_id)
    for capability, skill_ids in alternates.items():
        promoted_by_capability.setdefault(capability, set()).update(skill_ids)
    for capability, skill_ids in replace_candidates.items():
        promoted_by_capability.setdefault(capability, set()).update(skill_ids)
    cleaned_needs_more_data = {
        capability: [skill_id for skill_id in skill_ids if skill_id not in promoted_by_capability.get(capability, set())]
        for capability, skill_ids in needs_more_data.items()
    }
    cleaned_needs_more_data = {capability: skill_ids for capability, skill_ids in cleaned_needs_more_data.items() if skill_ids}
    return {
        "schema": "nexus.capability_skill_promotion_policy_draft.v1",
        "status": "PASS" if not failures else "RETURN",
        "runtime_update_allowed": False,
        "defaults": defaults,
        "alternates": {key: sorted(set(value)) for key, value in sorted(alternates.items())},
        "replace_candidates": {key: sorted(set(value)) for key, value in sorted(replace_candidates.items())},
        "needs_more_data": {key: sorted(set(value)) for key, value in sorted(cleaned_needs_more_data.items())},
        "rejected": {key: sorted(set(value)) for key, value in sorted(rejected.items())},
        "failures": sorted(set(str(item) for item in failures)),
        "claim_boundary": [
            "This is a promotion draft, not a runtime policy write.",
            "Runtime defaults require a later Flash50/100 validation gate.",
        ],
    }


def write_capability_skill_promotion_policy(
    *,
    catalog_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    policy = build_capability_skill_promotion_policy(catalog)
    Path(output_path).write_text(json.dumps(policy, indent=2, ensure_ascii=False), encoding="utf-8")
    return policy


def _policy_skills_by_capability(promotion_policy: Mapping[str, Any]) -> dict[str, dict[str, list[str]]]:
    skills_by_capability: dict[str, dict[str, list[str]]] = {
        capability: {
            "defaults": [],
            "alternates": [],
            "replace_candidates": [],
            "needs_more_data": [],
            "rejected": [],
        }
        for capability in KNOWN_CAPABILITIES
    }
    defaults = promotion_policy.get("defaults") if isinstance(promotion_policy.get("defaults"), Mapping) else {}
    for capability, skill_id in defaults.items():
        skill = str(skill_id or "")
        if skill:
            skills_by_capability.setdefault(str(capability), {}).setdefault("defaults", []).append(skill)
    for field in ("alternates", "replace_candidates", "needs_more_data", "rejected"):
        values = promotion_policy.get(field) if isinstance(promotion_policy.get(field), Mapping) else {}
        for capability, skill_ids in values.items():
            bucket = skills_by_capability.setdefault(
                str(capability),
                {
                    "defaults": [],
                    "alternates": [],
                    "replace_candidates": [],
                    "needs_more_data": [],
                    "rejected": [],
                },
            )
            bucket.setdefault(field, []).extend(str(skill) for skill in (skill_ids or []) if str(skill))
    return {
        capability: {field: sorted(set(skills)) for field, skills in fields.items()}
        for capability, fields in sorted(skills_by_capability.items())
    }


def build_skill_fit_completion_gate(
    catalog: Mapping[str, Any],
    promotion_policy: Mapping[str, Any],
    *,
    required_capabilities: Iterable[str] = KNOWN_CAPABILITIES,
) -> dict[str, Any]:
    """Close the SF loop without granting runtime or benchmark permission."""

    failures: list[str] = []
    required = tuple(str(capability) for capability in required_capabilities if str(capability))
    catalog_status = str(catalog.get("status") or "")
    policy_status = str(promotion_policy.get("status") or "")
    if catalog_status != "PASS":
        failures.append("catalog_not_pass")
    if policy_status != "PASS":
        failures.append("promotion_policy_not_pass")
    if not bool(catalog.get("skill_fit_complete")):
        failures.append("catalog_skill_fit_complete_false")
    if not bool(catalog.get("sf_catalog_complete")):
        failures.append("sf_catalog_complete_false")
    if not bool(catalog.get("sf_promotion_policy_draft_complete")):
        failures.append("sf_promotion_policy_draft_complete_false")
    if bool(promotion_policy.get("runtime_update_allowed")) or bool(catalog.get("runtime_update_allowed")):
        failures.append("runtime_update_must_remain_false")
    if bool(catalog.get("public_benchmark_allowed")):
        failures.append("public_benchmark_must_remain_false")

    policy_skills = _policy_skills_by_capability(promotion_policy)
    capability_statuses: list[dict[str, Any]] = []
    for capability in required:
        buckets = policy_skills.get(
            capability,
            {
                "defaults": [],
                "alternates": [],
                "replace_candidates": [],
                "needs_more_data": [],
                "rejected": [],
            },
        )
        positive_skills = buckets["defaults"] + buckets["alternates"] + buckets["replace_candidates"]
        if buckets["needs_more_data"]:
            failures.append(f"{capability}:needs_more_data_not_closed")
        if not positive_skills:
            failures.append(f"{capability}:no_actionable_skill_recommendation")
        if buckets["defaults"]:
            recommendation_state = "default_candidate"
        elif buckets["alternates"]:
            recommendation_state = "alternate_candidate"
        elif buckets["replace_candidates"]:
            recommendation_state = "replace_candidate"
        else:
            recommendation_state = "blocked"
        capability_statuses.append(
            {
                "capability": capability,
                "recommendation_state": recommendation_state,
                "default_candidates": buckets["defaults"],
                "alternate_candidates": buckets["alternates"],
                "replace_candidates": buckets["replace_candidates"],
                "needs_more_data": buckets["needs_more_data"],
                "rejected": buckets["rejected"],
                "sf_actionable": bool(positive_skills) and not buckets["needs_more_data"],
            }
        )

    runtime_promotion_complete = bool(catalog.get("sf_runtime_promotion_complete"))
    public_benchmark_allowed = bool(catalog.get("public_benchmark_allowed"))
    return {
        "schema": "nexus.skill_fit_completion_gate.v1",
        "status": "PASS" if not failures else "RETURN",
        "skill_fit_complete": not failures,
        "sf_catalog_complete": catalog_status == "PASS" and bool(catalog.get("sf_catalog_complete")),
        "sf_promotion_policy_draft_complete": policy_status == "PASS",
        "sf_runtime_promotion_complete": runtime_promotion_complete,
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "capability_statuses": capability_statuses,
        "summary": {
            "required_capability_count": len(required),
            "actionable_capability_count": sum(1 for item in capability_statuses if item["sf_actionable"]),
            "default_candidate_count": sum(len(item["default_candidates"]) for item in capability_statuses),
            "alternate_candidate_count": sum(len(item["alternate_candidates"]) for item in capability_statuses),
            "replace_candidate_count": sum(len(item["replace_candidates"]) for item in capability_statuses),
            "needs_more_data_count": sum(len(item["needs_more_data"]) for item in capability_statuses),
            "runtime_promotion_complete": runtime_promotion_complete,
            "public_benchmark_allowed": public_benchmark_allowed,
        },
        "failures": sorted(set(failures)),
        "claim_boundary": [
            "SF completion means capability-skill recommendations are closed for the current SF lane.",
            "Runtime default promotion remains blocked until a separate runtime validation gate is reviewed.",
            "Public benchmark remains blocked until runtime promotion and benchmark readiness gates are explicitly opened.",
        ],
    }


def write_skill_fit_completion_gate(
    *,
    catalog_path: str | Path,
    promotion_policy_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    promotion_policy = json.loads(Path(promotion_policy_path).read_text(encoding="utf-8"))
    gate = build_skill_fit_completion_gate(catalog, promotion_policy)
    Path(output_path).write_text(json.dumps(gate, indent=2, ensure_ascii=False), encoding="utf-8")
    return gate


def _candidate_metadata_by_skill_id(candidate_sources: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for source in candidate_sources:
        candidates = []
        for key in ("candidates", "materialized_skills", "assets", "skills"):
            value = source.get(key) if isinstance(source.get(key), list) else None
            if value:
                candidates.extend(item for item in value if isinstance(item, Mapping))
        if not candidates and "skill_id" in source:
            candidates.append(source)
        for item in candidates:
            skill_id = str(item.get("skill_id") or item.get("name") or item.get("dir_name") or "")
            if not skill_id:
                continue
            current = metadata.setdefault(skill_id, {})
            overlay = bool(item.get("metadata_overlay"))
            for key, value in item.items():
                if overlay and value not in (None, ""):
                    current[str(key)] = value
                else:
                    current.setdefault(str(key), value)
    return metadata


def _is_repo_local_skill_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized.startswith(".agents/skills/") or "/Workspace/nexus/.agents/skills/" in normalized


def build_skill_fit_runtime_promotion_review(
    catalog: Mapping[str, Any],
    promotion_policy: Mapping[str, Any],
    *,
    candidate_sources: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Review SF recommendations for runtime eligibility without updating runtime policy."""

    failures: list[str] = []
    completion_gate = build_skill_fit_completion_gate(catalog, promotion_policy)
    if completion_gate["status"] != "PASS":
        failures.append("sf_completion_gate_not_pass")
    metadata = _candidate_metadata_by_skill_id(candidate_sources)
    policy_skills = _policy_skills_by_capability(promotion_policy)
    review_items: list[dict[str, Any]] = []
    for capability, fields in policy_skills.items():
        for recommendation_kind, skill_ids in (
            ("default_candidate", fields.get("defaults", [])),
            ("alternate_candidate", fields.get("alternates", [])),
            ("replace_candidate", fields.get("replace_candidates", [])),
        ):
            for skill_id in skill_ids:
                meta = metadata.get(skill_id, {})
                path = str(meta.get("path") or "")
                source_root = str(meta.get("source_root") or "")
                source_type = str(meta.get("source_type") or "")
                safety_status = str(meta.get("safety_status") or "")
                runtime_eligible = bool(meta.get("runtime_eligible"))
                if runtime_eligible and safety_status == "runtime_reviewed":
                    disposition = "runtime_review_ready"
                    runtime_review_ready = True
                    follow_up = "review_for_runtime_default_or_capability_local_auto_mount"
                elif _is_repo_local_skill_path(path) or source_root == "nexus_repo":
                    disposition = "repo_candidate_runtime_review_required"
                    runtime_review_ready = False
                    follow_up = "complete_runtime_review_metadata_before_default_promotion"
                else:
                    disposition = "catalog_alternate_only"
                    runtime_review_ready = False
                    follow_up = "materialize_or_curate_repo_local_skill_before_runtime_promotion"
                review_items.append(
                    {
                        "capability": capability,
                        "skill_id": skill_id,
                        "recommendation_kind": recommendation_kind,
                        "disposition": disposition,
                        "runtime_review_ready": runtime_review_ready,
                        "source_root": source_root,
                        "source_type": source_type,
                        "path": path,
                        "safety_status": safety_status,
                        "runtime_eligible": runtime_eligible,
                        "follow_up": follow_up,
                    }
                )
    undecided = [
        item
        for item in review_items
        if item["disposition"] not in {
            "runtime_review_ready",
            "repo_candidate_runtime_review_required",
            "catalog_alternate_only",
        }
    ]
    if undecided:
        failures.append("runtime_review_has_undecided_items")
    return {
        "schema": "nexus.skill_fit_runtime_promotion_review.v1",
        "status": "PASS" if not failures else "RETURN",
        "sf_closed_loop_complete": not failures,
        "sf_completion_gate_status": completion_gate["status"],
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "runtime_review_items": review_items,
        "summary": {
            "review_item_count": len(review_items),
            "runtime_review_ready_count": sum(1 for item in review_items if item["runtime_review_ready"]),
            "repo_candidate_runtime_review_required_count": sum(
                1 for item in review_items if item["disposition"] == "repo_candidate_runtime_review_required"
            ),
            "catalog_alternate_only_count": sum(
                1 for item in review_items if item["disposition"] == "catalog_alternate_only"
            ),
            "undecided_count": len(undecided),
        },
        "failures": sorted(set(failures)),
        "claim_boundary": [
            "This review closes SF by assigning every recommended skill a runtime-promotion disposition.",
            "It does not write runtime defaults.",
            "External/reference alternates remain catalog-only until they are materialized or curated as repo-local skills.",
        ],
    }


def write_skill_fit_runtime_promotion_review(
    *,
    catalog_path: str | Path,
    promotion_policy_path: str | Path,
    output_path: str | Path,
    candidate_source_paths: Iterable[str | Path] = (),
) -> dict[str, Any]:
    catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    promotion_policy = json.loads(Path(promotion_policy_path).read_text(encoding="utf-8"))
    candidate_sources = [
        json.loads(Path(candidate_path).read_text(encoding="utf-8"))
        for candidate_path in candidate_source_paths
        if Path(candidate_path).exists()
    ]
    review = build_skill_fit_runtime_promotion_review(
        catalog,
        promotion_policy,
        candidate_sources=candidate_sources,
    )
    Path(output_path).write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")
    return review


def _runtime_review_items_by_pair(promotion_review: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    return {
        (str(item.get("capability") or item.get("capability_id") or ""), str(item.get("skill_id") or "")): item
        for item in promotion_review.get("runtime_review_items", [])
        or promotion_review.get("review_items", [])
        or []
        if isinstance(item, Mapping)
    }


def build_skill_fit_runtime_policy_apply_gate(
    patch_plan: Mapping[str, Any],
    promotion_review: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate SF V5 primary-skill updates before producing a runtime policy overlay."""

    blockers: list[str] = []
    if patch_plan.get("status") != "PASS":
        blockers.append("patch_plan_not_pass")
    if promotion_review.get("status") != "PASS":
        blockers.append("promotion_review_not_pass")
    if not bool(promotion_review.get("sf_closed_loop_complete")):
        blockers.append("sf_closed_loop_not_complete")

    review_by_pair = _runtime_review_items_by_pair(promotion_review)
    apply_items: list[dict[str, Any]] = []
    held_items: list[dict[str, Any]] = []
    seen_capabilities: set[str] = set()
    for raw in patch_plan.get("planned_changes", []) or []:
        if not isinstance(raw, Mapping):
            continue
        capability = str(raw.get("capability_id") or "")
        skill_id = str(raw.get("skill_id") or "")
        planned_action = str(raw.get("planned_action") or "")
        apply_state = str(raw.get("apply_state") or "")
        if planned_action == "set_capability_primary_skill_candidate" and apply_state == "apply_ready_but_not_written":
            if not capability or not skill_id:
                blockers.append("primary_apply_item_missing_capability_or_skill")
                continue
            if capability in seen_capabilities:
                blockers.append(f"{capability}:duplicate_primary_apply_candidate")
            seen_capabilities.add(capability)
            review_item = review_by_pair.get((capability, skill_id), {})
            if review_item.get("disposition") != "runtime_review_ready":
                blockers.append(f"{capability}:{skill_id}:not_runtime_review_ready")
            if not bool(review_item.get("runtime_review_ready")):
                blockers.append(f"{capability}:{skill_id}:runtime_review_flag_false")
            if not bool(review_item.get("runtime_eligible")):
                blockers.append(f"{capability}:{skill_id}:runtime_eligible_false")
            if str(review_item.get("safety_status") or "") != "runtime_reviewed":
                blockers.append(f"{capability}:{skill_id}:safety_status_not_runtime_reviewed")
            evidence_refs = [str(ref) for ref in raw.get("evidence_refs", []) or [] if str(ref)]
            if not evidence_refs:
                blockers.append(f"{capability}:{skill_id}:missing_evidence_refs")
            apply_items.append(
                {
                    "capability_id": capability,
                    "skill_id": skill_id,
                    "source_root": str(review_item.get("source_root") or ""),
                    "source_type": str(review_item.get("source_type") or ""),
                    "path": str(review_item.get("path") or ""),
                    "evidence_refs": evidence_refs,
                }
            )
        elif apply_state in {"hold_primary_default", "not_runtime_patchable"}:
            held_items.append(
                {
                    "capability_id": capability,
                    "skill_id": skill_id,
                    "planned_action": planned_action,
                    "apply_state": apply_state,
                }
            )

    if not apply_items:
        blockers.append("no_primary_apply_ready_items")

    status = "PASS" if not blockers else "BLOCKED"
    return {
        "schema": "nexus.sf_runtime_policy_apply_gate.v1",
        "status": status,
        "summary": {
            "primary_apply_ready_count": len(apply_items),
            "held_item_count": len(held_items),
            "runtime_policy_apply_allowed": status == "PASS",
            "runtime_update_allowed": status == "PASS",
            "public_benchmark_allowed": False,
            "blocker_count": len(blockers),
        },
        "applied_primary_candidates": apply_items,
        "held_items": held_items,
        "blockers": sorted(set(blockers)),
        "claim_boundary": [
            "This gate only validates internal SF runtime policy overlay application.",
            "It does not unlock public benchmarks.",
            "Held alternates stay out of runtime primary defaults until a separate tie-break or curation gate passes.",
        ],
    }


def build_skill_fit_runtime_policy_overlay(apply_gate: Mapping[str, Any]) -> dict[str, Any]:
    """Build the applied capability-primary skill overlay after the apply gate passes."""

    if apply_gate.get("status") != "PASS":
        return {
            "schema": "nexus.sf_runtime_skill_policy_overlay.v1",
            "status": "BLOCKED",
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "primary_skill_by_capability": {},
            "applied_primary": [],
            "held_items": apply_gate.get("held_items", []),
            "blockers": apply_gate.get("blockers", ["apply_gate_not_pass"]),
            "claim_boundary": ["Blocked overlays must not be loaded as runtime primary skill policy."],
        }
    applied = [item for item in apply_gate.get("applied_primary_candidates", []) or [] if isinstance(item, Mapping)]
    primary_skill_by_capability = {
        str(item.get("capability_id") or ""): str(item.get("skill_id") or "")
        for item in applied
        if str(item.get("capability_id") or "") and str(item.get("skill_id") or "")
    }
    capability_aliases = {
        "forecast_pregate": ["pregate", "forecast_gate", "plan_quality_gate"],
        "repair_loop": ["repair_loop"],
    }
    return {
        "schema": "nexus.sf_runtime_skill_policy_overlay.v1",
        "status": "PASS",
        "runtime_update_allowed": True,
        "public_benchmark_allowed": False,
        "primary_skill_by_capability": primary_skill_by_capability,
        "capability_aliases": {
            capability: aliases
            for capability, aliases in capability_aliases.items()
            if capability in primary_skill_by_capability
        },
        "applied_primary": applied,
        "held_items": apply_gate.get("held_items", []),
        "blockers": [],
        "claim_boundary": [
            "This overlay records SF-approved capability primary skills.",
            "Runtime consumers must still produce runtime-confirmed skill mount receipts.",
            "Public benchmark remains a separate lane.",
        ],
    }


def write_skill_fit_runtime_policy_apply_gate(
    *,
    patch_plan_path: str | Path,
    promotion_review_path: str | Path,
    output_path: str | Path,
    overlay_output_path: str | Path | None = None,
) -> dict[str, Any]:
    patch_plan = json.loads(Path(patch_plan_path).read_text(encoding="utf-8"))
    promotion_review = json.loads(Path(promotion_review_path).read_text(encoding="utf-8"))
    apply_gate = build_skill_fit_runtime_policy_apply_gate(patch_plan, promotion_review)
    Path(output_path).write_text(json.dumps(apply_gate, indent=2, ensure_ascii=False), encoding="utf-8")
    if overlay_output_path:
        overlay = build_skill_fit_runtime_policy_overlay(apply_gate)
        Path(overlay_output_path).write_text(json.dumps(overlay, indent=2, ensure_ascii=False), encoding="utf-8")
    return apply_gate


def build_skill_promotion_threshold_contract(
    catalog: Mapping[str, Any],
    promotion_policy: Mapping[str, Any],
    *,
    rerun_queue: Mapping[str, Any] | None = None,
    min_tested_rows_per_skill: int = 30,
    min_seal_runs_before_runtime: int = 2,
    default_min_effective_rate: float = 0.8,
    alternate_min_effective_rate: float = 0.6,
    min_task_buckets_for_alternate: int = 2,
    required_validation_lanes: Iterable[str] = ("Flash50", "Flash100"),
) -> dict[str, Any]:
    """Freeze promotion thresholds without updating runtime defaults."""

    failures: list[str] = []
    catalog_summary = catalog.get("summary") if isinstance(catalog.get("summary"), Mapping) else {}
    matrix_complete = bool(catalog_summary.get("matrix_complete"))
    catalog_status = str(catalog.get("status") or "")
    policy_status = str(promotion_policy.get("status") or "")
    runtime_update_requested = bool(promotion_policy.get("runtime_update_allowed"))
    if catalog_status != "PASS":
        failures.append("catalog_not_pass")
    if policy_status != "PASS":
        failures.append("promotion_policy_not_pass")
    if not matrix_complete:
        failures.append("matrix_not_complete")
    if runtime_update_requested:
        failures.append("runtime_update_must_remain_false")

    validation_lanes = tuple(str(item) for item in required_validation_lanes if str(item))
    queue_items = rerun_queue.get("queue", []) if isinstance(rerun_queue, Mapping) else []
    queued = {
        (str(item.get("capability") or ""), str(item.get("skill_id") or ""))
        for item in queue_items
        if isinstance(item, Mapping)
    }
    capability_thresholds = []
    promotion_ready_count = 0
    for item in catalog.get("skill_verdicts", []) or []:
        if not isinstance(item, Mapping):
            continue
        capability = _infer_catalog_capability(catalog, item)
        skill_id = str(item.get("skill_id") or "")
        verdict = str(item.get("verdict") or "")
        tested_rows = int(item.get("tested_rows") or 0)
        effective_rows = int(item.get("effective_rows") or 0)
        effective_rate = (effective_rows / tested_rows) if tested_rows else 0.0
        task_buckets = [str(bucket) for bucket in item.get("task_buckets", []) or [] if str(bucket)]
        task_bucket_count = len(set(task_buckets))
        evidence_refs = [str(ref) for ref in item.get("evidence_refs", []) or [] if str(ref)]
        receipt_refs = [str(ref) for ref in item.get("receipt_refs", []) or [] if str(ref)]
        evidence_complete = bool(evidence_refs and receipt_refs)
        observed_rows_ok = tested_rows >= min_tested_rows_per_skill
        positive = verdict in {"keep", "replace_candidate"}
        if positive and not evidence_complete:
            failures.append(f"{capability}:{skill_id}:positive_without_evidence_or_receipt")
        if positive and not observed_rows_ok:
            failures.append(f"{capability}:{skill_id}:insufficient_tested_rows")
        threshold_status = "reject"
        threshold_recommendation = "reject"
        if (
            verdict == "needs_more_data"
            and evidence_complete
            and observed_rows_ok
            and effective_rate >= alternate_min_effective_rate
            and task_bucket_count >= min_task_buckets_for_alternate
        ):
            threshold_status = "validation_required"
            threshold_recommendation = "alternate_candidate"
            promotion_ready_count += 1
        elif verdict == "needs_more_data":
            threshold_status = "targeted_replay_required" if (capability, skill_id) in queued else "queue_missing"
            threshold_recommendation = "needs_more_data"
        elif positive and evidence_complete and observed_rows_ok:
            threshold_status = "validation_required"
            if verdict == "keep" and effective_rate >= default_min_effective_rate:
                threshold_recommendation = "default_candidate"
            elif effective_rate >= alternate_min_effective_rate and task_bucket_count >= min_task_buckets_for_alternate:
                threshold_recommendation = "alternate_candidate"
            else:
                threshold_recommendation = "needs_more_data"
            promotion_ready_count += 1
        elif verdict == "quarantine":
            threshold_status = "quarantine"
            threshold_recommendation = "quarantine"
        capability_thresholds.append(
            {
                "capability": capability,
                "skill_id": skill_id,
                "verdict": verdict,
                "tested_rows": tested_rows,
                "effective_rows": effective_rows,
                "effective_rate": round(effective_rate, 4),
                "task_bucket_count": task_bucket_count,
                "evidence_complete": evidence_complete,
                "observed_rows_ok": observed_rows_ok,
                "threshold_status": threshold_status,
                "threshold_recommendation": threshold_recommendation,
                "required_validation_lanes": list(validation_lanes) if threshold_status == "validation_required" else [],
            }
        )

    return {
        "schema": "nexus.skill_promotion_threshold_contract.v1",
        "status": "PASS" if not failures else "RETURN",
        "runtime_update_allowed": False,
        "flash100_allowed": promotion_ready_count > 0 and not failures,
        "promotion_allowed": False,
        "thresholds": {
            "min_tested_rows_per_skill": min_tested_rows_per_skill,
            "min_seal_runs_before_runtime": min_seal_runs_before_runtime,
            "default_min_effective_rate": default_min_effective_rate,
            "alternate_min_effective_rate": alternate_min_effective_rate,
            "min_task_buckets_for_alternate": min_task_buckets_for_alternate,
            "required_validation_lanes": list(validation_lanes),
            "requires_repeated_denominator": True,
            "requires_trust_mismatch_zero": True,
            "requires_evidence_and_receipt_refs": True,
        },
        "summary": {
            "skill_count": len(capability_thresholds),
            "promotion_ready_count": promotion_ready_count,
            "needs_targeted_replay_count": sum(
                1 for item in capability_thresholds if item["threshold_status"] == "targeted_replay_required"
            ),
            "default_candidate_count": sum(
                1 for item in capability_thresholds if item["threshold_recommendation"] == "default_candidate"
            ),
            "alternate_candidate_count": sum(
                1 for item in capability_thresholds if item["threshold_recommendation"] == "alternate_candidate"
            ),
            "queue_count": len(queued),
            "matrix_complete": matrix_complete,
        },
        "failures": sorted(set(failures)),
        "capability_skill_thresholds": capability_thresholds,
        "claim_boundary": [
            "This contract freezes promotion thresholds; it does not update runtime policy.",
            "A single diagnostic Flash180 run can schedule targeted replay but cannot by itself promote runtime defaults.",
            "Flash100 is allowed only after at least one capability/skill pair has receipt-backed positive verdict evidence.",
        ],
    }


def write_skill_promotion_threshold_contract(
    *,
    catalog_path: str | Path,
    promotion_policy_path: str | Path,
    output_path: str | Path,
    rerun_queue_path: str | Path | None = None,
    min_tested_rows_per_skill: int = 30,
    default_min_effective_rate: float = 0.8,
    alternate_min_effective_rate: float = 0.6,
    min_task_buckets_for_alternate: int = 2,
) -> dict[str, Any]:
    catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    promotion_policy = json.loads(Path(promotion_policy_path).read_text(encoding="utf-8"))
    rerun_queue = json.loads(Path(rerun_queue_path).read_text(encoding="utf-8")) if rerun_queue_path else None
    contract = build_skill_promotion_threshold_contract(
        catalog,
        promotion_policy,
        rerun_queue=rerun_queue,
        min_tested_rows_per_skill=min_tested_rows_per_skill,
        default_min_effective_rate=default_min_effective_rate,
        alternate_min_effective_rate=alternate_min_effective_rate,
        min_task_buckets_for_alternate=min_task_buckets_for_alternate,
    )
    Path(output_path).write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    return contract
