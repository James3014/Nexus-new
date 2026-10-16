#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ASSEMBLY = PROJECT_ROOT / "docs/reports/NEXUS_HEEP_ASSEMBLY_CATALOG_2026-05-20.json"
DEFAULT_GOLD_CASES = PROJECT_ROOT / "docs/reports/NEXUS_HEEP_GOLD_CASE_MANIFEST_2026-05-20.json"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "docs/reports"
DEFAULT_PILOT_CAPABILITIES = ()
RECEIPT_KEYS = ("selected", "injected", "used", "evidence_present", "gate_passed", "outcome_contributed")
MODES = ("Mode A (Solo)", "Mode B (Guard)", "Mode C (Swarm)")
MAT_B_KPIS = (
    "success_rate",
    "pollution_pct",
    "evidence_seal_count",
    "token_delta",
    "wall_delta",
    "reopen_rate",
)


def build_heep_live_pilot(
    *,
    assembly_catalog: Mapping[str, Any],
    gold_cases: Mapping[str, Any],
    pilot_capabilities: tuple[str, ...] = DEFAULT_PILOT_CAPABILITIES,
) -> dict[str, dict[str, Any]]:
    assembly_by_capability = _index_by(assembly_catalog.get("rows", []), "capability")
    gold_by_capability = _index_by(gold_cases.get("cases", []), "capability")
    role_pools = _role_pools(assembly_catalog.get("rows", []))
    pilot_capabilities = pilot_capabilities or tuple(sorted(assembly_by_capability))

    blockers = [
        f"missing_assembly:{capability}" for capability in pilot_capabilities if capability not in assembly_by_capability
    ] + [f"missing_gold_case:{capability}" for capability in pilot_capabilities if capability not in gold_by_capability]
    contract = _contract(pilot_capabilities, blockers)
    run_rows = []
    for capability in pilot_capabilities:
        assembly = assembly_by_capability.get(capability)
        gold = gold_by_capability.get(capability)
        if not assembly or not gold:
            continue
        for mode in MODES:
            run_rows.append(_run_row(capability, mode, assembly, gold, role_pools))
    run = _run_report(run_rows, blockers)
    run_blockers = list(run.get("blockers", []))
    decision = _decision_report(run_rows, run_blockers)
    map_gate = _map_update_gate(decision.get("decisions", []), run_blockers)
    compare_queue = _flash_nexus_compare_queue(run_rows, decision.get("decisions", []), run_blockers)
    apply_review = _runtime_apply_review_packet(decision.get("decisions", []), compare_queue.get("rows", []), run_blockers)
    return {
        "contract": contract,
        "run": run,
        "decision": decision,
        "map_gate": map_gate,
        "compare_queue": compare_queue,
        "apply_review": apply_review,
    }


def _contract(pilot_capabilities: tuple[str, ...], blockers: list[str]) -> dict[str, Any]:
    return {
        "schema": "nexus.heep_live_pilot_contract.v1",
        "status": "PASS" if not blockers else "RETURN",
        "pilot_capabilities": list(pilot_capabilities),
        "modes": list(MODES),
        "receipt_requirements": list(RECEIPT_KEYS),
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "claim_boundary": [
            "This pilot replays existing runtime receipts for HEEP ensemble mode selection.",
            "It is not a public benchmark and does not update runtime defaults.",
            "A future external model run must replace replay rows before publication-ready claims.",
        ],
        "blockers": blockers,
    }


def _run_row(
    capability: str,
    mode: str,
    assembly: Mapping[str, Any],
    gold_case: Mapping[str, Any],
    role_pools: Mapping[str, list[str]],
) -> dict[str, Any]:
    skills = _mode_skills(mode, assembly, role_pools)
    roles = {str(item.get("role")) for item in skills}
    receipt_chain = _receipt_chain(gold_case)
    receipt_complete = all(receipt_chain.values())
    role_coverage = _role_coverage(mode, roles)
    quality_score = round((1.0 if receipt_complete else 0.0) + role_coverage, 4)
    premium_cost = max(0, len(skills) - 1)
    return {
        "capability": capability,
        "mode": mode,
        "skills": skills,
        "skill_count": len(skills),
        "role_coverage": role_coverage,
        "quality_score": quality_score,
        "premium_cost": premium_cost,
        "source_evidence_ref": str(gold_case.get("source_evidence_ref") or ""),
        "assembly_recommended_mode": str(assembly.get("recommended_mode") or ""),
        "runtime_final_receipt_chain": receipt_chain,
        "status": "PASS" if receipt_complete and role_coverage > 0 else "RETURN",
        "public_claim_allowed": False,
        "runtime_update_allowed": False,
    }


def _run_report(rows: list[dict[str, Any]], blockers: list[str]) -> dict[str, Any]:
    row_blockers = [f"{row['capability']}:{row['mode']}:receipt_or_role_incomplete" for row in rows if row["status"] != "PASS"]
    all_blockers = blockers + row_blockers
    return {
        "schema": "nexus.heep_live_pilot_run.v1",
        "status": "PASS" if not all_blockers else "RETURN",
        "summary": {
            "capability_count": len({row["capability"] for row in rows}),
            "row_count": len(rows),
            "pass_count": sum(1 for row in rows if row["status"] == "PASS"),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "rows": rows,
        "blockers": all_blockers,
    }


def _decision_report(rows: list[dict[str, Any]], blockers: list[str]) -> dict[str, Any]:
    by_capability: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_capability.setdefault(str(row["capability"]), []).append(row)
    decisions = []
    for capability, cap_rows in sorted(by_capability.items()):
        pass_rows = [row for row in cap_rows if row["status"] == "PASS"]
        if not pass_rows:
            decisions.append(
                {
                    "capability": capability,
                    "decision": "hold_due_to_missing_receipt",
                    "selected_mode": "",
                    "mode_a_quality_score": 0.0,
                    "selected_minus_mode_a_quality": 0.0,
                    "selected_quality_score": 0.0,
                    "runtime_update_allowed": False,
                    "public_benchmark_allowed": False,
                }
            )
            continue
        mode_a = next((row for row in cap_rows if row["mode"] == "Mode A (Solo)"), {})
        mode_a_quality = float(mode_a.get("quality_score") or 0.0)
        recommended_mode = str((cap_rows[0] if cap_rows else {}).get("assembly_recommended_mode") or "")
        selected = next((row for row in pass_rows if row["mode"] == recommended_mode), None)
        if selected is None:
            selected = max(pass_rows, key=lambda row: (row["quality_score"] - row["premium_cost"] * 0.05, -row["premium_cost"]))
        decisions.append(
            {
                "capability": capability,
                "decision": _decision_for_mode(str(selected["mode"])),
                "assembly_recommended_mode": recommended_mode,
                "selected_mode": selected["mode"],
                "mode_a_quality_score": mode_a_quality,
                "selected_minus_mode_a_quality": round(float(selected["quality_score"]) - mode_a_quality, 4),
                "selected_quality_score": selected["quality_score"],
                "selected_skill_count": selected["skill_count"],
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            }
        )
    return {
        "schema": "nexus.heep_live_mode_decision.v1",
        "status": "PASS" if not blockers else "RETURN",
        "summary": {
            "capability_count": len(decisions),
            "mode_counts": _counts(decision["selected_mode"] for decision in decisions),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "decisions": decisions,
        "blockers": blockers,
    }


def _flash_nexus_compare_queue(
    rows: list[dict[str, Any]], decisions: Any, blockers: list[str]
) -> dict[str, Any]:
    rows_by_capability: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        rows_by_capability.setdefault(str(row["capability"]), {})[str(row["mode"])] = row

    queue_rows = []
    for decision in decisions if isinstance(decisions, list) else []:
        if not isinstance(decision, Mapping):
            continue
        capability = str(decision.get("capability") or "")
        selected_mode = str(decision.get("selected_mode") or "")
        if not selected_mode:
            continue
        mode_rows = rows_by_capability.get(capability, {})
        mode_a = mode_rows.get("Mode A (Solo)")
        if selected_mode == "Mode A (Solo)":
            selected = _best_non_solo_probe(mode_rows)
        else:
            selected = mode_rows.get(selected_mode)
            if float(decision.get("selected_minus_mode_a_quality") or 0.0) <= 0:
                continue
        if not mode_a or not selected:
            continue
        queue_rows.append(
            {
                "capability": capability,
                "baseline_arm": _compare_arm("mode_a_current_primary", mode_a),
                "challenger_arm": _compare_arm("heep_multi_skill", selected),
                "selected_mode": selected_mode,
                "local_quality_lift": decision.get("selected_minus_mode_a_quality"),
                "mat_b_gate": _mat_b_gate_template(capability=capability, selected_mode=selected_mode),
                "status": "READY" if not blockers else "BLOCKED",
                "runner": "Flash+Nexus internal live compare",
                "claim_boundary": "internal_heep_mode_candidate_only",
            }
        )

    return {
        "schema": "nexus.heep_flash_nexus_live_compare_queue.v1",
        "status": "PASS" if queue_rows and not blockers else ("PASS" if not blockers else "RETURN"),
        "summary": {
            "candidate_count": len(queue_rows),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "rows": queue_rows,
        "blockers": blockers,
        "claim_boundary": [
            "Rows are executable internal Flash+Nexus compare candidates.",
            "They are not public benchmark rows.",
            "Candidate replacement decisions must be made by MAT-B live KPIs, not local role coverage.",
            "Runtime default cannot change until live compare receipts pass and an apply gate approves.",
        ],
    }


def _best_non_solo_probe(mode_rows: Mapping[str, dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        row
        for mode, row in mode_rows.items()
        if mode != "Mode A (Solo)" and isinstance(row, Mapping) and row.get("status") == "PASS"
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda row: (float(row.get("quality_score") or 0.0), -int(row.get("premium_cost") or 0)))


def _mat_b_gate_template(*, capability: str, selected_mode: str) -> dict[str, Any]:
    return {
        "schema": "nexus.heep_mat_b_gate.v1",
        "capability": capability,
        "selected_mode": selected_mode,
        "status": "PENDING_LIVE_COMPARE",
        "required_kpis": list(MAT_B_KPIS),
        "thresholds": {
            "success_rate": "challenger >= baseline and no delivery RETURN",
            "pollution_pct": "challenger <= baseline and below task pollution threshold",
            "evidence_seal_count": "challenger >= baseline and all required receipt keys present",
            "token_delta": "evaluated only after reliability, quality, and governance pass",
            "wall_delta": "evaluated only after reliability, quality, and governance pass",
            "reopen_rate": "challenger <= baseline in replay/regression simulation",
        },
        "current_values": {
            "success_rate": None,
            "pollution_pct": None,
            "evidence_seal_count": None,
            "token_delta": None,
            "wall_delta": None,
            "reopen_rate": None,
        },
        "decision_order": [
            "Reliability",
            "Quality",
            "Governance",
            "Efficiency",
            "Regression",
        ],
        "claim_boundary": "local replay cannot pass MAT-B; live compare must fill these KPI values",
    }


def _compare_arm(arm_id: str, row: Mapping[str, Any]) -> dict[str, Any]:
    skill_ids = [str(item.get("skill_id") or "") for item in row.get("skills", []) if isinstance(item, Mapping)]
    return {
        "arm_id": arm_id,
        "mode": row.get("mode"),
        "skill_ids": [skill_id for skill_id in skill_ids if skill_id],
        "skill_count": row.get("skill_count"),
        "runtime_final_receipt_chain": dict(row.get("runtime_final_receipt_chain") or {}),
        "runner_env": {
            "NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS": "1",
            "NEXUS_BENCH_SKILL_MOUNT_REQUESTS": json.dumps([skill_id for skill_id in skill_ids if skill_id]),
            "NEXUS_HEEP_MODE": str(row.get("mode") or ""),
        },
    }


def _runtime_apply_review_packet(
    decisions: Any, compare_rows: Any, blockers: list[str]
) -> dict[str, Any]:
    compare_by_capability = {
        str(row.get("capability") or ""): row
        for row in (compare_rows if isinstance(compare_rows, list) else [])
        if isinstance(row, Mapping)
    }
    rows = []
    for decision in decisions if isinstance(decisions, list) else []:
        if not isinstance(decision, Mapping):
            continue
        capability = str(decision.get("capability") or "")
        selected_mode = str(decision.get("selected_mode") or "")
        if capability in compare_by_capability and not blockers:
            disposition = "PENDING_FLASH_NEXUS_LIVE_COMPARE"
        elif selected_mode == "Mode A (Solo)":
            disposition = "KEEP_SINGLE_PRIMARY"
        else:
            disposition = "HOLD"
        rows.append(
            {
                "capability": capability,
                "selected_mode": selected_mode,
                "local_decision": decision.get("decision"),
                "disposition": disposition,
                "mat_b_required_before_runtime_apply": disposition == "PENDING_FLASH_NEXUS_LIVE_COMPARE",
                "mat_b_kpis": list(MAT_B_KPIS) if disposition == "PENDING_FLASH_NEXUS_LIVE_COMPARE" else [],
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            }
        )
    return {
        "schema": "nexus.heep_runtime_apply_review_packet.v1",
        "status": "PASS" if rows and not blockers else "RETURN",
        "summary": {
            "capability_count": len(rows),
            "pending_live_compare_count": sum(
                1 for row in rows if row["disposition"] == "PENDING_FLASH_NEXUS_LIVE_COMPARE"
            ),
            "keep_single_primary_count": sum(1 for row in rows if row["disposition"] == "KEEP_SINGLE_PRIMARY"),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "rows": rows,
        "blockers": blockers,
        "claim_boundary": [
            "This packet can request review only after internal Flash+Nexus live compare receipts exist.",
            "Multi-skill replacements require MAT-B reliability, quality, governance, efficiency, and regression evidence.",
            "Local HEEP replay alone cannot approve runtime default changes.",
        ],
    }


def _map_update_gate(decisions: Any, blockers: list[str]) -> dict[str, Any]:
    rows = []
    for decision in decisions if isinstance(decisions, list) else []:
        if not isinstance(decision, Mapping):
            continue
        rows.append(
            {
                "capability": decision.get("capability"),
                "heep_mode_candidate": decision.get("selected_mode"),
                "decision": decision.get("decision"),
                "map_update_allowed": bool(decision.get("selected_mode") and not blockers),
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            }
        )
    return {
        "schema": "nexus.heep_live_map_update_gate.v1",
        "status": "PASS" if rows and not blockers else "RETURN",
        "summary": {
            "candidate_update_count": sum(1 for row in rows if row["map_update_allowed"]),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "rows": rows,
        "blockers": blockers,
        "claim_boundary": [
            "Map updates are HEEP mode candidates only.",
            "They do not alter runtime defaults or public benchmark readiness.",
        ],
    }


def _mode_skills(mode: str, assembly: Mapping[str, Any], role_pools: Mapping[str, list[str]]) -> list[dict[str, str]]:
    primary = str(assembly.get("primary_skill_id") or "")
    if mode == "Mode A (Solo)":
        return [{"role": "primary", "skill_id": primary}]
    if mode == "Mode B (Guard)":
        return [
            {"role": "primary", "skill_id": primary},
            {"role": "Audit", "skill_id": _first_not(role_pools.get("Audit", []), primary)},
        ]
    skills = []
    used: set[str] = set()
    for role in ("Scout", "Logic", "Audit"):
        skill_id = primary if role in set(assembly.get("primary_role_tags") or []) and primary not in used else _first_not(
            role_pools.get(role, []), *used
        )
        used.add(skill_id)
        skills.append({"role": role, "skill_id": skill_id})
    return skills


def _role_coverage(mode: str, roles: set[str]) -> float:
    if mode == "Mode A (Solo)":
        return 1.0 / 3.0
    if mode == "Mode B (Guard)":
        return min(1.0, len(roles) / 3.0)
    return len({"Scout", "Logic", "Audit"} & roles) / 3.0


def _decision_for_mode(mode: str) -> str:
    if mode == "Mode A (Solo)":
        return "solo_best"
    if mode == "Mode B (Guard)":
        return "guard_best"
    if mode == "Mode C (Swarm)":
        return "swarm_best"
    return "hold_due_to_no_quality_lift"


def _role_pools(rows: Any) -> dict[str, list[str]]:
    pools: dict[str, list[str]] = {"Scout": [], "Logic": [], "Audit": []}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, Mapping):
            continue
        for item in row.get("assembly", []) if isinstance(row.get("assembly"), list) else []:
            if isinstance(item, Mapping) and item.get("role") in pools:
                pools[str(item["role"])].append(str(item.get("skill_id") or ""))
    return {role: _dedupe(values) for role, values in pools.items()}


def _receipt_chain(gold_case: Mapping[str, Any]) -> dict[str, bool]:
    chain = gold_case.get("runtime_final_receipt_chain", {})
    chain = chain if isinstance(chain, Mapping) else {}
    return {key: bool(chain.get(key, False)) for key in RECEIPT_KEYS}


def _index_by(items: Any, key: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(items, list):
        return {}
    indexed: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if isinstance(item, Mapping):
            indexed[str(item.get(key) or "")] = item
    return {key: value for key, value in indexed.items() if key}


def _first_not(values: list[str], *excluded: str) -> str:
    excluded_set = {value for value in excluded if value}
    for value in values:
        if value and value not in excluded_set:
            return value
    return values[0] if values else "missing-role-candidate"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        value = str(value)
        counts[value] = counts.get(value, 0) + 1
    return counts


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def write_heep_live_pilot(*, artifacts: Mapping[str, Mapping[str, Any]], report_dir: Path) -> dict[str, str]:
    outputs = {
        "contract": report_dir / "NEXUS_HEEP_LIVE_PILOT_CONTRACT_2026-05-20.json",
        "run": report_dir / "NEXUS_HEEP_LIVE_PILOT_RUN_2026-05-20.json",
        "decision": report_dir / "NEXUS_HEEP_LIVE_MODE_DECISION_2026-05-20.json",
        "map_gate": report_dir / "NEXUS_HEEP_LIVE_MAP_UPDATE_GATE_2026-05-20.json",
        "compare_queue": report_dir / "NEXUS_HEEP_FLASH_NEXUS_LIVE_COMPARE_QUEUE_2026-05-20.json",
        "apply_review": report_dir / "NEXUS_HEEP_RUNTIME_APPLY_REVIEW_PACKET_2026-05-20.json",
    }
    for key, path in outputs.items():
        _write_json(path, artifacts[key])
    return {key: str(path) for key, path in outputs.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local HEEP-LIVE pilot from HEEP/EMAS assembly artifacts.")
    parser.add_argument("--assembly", type=Path, default=DEFAULT_ASSEMBLY)
    parser.add_argument("--gold-cases", type=Path, default=DEFAULT_GOLD_CASES)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--pilot-capabilities", default="ALL")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    assembly_catalog = _read_json(args.assembly)
    pilot_capabilities = _resolve_pilot_capabilities(assembly_catalog, args.pilot_capabilities)
    artifacts = build_heep_live_pilot(
        assembly_catalog=assembly_catalog,
        gold_cases=_read_json(args.gold_cases),
        pilot_capabilities=pilot_capabilities,
    )
    status = "PASS" if all(artifact["status"] == "PASS" for artifact in artifacts.values()) else "RETURN"
    outputs: dict[str, str] = {}
    if not args.dry_run:
        outputs = write_heep_live_pilot(artifacts=artifacts, report_dir=args.report_dir)
    print(
        json.dumps(
            {
                "status": status,
                "pilot_capability_count": len(pilot_capabilities),
                "row_count": artifacts["run"]["summary"]["row_count"],
                "candidate_update_count": artifacts["map_gate"]["summary"]["candidate_update_count"],
                "live_compare_candidate_count": artifacts["compare_queue"]["summary"]["candidate_count"],
                "pending_apply_review_count": artifacts["apply_review"]["summary"]["pending_live_compare_count"],
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
                "outputs": outputs,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if status == "PASS" else 1


def _resolve_pilot_capabilities(assembly_catalog: Mapping[str, Any], value: str) -> tuple[str, ...]:
    if not value or value.strip().upper() == "ALL":
        return tuple(sorted(_index_by(assembly_catalog.get("rows", []), "capability")))
    return tuple(cap.strip() for cap in value.split(",") if cap.strip())


if __name__ == "__main__":
    raise SystemExit(main())
