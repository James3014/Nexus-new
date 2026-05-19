#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INVENTORY = PROJECT_ROOT / "docs/reports/NEXUS_SF_COVERAGE_INVENTORY_2026-05-19.json"
DEFAULT_OVERLAY = PROJECT_ROOT / "docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V30_2026-05-19.json"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "docs/reports"
DEFAULT_SKILL_ROOT = PROJECT_ROOT / ".agents/skills/sf-systematic-challengers"
DEFAULT_MODEL = "gemini-3-flash-preview"


CAPABILITY_TERMS = {
    "artifact_gate": ["artifact", "evidence", "acceptance", "receipt", "proof"],
    "autonomic_router": ["autonomic", "router", "route", "routing", "policy"],
    "autoreason": ["reason", "first principles", "assumption", "causal", "decision"],
    "belief": ["belief", "confidence", "judgment", "uncertainty", "state"],
    "benchmark_meta_opt": ["benchmark", "ab test", "evaluation", "metric", "experiment"],
    "claim_gate": ["claim", "citation", "verify", "evidence", "proof"],
    "codeintel": ["code", "repo", "complexity", "impact", "context", "architecture"],
    "ddtree": ["ddtree", "decision tree", "candidate", "prune", "accelerate"],
    "direct_master_loop": ["execute", "implement", "workflow", "plan", "task"],
    "drone": ["drone", "delegate", "worker", "execution", "tactical"],
    "external_productivity": ["office", "document", "automation", "productivity"],
    "file_lock_security_gate": ["file lock", "lock", "security", "permission", "safe"],
    "forecast_pregate": ["forecast", "plan", "spec", "risk", "implementation"],
    "governance_and_trust": ["governance", "trust", "policy", "audit", "safety"],
    "hyper_sprint": ["hyper", "sprint", "fast", "candidate", "repair"],
    "lancedb": ["lancedb", "vector", "semantic", "embedding", "retrieval"],
    "learn_ask": ["learn", "ask", "question", "answer", "knowledge"],
    "learning_closure": ["learn", "learning", "closure", "feedback", "memory"],
    "memory": ["memory", "remember", "experience", "history", "recall"],
    "mempalace": ["mempalace", "policy", "ethics", "boundary", "governance"],
    "metabolism_resume": ["metabolism", "resume", "distill", "continue", "handoff"],
    "nightshift": ["nightshift", "long running", "recovery", "overnight", "repair"],
    "policy_capability_gate": ["policy", "capability", "gate", "guardrail", "permission"],
    "registry_skills_sync": ["skill", "registry", "catalog", "sync"],
    "regression_guard": ["regression", "guard", "test", "verify", "prevent"],
    "repair_loop": ["bug", "debug", "repair", "tdd", "test", "regression"],
    "research": ["research", "source", "paper", "citation", "lookup"],
    "research_and_source_discipline": ["research", "source", "citation", "verify", "discipline"],
    "research_control_plane": ["research", "paper", "source", "citation", "scientific"],
    "sandbox_replay": ["sandbox", "replay", "isolate", "verify", "execution"],
    "swarm_multi_agent": ["swarm", "multi-agent", "agent", "fleet", "coordination"],
    "ui_validator": ["ui", "browser", "playwright", "screenshot", "visual"],
    "ultra_review": ["security", "review", "vulnerability", "risk", "audit"],
    "xray": ["xray", "inspect", "scan", "trace", "diagnose"],
}

RUNNER_CAPABILITY_ALIAS = {
    "artifact_gate": "claim_gate",
    "autonomic_router": "autoreason",
    "autoreason": "autoreason",
    "belief": "autoreason",
    "benchmark_meta_opt": "judge_panel",
    "claim_gate": "claim_gate",
    "codeintel": "codeintel",
    "ddtree": "autoreason",
    "direct_master_loop": "hyper",
    "drone": "hyper",
    "external_productivity": "research",
    "file_lock_security_gate": "ultra_review",
    "forecast_pregate": "autoreason",
    "governance_and_trust": "claim_gate",
    "hyper_sprint": "hyper",
    "lancedb": "semantic_searcher",
    "learn_ask": "research",
    "learning_closure": "semantic_failure_sensor",
    "memory": "semantic_searcher",
    "mempalace": "claim_gate",
    "metabolism_resume": "semantic_failure_sensor",
    "nightshift": "hyper",
    "policy_capability_gate": "claim_gate",
    "registry_skills_sync": "semantic_searcher",
    "regression_guard": "ultra_review",
    "repair_loop": "hyper",
    "research": "research",
    "research_and_source_discipline": "research",
    "research_control_plane": "research",
    "sandbox_replay": "ultra_review",
    "swarm_multi_agent": "hyper",
    "ui_validator": "ultra_review",
    "ultra_review": "ultra_review",
    "xray": "codeintel",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:80] or "skill"


def _tokens(value: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9]+", value.lower()) if len(part) >= 3}


def _skill_source_path(item: Mapping[str, Any]) -> Path:
    return Path(str(item.get("source_root") or "")) / str(item.get("relative_skill_path") or "")


def _extract_triggers(text: str, headings: tuple[str, ...]) -> list[str]:
    lines = text.splitlines()
    out: list[str] = []
    capture = False
    for raw in lines:
        line = raw.strip()
        lower = line.lower().rstrip(":")
        if line.startswith("#") and capture:
            break
        if any(head in lower for head in headings):
            capture = True
            continue
        if capture and line.startswith(("-", "*")):
            out.append(line.lstrip("-* ").strip())
        if len(out) >= 5:
            break
    return out


def compile_interfaces(inventory: Mapping[str, Any]) -> dict[str, Any]:
    by_hash: dict[str, dict[str, Any]] = {}
    duplicates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in inventory.get("inventory", []) or []:
        if not isinstance(item, dict):
            continue
        content_sha = str(item.get("content_sha256") or "")
        if not content_sha:
            continue
        duplicates[content_sha].append(item)
        current = by_hash.get(content_sha)
        score = 0
        if item.get("safety_class") == "prompt_only_candidate":
            score += 2
        if item.get("round") != "round4":
            score += 1
        if not item.get("risk_flags"):
            score += 1
        if current is None or score > int(current.get("_source_score", 0)):
            by_hash[content_sha] = {**item, "_source_score": score}

    interfaces = []
    for content_sha, item in sorted(by_hash.items()):
        source_path = _skill_source_path(item)
        text = source_path.read_text(errors="ignore") if source_path.exists() else ""
        name = str(item.get("skill_name") or item.get("skill_slug_guess") or "skill")
        description = str(item.get("description") or "")
        capability_guess = str(item.get("capability_guess") or "unclassified")
        risk_flags = list(item.get("risk_flags") or [])
        load_when = _extract_triggers(text, ("load when", "when to use", "use when", "triggers"))
        do_not_load_when = _extract_triggers(text, ("do not load", "do not use", "avoid", "do not"))
        capability_hints = [capability_guess] if capability_guess != "unclassified" else []
        for cap, terms in CAPABILITY_TERMS.items():
            blob = f"{name} {description} {item.get('relative_skill_path')} {text[:1200]}".lower()
            if sum(1 for term in terms if term in blob) >= 2 and cap not in capability_hints:
                capability_hints.append(cap)
        estimated_context_tokens = max(16, min(600, len(text[:2400].split()) * 4 // 3))
        interfaces.append(
            {
                "interface_id": f"sfci-{content_sha}",
                "skill_name": name,
                "skill_slug": str(item.get("skill_slug_guess") or _slug(name)),
                "canonical_source": str(source_path),
                "round": item.get("round"),
                "content_sha16": content_sha,
                "duplicate_count": len(duplicates[content_sha]),
                "capability_hints": capability_hints,
                "description": description,
                "load_when": load_when[:5] or [description[:180]],
                "do_not_load_when": do_not_load_when[:5],
                "tool_boundary": "review_required" if risk_flags else "prompt_only",
                "risk_flags": risk_flags,
                "receipt_requirements": ["selected", "injected", "used", "evidence_present", "gate_passed", "outcome_contributed"],
                "estimated_context_tokens": estimated_context_tokens,
            }
        )
    return {
        "schema": "nexus.sf_systematic_compiled_skill_interfaces.v1",
        "status": "PASS",
        "summary": {
            "raw_candidate_count": len(inventory.get("inventory", []) or []),
            "compiled_interface_count": len(interfaces),
            "duplicate_group_count": sum(1 for items in duplicates.values() if len(items) > 1),
        },
        "interfaces": interfaces,
        "claim_boundary": [
            "Compiled interfaces are static ranking artifacts, not live skill effectiveness evidence.",
            "Runtime should inject task-relevant interface slices, not full raw SKILL.md content.",
        ],
    }


def _score_interface(interface: Mapping[str, Any], capability: str) -> tuple[float, list[str]]:
    terms = CAPABILITY_TERMS.get(capability, [])
    blob = " ".join(
        [
            str(interface.get("skill_name") or ""),
            str(interface.get("description") or ""),
            " ".join(interface.get("capability_hints") or []),
            " ".join(interface.get("load_when") or []),
        ]
    ).lower()
    reasons: list[str] = []
    score = 0.0
    for term in terms:
        if term in blob:
            score += 3.0
            reasons.append(f"term:{term}")
    if capability in (interface.get("capability_hints") or []):
        score += 8.0
        reasons.append("capability_hint")
    if reasons:
        score += min(3.0, float(len(interface.get("load_when") or [])))
    if interface.get("tool_boundary") != "prompt_only":
        score -= 8.0
        reasons.append("risk_penalty")
    score -= max(0, int(interface.get("duplicate_count") or 1) - 1) * 0.2
    score -= min(3.0, float(interface.get("estimated_context_tokens") or 0) / 400.0)
    return round(score, 4), reasons[:8]


def build_tournament(interfaces: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    current_primary = overlay.get("candidate_primary_skill_by_capability") or {}
    rows = []
    top_by_capability: dict[str, list[dict[str, Any]]] = {}
    for capability in sorted(current_primary):
        candidates = []
        for interface in interfaces.get("interfaces", []) or []:
            if not isinstance(interface, dict):
                continue
            score, reasons = _score_interface(interface, capability)
            if score <= 0:
                continue
            candidates.append(
                {
                    "capability": capability,
                    "interface_id": interface["interface_id"],
                    "skill_name": interface["skill_name"],
                    "skill_slug": interface["skill_slug"],
                    "canonical_source": interface["canonical_source"],
                    "score": score,
                    "reasons": reasons,
                    "risk_flags": interface.get("risk_flags", []),
                    "tool_boundary": interface.get("tool_boundary"),
                    "estimated_context_tokens": interface.get("estimated_context_tokens"),
                    "current_primary_skill": current_primary[capability],
                }
            )
        candidates.sort(key=lambda item: (-item["score"], item["risk_flags"], item["skill_slug"]))
        top_by_capability[capability] = candidates[:16]
        rows.extend(candidates[:16])
    return {
        "schema": "nexus.sf_systematic_offline_tournament.v1",
        "status": "PASS",
        "summary": {
            "capability_count": len(current_primary),
            "ranked_row_count": len(rows),
            "top_k_per_capability": 16,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "top_by_capability": top_by_capability,
        "claim_boundary": [
            "Offline score is a routing prior only.",
            "No replacement is allowed until paired Flash+Nexus receipts confirm effectiveness.",
        ],
    }


def build_successive_halving(tournament: Mapping[str, Any]) -> dict[str, Any]:
    stages: dict[str, dict[str, list[dict[str, Any]]]] = {"top16": {}, "top8": {}, "top4": {}}
    for capability, rows in (tournament.get("top_by_capability") or {}).items():
        safe_rows = [row for row in rows if not row.get("risk_flags")]
        if not safe_rows:
            safe_rows = list(rows)
        stages["top16"][capability] = list(rows)[:16]
        stages["top8"][capability] = safe_rows[:8]
        stages["top4"][capability] = safe_rows[:4]
    return {
        "schema": "nexus.sf_systematic_successive_halving.v1",
        "status": "PASS",
        "summary": {
            "capability_count": len(stages["top4"]),
            "top4_row_count": sum(len(rows) for rows in stages["top4"].values()),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "stages": stages,
        "claim_boundary": [
            "Successive halving narrows live candidates; it is not a final skill verdict.",
            "Risk-flagged candidates are excluded from top8/top4 unless no safe candidate exists.",
        ],
    }


def _copy_slice_skill(interface: Mapping[str, Any], *, skill_id: str, target_root: Path) -> str:
    target = target_root / skill_id / "SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f"name: {skill_id}",
        f"description: {interface.get('description') or interface.get('skill_name')}",
        "metadata: {\"source_status\":\"systematic_compiled_interface\", \"runtime_eligible\":false, \"ablation_eligible\":true}",
        "---",
        "",
        f"# {interface.get('skill_name')}",
        "",
        "## Load when",
        *[f"- {item}" for item in interface.get("load_when") or []],
        "",
        "## Do not load when",
        *[f"- {item}" for item in interface.get("do_not_load_when") or ["runtime default promotion is requested without receipt review"]],
        "",
        "## Required receipts",
        *[f"- {item}" for item in interface.get("receipt_requirements") or []],
        "",
        "## Source",
        f"- {interface.get('canonical_source')}",
        "",
    ]
    target.write_text("\n".join(lines), encoding="utf-8")
    try:
        return str(target.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(target)


def _runner_args(tasks_path: Path, task_id: str, model: str) -> list[str]:
    return [
        "uv",
        "run",
        "python",
        "scripts/bench/capability_ab_runner.py",
        "--tasks-file",
        str(tasks_path),
        "--task-id-filter",
        task_id,
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
        "--enable-autoreason-executor",
        "--enable-ddtree-executor",
        "--enable-ultra-review-dry-gate",
        "--llm-candidate-cap",
        "3",
        "--evidence-bundle",
        "--no-progress-log",
    ]


def build_batch_matrix(
    *,
    interfaces: Mapping[str, Any],
    halving: Mapping[str, Any],
    overlay: Mapping[str, Any],
    report_dir: Path,
    skill_root: Path,
    batch_cap: int,
    model: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    interface_by_id = {item["interface_id"]: item for item in interfaces.get("interfaces", []) or []}
    current_primary = overlay.get("candidate_primary_skill_by_capability") or {}
    selected = []
    for capability, rows in (halving.get("stages", {}).get("top4") or {}).items():
        if capability not in RUNNER_CAPABILITY_ALIAS:
            continue
        for row in rows:
            interface = interface_by_id[row["interface_id"]]
            skill_id = f"sf-systematic-{capability}-{_slug(str(interface['skill_name']))}-{interface['content_sha16'][:8]}"
            if row["skill_slug"] == current_primary.get(capability) or skill_id == current_primary.get(capability):
                continue
            selected.append((capability, row))
            break
        if len(selected) >= batch_cap:
            break
    tasks_path = report_dir / "NEXUS_SF_SYSTEMATIC_BATCH_FLASH_SMOKE_TASKS_2026-05-19.json"
    status_path = report_dir / "NEXUS_SF_SYSTEMATIC_BATCH_SKILL_STATUS_2026-05-19.json"
    matrix_path = report_dir / "NEXUS_SF_SYSTEMATIC_BATCH_FLASH_SMOKE_MATRIX_2026-05-19.json"
    tasks = []
    status_rows = []
    matrix_rows = []
    runtime_slices = []
    for capability, row in selected:
        interface = interface_by_id[row["interface_id"]]
        skill_id = f"sf-systematic-{capability}-{_slug(str(interface['skill_name']))}-{interface['content_sha16'][:8]}"
        slice_path = _copy_slice_skill(interface, skill_id=skill_id, target_root=skill_root)
        runtime_slices.append({"capability": capability, "skill_id": skill_id, "interface_id": row["interface_id"], "path": slice_path})
        task_id = f"sf-systematic-batch-{capability}-001"
        runner_capability = RUNNER_CAPABILITY_ALIAS[capability]
        tasks.append(
            {
                "id": task_id,
                "task_desc": f"Systematic SF batch compare for {capability}: current_best vs compiled-interface challenger.",
                "target_file": "unused",
                "test_file": "unused",
                "success_criteria": "sf_systematic_batch_receipt_chain_complete",
                "category": capability,
                "difficulty": "medium",
                "repo_kind": "neutral_fixture",
                "repo": "fixture://sf-systematic-batch",
                "repo_ref": "v1",
                "fixture_kind": "sf_systematic_batch",
                "mutation_required": False,
                "allowed_files": ["unused"],
                "forbidden_files": [".nexus/", "logs/", "benchmarks/"],
                "setup_command": "python -V",
                "verification_command": "python -V",
                "expected_capabilities": [runner_capability],
                "capability_activation_contract": "required",
                "eligibility_class": "model_required",
                "public_claim_allowed_metrics": [],
            }
        )
        for arm, mounted_skill, root, path in [
            ("current_best", current_primary[capability], "current_best", ""),
            ("challenger", skill_id, "sf_systematic_compiled_interface", slice_path),
        ]:
            status_rows.append(
                {
                    "name": mounted_skill,
                    "path": path,
                    "root": root,
                    "skill_status": "nexus_curated_candidate" if arm == "current_best" else "external_reference_candidate",
                    "test_level": "sf_systematic_batch",
                    "action": "ablation_only_compare",
                    "capability_mount": runner_capability,
                    "family": capability,
                    "reason_codes": [f"sf_systematic_{arm}"],
                }
            )
            matrix_rows.append(
                {
                    "row_id": f"{capability}::{task_id}::{arm}::{mounted_skill}",
                    "task_ref": {"manifest": str(tasks_path), "task_id": task_id},
                    "model": model,
                    "capability": capability,
                    "sf_route_capability_id": capability,
                    "runner_capability_id": runner_capability,
                    "arm_id": arm,
                    "arm_type": "skill_ablation",
                    "anonymous_label": arm,
                    "skill_id": mounted_skill,
                    "source_root": root,
                    "source_type": "nexus_curated_candidate" if arm == "current_best" else "external_reference_candidate",
                    "runtime_eligible": arm == "current_best",
                    "ablation_eligible": True,
                    "skill_mount_requests": [mounted_skill],
                    "runner_env": {
                        "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
                        "NEXUS_DIRECT_GEMINI_MODEL": model,
                        "NEXUS_CAPABILITY_RECEIPT_FIRST": "1",
                        "NEXUS_BENCH_SKILL_STATUS_REPORT": str(status_path),
                        "NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS": "1",
                        "NEXUS_BENCH_SKILL_MOUNT_REQUESTS": json.dumps([mounted_skill]),
                    },
                    "runner_args": _runner_args(tasks_path, task_id, model),
                    "expected_outcome": "sf_systematic_compiled_interface_receipt_chain_complete",
                }
            )
    task_manifest = {
        "benchmark_id": "nexus-sf-systematic-batch-v1",
        "description": "Internal SF systematic compiled-interface batch current_best vs challenger matrix. Not a public benchmark.",
        "frozen": True,
        "schema": "nexus.sf_systematic_batch_tasks.v1",
        "status": "PASS",
        "summary": {"task_count": len(tasks), "capability_count": len(tasks), "runtime_update_allowed": False, "public_benchmark_allowed": False},
        "tasks": tasks,
        "version": "2026-05-19",
    }
    status_report = {
        "schema": "nexus.sf_systematic_batch_skill_status.v1",
        "summary": {"skill_count": len(status_rows), "runtime_update_allowed": False, "public_benchmark_allowed": False},
        "skills": status_rows,
    }
    matrix = {
        "schema": "nexus.sf_systematic_batch_matrix.v1",
        "status": "PASS",
        "summary": {"capability_count": len(tasks), "task_count": len(tasks), "row_count": len(matrix_rows), "arm_count": 2, "model": model, "runtime_update_allowed": False, "public_benchmark_allowed": False},
        "rows": matrix_rows,
        "claim_boundary": ["Batch matrix is queued evidence, not a replacement decision."],
    }
    slices = {
        "schema": "nexus.sf_systematic_runtime_slices.v1",
        "status": "PASS",
        "summary": {"slice_count": len(runtime_slices), "runtime_update_allowed": False, "public_benchmark_allowed": False},
        "runtime_slices": runtime_slices,
        "claim_boundary": ["Slices are ablation-only compiled interfaces; do not mount as runtime default without apply gate."],
    }
    _write_json(tasks_path, task_manifest)
    _write_json(status_path, status_report)
    _write_json(matrix_path, matrix)
    return task_manifest, status_report, matrix, slices


def build_decision_gate(*, overlay: Mapping[str, Any], batch_matrix: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "nexus.sf_systematic_replacement_decision_gate.v1",
        "status": "PASS",
        "summary": {
            "queued_batch_row_count": len(batch_matrix.get("rows", []) or []),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "required_replacement_conditions": [
            "current_best_status_PASS",
            "challenger_status_PASS",
            "selected_injected_used_evidence_gate_outcome_all_true",
            "challenger_token_delta_lower_than_current",
            "challenger_wall_delta_lower_than_current",
            "receipt_path_present",
            "evidence_path_present",
        ],
        "current_overlay_schema": overlay.get("schema"),
        "claim_boundary": [
            "This gate defines replacement criteria for future live rollup.",
            "It does not approve runtime default writes.",
        ],
    }


def build_all(args: argparse.Namespace) -> dict[str, Any]:
    inventory = _read_json(Path(args.inventory))
    overlay = _read_json(Path(args.overlay))
    report_dir = Path(args.report_dir)
    interfaces = compile_interfaces(inventory)
    tournament = build_tournament(interfaces, overlay)
    halving = build_successive_halving(tournament)
    _, _, batch_matrix, slices = build_batch_matrix(
        interfaces=interfaces,
        halving=halving,
        overlay=overlay,
        report_dir=report_dir,
        skill_root=Path(args.skill_root),
        batch_cap=int(args.batch_cap),
        model=str(args.model),
    )
    decision_gate = build_decision_gate(overlay=overlay, batch_matrix=batch_matrix)
    paths = {
        "interfaces": report_dir / "NEXUS_SF_SYSTEMATIC_COMPILED_INTERFACES_2026-05-19.json",
        "tournament": report_dir / "NEXUS_SF_SYSTEMATIC_OFFLINE_TOURNAMENT_2026-05-19.json",
        "halving": report_dir / "NEXUS_SF_SYSTEMATIC_SUCCESSIVE_HALVING_2026-05-19.json",
        "runtime_slices": report_dir / "NEXUS_SF_SYSTEMATIC_RUNTIME_SLICES_2026-05-19.json",
        "decision_gate": report_dir / "NEXUS_SF_SYSTEMATIC_DECISION_GATE_2026-05-19.json",
        "plan": report_dir / "NEXUS_SF_SYSTEMATIC_SKILLSMITH_LITE_PLAN_2026-05-19.md",
    }
    _write_json(paths["interfaces"], interfaces)
    _write_json(paths["tournament"], tournament)
    _write_json(paths["halving"], halving)
    _write_json(paths["runtime_slices"], slices)
    _write_json(paths["decision_gate"], decision_gate)
    paths["plan"].write_text(render_plan(interfaces, tournament, halving, batch_matrix, decision_gate), encoding="utf-8")
    return {
        "status": "PASS",
        "compiled_interface_count": interfaces["summary"]["compiled_interface_count"],
        "tournament_row_count": tournament["summary"]["ranked_row_count"],
        "top4_row_count": halving["summary"]["top4_row_count"],
        "batch_row_count": batch_matrix["summary"]["row_count"],
        "paths": {key: str(path) for key, path in paths.items()},
    }


def render_plan(
    interfaces: Mapping[str, Any],
    tournament: Mapping[str, Any],
    halving: Mapping[str, Any],
    batch_matrix: Mapping[str, Any],
    decision_gate: Mapping[str, Any],
) -> str:
    return "\n".join(
        [
            "# NEXUS SF Systematic Skill Tournament Plan - 2026-05-19",
            "",
            "## Status",
            "PASS: SkillSmith-lite compiled interface, offline tournament, successive halving, batch matrix, runtime slices, and decision gate were generated.",
            "",
            "## Counts",
            f"- compiled_interface_count: {interfaces['summary']['compiled_interface_count']}",
            f"- duplicate_group_count: {interfaces['summary']['duplicate_group_count']}",
            f"- tournament_row_count: {tournament['summary']['ranked_row_count']}",
            f"- top4_row_count: {halving['summary']['top4_row_count']}",
            f"- queued_batch_row_count: {batch_matrix['summary']['row_count']}",
            "",
            "## Replacement Gate",
            *[f"- {item}" for item in decision_gate["required_replacement_conditions"]],
            "",
            "## Milestone Roadmap",
            "- DONE: SF-SYS-1 compiled skill interface.",
            "- DONE: SF-SYS-2 all-candidate offline tournament.",
            "- DONE: SF-SYS-3 successive halving.",
            "- DONE: SF-SYS-4 batched Flash+Nexus matrix queued.",
            "- DONE: SF-SYS-5 replacement decision gate.",
            "- DONE: SF-SYS-6 SkillSmith-lite runtime slices.",
            "- NEXT: run the generated batch matrix live when ready.",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build systematic SF SkillSmith-lite tournament artifacts.")
    parser.add_argument("--inventory", default=str(DEFAULT_INVENTORY))
    parser.add_argument("--overlay", default=str(DEFAULT_OVERLAY))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--skill-root", default=str(DEFAULT_SKILL_ROOT))
    parser.add_argument("--batch-cap", type=int, default=16)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    report = build_all(args)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
