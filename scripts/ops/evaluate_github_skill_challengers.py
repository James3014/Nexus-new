#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any, Mapping

from scripts.ops.evaluate_sf_skill_creator_before_after import (
    _capability_keywords,
    _frontmatter,
    _rank,
    _read_json,
    _skill_path,
    _write_json,
)


REPOS = {
    "andrej-karpathy-skills": {
        "url": "https://github.com/multica-ai/andrej-karpathy-skills",
        "candidate_slug": "github-karpathy-guidelines",
        "source_skill": "skills/karpathy-guidelines/SKILL.md",
        "target_capabilities": ["repair_loop", "direct_master_loop", "codeintel"],
        "safety": "PASS",
        "notes": "No install-time code in the skill; README contains curl install examples only.",
    },
    "Skills-Security-Check": {
        "url": "https://github.com/Toolsai/Skills-Security-Check",
        "candidate_slug": "github-skills-security-check",
        "source_skill": "SKILL.md",
        "target_capabilities": ["governance_and_trust", "artifact_gate", "ultra_review"],
        "safety": "PASS",
        "notes": "Static scanner skill; script uses regex scanning and does not execute scanned skills.",
    },
    "auto-skill": {
        "url": "https://github.com/Toolsai/auto-skill",
        "candidate_slug": "github-auto-skill-safe-learning",
        "source_skill": "SKILL.md",
        "target_capabilities": ["learning_closure", "metabolism_resume", "registry_skills_sync"],
        "safety": "REJECT_OR_REWRITE",
        "notes": "Original skill self-modifies global IDE rules and mandates itself for all tasks; use only a generated safe candidate.",
    },
    "idea-reality-mcp": {
        "url": "https://github.com/mnemox-ai/idea-reality-mcp",
        "candidate_slug": "github-idea-reality-check",
        "source_skill": "skills/idea-check/SKILL.md",
        "target_capabilities": ["forecast_pregate", "research", "research_control_plane", "benchmark_meta_opt"],
        "safety": "PASS_WITH_RUNTIME_BOUNDARY",
        "notes": "Skill is useful for prior-art checks; MCP/API code uses optional tokens and external network, so keep as candidate-only unless runtime tool boundary is reviewed.",
    },
}


GENERATED_SKILLS = {
    "github-auto-skill-safe-learning": {
        "name": "github-auto-skill-safe-learning",
        "description": "當使用者要求 Nexus 執行 learning_closure, metabolism_resume, or registry_skills_sync work that needs safe cross-skill learning, experience writeback planning, or skill registry maintenance without modifying global IDE rules; return receipt/evidence/gate/outcome-backed guidance for SF review. Do not use for automatic global rule edits, forced always-on behavior, or memory writes without explicit approval.",
        "body": """# GitHub Auto Skill Safe Learning

Candidate-only adaptation of Toolsai/auto-skill principles.

## Load when
- Nexus needs a safe learning-closure or registry-sync skill candidate.
- The task asks for experience writeback planning, knowledge indexing, or skill maintenance.

## Do not load when
- A workflow tries to edit global IDE rules automatically.
- A skill declares itself mandatory for every task.
- Memory writes lack explicit user approval.

## Required receipts
- source_screen
- explicit_user_approval_for_writeback
- changed_index_paths
- rollback_plan

## Boundary
This is a generated candidate. It is not the original auto-skill and must not inherit its forced self-install or global-rule mutation behavior.
""",
    }
}


DESCRIPTION_OVERRIDES = {
    "github-karpathy-guidelines": "當使用者要求 Nexus 執行 repair_loop, direct_master_loop, or codeintel work that needs careful coding judgment, surgical edits, assumption surfacing, and verifiable success criteria. Do not use when the task only needs security scanning, source research, or runtime policy promotion.",
    "github-skills-security-check": "當使用者要求 Nexus 執行 governance_and_trust, artifact_gate, or ultra_review work that needs static skill safety screening, suspicious command detection, and AI-reviewed risk notes. Do not use to execute untrusted skills or to auto-promote scanned skills.",
    "github-idea-reality-check": "當使用者要求 Nexus 執行 forecast_pregate, research, research_control_plane, or benchmark_meta_opt work that needs build-vs-buy prior-art checks, competitor discovery, or idea feasibility screening. Do not use as a runtime MCP tool unless external network and token boundaries are separately approved.",
}


def _repo_commit(repo_dir: Path) -> str:
    head = repo_dir / ".git" / "HEAD"
    if not head.exists():
        return ""
    import subprocess

    cp = subprocess.run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], text=True, capture_output=True)
    return cp.stdout.strip() if cp.returncode == 0 else ""


def _description_from_skill(path: Path) -> str:
    return _frontmatter(path.read_text(encoding="utf-8")).get("description", "")


def _candidate_skill_doc(repo_root: Path, repo_dir: Path, repo_name: str) -> dict[str, str]:
    meta = REPOS[repo_name]
    slug = meta["candidate_slug"]
    if slug in GENERATED_SKILLS:
        generated = GENERATED_SKILLS[slug]
        return {
            "skill_id": slug,
            "description": generated["description"],
            "body": generated["body"],
            "source_path": str(repo_dir / meta["source_skill"]),
        }
    source = repo_dir / meta["source_skill"]
    text = source.read_text(encoding="utf-8")
    description = DESCRIPTION_OVERRIDES.get(slug) or _description_from_skill(source)
    return {"skill_id": slug, "description": description, "body": text, "source_path": str(source)}


def _fixtures(capability: str) -> list[str]:
    keywords = _capability_keywords(capability)
    return [
        f"Nexus route capability {capability}: handle a task requiring {keywords} with receipt-backed evidence.",
        f"Choose the best skill for {keywords}; return selected, used, evidence, gate, and outcome details.",
        f"請用 {capability} 能力處理，重點是 {keywords}，需要 runtime receipt 和 fail-closed gate。",
    ]


def _compare_descriptions(capability: str, current_skill: str, current_desc: str, challenger: str, challenger_desc: str) -> dict[str, Any]:
    descriptions = {current_skill: current_desc, challenger: challenger_desc}
    rows = []
    current_wins = 0
    challenger_wins = 0
    margin_total = 0.0
    for query in _fixtures(capability):
        ranked = _rank(query, descriptions)
        top = ranked[0]["skill_id"] if ranked else ""
        current_score = next((row["score"] for row in ranked if row["skill_id"] == current_skill), 0.0)
        challenger_score = next((row["score"] for row in ranked if row["skill_id"] == challenger), 0.0)
        if top == current_skill:
            current_wins += 1
        if top == challenger:
            challenger_wins += 1
        margin_total += challenger_score - current_score
        rows.append(
            {
                "query": query,
                "top": top,
                "current_score": current_score,
                "challenger_score": challenger_score,
                "challenger_minus_current": round(challenger_score - current_score, 6),
                "ranked": ranked,
            }
        )
    return {
        "capability": capability,
        "current_skill": current_skill,
        "challenger_skill": challenger,
        "current_wins": current_wins,
        "challenger_wins": challenger_wins,
        "avg_challenger_margin": round(margin_total / len(rows), 6),
        "decision": "REPLACE_CURRENT" if challenger_wins > current_wins and margin_total > 0 else "KEEP_CURRENT",
        "rows": rows,
    }


def _materialize_candidate(repo_root: Path, candidate: Mapping[str, str], repo_name: str, commit: str) -> str:
    target_dir = repo_root / ".agents/skills/github-challengers" / candidate["skill_id"]
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "SKILL.md"
    if candidate["skill_id"] in GENERATED_SKILLS:
        text = (
            "---\n"
            f"name: {candidate['skill_id']}\n"
            f"description: {candidate['description']}\n"
            f"metadata: {{\"source_repo\":\"{REPOS[repo_name]['url']}\",\"source_commit\":\"{commit}\",\"source_status\":\"generated_candidate\",\"runtime_eligible\":false,\"ablation_eligible\":true}}\n"
            "---\n\n"
            f"{candidate['body']}\n"
        )
    else:
        text = candidate["body"]
        if text.startswith("---\n"):
            text = re.sub(r"^name:\s*.+$", f"name: {candidate['skill_id']}", text, count=1, flags=re.MULTILINE)
            text = re.sub(
                r"^description:\s*.+$",
                f"description: {candidate['description']}",
                text,
                count=1,
                flags=re.MULTILINE,
            )
            if "metadata:" not in text.split("---", 2)[1]:
                text = text.replace(
                    "---\n\n",
                    f"metadata: {{\"source_repo\":\"{REPOS[repo_name]['url']}\",\"source_commit\":\"{commit}\",\"source_status\":\"external_challenger\",\"runtime_eligible\":false,\"ablation_eligible\":true}}\n---\n\n",
                    1,
                )
        else:
            text = (
                "---\n"
                f"name: {candidate['skill_id']}\n"
                f"description: {candidate['description']}\n"
                f"metadata: {{\"source_repo\":\"{REPOS[repo_name]['url']}\",\"source_commit\":\"{commit}\",\"source_status\":\"external_challenger\",\"runtime_eligible\":false,\"ablation_eligible\":true}}\n"
                "---\n\n"
                f"{text}"
            )
    text = "\n".join(line.rstrip() for line in text.splitlines()) + "\n"
    target.write_text(text, encoding="utf-8")
    return str(target)


def build_report(repo_root: Path, source_root: Path, overlay: Mapping[str, Any], apply: bool) -> dict[str, Any]:
    primary = dict(overlay.get("primary_skill_by_capability") or {})
    current_descs: dict[str, str] = {}
    for skill_id in sorted(set(primary.values())):
        path = _skill_path(repo_root, skill_id)
        if path:
            current_descs[skill_id] = _description_from_skill(path)
    repo_reports = []
    comparisons = []
    replacements: dict[str, str] = {}
    materialized: list[dict[str, str]] = []
    for repo_name, meta in REPOS.items():
        repo_dir = source_root / repo_name
        commit = _repo_commit(repo_dir)
        candidate = _candidate_skill_doc(repo_root, repo_dir, repo_name)
        repo_report = {
            "repo": repo_name,
            "url": meta["url"],
            "commit": commit,
            "safety": meta["safety"],
            "notes": meta["notes"],
            "candidate_skill": candidate["skill_id"],
            "source_skill": candidate["source_path"],
            "target_capabilities": meta["target_capabilities"],
        }
        if meta["safety"] == "REJECT_OR_REWRITE":
            repo_report["original_rejected"] = True
            repo_report["generated_safe_candidate"] = candidate["skill_id"]
        repo_reports.append(repo_report)
        if meta["safety"] not in {"PASS", "PASS_WITH_RUNTIME_BOUNDARY", "REJECT_OR_REWRITE"}:
            continue
        target_path = _materialize_candidate(repo_root, candidate, repo_name, commit) if apply else ""
        if target_path:
            materialized.append({"skill_id": candidate["skill_id"], "path": target_path})
        for capability in meta["target_capabilities"]:
            current_skill = primary.get(capability)
            if not current_skill or current_skill not in current_descs:
                continue
            comparison = _compare_descriptions(
                capability,
                current_skill,
                current_descs[current_skill],
                candidate["skill_id"],
                candidate["description"],
            )
            comparisons.append(comparison)
            if comparison["decision"] == "REPLACE_CURRENT":
                replacements[capability] = candidate["skill_id"]
    overlay_candidate = dict(primary)
    overlay_candidate.update(replacements)
    return {
        "schema": "nexus.github_skill_challenger_eval.v1",
        "status": "PASS",
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "summary": {
            "repo_count": len(REPOS),
            "candidate_count": len(repo_reports),
            "comparison_count": len(comparisons),
            "replacement_candidate_count": len(replacements),
            "materialized_candidate_count": len(materialized),
        },
        "source_root": str(source_root),
        "repo_reports": repo_reports,
        "comparisons": comparisons,
        "replacement_candidates": dict(sorted(replacements.items())),
        "overlay_candidate_primary_skill_by_capability": dict(sorted(overlay_candidate.items())),
        "materialized": materialized,
        "claim_boundary": [
            "External GitHub skills are challenger candidates only.",
            "A replacement candidate here updates the SF candidate overlay, not runtime default.",
            "Runtime apply still requires SF ablation receipt and apply gate.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate GitHub skill challengers against Nexus SF V17 current best pairings.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--source-root", default="/private/tmp/nexus_github_skill_challenge_20260519")
    parser.add_argument("--overlay", default="docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V17_2026-05-19.json")
    parser.add_argument("--output", default="docs/reports/NEXUS_SF_GITHUB_SKILL_CHALLENGER_EVAL_2026-05-19.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    report = build_report(
        repo_root=repo_root,
        source_root=Path(args.source_root),
        overlay=_read_json(args.overlay),
        apply=args.apply,
    )
    _write_json(args.output, report)
    print(json.dumps({"status": report["status"], **report["summary"], "output": args.output}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
