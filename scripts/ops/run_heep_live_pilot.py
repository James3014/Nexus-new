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
DEFAULT_PILOT_CAPABILITIES = ("codeintel", "artifact_gate", "research", "repair_loop")
RECEIPT_KEYS = ("selected", "injected", "used", "evidence_present", "gate_passed", "outcome_contributed")
MODES = ("Mode A (Solo)", "Mode B (Guard)", "Mode C (Swarm)")


def build_heep_live_pilot(
    *,
    assembly_catalog: Mapping[str, Any],
    gold_cases: Mapping[str, Any],
    pilot_capabilities: tuple[str, ...] = DEFAULT_PILOT_CAPABILITIES,
) -> dict[str, dict[str, Any]]:
    assembly_by_capability = _index_by(assembly_catalog.get("rows", []), "capability")
    gold_by_capability = _index_by(gold_cases.get("cases", []), "capability")
    role_pools = _role_pools(assembly_catalog.get("rows", []))

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
    return {
        "contract": contract,
        "run": run,
        "decision": decision,
        "map_gate": map_gate,
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
                    "selected_quality_score": 0.0,
                    "runtime_update_allowed": False,
                    "public_benchmark_allowed": False,
                }
            )
            continue
        selected = max(pass_rows, key=lambda row: (row["quality_score"] - row["premium_cost"] * 0.05, -row["premium_cost"]))
        decisions.append(
            {
                "capability": capability,
                "decision": _decision_for_mode(str(selected["mode"])),
                "selected_mode": selected["mode"],
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
    }
    for key, path in outputs.items():
        _write_json(path, artifacts[key])
    return {key: str(path) for key, path in outputs.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local HEEP-LIVE pilot from HEEP/EMAS assembly artifacts.")
    parser.add_argument("--assembly", type=Path, default=DEFAULT_ASSEMBLY)
    parser.add_argument("--gold-cases", type=Path, default=DEFAULT_GOLD_CASES)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--pilot-capabilities", default=",".join(DEFAULT_PILOT_CAPABILITIES))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    pilot_capabilities = tuple(cap.strip() for cap in args.pilot_capabilities.split(",") if cap.strip())
    artifacts = build_heep_live_pilot(
        assembly_catalog=_read_json(args.assembly),
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
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
                "outputs": outputs,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
