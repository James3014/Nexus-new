#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping


EVIDENCE_TERMS = (
    "receipt",
    "evidence",
    "gate",
    "outcome",
    "capability",
)

SKILL_HINTS = {
    "acceptance-evidence-failclosed": "rejecting unsupported acceptance, delivery, claim, artifact, and governance evidence",
    "diagnose": "debugging failures, regressions, root cause isolation, and runtime evidence checks",
    "nexus-root-cause-probe": "Nexus route, policy, gate, report, and runtime receipt root-cause diagnosis",
    "research-citation-chain-verifier": "research claim-to-source tracing, citation chain verification, and source-discipline receipts",
    "nexus-benchmark-continuous-optimization": "benchmark, route-cost, claim-boundary, and continuous optimization review",
    "sf2-belief-route-fit-spec": "belief, autoreason confidence state, subjective route assessment, and decision evidence",
    "create-plan": "forecast pregate planning, risk forecast, implementation sequencing, and plan quality review",
    "nexus-capability-upgrade": "learn/ask capability upgrade, fixed evaluation, A/B evidence, and capability improvement closure",
    "nexus-goal-closure-executor": "metabolism/resume execution, long-goal closure, dynamic replanning, and evidence-backed completion",
    "research-source-validation-auditor": "LanceDB-backed source validation, missing-source audit, and retrieval evidence discipline",
    "sf2-autonomic_router-route-fit-spec": "autonomic route selection, route evolution, routing policy feedback, and route-fit receipts",
    "sf2-codeintel-route-fit-spec": "code scanning, impact analysis, symbol context, dependency graph, and code intelligence receipts",
    "sf2-direct_master_loop-route-fit-spec": "direct master loop execution, default task control, content rewrite, and execution receipts",
    "sf2-external_productivity-route-fit-spec": "external productivity tools, docs, sheets, calendar, mail, and connector-safe receipts",
    "sf2-file_lock_security_gate-route-fit-spec": "file lock, delegated execution safety, sandbox permission, and security gate evidence",
    "sf2-hyper_sprint-route-fit-spec": "hyper sprint repair, fast multi-candidate fixes, quick local recovery, and sprint evidence",
    "sf2-learning_closure-route-fit-spec": "learning closure, lesson writeback, SLO/KPI closure matrix, and policy writeback evidence",
    "sf2-mempalace-route-fit-spec": "MemPalace ethics, policy boundaries, forbidden-action checks, and governance guardrail evidence",
    "sf2-nightshift-route-fit-spec": "nightshift long-running recovery, autonomous repair continuation, and delayed evidence closure",
    "sf2-registry_skills_sync-route-fit-spec": "skill registry sync, catalog maintenance, plugin/source refresh, and candidate intake evidence",
    "sf2-sandbox_replay-route-fit-spec": "sandboxed execution, replay validation, isolation checks, rerun evidence, and trace receipts",
    "sf2-swarm_multi_agent-route-fit-spec": "swarm and multi-agent orchestration, worktree delegation, submit/verify/integrate receipts",
    "tdd": "repair loop test-first implementation, red-green-refactor, regression protection, and behavior-level evidence",
}


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _tokens(text: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9_]+", text.lower()) if len(part) >= 3}


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    raw = text[4:end].strip().splitlines()
    data: dict[str, str] = {}
    for line in raw:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    return data, text[end + 4 :].lstrip("\n")


def _replace_frontmatter_description(text: str, description: str) -> str:
    frontmatter, body = _frontmatter(text)
    if not frontmatter:
        title_match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
        name = title_match.group(1).strip().lower().replace(" ", "-") if title_match else "unnamed-skill"
        return f"---\nname: {name}\ndescription: {description}\n---\n\n{text.lstrip()}"
    end = text.find("\n---", 4)
    raw_lines = text[4:end].strip().splitlines()
    lines = ["---"]
    replaced = False
    has_description = any(line.startswith("description:") for line in raw_lines)
    for line in raw_lines:
        if line.startswith("description:"):
            lines.append(f"description: {description}")
            replaced = True
        else:
            lines.append(line)
        if line.startswith("name:") and not has_description:
            lines.append(f"description: {description}")
            replaced = True
    if not replaced:
        lines.insert(1, f"description: {description}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + body


def _skill_path(repo_root: Path, skill_id: str) -> Path | None:
    candidates = [
        repo_root / ".agents/skills" / skill_id / "SKILL.md",
        repo_root / ".agents/skills/sf2" / skill_id / "SKILL.md",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _capability_phrase(capabilities: list[str]) -> str:
    readable = ", ".join(capabilities[:5])
    if len(capabilities) > 5:
        readable += f", and {len(capabilities) - 5} related capabilities"
    return readable


def _candidate_description(skill_id: str, capabilities: list[str], old: str) -> str:
    hint = SKILL_HINTS.get(skill_id, "the listed Nexus route capabilities")
    cap_phrase = _capability_phrase(capabilities)
    negative = "Do not use for unrelated one-off writing or tasks without runtime evidence needs."
    return (
        f"Use when Nexus route capability is {cap_phrase} and the task needs {hint}; "
        f"return receipt/evidence/gate/outcome-backed guidance for SF or runtime review. {negative}"
    )


def _score(description: str, capabilities: list[str], skill_id: str) -> dict[str, Any]:
    desc_tokens = _tokens(description)
    capability_tokens = set()
    for capability in capabilities:
        capability_tokens |= _tokens(capability)
    hint_tokens = _tokens(SKILL_HINTS.get(skill_id, ""))
    positive_hits = len((capability_tokens | hint_tokens | set(EVIDENCE_TERMS)) & desc_tokens)
    negative_boundary = int("do not use" in description.lower() or "not use" in description.lower())
    evidence_hits = len(set(EVIDENCE_TERMS) & desc_tokens)
    length_ok = int(90 <= len(description) <= 900)
    return {
        "positive_hits": positive_hits,
        "evidence_hits": evidence_hits,
        "negative_boundary": negative_boundary,
        "length_ok": length_ok,
        "score": positive_hits * 3 + evidence_hits * 2 + negative_boundary * 3 + length_ok,
    }


def build_report(
    *,
    repo_root: Path,
    overlay: Mapping[str, Any],
    max_apply: int,
    apply: bool,
) -> dict[str, Any]:
    primary = overlay.get("primary_skill_by_capability") if isinstance(overlay.get("primary_skill_by_capability"), Mapping) else {}
    by_skill: dict[str, list[str]] = defaultdict(list)
    for capability, skill_id in primary.items():
        by_skill[str(skill_id)].append(str(capability))
    ranked_skills = [
        skill_id
        for skill_id, _ in Counter(primary.values()).most_common()
        if skill_id and _skill_path(repo_root, str(skill_id)) is not None
    ]

    items = []
    applied = []
    for skill_id in ranked_skills:
        path = _skill_path(repo_root, skill_id)
        if path is None:
            continue
        text = path.read_text(encoding="utf-8")
        frontmatter, _ = _frontmatter(text)
        old_description = str(frontmatter.get("description") or "")
        capabilities = sorted(by_skill[skill_id])
        if skill_id not in SKILL_HINTS:
            items.append(
                {
                    "skill_id": skill_id,
                    "path": str(path),
                    "capabilities": capabilities,
                    "capability_count": len(capabilities),
                    "before": _score(old_description, capabilities, skill_id),
                    "after": None,
                    "improved": False,
                    "applied": False,
                    "skip_reason": "no_domain_hint",
                    "old_description": old_description,
                    "candidate_description": None,
                }
            )
            continue
        new_description = _candidate_description(skill_id, capabilities, old_description)
        before = _score(old_description, capabilities, skill_id)
        after = _score(new_description, capabilities, skill_id)
        improved = after["score"] > before["score"]
        item = {
            "skill_id": skill_id,
            "path": str(path),
            "capabilities": capabilities,
            "capability_count": len(capabilities),
            "before": before,
            "after": after,
            "improved": improved,
            "old_description": old_description,
            "candidate_description": new_description,
        }
        if apply and improved and len(applied) < max_apply:
            path.write_text(_replace_frontmatter_description(text, new_description), encoding="utf-8")
            item["applied"] = True
            applied.append(skill_id)
        else:
            item["applied"] = False
        items.append(item)

    return {
        "schema": "nexus.sf_primary_skill_description_optimization.v1",
        "status": "PASS",
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "summary": {
            "primary_skill_count": len(ranked_skills),
            "evaluated_candidate_count": sum(1 for item in items if item["after"] is not None),
            "skipped_no_domain_hint_count": sum(1 for item in items if item.get("skip_reason") == "no_domain_hint"),
            "improved_candidate_count": sum(1 for item in items if item["improved"]),
            "applied_count": len(applied),
            "max_apply": max_apply,
        },
        "applied_skills": applied,
        "items": items,
        "claim_boundary": [
            "This optimizes skill routing metadata only.",
            "It does not replace runtime skill pairings.",
            "Functional replacement still requires SF ablation evidence.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimize V17 SF primary skill descriptions with before/after scoring.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--overlay", default="docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V17_2026-05-19.json")
    parser.add_argument("--output", default="docs/reports/NEXUS_SF_PRIMARY_SKILL_DESCRIPTION_OPTIMIZATION_2026-05-19.json")
    parser.add_argument("--max-apply", type=int, default=10)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    report = build_report(
        repo_root=repo_root,
        overlay=_read_json(args.overlay),
        max_apply=args.max_apply,
        apply=args.apply,
    )
    _write_json(args.output, report)
    print(json.dumps({"status": report["status"], **report["summary"], "output": args.output}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
