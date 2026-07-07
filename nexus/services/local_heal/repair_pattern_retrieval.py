"""C6AB: Local repair pattern retrieval from learning closure JSONL.

Retrieves only successful repair patterns (verifier_pass, correct_abstain)
for injection into semantic retry prompt. Excludes failure records.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SUCCESS_CLASSIFICATIONS = {"verifier_pass", "correct_abstain"}


def retrieve_successful_repair_patterns(
    jsonl_path: str | Path,
    limit: int = 5,
    query_hint: str = "",
) -> list[dict[str, Any]]:
    """Retrieve bounded successful repair patterns from learning closure JSONL.

    Only returns records with classification in SUCCESS_CLASSIFICATIONS.
    Excludes verifier_fail, owner_gated, parser_fail, etc.

    Returns list of dicts with: classification, summary, task_id, lesson_id, provenance.
    """
    path = Path(jsonl_path)
    if not path.exists():
        return []

    results: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                classification = rec.get("classification", "")
                if classification not in SUCCESS_CLASSIFICATIONS:
                    continue

                results.append({
                    "classification": classification,
                    "summary": str(rec.get("summary", ""))[:300],
                    "task_id": str(rec.get("task_id", "")),
                    "lesson_id": str(rec.get("lesson_id", "")),
                    "provenance": str(rec.get("receipt_id", "") or rec.get("provenance", "")),
                })

                if len(results) >= limit:
                    break
    except (OSError, IOError):
        return []

    return results


def format_research_patterns_for_prompt(
    patterns: list[dict[str, Any]],
    max_chars: int = 1500,
) -> str:
    """Format retrieved patterns into bounded prompt-ready text.

    Output format:
    - Symptom: <classification>
      Fix: <summary>
      Evidence: <provenance>
    """
    if not patterns:
        return ""

    lines = []
    for p in patterns:
        classification = p.get("classification", "unknown")
        summary = p.get("summary", "")
        provenance = p.get("provenance", "")

        label = "Success pattern" if classification == "verifier_pass" else "Correct abstain (no patch needed)"
        lines.append(f"- {label}: {summary}")
        if provenance:
            lines.append(f"  Evidence: {provenance}")

    text = "\n".join(lines)
    return text[:max_chars]
