#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ops.build_sf_final_capability_skill_settlement import CAPABILITY_TERMS


DEFAULT_SETTLEMENT = PROJECT_ROOT / "docs/reports/NEXUS_SF_FINAL_CAPABILITY_SKILL_SETTLEMENT_2026-05-21.json"
DEFAULT_COMPARE = PROJECT_ROOT / "docs/reports/NEXUS_SF_FINAL_COMPARE_REPORT_2026-05-21.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "docs/reports/NEXUS_SF_FINAL_LOCAL_SKILL_COMPARE_2026-05-21.json"
DEFAULT_SKILL_ROOTS = [
    PROJECT_ROOT / ".agents/skills",
    PROJECT_ROOT / "skills",
    Path("/Users/jameschen/.agents/skills"),
    Path("/Users/jameschen/.codex/skills"),
    Path("/Users/jameschen/Workspace/hermes-agent/skills"),
    Path("/Users/jameschen/Workspace/skills_audit/skills"),
]

DECISION_REPLACE = "REPLACE_PRIMARY_LOCAL_CANDIDATE"
DECISION_KEEP = "KEEP_CURRENT"
DECISION_HOLD = "HOLD_LOCAL_EVIDENCE"
DECISION_REJECT = "REJECT_LOCAL_PRECHECK"


def build_sf_final_local_skill_compare(
    *,
    settlement: Mapping[str, Any],
    compare_report: Mapping[str, Any],
    skill_roots: list[Path] | None = None,
    replace_margin: int = 15,
) -> dict[str, Any]:
    roots = skill_roots or DEFAULT_SKILL_ROOTS
    index = _skill_index(roots)
    settlement_rows = {
        str(row.get("capability") or ""): row
        for row in settlement.get("settlement_rows", []) or []
        if isinstance(row, Mapping)
    }
    rows = [
        _compare_row(row, settlement_rows=settlement_rows, skill_index=index, replace_margin=replace_margin)
        for row in compare_report.get("compare_rows", []) or []
        if isinstance(row, Mapping)
    ]
    capability_decisions = _capability_decisions(rows, settlement_rows)
    blockers = _blockers(settlement, compare_report, rows, capability_decisions)
    return {
        "schema": "nexus.sf_final_local_skill_compare.v1",
        "status": "PASS" if not blockers else "RETURN",
        "summary": _summary(rows=rows, capability_decisions=capability_decisions, skill_index=index),
        "rubric": {
            "replace_margin": replace_margin,
            "scoring": [
                "capability term hits",
                "actionable instruction structure",
                "verification and test language",
                "evidence/gate/fail-closed discipline",
                "source tier and local existence",
                "generic or unsafe wording penalties",
            ],
            "claim_boundary": "local deterministic content comparison; not live Flash+Nexus proof and not runtime default apply",
        },
        "capability_decisions": capability_decisions,
        "compare_rows": rows,
        "claim_boundary": [
            "A local replacement candidate means its SKILL.md is stronger than the current primary under deterministic rubric.",
            "Runtime defaults remain unchanged until live Flash+Nexus and runtime apply gates pass.",
            "Missing local files are held, not treated as weak or strong.",
        ],
        "blockers": blockers,
    }


def _compare_row(
    row: Mapping[str, Any],
    *,
    settlement_rows: Mapping[str, Mapping[str, Any]],
    skill_index: Mapping[str, Path],
    replace_margin: int,
) -> dict[str, Any]:
    capability = str(row.get("capability") or "")
    candidate = str(row.get("candidate_skill_id") or "")
    current = str(row.get("baseline_arm", {}).get("skill_ids", [""])[0] if isinstance(row.get("baseline_arm"), Mapping) else "")
    if not current:
        current = str(settlement_rows.get(capability, {}).get("current_primary_skill_id") or "")
    current_path = _resolve_skill_path(current, explicit_path="", skill_index=skill_index)
    candidate_path = _resolve_skill_path(candidate, explicit_path=str(row.get("canonical_source_path") or ""), skill_index=skill_index)
    blockers = [str(item) for item in row.get("deterministic_precheck", {}).get("blockers", []) or [] if isinstance(row.get("deterministic_precheck"), Mapping)]
    current_profile = _profile_skill(capability, current, current_path)
    candidate_profile = _profile_skill(capability, candidate, candidate_path)
    if current_path is None:
        blockers.append("current_primary_skill_file_missing")
    if candidate_path is None:
        blockers.append("candidate_skill_file_missing")
    if str(row.get("decision") or "") == "REJECT_PRECHECK":
        decision = DECISION_REJECT
        reason = str(row.get("reason") or "precheck_rejected")
    elif blockers:
        decision = DECISION_HOLD
        reason = blockers[0]
    else:
        delta = int(candidate_profile["score"]) - int(current_profile["score"])
        if _is_locally_stronger(current_profile=current_profile, candidate_profile=candidate_profile, delta=delta, replace_margin=replace_margin):
            decision = DECISION_REPLACE
            reason = "candidate_local_rubric_score_beats_current"
        else:
            decision = DECISION_KEEP
            reason = "current_primary_not_beaten_locally"
    return {
        "capability": capability,
        "current_primary_skill_id": current,
        "current_primary_path": str(current_path or ""),
        "candidate_skill_id": candidate,
        "candidate_path": str(candidate_path or ""),
        "candidate_role": str(row.get("candidate_role") or ""),
        "current_profile": current_profile,
        "candidate_profile": candidate_profile,
        "score_delta": int(candidate_profile["score"]) - int(current_profile["score"]),
        "decision": decision,
        "reason": reason,
        "blockers": sorted(set(blockers)),
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def _capability_decisions(rows: list[Mapping[str, Any]], settlement_rows: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for capability in sorted(set(settlement_rows) | {str(row.get("capability") or "") for row in rows}):
        capability_rows = [row for row in rows if row.get("capability") == capability]
        replacements = [row for row in capability_rows if row.get("decision") == DECISION_REPLACE]
        replacements.sort(key=lambda item: (-int(item.get("score_delta") or 0), str(item.get("candidate_skill_id") or "")))
        current_primary = str(settlement_rows.get(capability, {}).get("current_primary_skill_id") or "")
        if replacements:
            winner = replacements[0]
            decision = DECISION_REPLACE
            recommended = str(winner.get("candidate_skill_id") or "")
            reason = "best_local_candidate_beats_current_primary"
        elif capability_rows:
            winner = max(capability_rows, key=lambda item: int(item.get("score_delta") or -9999))
            decision = DECISION_KEEP
            recommended = current_primary
            reason = "no_local_candidate_cleared_replace_margin"
        else:
            winner = {}
            decision = DECISION_HOLD
            recommended = current_primary
            reason = "no_local_compare_rows"
        decisions.append(
            {
                "capability": capability,
                "current_primary_skill_id": current_primary,
                "recommended_skill_id": recommended,
                "decision": decision,
                "reason": reason,
                "best_candidate_skill_id": str(winner.get("candidate_skill_id") or ""),
                "best_score_delta": int(winner.get("score_delta") or 0),
                "local_compare_row_count": len(capability_rows),
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            }
        )
    return decisions


def _profile_skill(capability: str, skill_id: str, path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "skill_id": skill_id,
            "path": "",
            "score": 0,
            "term_hits": 0,
            "quality_hits": 0,
            "evidence_hits": 0,
            "penalties": ["skill_file_missing"],
        }
    text = path.read_text(encoding="utf-8", errors="replace")
    lowered = text.lower()
    terms = CAPABILITY_TERMS.get(capability, ())
    term_hits = sum(1 for term in terms if term.lower() in lowered)
    quality_terms = (
        "steps",
        "workflow",
        "checklist",
        "verify",
        "test",
        "example",
        "when to use",
        "do not",
        "output",
    )
    evidence_terms = ("evidence", "receipt", "gate", "fail-closed", "trust", "risk", "rollback", "ci")
    quality_hits = sum(1 for term in quality_terms if term in lowered)
    evidence_hits = sum(1 for term in evidence_terms if term in lowered)
    penalties: list[str] = []
    word_count = len(re.findall(r"[A-Za-z0-9_]+", text))
    if word_count < 80:
        penalties.append("too_short")
    if "todo" in lowered or "placeholder" in lowered:
        penalties.append("placeholder_language")
    score = term_hits * 12 + quality_hits * 5 + evidence_hits * 7 + min(word_count // 120, 10)
    score -= len(penalties) * 12
    return {
        "skill_id": skill_id,
        "path": str(path),
        "score": max(score, 0),
        "term_hits": term_hits,
        "quality_hits": quality_hits,
        "evidence_hits": evidence_hits,
        "word_count": word_count,
        "penalties": penalties,
    }


def _is_locally_stronger(
    *,
    current_profile: Mapping[str, Any],
    candidate_profile: Mapping[str, Any],
    delta: int,
    replace_margin: int,
) -> bool:
    if delta < replace_margin:
        return False
    if int(candidate_profile.get("term_hits") or 0) < int(current_profile.get("term_hits") or 0):
        return False
    if candidate_profile.get("penalties"):
        return False
    return True


def _skill_index(skill_roots: Iterable[Path]) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for root in skill_roots:
        if not root.exists():
            continue
        for path in root.rglob("SKILL.md"):
            skill_id = path.parent.name
            index.setdefault(skill_id, path)
    return index


def _resolve_skill_path(skill_id: str, *, explicit_path: str, skill_index: Mapping[str, Path]) -> Path | None:
    if explicit_path:
        path = Path(explicit_path)
        if path.exists():
            return path
    return skill_index.get(skill_id)


def _summary(
    *,
    rows: list[Mapping[str, Any]],
    capability_decisions: list[Mapping[str, Any]],
    skill_index: Mapping[str, Path],
) -> dict[str, Any]:
    return {
        "local_skill_index_count": len(skill_index),
        "compare_row_count": len(rows),
        "capability_count": len(capability_decisions),
        "decision_counts": _counts(str(row.get("decision") or "") for row in rows),
        "capability_decision_counts": _counts(str(row.get("decision") or "") for row in capability_decisions),
        "replacement_candidate_count": sum(1 for row in capability_decisions if row.get("decision") == DECISION_REPLACE),
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def _blockers(
    settlement: Mapping[str, Any],
    compare_report: Mapping[str, Any],
    rows: list[Mapping[str, Any]],
    capability_decisions: list[Mapping[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    if settlement.get("status") != "PASS":
        blockers.append("source_settlement_not_pass")
    if compare_report.get("status") != "PASS":
        blockers.append("source_compare_report_not_pass")
    if not rows:
        blockers.append("missing_local_compare_rows")
    if not capability_decisions:
        blockers.append("missing_capability_decisions")
    return blockers


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare local skill files against current capability primary skills.")
    parser.add_argument("--settlement", type=Path, default=DEFAULT_SETTLEMENT)
    parser.add_argument("--compare", type=Path, default=DEFAULT_COMPARE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--skill-root", type=Path, action="append", default=[])
    parser.add_argument("--replace-margin", type=int, default=15)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    roots = args.skill_root or DEFAULT_SKILL_ROOTS
    payload = build_sf_final_local_skill_compare(
        settlement=_read_json(args.settlement),
        compare_report=_read_json(args.compare),
        skill_roots=roots,
        replace_margin=args.replace_margin,
    )
    if not args.dry_run:
        _write_json(args.output, payload)
    print(json.dumps({"status": payload["status"], **payload["summary"], "output": "" if args.dry_run else str(args.output)}, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
