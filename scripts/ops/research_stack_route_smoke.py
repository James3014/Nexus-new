#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.bench.gemini_nexus_report import _row_route_quality_counts


REQUIRED_STACK = frozenset({"autoreason", "codex-autoresearch", "autoresearch", "autoresearchclaw"})


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _receipts(row: dict[str, Any]) -> list[dict[str, Any]]:
    receipts = row.get("capability_receipts")
    if isinstance(receipts, list):
        return [item for item in receipts if isinstance(item, dict)]
    raw = row.get("capability_receipts_json")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    return []


def _research_stack_sources(row: dict[str, Any]) -> set[str]:
    sources: set[str] = set()
    for receipt in _receipts(row):
        if str(receipt.get("name") or "") != "research":
            continue
        for source in receipt.get("source_projects", []) or []:
            sources.add(str(source).strip().lower())
    session = row.get("research_session") if isinstance(row.get("research_session"), dict) else {}
    for source in session.get("source_projects", []) or []:
        sources.add(str(source).strip().lower())
    return {source for source in sources if source}


def summarize(path: Path, *, require_autoreason_invoked: bool) -> dict[str, Any]:
    rows = _load_jsonl(path)
    failures: list[dict[str, Any]] = []
    selected_total = invoked_total = evidence_total = outcome_total = 0
    preflight_present = session_logged = research_public_safe = 0
    autoreason_selected = autoreason_invoked = 0
    sources_seen: set[str] = set()
    for row in rows:
        row_failures: list[str] = []
        counts = _row_route_quality_counts(row)
        if counts is not None:
            selected_total += counts["selected"]
            invoked_total += counts["invoked"]
            evidence_total += counts["evidence"]
            outcome_total += counts["outcome"]
        if bool(row.get("research_preflight_present")) or isinstance(row.get("research_preflight"), dict):
            preflight_present += 1
        if bool(row.get("research_session_logged")) or bool((row.get("research_session") or {}).get("logged")):
            session_logged += 1
        row_sources = _research_stack_sources(row)
        sources_seen.update(row_sources)
        receipts = _receipts(row)
        for receipt in receipts:
            name = str(receipt.get("name") or "")
            if name == "research" and bool(receipt.get("public_claim_safe")):
                research_public_safe += 1
            if name == "autoreason":
                if bool(receipt.get("selected")):
                    autoreason_selected += 1
                if bool(receipt.get("invoked")):
                    autoreason_invoked += 1
        if str(row.get("status") or "").upper() != "SUCCESS":
            row_failures.append("status_not_success")
        if str(row.get("semantic_status") or "").upper() not in {"VERIFIED", "PARTIAL"}:
            row_failures.append("semantic_not_verified")
        if row_failures:
            failures.append({"task_id": row.get("task_id"), "row_failures": row_failures})
    missing_sources = sorted(REQUIRED_STACK - sources_seen)
    if missing_sources:
        failures.append({"task_id": "__research_stack__", "row_failures": ["source_project_missing"], "missing": missing_sources})
    if rows and preflight_present < len(rows):
        failures.append({"task_id": "__research_stack__", "row_failures": ["research_preflight_missing"]})
    if rows and session_logged < len(rows):
        failures.append({"task_id": "__research_stack__", "row_failures": ["research_session_missing"]})
    if research_public_safe <= 0:
        failures.append({"task_id": "__research_stack__", "row_failures": ["research_public_safe_receipt_missing"]})
    if require_autoreason_invoked and autoreason_selected > 0 and autoreason_invoked <= 0:
        failures.append({"task_id": "__research_stack__", "row_failures": ["autoreason_selected_but_not_invoked"]})
    selected_to_invoked = (invoked_total / selected_total) if selected_total else 0.0
    invoked_to_evidence = (evidence_total / invoked_total) if invoked_total else 0.0
    evidence_to_outcome = (outcome_total / evidence_total) if evidence_total else 0.0
    unnecessary_selected = ((selected_total - invoked_total) / selected_total) if selected_total else 0.0
    return {
        "passed": not failures,
        "file": str(path),
        "metrics": {
            "rows": len(rows),
            "research_preflight_present": preflight_present,
            "research_session_logged": session_logged,
            "research_public_safe": research_public_safe,
            "autoreason_selected": autoreason_selected,
            "autoreason_invoked": autoreason_invoked,
            "source_projects_seen": sorted(sources_seen),
            "route_quality": {
                "selected_total": selected_total,
                "invoked_total": invoked_total,
                "evidence_total": evidence_total,
                "outcome_total": outcome_total,
                "selected_to_invoked_rate": selected_to_invoked,
                "invoked_to_evidence_rate": invoked_to_evidence,
                "evidence_to_outcome_rate": evidence_to_outcome,
                "unnecessary_selected_rate": unnecessary_selected,
            },
        },
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Nexus research-stack route receipts from a with_nexus JSONL.")
    parser.add_argument("--jsonl", required=True, type=Path)
    parser.add_argument("--require-autoreason-invoked", action="store_true")
    args = parser.parse_args(argv)
    summary = summarize(args.jsonl, require_autoreason_invoked=bool(args.require_autoreason_invoked))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
