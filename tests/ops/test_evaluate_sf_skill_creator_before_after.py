from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.evaluate_sf_skill_creator_before_after import build_report


def _write_skill(root: Path, skill_id: str, description: str) -> None:
    skill_dir = root / ".agents" / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill_id}\ndescription: {description}\n---\n\n# {skill_id}\n",
        encoding="utf-8",
    )


def test_before_after_eval_keeps_after_only_when_triggering_improves(tmp_path: Path) -> None:
    _write_skill(tmp_path, "tdd", "Test-driven development.")
    _write_skill(
        tmp_path,
        "codeintel-skill",
        "Use when Nexus route capability is codeintel and the task needs code scan, impact analysis, symbol context, dependency graph, and code intelligence receipts.",
    )
    report_path = tmp_path / "optimization.json"
    report_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "skill_id": "tdd",
                        "old_description": "Test-driven development.",
                        "candidate_description": (
                            "Use when Nexus route capability is repair_loop and the task needs repair loop "
                            "test-first implementation, red-green-refactor, regression protection, and "
                            "behavior-level evidence; return receipt/evidence/gate/outcome-backed guidance."
                        ),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    _write_skill(
        tmp_path,
        "tdd",
        "Use when Nexus route capability is repair_loop and the task needs repair loop "
        "test-first implementation, red-green-refactor, regression protection, and behavior-level evidence; "
        "return receipt/evidence/gate/outcome-backed guidance.",
    )

    report = build_report(
        repo_root=tmp_path,
        overlay={"primary_skill_by_capability": {"repair_loop": "tdd", "codeintel": "codeintel-skill"}},
        reports=[report_path],
    )

    tdd = {item["skill_id"]: item for item in report["skill_decisions"]}["tdd"]
    assert tdd["decision"] == "KEEP_AFTER"
    assert tdd["delta"]["hit1_delta"] >= 0
    assert tdd["delta"]["false_positive_delta"] <= 0
