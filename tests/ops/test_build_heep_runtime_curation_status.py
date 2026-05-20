from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.build_heep_runtime_curation_status import build_heep_runtime_curation_status


def test_heep_runtime_curation_status_curates_repo_local_winner(tmp_path: Path) -> None:
    skill_file = tmp_path / ".agents/skills/good/SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("# Good skill\n\nUse local evidence.\n", encoding="utf-8")
    apply_gate = {"cases": [{"skill_ids": ["good"]}]}
    skill_status = {
        "skills": [
            {
                "name": "good",
                "path": ".agents/skills/good/SKILL.md",
                "skill_status": "external_reference_candidate",
            }
        ]
    }

    report = build_heep_runtime_curation_status(
        apply_gate=apply_gate,
        skill_status=skill_status,
        repo_root=tmp_path,
    )

    assert report["status"] == "PASS"
    assert report["summary"]["runtime_update_allowed"] is False
    assert report["skills"][0]["skill_status"] == "nexus_curated_candidate"
    assert report["skills"][0]["test_level"] == "runtime_reviewed"


def test_heep_runtime_curation_status_blocks_unsafe_text(tmp_path: Path) -> None:
    skill_file = tmp_path / ".agents/skills/bad/SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("run rm -rf /tmp/example\n", encoding="utf-8")
    apply_gate = {"cases": [{"skill_ids": ["bad"]}]}
    skill_status = {
        "skills": [
            {
                "name": "bad",
                "path": ".agents/skills/bad/SKILL.md",
                "skill_status": "external_reference_candidate",
            }
        ]
    }

    report = build_heep_runtime_curation_status(
        apply_gate=apply_gate,
        skill_status=skill_status,
        repo_root=tmp_path,
    )

    assert report["status"] == "RETURN"
    assert report["skills"] == []
    assert "bad:dangerous_text_pattern:rm -rf" in report["blockers"]
