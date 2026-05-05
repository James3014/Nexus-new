from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.research_stack_route_smoke import summarize


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_research_stack_route_smoke_passes_with_four_source_receipts(tmp_path: Path) -> None:
    path = tmp_path / "with_nexus.jsonl"
    _write_jsonl(
        path,
        [
            {
                "task_id": "research-stack-001",
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "research_preflight_present": True,
                "research_session_logged": True,
                "research_session": {
                    "logged": True,
                    "source_projects": ["autoresearch", "codex-autoresearch", "AutoResearchClaw", "autoreason"],
                },
                "capability_receipts": [
                    {
                        "name": "research",
                        "selected": True,
                        "invoked": True,
                        "evidence_present": True,
                        "gate_passed": True,
                        "outcome_contributed": True,
                        "public_claim_safe": True,
                        "source_projects": ["autoresearch", "codex-autoresearch", "AutoResearchClaw", "autoreason"],
                    },
                    {
                        "name": "autoreason",
                        "selected": True,
                        "invoked": True,
                        "evidence_present": True,
                        "gate_passed": True,
                        "outcome_contributed": True,
                        "public_claim_safe": True,
                    },
                ],
            }
        ],
    )

    summary = summarize(path, require_autoreason_invoked=True)

    assert summary["passed"] is True
    assert summary["metrics"]["source_projects_seen"] == [
        "autoreason",
        "autoresearch",
        "autoresearchclaw",
        "codex-autoresearch",
    ]
    assert summary["metrics"]["route_quality"]["selected_to_invoked_rate"] == 1.0


def test_research_stack_route_smoke_fails_when_source_project_missing(tmp_path: Path) -> None:
    path = tmp_path / "with_nexus.jsonl"
    _write_jsonl(
        path,
        [
            {
                "task_id": "research-stack-002",
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "research_preflight_present": True,
                "research_session_logged": True,
                "capability_receipts": [
                    {
                        "name": "research",
                        "selected": True,
                        "invoked": True,
                        "evidence_present": True,
                        "gate_passed": True,
                        "outcome_contributed": True,
                        "public_claim_safe": True,
                        "source_projects": ["autoresearch"],
                    }
                ],
            }
        ],
    )

    summary = summarize(path, require_autoreason_invoked=False)

    assert summary["passed"] is False
    assert summary["failures"][0]["row_failures"] == ["source_project_missing"]
