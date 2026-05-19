#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


RESEARCH_CANDIDATES = (
    "research-citation-chain-verifier",
    "research-source-validation-auditor",
)

GOVERNANCE_CANDIDATES = (
    "acceptance-evidence-failclosed",
    "cso",
    "claudeosint-safe-surface-audit",
    "gbrain-soul-audit",
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seal_verdicts(seal_catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("skill_id")): item
        for item in seal_catalog.get("skill_verdicts", [])
        if isinstance(item, dict) and str(item.get("skill_id")) in RESEARCH_CANDIDATES
    }


def _paired_live_by_skill(pair_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("skill_id")): item
        for item in pair_report.get("comparisons", [])
        if isinstance(item, dict) and str(item.get("skill_id")) in RESEARCH_CANDIDATES
    }


def _research_score(skill_id: str, seal: dict[str, Any], pair: dict[str, Any] | None) -> dict[str, Any]:
    tested = int(seal.get("tested_rows") or 0)
    effective = int(seal.get("effective_rows") or 0)
    trust_clean = int(seal.get("trust_clean_rows") or 0)
    paired_keep = bool(pair and str(pair.get("verdict") or "").upper() == "KEEP")
    chain = pair.get("with_skill", {}) if isinstance(pair, dict) else {}
    receipt_chain_present = bool(
        chain.get("selected")
        and chain.get("injected")
        and chain.get("used")
        and chain.get("evidence_present")
        and chain.get("gate_passed")
        and chain.get("outcome_contributed")
    )
    score = effective * 10 + trust_clean * 2 + (25 if paired_keep else 0) + (10 if receipt_chain_present else 0)
    return {
        "skill_id": skill_id,
        "tested_rows": tested,
        "effective_rows": effective,
        "trust_clean_rows": trust_clean,
        "paired_live_keep": paired_keep,
        "paired_live_receipt_chain_present": receipt_chain_present,
        "score": score,
        "evidence_refs": list(seal.get("evidence_refs", []) or []),
        "receipt_refs": list(seal.get("receipt_refs", []) or []),
    }


def _governance_item(repo_root: Path, skill_id: str, review_items: list[dict[str, Any]]) -> dict[str, Any]:
    source = next((item for item in review_items if item.get("skill_id") == skill_id), {})
    repo_path = repo_root / ".agents" / "skills" / skill_id / "SKILL.md"
    return {
        "skill_id": skill_id,
        "capability": "governance_and_trust",
        "source_disposition": source.get("disposition", "catalog_alternate_only"),
        "previous_source_path": source.get("path", ""),
        "repo_local_path": str(repo_path),
        "materialized": repo_path.exists(),
        "source_status": "runtime_review_candidate" if repo_path.exists() else "missing_repo_local_asset",
        "runtime_eligible": False,
        "ablation_eligible": repo_path.exists(),
        "next_action": "run_governance_runtime_review_seal_before_default_promotion",
    }


def build_report(repo_root: Path, output: Path) -> dict[str, Any]:
    seal_catalog = _load(repo_root / "docs/reports/NEXUS_SF_RESEARCH_EXPECTED_CAPABILITY_SEAL_CATALOG_2026-05-18.json")
    pair_report = _load(repo_root / "docs/reports/NEXUS_SF_FLASH_PAIR_CHUNK14_RESEARCH_LIVE_REPORT_2026-05-18.json")
    review = _load(repo_root / "docs/reports/NEXUS_SF_RUNTIME_PROMOTION_REVIEW_V5_2026-05-18.json")
    seal = _seal_verdicts(seal_catalog)
    paired = _paired_live_by_skill(pair_report)
    research_scores = [_research_score(skill_id, seal.get(skill_id, {}), paired.get(skill_id)) for skill_id in RESEARCH_CANDIDATES]
    research_scores.sort(key=lambda item: (item["score"], item["effective_rows"], item["paired_live_keep"]), reverse=True)
    primary = research_scores[0]["skill_id"] if research_scores else ""
    alternate = [item["skill_id"] for item in research_scores[1:]]
    review_items = [item for item in review.get("runtime_review_items", []) if isinstance(item, dict)]
    governance = [_governance_item(repo_root, skill_id, review_items) for skill_id in GOVERNANCE_CANDIDATES]
    report = {
        "schema": "nexus_sf_research_tiebreak_and_governance_curation_v1",
        "status": "PASS" if primary and all(item["materialized"] for item in governance) else "RETURN",
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "research_tiebreak": {
            "capability": "research_and_source_discipline",
            "primary_skill": primary,
            "alternate_skills": alternate,
            "reason": "both candidates have 3/3 expected-capability evidence; citation-chain has additional same-runner paired live KEEP receipt",
            "scores": research_scores,
        },
        "governance_curation": {
            "capability": "governance_and_trust",
            "materialized_count": sum(1 for item in governance if item["materialized"]),
            "candidate_count": len(governance),
            "items": governance,
        },
        "claim_boundary": {
            "catalog_update_allowed": True,
            "runtime_default_change": False,
            "requires_next": "governance_runtime_review_seal_and_runtime_apply_gate",
        },
    }
    _write(output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = build_report(Path(args.repo_root).resolve(), Path(args.output))
    print(
        json.dumps(
            {
                "status": report["status"],
                "research_primary": report["research_tiebreak"]["primary_skill"],
                "governance_materialized": report["governance_curation"]["materialized_count"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
