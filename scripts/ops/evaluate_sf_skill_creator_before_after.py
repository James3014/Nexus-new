#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


NEAR_MISS_CAPABILITIES = {
    "artifact_gate": "claim_gate",
    "claim_gate": "artifact_gate",
    "governance_and_trust": "policy_capability_gate",
    "policy_capability_gate": "governance_and_trust",
    "research": "research_and_source_discipline",
    "research_and_source_discipline": "research_control_plane",
    "research_control_plane": "research",
    "memory": "lancedb",
    "lancedb": "memory",
    "autoreason": "belief",
    "belief": "autoreason",
    "hyper_sprint": "nightshift",
    "nightshift": "hyper_sprint",
    "sandbox_replay": "delivery_acceptance_gate",
    "repair_loop": "codeintel",
}


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    data: dict[str, str] = {}
    for line in text[4:end].strip().splitlines():
        if ":" not in line or line.startswith(" "):
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    return data


def _tokens(text: str) -> list[str]:
    parts = re.split(r"[^a-z0-9_]+", text.lower())
    return [part for part in parts if len(part) >= 3]


def _skill_path(repo_root: Path, skill_id: str) -> Path | None:
    candidates = [
        repo_root / ".agents/skills" / skill_id / "SKILL.md",
        repo_root / ".agents/skills/sf2" / skill_id / "SKILL.md",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _current_descriptions(repo_root: Path, skill_ids: Iterable[str]) -> dict[str, str]:
    descriptions: dict[str, str] = {}
    for skill_id in skill_ids:
        path = _skill_path(repo_root, skill_id)
        if path is None:
            continue
        descriptions[skill_id] = _frontmatter(path.read_text(encoding="utf-8")).get("description", "")
    return descriptions


def _before_after_from_reports(repo_root: Path, report_paths: list[Path], skill_ids: Iterable[str]) -> tuple[dict[str, str], dict[str, str]]:
    current = _current_descriptions(repo_root, skill_ids)
    before = dict(current)
    for report_path in report_paths:
        if not report_path.exists():
            continue
        report = _read_json(report_path)
        for item in report.get("items", []) or []:
            skill_id = str(item.get("skill_id") or "")
            old_description = str(item.get("old_description") or "")
            candidate_description = str(item.get("candidate_description") or "")
            if not skill_id or skill_id not in before or not old_description or not candidate_description:
                continue
            if old_description != candidate_description:
                before.setdefault(skill_id, old_description)
                if before[skill_id] == current.get(skill_id):
                    before[skill_id] = old_description
    return before, current


def _capability_keywords(capability: str) -> str:
    readable = capability.replace("_", " ")
    phrases = {
        "artifact_gate": "artifact evidence acceptance verifier receipt",
        "autonomic_router": "autonomic router route selection policy feedback",
        "autoreason": "autoreason confidence semantic judgment candidate review",
        "belief": "belief confidence prior budget doubt route assessment",
        "benchmark_meta_opt": "benchmark route cost meta optimization public claim boundary",
        "claim_gate": "claim gate claim verification public readiness",
        "codeintel": "code scan impact symbol dependency graph repository context",
        "ddtree": "decision tree candidate pruning diagnosis acceleration",
        "direct_master_loop": "direct master loop execution content rewrite task control",
        "drone": "drone delegated worker tactical execution status",
        "external_productivity": "gmail calendar sheets docs slides airtable connector",
        "file_lock_security_gate": "file lock security gate worktree permission sandbox",
        "forecast_pregate": "forecast pregate plan quality risk prediction",
        "governance_and_trust": "governance trust mismatch evidence fail closed",
        "hyper_sprint": "hyper sprint fast multi candidate local repair",
        "lancedb": "LanceDB retrieval vector source validation context",
        "learn_ask": "learn ask capability upgrade research ingest report",
        "learning_closure": "learning closure lesson writeback SLO KPI matrix",
        "memory": "memory long term findings retrieval prior fix",
        "mempalace": "MemPalace ethical boundary policy guardrail forbidden action",
        "metabolism_resume": "metabolism resume long goal closure continuation",
        "nightshift": "nightshift long running recovery delayed repair",
        "policy_capability_gate": "policy capability gate route governance permission",
        "registry_skills_sync": "skill registry catalog sync plugin source refresh",
        "regression_guard": "regression guard failing test reproduce bug",
        "repair_loop": "repair loop TDD red green refactor behavior test",
        "research": "research source citation claim source report",
        "research_and_source_discipline": "source discipline citation chain validation evidence",
        "research_control_plane": "research control plane ingest refresh converge questions",
        "sandbox_replay": "sandbox replay isolation rerun execution trace",
        "swarm_multi_agent": "swarm multi agent worktree submit verify integrate",
        "ui_validator": "UI validator browser screenshot interaction visual gate",
        "ultra_review": "ultra review sandbox fleet security logic regression",
        "xray": "xray deep inspection hidden context diagnosis",
    }
    return f"{readable} {phrases.get(capability, '')}".strip()


def _fixtures_for_capability(capability: str, capability_to_skill: Mapping[str, str]) -> list[dict[str, Any]]:
    keywords = _capability_keywords(capability)
    near = NEAR_MISS_CAPABILITIES.get(capability)
    fixtures = [
        {
            "id": f"{capability}:obvious",
            "kind": "should_trigger",
            "query": f"Nexus route capability {capability}: handle a task requiring {keywords} with receipt-backed evidence.",
        },
        {
            "id": f"{capability}:paraphrase",
            "kind": "should_trigger",
            "query": f"Choose the best skill for {keywords}; return selected, used, evidence, gate, and outcome details.",
        },
        {
            "id": f"{capability}:mixed",
            "kind": "should_trigger",
            "query": f"請用 {capability} 能力處理，重點是 {keywords}，需要 runtime receipt 和 fail-closed gate。",
        },
    ]
    if near and capability_to_skill.get(near) != capability_to_skill.get(capability):
        fixtures.append(
            {
                "id": f"{capability}:near_miss:{near}",
                "kind": "should_not_trigger",
                "query": f"This task needs {near}: {_capability_keywords(near)}. Select the skill for that neighboring capability.",
            }
        )
    return fixtures


def _idf(corpus_tokens: Mapping[str, set[str]], token: str) -> float:
    containing = sum(1 for tokens in corpus_tokens.values() if token in tokens)
    return math.log((1 + len(corpus_tokens)) / (1 + containing)) + 1.0


def _rank(query: str, descriptions: Mapping[str, str]) -> list[dict[str, Any]]:
    query_tokens = set(_tokens(query))
    corpus_tokens = {skill_id: set(_tokens(description)) for skill_id, description in descriptions.items()}
    ranked = []
    for skill_id, desc_tokens in corpus_tokens.items():
        overlap = sorted(query_tokens & desc_tokens)
        score = sum(_idf(corpus_tokens, token) for token in overlap)
        ranked.append({"skill_id": skill_id, "score": round(score, 6), "overlap": overlap})
    return sorted(ranked, key=lambda row: (-row["score"], row["skill_id"]))


def _evaluate_version(
    *,
    version: str,
    descriptions: Mapping[str, str],
    capability_to_skill: Mapping[str, str],
) -> dict[str, Any]:
    rows = []
    hit1 = hit3 = trigger_count = 0
    false_positive = negative_count = 0
    margins = []
    for capability, expected_skill in sorted(capability_to_skill.items()):
        for fixture in _fixtures_for_capability(capability, capability_to_skill):
            ranked = _rank(fixture["query"], descriptions)
            top_ids = [row["skill_id"] for row in ranked[:3]]
            expected_rank = next((index + 1 for index, row in enumerate(ranked) if row["skill_id"] == expected_skill), None)
            if fixture["kind"] == "should_trigger":
                trigger_count += 1
                if expected_rank == 1:
                    hit1 += 1
                if expected_rank is not None and expected_rank <= 3:
                    hit3 += 1
                top_score = ranked[0]["score"] if ranked else 0.0
                expected_score = next((row["score"] for row in ranked if row["skill_id"] == expected_skill), 0.0)
                next_best = max((row["score"] for row in ranked if row["skill_id"] != expected_skill), default=0.0)
                margins.append(round(expected_score - next_best, 6))
            else:
                negative_count += 1
                if top_ids and top_ids[0] == expected_skill:
                    false_positive += 1
                top_score = ranked[0]["score"] if ranked else 0.0
                expected_score = next((row["score"] for row in ranked if row["skill_id"] == expected_skill), 0.0)
            rows.append(
                {
                    "version": version,
                    "capability": capability,
                    "expected_skill": expected_skill,
                    "fixture_id": fixture["id"],
                    "kind": fixture["kind"],
                    "expected_rank": expected_rank,
                    "top3": top_ids,
                    "top_score": top_score,
                    "expected_score": expected_score,
                    "query": fixture["query"],
                }
            )
    return {
        "version": version,
        "summary": {
            "trigger_count": trigger_count,
            "hit1": hit1,
            "hit3": hit3,
            "hit1_rate": round(hit1 / trigger_count, 6) if trigger_count else 0.0,
            "hit3_rate": round(hit3 / trigger_count, 6) if trigger_count else 0.0,
            "negative_count": negative_count,
            "false_positive": false_positive,
            "false_positive_rate": round(false_positive / negative_count, 6) if negative_count else 0.0,
            "avg_margin": round(sum(margins) / len(margins), 6) if margins else 0.0,
        },
        "rows": rows,
    }


def _summarize_rows(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    trigger_rows = [row for row in rows if row["kind"] == "should_trigger"]
    negative_rows = [row for row in rows if row["kind"] == "should_not_trigger"]
    margins = []
    for row in trigger_rows:
        expected_score = float(row.get("expected_score") or 0.0)
        top_score = float(row.get("top_score") or 0.0)
        expected_rank = row.get("expected_rank")
        if expected_rank == 1:
            margins.append(expected_score - top_score)
        else:
            margins.append(expected_score - top_score)
    return {
        "trigger_count": len(trigger_rows),
        "hit1": sum(1 for row in trigger_rows if row.get("expected_rank") == 1),
        "hit3": sum(1 for row in trigger_rows if row.get("expected_rank") is not None and row.get("expected_rank") <= 3),
        "negative_count": len(negative_rows),
        "false_positive": sum(
            1 for row in negative_rows if row.get("top3") and row["top3"][0] == row.get("expected_skill")
        ),
        "avg_expected_minus_top": round(sum(margins) / len(margins), 6) if margins else 0.0,
    }


def _skill_decisions(before_rows: list[Mapping[str, Any]], after_rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_skill_before: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    by_skill_after: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in before_rows:
        by_skill_before[str(row["expected_skill"])].append(row)
    for row in after_rows:
        by_skill_after[str(row["expected_skill"])].append(row)
    decisions = []
    for skill_id in sorted(set(by_skill_before) | set(by_skill_after)):
        before = _summarize_rows(by_skill_before.get(skill_id, []))
        after = _summarize_rows(by_skill_after.get(skill_id, []))
        delta = {
            "hit1_delta": after["hit1"] - before["hit1"],
            "hit3_delta": after["hit3"] - before["hit3"],
            "false_positive_delta": after["false_positive"] - before["false_positive"],
            "avg_expected_minus_top_delta": round(
                after["avg_expected_minus_top"] - before["avg_expected_minus_top"], 6
            ),
        }
        keep = (
            delta["hit1_delta"] >= 0
            and delta["hit3_delta"] >= 0
            and delta["false_positive_delta"] <= 0
            and (
                delta["hit1_delta"] > 0
                or delta["hit3_delta"] > 0
                or delta["avg_expected_minus_top_delta"] > 0
            )
        )
        decisions.append(
            {
                "skill_id": skill_id,
                "decision": "KEEP_AFTER" if keep else "REVERT_BEFORE",
                "before": before,
                "after": after,
                "delta": delta,
            }
        )
    return decisions


def build_report(
    *,
    repo_root: Path,
    overlay: Mapping[str, Any],
    reports: list[Path],
) -> dict[str, Any]:
    capability_to_skill = dict(overlay.get("primary_skill_by_capability") or {})
    skill_ids = sorted(set(capability_to_skill.values()))
    before_descriptions, after_descriptions = _before_after_from_reports(repo_root, reports, skill_ids)
    before_eval = _evaluate_version(version="before", descriptions=before_descriptions, capability_to_skill=capability_to_skill)
    after_eval = _evaluate_version(version="after", descriptions=after_descriptions, capability_to_skill=capability_to_skill)
    before_summary = before_eval["summary"]
    after_summary = after_eval["summary"]
    deltas = {
        "hit1_delta": after_summary["hit1"] - before_summary["hit1"],
        "hit3_delta": after_summary["hit3"] - before_summary["hit3"],
        "false_positive_delta": after_summary["false_positive"] - before_summary["false_positive"],
        "avg_margin_delta": round(after_summary["avg_margin"] - before_summary["avg_margin"], 6),
    }
    keep_after = (
        deltas["hit1_delta"] >= 0
        and deltas["hit3_delta"] >= 0
        and deltas["false_positive_delta"] <= 0
        and deltas["avg_margin_delta"] > 0
    )
    skill_decisions = _skill_decisions(before_eval["rows"], after_eval["rows"])
    per_skill_reverts = [row for row in skill_decisions if row["decision"] != "KEEP_AFTER"]
    return {
        "schema": "nexus.sf_skill_creator_before_after_trigger_eval.v1",
        "status": "PASS" if keep_after and not per_skill_reverts else "RETURN",
        "decision": "KEEP_AFTER" if keep_after and not per_skill_reverts else "REVERT_SOME_OR_ALL",
        "summary": {
            "capability_count": len(capability_to_skill),
            "unique_skill_count": len(skill_ids),
            "fixture_count_per_version": len(before_eval["rows"]),
            "before": before_summary,
            "after": after_summary,
            "delta": deltas,
            "keep_after_skill_count": sum(1 for row in skill_decisions if row["decision"] == "KEEP_AFTER"),
            "revert_before_skill_count": len(per_skill_reverts),
        },
        "claim_boundary": [
            "This compares before-skill vs after-skill trigger routing for the same SF primary skills.",
            "It is not a no-skill baseline.",
            "It is not a public benchmark or runtime default apply gate.",
        ],
        "before_rows": before_eval["rows"],
        "after_rows": after_eval["rows"],
        "skill_decisions": skill_decisions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate skill-creator before/after trigger-routing deltas for SF primary skills.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--overlay", default="docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V17_2026-05-19.json")
    parser.add_argument(
        "--optimization-report",
        action="append",
        default=[
            "docs/reports/NEXUS_SF_PRIMARY_SKILL_DESCRIPTION_OPTIMIZATION_APPLY_2026-05-19.json",
            "docs/reports/NEXUS_SF_PRIMARY_SKILL_DESCRIPTION_OPTIMIZATION_FULL_APPLY_2026-05-19.json",
        ],
    )
    parser.add_argument("--output", default="docs/reports/NEXUS_SF_SKILL_CREATOR_BEFORE_AFTER_TRIGGER_EVAL_2026-05-19.json")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    report = build_report(
        repo_root=repo_root,
        overlay=_read_json(args.overlay),
        reports=[Path(path) for path in args.optimization_report],
    )
    _write_json(args.output, report)
    print(json.dumps({"status": report["status"], "decision": report["decision"], **report["summary"]["delta"], "output": args.output}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
