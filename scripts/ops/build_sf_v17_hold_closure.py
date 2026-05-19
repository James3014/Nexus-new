#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping


TARGET_CAPABILITIES = {
    "benchmark_meta_opt",
    "delivery_acceptance_gate",
    "policy_capability_gate",
}


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(path: str | Path, *, rollup: Mapping[str, Any], closure: Mapping[str, Any]) -> None:
    lines = [
        "# Nexus SF V17 Hold Closure",
        "",
        "## Summary",
        f"- status: `{closure.get('status')}`",
        f"- sf_closed: `{closure.get('sf_closed')}`",
        f"- runtime_update_allowed: `{closure.get('runtime_update_allowed')}`",
        f"- public_benchmark_allowed: `{closure.get('public_benchmark_allowed')}`",
        f"- promoted_from_hold: `{closure.get('summary', {}).get('promoted_from_hold')}`",
        f"- documented_no_skill_primary: `{closure.get('summary', {}).get('documented_no_skill_primary')}`",
        "",
        "## Decisions",
        "| capability | decision | skill | reason |",
        "|---|---|---|---|",
    ]
    for decision in rollup.get("decisions", []) or []:
        lines.append(
            "| {capability_id} | {decision} | {skill_id} | {reason} |".format(
                capability_id=decision.get("capability_id", ""),
                decision=decision.get("decision", ""),
                skill_id=decision.get("skill_id", ""),
                reason=decision.get("reason", ""),
            )
        )
    lines.extend(
        [
            "",
            "## Claim Boundary",
            "- This closes documented HOLD disposition for SF.",
            "- This is not a public benchmark.",
            "- Runtime consumers still need runtime-final skill mount receipts.",
            "",
        ]
    )
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _nested_number(payload: Mapping[str, Any], paths: list[tuple[str, ...]]) -> float | None:
    for path in paths:
        current: Any = payload
        for key in path:
            if not isinstance(current, Mapping) or key not in current:
                current = None
                break
            current = current[key]
        if isinstance(current, (int, float)):
            return float(current)
    return None


def _evidence_provider_rate(evidence_path: str) -> float | None:
    if not evidence_path:
        return None
    path = Path(evidence_path)
    if not path.exists():
        return None
    evidence = _read_json(path)
    return _nested_number(
        evidence,
        [
            ("route_cost_ledger", "arms", "with_nexus", "provider_token_measured_rate"),
            ("route_cost_ledger", "arms", "with_nexus", "clean_model_cost_evidence_rate"),
            ("telemetry_completeness", "provider_token_measured_rate_with"),
        ],
    )


def _receipt_clean(row: Mapping[str, Any]) -> tuple[bool, float | None, str]:
    row_rate = row.get("provider_token_measured_rate")
    if isinstance(row_rate, (int, float)) and float(row_rate) >= 1.0:
        return True, float(row_rate), "row_provider_token_measured_rate"
    evidence_rate = _evidence_provider_rate(str(row.get("evidence_path") or ""))
    if isinstance(evidence_rate, (int, float)) and float(evidence_rate) >= 1.0:
        return True, float(evidence_rate), "evidence_bundle_provider_token_rate"
    if bool(row.get("token_measured")) and int(row.get("tokens") or 0) > 0:
        return False, evidence_rate, "token_measured_without_provider_rate"
    return False, evidence_rate, "provider_token_not_measured"


def _catalogive(row: Mapping[str, Any]) -> bool:
    return str(row.get("catalog_verdict") or "") == "keep" and int(row.get("effective_rows") or 0) > 0


def _cost_dominates(row: Mapping[str, Any]) -> bool:
    return float(row.get("token_delta_vs_no_skill") or 0) <= 0 and float(row.get("wall_delta_vs_no_skill_sec") or 0) <= 0


def _promotable(row: Mapping[str, Any]) -> bool:
    receipt_clean, _, _ = _receipt_clean(row)
    return (
        str(row.get("status") or "") == "SUCCESS"
        and str(row.get("semantic_status") or "") == "VERIFIED"
        and not bool(row.get("trust_mismatch"))
        and receipt_clean
        and _catalogive(row)
        and _cost_dominates(row)
    )


def _candidate_decision(capability_id: str, decision: Mapping[str, Any]) -> dict[str, Any]:
    candidates = [item for item in decision.get("candidates", []) or [] if isinstance(item, Mapping)]
    normalized: list[dict[str, Any]] = []
    for raw in candidates:
        item = dict(raw)
        clean, rate, source = _receipt_clean(item)
        item["provider_token_measured_rate"] = rate
        item["provider_token_source"] = source
        item["receipt_clean"] = clean
        item["catalog_effective"] = _catalogive(item)
        item["cost_dominates_no_skill"] = _cost_dominates(item)
        item["promotable"] = _promotable(item)
        normalized.append(item)
    promoted = [item for item in normalized if item["promotable"]]
    if promoted:
        promoted.sort(
            key=lambda item: (
                float(item.get("token_delta_vs_no_skill") or 0),
                float(item.get("wall_delta_vs_no_skill_sec") or 0),
                str(item.get("skill_id") or ""),
            )
        )
        winner = promoted[0]
        return {
            "capability_id": capability_id,
            "decision": "approve_primary",
            "skill_id": str(winner.get("skill_id") or ""),
            "reason": "receipt_clean_effective_and_token_wall_dominates_no_skill",
            "winner": winner,
            "candidates": normalized,
        }
    effective = [item for item in normalized if item.get("catalog_effective")]
    if effective:
        return {
            "capability_id": capability_id,
            "decision": "hold_tradeoff_or_receipt_gap",
            "skill_id": str(effective[0].get("skill_id") or ""),
            "reason": "effective_candidate_not_receipt_clean_or_cost_dominant",
            "winner": effective[0],
            "candidates": normalized,
        }
    cheapest = sorted(
        normalized,
        key=lambda item: (
            float(item.get("token_delta_vs_no_skill") or 0),
            float(item.get("wall_delta_vs_no_skill_sec") or 0),
            str(item.get("skill_id") or ""),
        ),
    )
    winner = cheapest[0] if cheapest else {}
    return {
        "capability_id": capability_id,
        "decision": "documented_no_skill_primary",
        "skill_id": "",
        "best_non_promoted_skill": str(winner.get("skill_id") or ""),
        "reason": "no_candidate_had_catalog_effective_rows",
        "winner": winner,
        "candidates": normalized,
    }


def build_v17_hold_closure(
    *,
    v16_rollup: Mapping[str, Any],
    v16_overlay: Mapping[str, Any],
    v16_closure: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_decisions = {
        str(item.get("capability_id") or ""): item
        for item in v16_rollup.get("decisions", []) or []
        if isinstance(item, Mapping)
    }
    decisions = [
        _candidate_decision(capability_id, source_decisions[capability_id])
        for capability_id in sorted(TARGET_CAPABILITIES)
        if capability_id in source_decisions
    ]
    promoted = [item for item in decisions if item["decision"] == "approve_primary"]
    documented = [item for item in decisions if item["decision"] == "documented_no_skill_primary"]
    blockers = [
        f"{item['capability_id']}:unclosed_hold:{item['reason']}"
        for item in decisions
        if item["decision"] not in {"approve_primary", "documented_no_skill_primary"}
    ]
    rollup = {
        "schema": "nexus.sf_v17_hold_closure_rollup.v1",
        "status": "PASS" if not blockers else "RETURN",
        "runtime_update_allowed": not blockers,
        "public_benchmark_allowed": False,
        "summary": {
            "target_hold_count": len(decisions),
            "approve_primary_count": len(promoted),
            "documented_no_skill_primary_count": len(documented),
            "unclosed_hold_count": len(blockers),
        },
        "decisions": decisions,
        "blockers": blockers,
        "claim_boundary": [
            "V17 closes documented SF holds by either approving a receipt-clean effective primary or documenting no-skill primary.",
            "Cost-only wins without effective rows remain blocked from primary promotion.",
            "Public benchmark remains separate from SF hold closure.",
        ],
    }

    overlay = deepcopy(v16_overlay)
    primary = dict(overlay.get("primary_skill_by_capability") or {})
    applied = [dict(item) for item in overlay.get("applied_primary", []) or [] if isinstance(item, Mapping)]
    for item in promoted:
        winner = item["winner"]
        capability_id = item["capability_id"]
        skill_id = item["skill_id"]
        primary[capability_id] = skill_id
        applied.append(
            {
                "capability_id": capability_id,
                "skill_id": skill_id,
                "source_root": "nexus_repo",
                "source_type": "sf_v17_hold_closure_primary",
                "runtime_eligible": True,
                "evidence_refs": [str(winner.get("evidence_path") or "")],
                "receipt_refs": [str(winner.get("receipt_path") or "")],
                "promotion_reason": item["reason"],
                "token_delta": winner.get("token_delta_vs_no_skill"),
                "wall_delta_sec": winner.get("wall_delta_vs_no_skill_sec"),
            }
        )
    overlay.update(
        {
            "schema": "nexus.sf_runtime_skill_policy_overlay.v17",
            "formalized_from": "docs/reports/NEXUS_SF_V17_HOLD_CLOSURE_ROLLUP_2026-05-19.json",
            "source_review": "docs/reports/NEXUS_SF_V17_HOLD_CLOSURE_ROLLUP_2026-05-19.json",
            "primary_skill_by_capability": dict(sorted(primary.items())),
            "applied_primary": applied,
            "documented_no_skill_primary": documented,
            "runtime_update_allowed": not blockers,
            "public_benchmark_allowed": False,
            "blockers": blockers,
            "v17_hold_closure_rollup": "docs/reports/NEXUS_SF_V17_HOLD_CLOSURE_ROLLUP_2026-05-19.json",
        }
    )

    closure = deepcopy(v16_closure)
    old_summary = dict(closure.get("summary") or {})
    closure.update(
        {
            "schema": "nexus.sf_final_closure.v17",
            "status": "PASS" if not blockers else "RETURN",
            "source_rollup": "docs/reports/NEXUS_SF_V17_HOLD_CLOSURE_ROLLUP_2026-05-19.json",
            "source_overlay": "docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V17_2026-05-19.json",
            "sf_closed": not blockers,
            "runtime_update_allowed": not blockers,
            "public_benchmark_allowed": False,
            "summary": {
                **old_summary,
                "runtime_primary_capability_count": len(primary),
                "v17_promoted_from_hold": len(promoted),
                "documented_no_skill_primary": len(documented),
                "residual_held": len(blockers),
                "all_hold_items_finally_dispositioned": not blockers,
            },
            "held_items": [],
            "documented_no_skill_primary": documented,
            "blockers": blockers,
        }
    )
    return rollup, overlay, closure


def main() -> int:
    parser = argparse.ArgumentParser(description="Close the final three SF documented HOLD decisions.")
    parser.add_argument("--v16-rollup", default="docs/reports/NEXUS_SF_V16_RESIDUAL_SELECTION_ROLLUP_2026-05-19.json")
    parser.add_argument("--v16-overlay", default="docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V16_2026-05-19.json")
    parser.add_argument("--v16-closure", default="docs/reports/NEXUS_SF_FINAL_CLOSURE_V16_2026-05-19.json")
    parser.add_argument("--rollup-output", default="docs/reports/NEXUS_SF_V17_HOLD_CLOSURE_ROLLUP_2026-05-19.json")
    parser.add_argument("--overlay-output", default="docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V17_2026-05-19.json")
    parser.add_argument("--closure-output", default="docs/reports/NEXUS_SF_FINAL_CLOSURE_V17_2026-05-19.json")
    parser.add_argument("--md-output", default="docs/reports/NEXUS_SF_FINAL_CLOSURE_V17_2026-05-19.md")
    args = parser.parse_args()
    rollup, overlay, closure = build_v17_hold_closure(
        v16_rollup=_read_json(args.v16_rollup),
        v16_overlay=_read_json(args.v16_overlay),
        v16_closure=_read_json(args.v16_closure),
    )
    _write_json(args.rollup_output, rollup)
    _write_json(args.overlay_output, overlay)
    _write_json(args.closure_output, closure)
    _write_md(args.md_output, rollup=rollup, closure=closure)
    print(
        json.dumps(
            {
                "status": closure["status"],
                "rollup": args.rollup_output,
                "overlay": args.overlay_output,
                "closure": args.closure_output,
                **closure["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if closure["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
