"""Status rollups for capability-to-skill fit evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _capability_items(mapping: Mapping[str, Any], capability: str) -> list[str]:
    value = mapping.get(capability)
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return []


def _threshold_by_skill(threshold: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    return {
        (str(item.get("capability") or ""), str(item.get("skill_id") or "")): item
        for item in threshold.get("capability_skill_thresholds", []) or []
        if isinstance(item, Mapping)
    }


def _positive_policy_pairs(policy: Mapping[str, Any]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    defaults = policy.get("defaults") if isinstance(policy.get("defaults"), Mapping) else {}
    alternates = policy.get("alternates") if isinstance(policy.get("alternates"), Mapping) else {}
    for capability, skill_id in defaults.items():
        if str(capability) and str(skill_id):
            pairs.add((str(capability), str(skill_id)))
    for capability, skill_ids in alternates.items():
        for skill_id in _capability_items(alternates, str(capability)):
            if str(capability) and skill_id:
                pairs.add((str(capability), skill_id))
        if isinstance(skill_ids, str) and str(capability) and skill_ids:
            pairs.add((str(capability), str(skill_ids)))
    return pairs


def _catalog_verdicts(catalog: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    verdicts: dict[tuple[str, str], Mapping[str, Any]] = {}
    for item in catalog.get("skill_verdicts", []) or []:
        if not isinstance(item, Mapping):
            continue
        capability = str(item.get("capability") or "")
        skill_id = str(item.get("skill_id") or "")
        if capability and skill_id:
            verdicts[(capability, skill_id)] = item
    return verdicts


def build_skill_fit_data_shape_pregate(
    *,
    catalog: Mapping[str, Any],
    promotion_policy: Mapping[str, Any],
    threshold_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate skill-fit artifact shape before deeper refactor or runtime gates."""

    failures: list[str] = []
    catalog_summary = catalog.get("summary") if isinstance(catalog.get("summary"), Mapping) else {}
    threshold_summary = (
        threshold_contract.get("summary") if isinstance(threshold_contract.get("summary"), Mapping) else {}
    )
    if str(catalog.get("status") or "") != "PASS":
        failures.append("catalog_not_pass")
    if str(promotion_policy.get("status") or "") != "PASS":
        failures.append("promotion_policy_not_pass")
    if not bool(catalog_summary.get("matrix_complete")):
        failures.append("catalog_matrix_not_complete")
    if threshold_summary and not bool(threshold_summary.get("matrix_complete")):
        failures.append("threshold_matrix_not_complete")
    if bool(promotion_policy.get("runtime_update_allowed")):
        failures.append("promotion_policy_runtime_update_must_remain_false")
    if bool(threshold_contract.get("runtime_update_allowed")):
        failures.append("threshold_runtime_update_must_remain_false")

    catalog_verdicts = _catalog_verdicts(catalog)
    threshold_rows: dict[tuple[str, str], Mapping[str, Any]] = {}
    for item in threshold_contract.get("capability_skill_thresholds", []) or []:
        if not isinstance(item, Mapping):
            continue
        capability = str(item.get("capability") or "")
        skill_id = str(item.get("skill_id") or "")
        if not capability or not skill_id:
            failures.append("threshold_row_missing_capability_or_skill_id")
            continue
        pair = (capability, skill_id)
        threshold_rows[pair] = item
        if pair not in catalog_verdicts:
            failures.append(f"{capability}:{skill_id}:threshold_pair_missing_catalog_verdict")

    positive_policy_pairs = _positive_policy_pairs(promotion_policy)
    for capability, skill_id in sorted(positive_policy_pairs):
        verdict = catalog_verdicts.get((capability, skill_id))
        if verdict is None:
            failures.append(f"{capability}:{skill_id}:policy_pair_missing_catalog_verdict")
        elif str(verdict.get("verdict") or "") in {"keep", "replace_candidate"}:
            evidence_refs = [str(ref) for ref in verdict.get("evidence_refs", []) or [] if str(ref)]
            receipt_refs = [str(ref) for ref in verdict.get("receipt_refs", []) or [] if str(ref)]
            if not evidence_refs or not receipt_refs:
                failures.append(f"{capability}:{skill_id}:catalog_positive_missing_evidence_or_receipt")
        if (capability, skill_id) not in threshold_rows:
            failures.append(f"{capability}:{skill_id}:missing_threshold_contract")

    for (capability, skill_id), verdict in sorted(catalog_verdicts.items()):
        if str(verdict.get("verdict") or "") not in {"keep", "replace_candidate"}:
            continue
        evidence_refs = [str(ref) for ref in verdict.get("evidence_refs", []) or [] if str(ref)]
        receipt_refs = [str(ref) for ref in verdict.get("receipt_refs", []) or [] if str(ref)]
        if not evidence_refs or not receipt_refs:
            failures.append(f"{capability}:{skill_id}:catalog_positive_missing_evidence_or_receipt")

    positive_pairs = [
        {
            "capability": capability,
            "skill_id": skill_id,
            "catalog_verdict": str((catalog_verdicts.get((capability, skill_id)) or {}).get("verdict") or ""),
            "threshold_recommendation": str(
                (threshold_rows.get((capability, skill_id)) or {}).get("threshold_recommendation") or ""
            ),
        }
        for capability, skill_id in sorted(positive_policy_pairs)
    ]
    unique_failures = sorted(set(failures))
    return {
        "schema": "nexus.skill_fit_data_shape_pregate.v1",
        "status": "PASS" if not unique_failures else "RETURN",
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "summary": {
            "catalog_pair_count": len(catalog_verdicts),
            "threshold_pair_count": len(threshold_rows),
            "positive_pair_count": len(positive_pairs),
            "failure_count": len(unique_failures),
        },
        "positive_pairs": positive_pairs,
        "failures": unique_failures,
        "claim_boundary": [
            "This pregate validates skill-fit artifact shape only.",
            "It must not update runtime policy or allow public benchmark claims.",
        ],
    }


def build_skill_fit_status_rollup(
    *,
    promotion_policies: Iterable[Mapping[str, Any]],
    threshold_contracts: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize found skills and fail-closed promotion blockers."""

    thresholds: dict[tuple[str, str], Mapping[str, Any]] = {}
    threshold_failures: list[str] = []
    for contract in threshold_contracts:
        thresholds.update(_threshold_by_skill(contract))
        threshold_failures.extend(str(item) for item in contract.get("failures", []) or [])

    capabilities: dict[str, dict[str, Any]] = {}
    for policy in promotion_policies:
        defaults = policy.get("defaults") if isinstance(policy.get("defaults"), Mapping) else {}
        alternates = policy.get("alternates") if isinstance(policy.get("alternates"), Mapping) else {}
        needs_more_data = (
            policy.get("needs_more_data") if isinstance(policy.get("needs_more_data"), Mapping) else {}
        )
        rejected = policy.get("rejected") if isinstance(policy.get("rejected"), Mapping) else {}
        capability_names = sorted(set(defaults) | set(alternates) | set(needs_more_data) | set(rejected))
        for capability in capability_names:
            row = capabilities.setdefault(
                capability,
                {
                    "default_candidates": [],
                    "alternate_candidates": [],
                    "needs_more_data": [],
                    "rejected": [],
                    "blockers": [],
                },
            )
            row["default_candidates"].extend(_capability_items(defaults, capability))
            row["alternate_candidates"].extend(_capability_items(alternates, capability))
            row["needs_more_data"].extend(_capability_items(needs_more_data, capability))
            row["rejected"].extend(_capability_items(rejected, capability))

    for (capability, skill_id), threshold in thresholds.items():
        recommendation = str(threshold.get("threshold_recommendation") or "")
        if recommendation not in {"default_candidate", "alternate_candidate"} or not capability or not skill_id:
            continue
        row = capabilities.setdefault(
            capability,
            {
                "default_candidates": [],
                "alternate_candidates": [],
                "needs_more_data": [],
                "rejected": [],
                "blockers": [],
            },
        )
        target = "default_candidates" if recommendation == "default_candidate" else "alternate_candidates"
        row[target].append(skill_id)

    found_pairs = []
    for capability, row in sorted(capabilities.items()):
        positives = sorted(set(row["default_candidates"] + row["alternate_candidates"]))
        for skill_id in positives:
            threshold = thresholds.get((capability, skill_id), {})
            blockers = []
            if not threshold:
                blockers.append("missing_threshold_contract")
            elif not bool(threshold.get("observed_rows_ok")):
                blockers.append("insufficient_tested_rows")
            if any(failure.startswith(f"{capability}:{skill_id}:") for failure in threshold_failures):
                blockers.extend(
                    failure.split(":", 2)[-1]
                    for failure in threshold_failures
                    if failure.startswith(f"{capability}:{skill_id}:")
                )
            row["blockers"].extend(blockers)
            found_pairs.append(
                {
                    "capability": capability,
                    "skill_id": skill_id,
                    "promotion_blockers": sorted(set(blockers)),
                    "tested_rows": int(threshold.get("tested_rows") or 0),
                    "effective_rows": int(threshold.get("effective_rows") or 0),
                    "effective_rate": threshold.get("effective_rate", 0),
                    "threshold_recommendation": str(threshold.get("threshold_recommendation") or ""),
                }
            )
        for key in ("default_candidates", "alternate_candidates", "needs_more_data", "rejected", "blockers"):
            row[key] = sorted(set(str(item) for item in row[key] if str(item)))

    has_found_skill = bool(found_pairs)
    promotion_ready_pairs = [
        item for item in found_pairs if not item["promotion_blockers"] and item["threshold_recommendation"] in {"default_candidate", "alternate_candidate"}
    ]
    return {
        "schema": "nexus.skill_fit_status_rollup.v1",
        "status": "PASS",
        "has_found_skill": has_found_skill,
        "promotion_ready": bool(promotion_ready_pairs),
        "benchmark_allowed": bool(promotion_ready_pairs),
        "summary": {
            "capability_count": len(capabilities),
            "found_skill_pair_count": len(found_pairs),
            "promotion_ready_pair_count": len(promotion_ready_pairs),
        },
        "capabilities": capabilities,
        "found_skill_pairs": found_pairs,
        "promotion_ready_pairs": promotion_ready_pairs,
        "next_task_cards": _next_task_cards(capabilities, found_pairs, promotion_ready_pairs),
        "claim_boundary": [
            "This rollup is skill-fit evidence control only; it must not run or unlock public benchmark by itself.",
            "A found skill is not runtime promotion until threshold, repeated validation, and receipt gates are clean.",
        ],
    }


def _next_task_cards(
    capabilities: Mapping[str, Mapping[str, Any]],
    found_pairs: list[Mapping[str, Any]],
    promotion_ready_pairs: list[Mapping[str, Any]],
) -> list[dict[str, str]]:
    if promotion_ready_pairs:
        cards = [
            {
                "id": "SF-SEAL",
                "goal": "Run deterministic seal checks for promotion-ready capability-skill pairs before any benchmark lane.",
                "exit": "Every pair has clean threshold recommendation, receipt refs, and no promotion blockers.",
            }
        ]
        for capability, row in sorted(capabilities.items()):
            positives = set(row.get("default_candidates", []) or []) | set(row.get("alternate_candidates", []) or [])
            if positives:
                continue
            if row.get("needs_more_data"):
                cards.append(
                    {
                        "id": f"SF-{capability}-TARGETED-REPLAY",
                        "goal": "Continue capability-local targeted replay for needs_more_data skills; do not open public benchmark.",
                        "exit": "Each queued skill reaches alternate/default threshold or is demoted with receipt-backed reason.",
                    }
                )
            else:
                cards.append(
                    {
                        "id": f"SF-{capability}-DISCOVERY",
                        "goal": "Refresh the capability-local candidate bucket and preflight only source-safe candidates.",
                        "exit": "The capability has at least one receipt-backed candidate or a supply-gap report.",
                    }
                )
        return cards
    if found_pairs:
        return [
            {
                "id": "SF-1",
                "goal": "Collect enough same-capability evidence for found skills without opening public benchmark.",
                "exit": "Each found skill reaches the configured tested-row threshold or is demoted with receipt-backed reason.",
            },
            {
                "id": "SF-2",
                "goal": "Regenerate current catalog, promotion draft, threshold contract, and status rollup from one evidence chain.",
                "exit": "No stale catalog/promotion/threshold mismatch remains.",
            },
        ]
    return [
        {
            "id": "SF-DISCOVERY",
            "goal": "Refresh candidate pool and run capability-local discovery until at least one receipt-backed skill is found.",
            "exit": "At least one capability-skill pair has keep or replace_candidate evidence.",
        }
    ]


def write_skill_fit_status_rollup(
    *,
    promotion_policy_paths: Iterable[str | Path],
    threshold_contract_paths: Iterable[str | Path],
    output_path: str | Path,
) -> dict[str, Any]:
    rollup = build_skill_fit_status_rollup(
        promotion_policies=[_load_json(path) for path in promotion_policy_paths],
        threshold_contracts=[_load_json(path) for path in threshold_contract_paths],
    )
    Path(output_path).write_text(json.dumps(rollup, indent=2, ensure_ascii=False), encoding="utf-8")
    return rollup
