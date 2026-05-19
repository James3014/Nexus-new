#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_ROLLUP = Path("docs/reports/NEXUS_SF_SYSTEMATIC_ALL_CAPABILITY_LIVE_ROLLUP_V32_2026-05-19.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_2026-05-20.json")
DEFAULT_MD_OUTPUT = Path("docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_2026-05-20.md")

CAPABILITY_ALIASES: dict[str, list[str]] = {
    "forecast_pregate": ["pregate", "forecast_gate", "plan_quality_gate"],
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _winner_for_row(row: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    verdict = str(row.get("verdict") or "")
    challenger = row.get("challenger") if isinstance(row.get("challenger"), dict) else {}
    current = row.get("current_best") if isinstance(row.get("current_best"), dict) else {}
    if verdict == "replace_candidate":
        return "replace_candidate", challenger, str(challenger.get("skill_id") or "")
    return "keep_current_best", current, str(current.get("skill_id") or "")


def build_current_overlay(rollup: dict[str, Any]) -> dict[str, Any]:
    rows = [item for item in rollup.get("rows", []) if isinstance(item, dict)]
    primary: dict[str, str] = {}
    selected_rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    replace_count = 0
    keep_count = 0

    for row in rows:
        capability = str(row.get("capability") or "").strip()
        action, winner, skill_id = _winner_for_row(row)
        if not capability:
            blockers.append("missing_capability")
            continue
        if not skill_id:
            blockers.append(f"{capability}:missing_skill_id")
            continue
        if not winner.get("effective"):
            blockers.append(f"{capability}:{skill_id}:winner_not_effective")
        if winner.get("status") != "PASS":
            blockers.append(f"{capability}:{skill_id}:winner_not_pass")
        if winner.get("skill_mount_contract_status") != "PASS":
            blockers.append(f"{capability}:{skill_id}:skill_mount_contract_not_pass")
        if not winner.get("provider_token_measured"):
            blockers.append(f"{capability}:{skill_id}:provider_token_not_measured")
        if winner.get("trust_mismatch"):
            blockers.append(f"{capability}:{skill_id}:trust_mismatch")
        evidence_refs = [str(winner.get("evidence_path") or "").strip()]
        evidence_refs = [item for item in evidence_refs if item]
        if not evidence_refs:
            blockers.append(f"{capability}:{skill_id}:missing_evidence_path")
        primary[capability] = skill_id
        if action == "replace_candidate":
            replace_count += 1
        else:
            keep_count += 1
        selected_rows.append(
            {
                "capability_id": capability,
                "skill_id": skill_id,
                "decision": action,
                "evidence_refs": evidence_refs,
                "receipt_path": str(winner.get("receipt_path") or ""),
                "token_delta_challenger_minus_current": row.get("token_delta_challenger_minus_current"),
                "wall_delta_challenger_minus_current": row.get("wall_delta_challenger_minus_current"),
            }
        )

    expected_count = int((rollup.get("summary") or {}).get("capability_count") or len(rows))
    if len(primary) != expected_count:
        blockers.append(f"capability_count_mismatch:{len(primary)}!={expected_count}")

    status = "PASS" if not blockers and bool(primary) else "BLOCKED"
    aliases = {
        capability: aliases
        for capability, aliases in CAPABILITY_ALIASES.items()
        if capability in primary
    }
    return {
        "schema": "nexus.sf_runtime_skill_policy_overlay.current.v1",
        "status": status,
        "created_at": datetime.now(UTC).isoformat(),
        "source_rollup_schema": rollup.get("schema"),
        "runtime_update_allowed": status == "PASS",
        "public_benchmark_allowed": False,
        "primary_skill_by_capability": dict(sorted(primary.items())),
        "candidate_primary_skill_by_capability": dict(sorted(primary.items())),
        "capability_aliases": aliases,
        "selected_primary": sorted(selected_rows, key=lambda item: item["capability_id"]),
        "summary": {
            "capability_count": len(primary),
            "replace_candidate_count": replace_count,
            "keep_current_best_count": keep_count,
            "blocker_count": len(blockers),
            "runtime_update_allowed": status == "PASS",
            "public_benchmark_allowed": False,
        },
        "blockers": sorted(set(blockers)),
        "claim_boundary": [
            "This is the 34/34 SF current capability-skill overlay.",
            "It combines V32 replacements with V32 held current_best winners.",
            "Runtime consumers must still emit runtime-confirmed skill mount receipts.",
            "Public benchmark remains a separate lane.",
        ],
    }


def write_markdown(overlay: dict[str, Any], output: Path) -> None:
    lines = [
        "# Nexus SF Current Runtime Skill Overlay V32",
        "",
        f"- status: `{overlay['status']}`",
        f"- capability_count: `{overlay['summary']['capability_count']}`",
        f"- replace_candidate_count: `{overlay['summary']['replace_candidate_count']}`",
        f"- keep_current_best_count: `{overlay['summary']['keep_current_best_count']}`",
        f"- runtime_update_allowed: `{overlay['runtime_update_allowed']}`",
        f"- public_benchmark_allowed: `{overlay['public_benchmark_allowed']}`",
        "",
        "| capability | primary_skill | decision |",
        "|---|---|---|",
    ]
    for item in overlay.get("selected_primary", []):
        lines.append(f"| `{item['capability_id']}` | `{item['skill_id']}` | `{item['decision']}` |")
    lines.extend(
        [
            "",
            "## Claim Boundary",
            "",
            "- Internal SF runtime overlay only.",
            "- Not a public benchmark claim.",
            "- Runtime must still confirm selected/injected/used/evidence/gate/outcome receipts.",
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the full SF current runtime skill overlay from V32 rollup.")
    parser.add_argument("--rollup", default=str(DEFAULT_ROLLUP))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT))
    args = parser.parse_args()

    overlay = build_current_overlay(_load_json(Path(args.rollup)))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(overlay, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(overlay, Path(args.md_output))
    print(json.dumps({"status": overlay["status"], **overlay["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if overlay["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
