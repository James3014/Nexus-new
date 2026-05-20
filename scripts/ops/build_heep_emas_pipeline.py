#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ORIGINAL_MAP = PROJECT_ROOT / "docs/reports/NEXUS_SF_CAPABILITY_PRIMARY_ORIGINAL_SKILL_MAP_2026-05-20.json"
DEFAULT_OVERLAY = PROJECT_ROOT / "docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_2026-05-20.json"
DEFAULT_SMOKE = PROJECT_ROOT / "docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_SMOKE_2026-05-20.json"
DEFAULT_MAT_B_REPORT = PROJECT_ROOT / "docs/reports/NEXUS_HEEP_MAT_B_LIVE_REPORT_2026-05-20.json"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "docs/reports"
DEFAULT_INFO_MAP = PROJECT_ROOT / "docs/info/NEXUS_CAPABILITY_SKILL_MAP.md"

MODE_A = "Mode A (Solo)"
MODE_B = "Mode B (Guard)"
MODE_C = "Mode C (Swarm)"

RECEIPT_KEYS = (
    "selected",
    "injected",
    "used",
    "evidence_present",
    "gate_passed",
    "outcome_contributed",
)

ROLE_TERMS = {
    "Scout": (
        "codeintel",
        "lancedb",
        "memory",
        "research",
        "source",
        "lookup",
        "xray",
        "browser",
        "scout",
        "repo",
        "validation",
    ),
    "Logic": (
        "plan",
        "reason",
        "tdd",
        "repair",
        "build",
        "route",
        "hyper",
        "direct",
        "first-principles",
        "root-cause",
        "optimizer",
    ),
    "Audit": (
        "gate",
        "guard",
        "audit",
        "security",
        "review",
        "verify",
        "verifier",
        "policy",
        "claim",
        "regression",
        "aegis",
        "differential",
    ),
}

LEAN_CAPABILITIES = {
    "direct_master_loop",
    "drone",
    "external_productivity",
    "hyper_sprint",
    "metabolism_resume",
    "nightshift",
}

SWARM_CAPABILITY_TERMS = (
    "artifact",
    "benchmark",
    "codeintel",
    "file_lock",
    "governance",
    "learn",
    "policy",
    "research",
    "swarm",
    "ultra",
)


def build_heep_emas_artifacts(
    *,
    original_map: Mapping[str, Any],
    overlay: Mapping[str, Any],
    smoke: Mapping[str, Any],
    mat_b_report: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any] | str]:
    rows = [row for row in original_map.get("rows", []) if isinstance(row, Mapping)]
    selected = _index_by(overlay.get("selected_primary", []), "capability_id")
    smoke_cases = _index_by(smoke.get("cases", []), "capability")
    primary_by_capability = overlay.get("primary_skill_by_capability", {})
    primary_by_capability = primary_by_capability if isinstance(primary_by_capability, Mapping) else {}
    catalog_rows = [
        _build_catalog_row(
            row,
            selected.get(str(row.get("capability") or ""), {}),
            smoke_cases.get(str(row.get("capability") or ""), {}),
        )
        for row in rows
    ]
    role_pools = _role_pools(catalog_rows)

    contract = _build_contract(len(catalog_rows))
    assembly = _build_assembly_catalog(catalog_rows, role_pools)
    gold_cases = _build_gold_cases(catalog_rows)
    rollup = _build_rollup(assembly["rows"])
    intake = _build_safe_candidate_intake(catalog_rows)
    markdown_map = _render_markdown_map(assembly["rows"], mat_b_report=mat_b_report or {})

    missing_capabilities = sorted(set(primary_by_capability) - {row["capability"] for row in catalog_rows})
    receipt_blockers = [
        f"{row['capability']}:{row['primary_skill_id']}:runtime_receipt_chain_incomplete"
        for row in catalog_rows
        if not row["receipt_chain_complete"]
    ]
    for payload in (contract, assembly, gold_cases, rollup, intake):
        payload["status"] = "PASS" if not missing_capabilities and not receipt_blockers else "RETURN"
        payload["blockers"] = [f"missing_original_map_row:{capability}" for capability in missing_capabilities] + receipt_blockers
    return {
        "contract": contract,
        "assembly": assembly,
        "gold_cases": gold_cases,
        "rollup": rollup,
        "intake": intake,
        "markdown_map": markdown_map,
    }


def _build_catalog_row(row: Mapping[str, Any], selected: Mapping[str, Any], smoke_case: Mapping[str, Any]) -> dict[str, Any]:
    capability = str(row.get("capability") or "")
    skill_id = str(row.get("primary_skill_id") or "")
    role_tags = _role_tags(capability, skill_id, str(row.get("original_skill_name") or ""))
    return {
        "capability": capability,
        "primary_skill_id": skill_id,
        "original_skill_name": str(row.get("original_skill_name") or skill_id),
        "original_source_path": str(row.get("original_source_path") or ""),
        "source_round_or_root": str(row.get("source_round_or_root") or ""),
        "decision": str(row.get("decision") or ""),
        "role_tags": role_tags,
        "heep_mode": _recommended_mode(capability, role_tags),
        "evidence_refs": list(row.get("evidence_refs") or []),
        "token_delta": selected.get("token_delta_challenger_minus_current"),
        "wall_delta": selected.get("wall_delta_challenger_minus_current"),
        "receipt_path": str(selected.get("receipt_path") or ""),
        "runtime_final_receipt_chain": _receipt_chain(smoke_case),
        "receipt_chain_complete": all(_receipt_chain(smoke_case).values()),
    }


def _build_contract(capability_count: int) -> dict[str, Any]:
    return {
        "schema": "nexus.heep_emas_contract.v1",
        "status": "PASS",
        "summary": {
            "capability_count": capability_count,
            "modes": [MODE_A, MODE_B, MODE_C],
            "roles": ["Scout", "Logic", "Audit"],
            "public_benchmark_allowed": False,
            "runtime_update_allowed": False,
        },
        "modes": {
            MODE_A: {
                "skill_count": 1,
                "purpose": "Primary skill only; lowest coordination cost.",
                "required_roles": ["primary"],
            },
            MODE_B: {
                "skill_count": 2,
                "purpose": "Primary skill plus complementary guard/auditor.",
                "required_roles": ["primary", "complementary_guard"],
            },
            MODE_C: {
                "skill_count": 3,
                "purpose": "Scout, Logic, and Audit roles assembled for consensus.",
                "required_roles": ["Scout", "Logic", "Audit"],
            },
        },
        "metrics": {
            "quality_lift": "dry-run score delta until live ensemble evidence exists",
            "premium_factor": "extra skill count divided by quality lift; lower is better",
            "consensus_score": "role coverage ratio for the proposed assembly",
            "synergy_factor": "ensemble role coverage minus solo role coverage",
        },
        "receipt_requirements": list(RECEIPT_KEYS),
        "claim_boundary": [
            "HEEP/EMAS artifacts are discovery-only until a live ensemble runner produces runtime receipts.",
            "External GitHub skills may enter Safe-Candidate intake only; they do not auto-promote to runtime default.",
            "Public benchmark and runtime apply gates remain separate and fail-closed.",
        ],
        "blockers": [],
    }


def _build_assembly_catalog(catalog_rows: list[dict[str, Any]], role_pools: Mapping[str, list[str]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row in sorted(catalog_rows, key=lambda item: item["capability"]):
        rows.append(_assembly_row(row, role_pools))
    mode_counts: dict[str, int] = {}
    for row in rows:
        mode_counts[row["recommended_mode"]] = mode_counts.get(row["recommended_mode"], 0) + 1
    return {
        "schema": "nexus.heep_assembly_catalog.v1",
        "status": "PASS",
        "summary": {
            "capability_count": len(rows),
            "mode_counts": mode_counts,
            "public_benchmark_allowed": False,
            "runtime_update_allowed": False,
        },
        "rows": rows,
        "claim_boundary": [
            "Assemblies are generated from the current SF SSOT and deterministic role heuristics.",
            "Mode selection is a local evaluation plan, not a public uplift claim.",
        ],
        "blockers": [],
    }


def _assembly_row(row: Mapping[str, Any], role_pools: Mapping[str, list[str]]) -> dict[str, Any]:
    mode = str(row["heep_mode"])
    primary = str(row["primary_skill_id"])
    capability = str(row["capability"])
    if mode == MODE_A:
        assembly = [{"role": "primary", "skill_id": primary}]
    elif mode == MODE_B:
        guard_role = "Audit" if "Audit" not in row["role_tags"] else "Logic"
        assembly = [
            {"role": "primary", "skill_id": primary},
            {"role": guard_role, "skill_id": _pick_complement(role_pools, guard_role, primary)},
        ]
    else:
        assembly = []
        used: set[str] = set()
        for role in ("Scout", "Logic", "Audit"):
            skill_id = primary if role in row["role_tags"] and primary not in used else _pick_complement(role_pools, role, *used)
            used.add(skill_id)
            assembly.append({"role": role, "skill_id": skill_id})
    return {
        "capability": capability,
        "primary_skill_id": primary,
        "primary_role_tags": list(row["role_tags"]),
        "recommended_mode": mode,
        "assembly": assembly,
        "evidence_refs": list(row.get("evidence_refs") or []),
        "receipt_path": str(row.get("receipt_path") or ""),
        "runtime_final_receipt_chain": dict(row.get("runtime_final_receipt_chain") or {}),
        "receipt_chain_complete": bool(row.get("receipt_chain_complete")),
        "decision": str(row.get("decision") or ""),
    }


def _build_gold_cases(catalog_rows: list[dict[str, Any]]) -> dict[str, Any]:
    cases = []
    for row in sorted(catalog_rows, key=lambda item: item["capability"]):
        source = str((row.get("evidence_refs") or [""])[0])
        cases.append(
            {
                "case_id": f"heep-gold-{row['capability']}",
                "capability": row["capability"],
                "primary_skill_id": row["primary_skill_id"],
                "source_evidence_ref": source,
                "expected_receipt_keys": list(RECEIPT_KEYS),
                "runtime_final_receipt_chain": dict(row.get("runtime_final_receipt_chain") or {}),
                "receipt_chain_complete": bool(row.get("receipt_chain_complete")),
                "expected_mode": row["heep_mode"],
                "live_required_for_public_claim": True,
            }
        )
    return {
        "schema": "nexus.heep_gold_case_manifest.v1",
        "status": "PASS",
        "summary": {"case_count": len(cases), "public_benchmark_allowed": False},
        "cases": cases,
        "claim_boundary": [
            "Gold cases point at existing SF evidence roots for deterministic local HEEP dry-runs.",
            "They are not a replacement for live same-model public benchmarks.",
        ],
        "blockers": [],
    }


def _build_rollup(assembly_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    rows = []
    for row in sorted(assembly_rows, key=lambda item: str(item["capability"])):
        mode = str(row["recommended_mode"])
        skill_count = len(row.get("assembly") or [])
        unique_roles = {str(item.get("role")) for item in row.get("assembly", []) if isinstance(item, Mapping)}
        solo_role_count = len(row.get("primary_role_tags") or [])
        quality_lift = max(0.0, (len(unique_roles) - min(solo_role_count, len(unique_roles))) / 3.0)
        premium_factor = round((skill_count - 1) / quality_lift, 4) if quality_lift else None
        consensus_score = round(len(unique_roles) / 3.0, 4)
        rows.append(
            {
                "capability": row["capability"],
                "recommended_mode": mode,
                "evaluation_type": "deterministic_local_dry_run",
                "quality_lift": round(quality_lift, 4),
                "premium_factor": premium_factor,
                "consensus_score": consensus_score,
                "synergy_factor": round(quality_lift, 4),
                "decision": "ready_for_live_heep" if mode != MODE_A else "solo_policy_retained",
                "public_claim_allowed": False,
                "runtime_update_allowed": False,
            }
        )
    return {
        "schema": "nexus.heep_local_abc_rollup.v1",
        "status": "PASS",
        "summary": {
            "capability_count": len(rows),
            "ready_for_live_heep_count": sum(1 for row in rows if row["decision"] == "ready_for_live_heep"),
            "public_benchmark_allowed": False,
            "runtime_update_allowed": False,
        },
        "rows": rows,
        "claim_boundary": [
            "Rollup is a deterministic local HEEP dry-run using role coverage, not a live uplift measurement.",
            "A future live runner must replace dry-run metrics before any runtime or public claim.",
        ],
        "blockers": [],
    }


def _build_safe_candidate_intake(catalog_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for row in sorted(catalog_rows, key=lambda item: item["capability"]):
        source_path = str(row.get("original_source_path") or "")
        source_root = str(row.get("source_round_or_root") or "")
        external = source_root.startswith("round") or source_path.startswith("/private/tmp/")
        rows.append(
            {
                "capability": row["capability"],
                "skill_id": row["primary_skill_id"],
                "original_skill_name": row["original_skill_name"],
                "source_round_or_root": source_root,
                "source_path": source_path,
                "source_class": "safe_candidate" if external else "repo_local_or_current_best",
                "sanitize_status": "sanitized_prompt_only" if external else "not_required_repo_local",
                "runtime_promotion_allowed": False,
                "public_benchmark_allowed": False,
            }
        )
    return {
        "schema": "nexus.emas_safe_candidate_intake.v1",
        "status": "PASS",
        "summary": {
            "candidate_count": len(rows),
            "safe_candidate_count": sum(1 for row in rows if row["source_class"] == "safe_candidate"),
            "runtime_promotion_allowed": False,
            "public_benchmark_allowed": False,
        },
        "rows": rows,
        "claim_boundary": [
            "EMAS intake records sanitized candidate provenance only.",
            "No candidate in this artifact is automatically promoted to runtime default.",
        ],
        "blockers": [],
    }


def _render_markdown_map(rows: list[Mapping[str, Any]], *, mat_b_report: Mapping[str, Any]) -> str:
    mat_b_by_capability = {
        str(row.get("capability") or ""): row
        for row in (mat_b_report.get("comparisons", []) or [])
        if isinstance(row, Mapping) and row.get("capability")
    }
    mat_b_summary = mat_b_report.get("summary", {}) if isinstance(mat_b_report.get("summary"), Mapping) else {}
    comparison_count = int(mat_b_summary.get("comparison_count") or 0)
    capability_count = len(rows)
    evidence_note = (
        f"> MAT-B live compare coverage: {comparison_count}/{capability_count} capabilities."
        if comparison_count
        else "> MAT-B live compare coverage: not attached; this map is local HEEP assembly only."
    )
    lines = [
        "# Nexus 能力與 Skill 映射表 (2026-05-20)",
        "",
        "> [!NOTE]",
        "> 本文件由 `scripts/ops/build_heep_emas_pipeline.py` 依據 SF SSOT 與 HEEP/EMAS contract 自動生成。",
        evidence_note,
        "> runtime default 與 public benchmark 仍需獨立 gate。",
        "",
        "## 映射總表",
        "",
        "| 能力 (Capability) | 當前主技能 (Primary Skill ID) | HEEP Mode | EMAS Assembly | MAT-B Live Verdict | Evidence |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for row in sorted(rows, key=lambda item: str(item["capability"])):
        mat_b = mat_b_by_capability.get(str(row["capability"]), {})
        verdict = str(mat_b.get("verdict") or "NOT_IN_MAT_B_LIVE_COMPARE")
        reasons = ", ".join(str(item) for item in (mat_b.get("reason_codes", []) or []))
        verdict_cell = verdict if not reasons else f"{verdict} ({reasons})"
        assembly = ", ".join(f"{item['role']}={item['skill_id']}" for item in row.get("assembly", []))
        evidence = (
            "[MAT-B live report](../reports/NEXUS_HEEP_MAT_B_LIVE_REPORT_2026-05-20.json)"
            if mat_b
            else ("receipt-backed SF root" if row.get("evidence_refs") else "missing evidence ref")
        )
        lines.append(
            f"| `{row['capability']}` | `{row['primary_skill_id']}` | **{row['recommended_mode']}** | {assembly} | {verdict_cell} | {evidence} |"
        )
    lines.extend(
        [
            "",
            "## 邊界",
            "- Mode A/B/C 是 HEEP internal evaluation policy，不是 public benchmark claim。",
            "- MAT-B verdict 只代表內部 Flash+Nexus multi-skill compare，不等於 runtime default apply。",
            "- EMAS Safe-Candidate 不會自動 promotion 到 runtime default。",
            "- 任何 runtime apply 仍需 runtime-confirmed selected/injected/used/evidence/gate/outcome receipt。",
            "",
            "---",
            "*Generated by Nexus HEEP/EMAS pipeline.*",
            "",
        ]
    )
    return "\n".join(lines)


def _role_tags(capability: str, skill_id: str, skill_name: str) -> list[str]:
    blob = f"{capability} {skill_id} {skill_name}".lower()
    roles = [role for role, terms in ROLE_TERMS.items() if any(term in blob for term in terms)]
    return roles or ["Logic"]


def _recommended_mode(capability: str, roles: list[str]) -> str:
    if capability in LEAN_CAPABILITIES:
        return MODE_A
    if any(term in capability for term in SWARM_CAPABILITY_TERMS):
        return MODE_C
    if len(set(roles)) >= 3:
        return MODE_C
    return MODE_B


def _role_pools(catalog_rows: list[Mapping[str, Any]]) -> dict[str, list[str]]:
    pools: dict[str, list[str]] = {"Scout": [], "Logic": [], "Audit": []}
    for row in sorted(catalog_rows, key=lambda item: str(item["capability"])):
        for role in row.get("role_tags") or []:
            if role in pools:
                pools[role].append(str(row["primary_skill_id"]))
    for role, fallback in (
        ("Scout", "diagnose"),
        ("Logic", "create-plan"),
        ("Audit", "acceptance-evidence-failclosed"),
    ):
        if not pools[role]:
            pools[role].append(fallback)
    return {role: _dedupe(values) for role, values in pools.items()}


def _pick_complement(role_pools: Mapping[str, list[str]], role: str, *excluded: str) -> str:
    excluded_set = {value for value in excluded if value}
    for skill_id in role_pools.get(role, []):
        if skill_id not in excluded_set:
            return skill_id
    return (role_pools.get(role) or [f"missing-{role.lower()}-candidate"])[0]


def _index_by(items: Any, key: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(items, list):
        return {}
    indexed: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if isinstance(item, Mapping):
            indexed[str(item.get(key) or "")] = item
    return {key: value for key, value in indexed.items() if key}


def _receipt_chain(smoke_case: Mapping[str, Any]) -> dict[str, bool]:
    raw_chain = smoke_case.get("runtime_final_receipt_chain", {})
    chain = raw_chain if isinstance(raw_chain, Mapping) else {}
    return {key: bool(chain.get(key, False)) for key in RECEIPT_KEYS}


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def write_heep_emas_artifacts(
    *,
    artifacts: Mapping[str, dict[str, Any] | str],
    report_dir: Path,
    info_map: Path,
) -> dict[str, str]:
    outputs = {
        "contract": report_dir / "NEXUS_HEEP_EMAS_CONTRACT_2026-05-20.json",
        "assembly": report_dir / "NEXUS_HEEP_ASSEMBLY_CATALOG_2026-05-20.json",
        "gold_cases": report_dir / "NEXUS_HEEP_GOLD_CASE_MANIFEST_2026-05-20.json",
        "rollup": report_dir / "NEXUS_HEEP_LOCAL_ABC_ROLLUP_2026-05-20.json",
        "intake": report_dir / "NEXUS_EMAS_SAFE_CANDIDATE_INTAKE_2026-05-20.json",
    }
    for key, path in outputs.items():
        _write_json(path, artifacts[key])  # type: ignore[arg-type]
    info_map.parent.mkdir(parents=True, exist_ok=True)
    info_map.write_text(str(artifacts["markdown_map"]), encoding="utf-8")
    return {key: str(path) for key, path in outputs.items()} | {"markdown_map": str(info_map)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build HEEP/EMAS discovery-only artifacts from the current SF SSOT.")
    parser.add_argument("--original-map", default=str(DEFAULT_ORIGINAL_MAP), type=Path)
    parser.add_argument("--overlay", default=str(DEFAULT_OVERLAY), type=Path)
    parser.add_argument("--smoke", default=str(DEFAULT_SMOKE), type=Path)
    parser.add_argument("--mat-b-report", default=str(DEFAULT_MAT_B_REPORT), type=Path)
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR), type=Path)
    parser.add_argument("--info-map", default=str(DEFAULT_INFO_MAP), type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    artifacts = build_heep_emas_artifacts(
        original_map=_read_json(args.original_map),
        overlay=_read_json(args.overlay),
        smoke=_read_json(args.smoke),
        mat_b_report=_read_json(args.mat_b_report) if args.mat_b_report.exists() else {},
    )
    status = "PASS" if all(artifacts[key]["status"] == "PASS" for key in ("contract", "assembly", "gold_cases", "rollup", "intake")) else "RETURN"  # type: ignore[index]
    outputs: dict[str, str] = {}
    if not args.dry_run:
        outputs = write_heep_emas_artifacts(artifacts=artifacts, report_dir=args.report_dir, info_map=args.info_map)
    print(
        json.dumps(
            {
                "status": status,
                "capability_count": artifacts["assembly"]["summary"]["capability_count"],  # type: ignore[index]
                "ready_for_live_heep_count": artifacts["rollup"]["summary"]["ready_for_live_heep_count"],  # type: ignore[index]
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
