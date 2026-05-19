from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts.ops.build_sf_systematic_skill_tournament import build_all, compile_interfaces


def test_compile_interfaces_dedupes_by_content_hash(tmp_path: Path) -> None:
    skill = tmp_path / "repo/skills/paper/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: paper\n"
        "description: Research paper lookup with source citation evidence.\n---\n\n"
        "## Load when\n- Need scientific research source lookup.\n",
        encoding="utf-8",
    )
    inventory = {
        "inventory": [
            {
                "source_root": str(tmp_path),
                "relative_skill_path": "repo/skills/paper/SKILL.md",
                "content_sha256": "abc123",
                "skill_name": "paper",
                "skill_slug_guess": "paper",
                "description": "Research paper lookup with source citation evidence.",
                "capability_guess": "research_control_plane",
                "risk_flags": [],
                "safety_class": "prompt_only_candidate",
                "round": "round9",
            },
            {
                "source_root": str(tmp_path),
                "relative_skill_path": "repo/skills/paper/SKILL.md",
                "content_sha256": "abc123",
                "skill_name": "paper-copy",
                "skill_slug_guess": "paper-copy",
                "description": "duplicate",
                "capability_guess": "research_control_plane",
                "risk_flags": [],
                "safety_class": "prompt_only_candidate",
                "round": "round4",
            },
        ]
    }

    compiled = compile_interfaces(inventory)

    assert compiled["status"] == "PASS"
    assert compiled["summary"]["compiled_interface_count"] == 1
    assert compiled["summary"]["duplicate_group_count"] == 1
    assert compiled["interfaces"][0]["capability_hints"][0] == "research_control_plane"


def test_build_all_writes_systematic_artifacts(tmp_path: Path) -> None:
    skill = tmp_path / "src/repo/skills/code/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: code-simplification\n"
        "description: Code repo complexity impact context simplification.\n---\n\n"
        "## Load when\n- Need code complexity and repository impact analysis.\n",
        encoding="utf-8",
    )
    inventory = {
        "inventory": [
            {
                "source_root": str(tmp_path / "src"),
                "relative_skill_path": "repo/skills/code/SKILL.md",
                "content_sha256": "def456",
                "skill_name": "code-simplification",
                "skill_slug_guess": "code-simplification",
                "description": "Code repo complexity impact context simplification.",
                "capability_guess": "codeintel",
                "risk_flags": [],
                "safety_class": "prompt_only_candidate",
                "round": "round6",
            }
        ]
    }
    overlay = {
        "schema": "test.overlay",
        "candidate_primary_skill_by_capability": {
            "codeintel": "current-codeintel",
            "research_control_plane": "current-research",
        },
    }
    inventory_path = tmp_path / "inventory.json"
    overlay_path = tmp_path / "overlay.json"
    report_dir = tmp_path / "reports"
    skill_root = tmp_path / "skills"
    inventory_path.write_text(__import__("json").dumps(inventory), encoding="utf-8")
    overlay_path.write_text(__import__("json").dumps(overlay), encoding="utf-8")

    report = build_all(
        SimpleNamespace(
            inventory=str(inventory_path),
            overlay=str(overlay_path),
            report_dir=str(report_dir),
            skill_root=str(skill_root),
            batch_cap=4,
            model="gemini-3-flash-preview",
        )
    )

    assert report["status"] == "PASS"
    assert report["compiled_interface_count"] == 1
    assert (report_dir / "NEXUS_SF_SYSTEMATIC_COMPILED_INTERFACES_2026-05-19.json").exists()
    assert (report_dir / "NEXUS_SF_SYSTEMATIC_BATCH_FLASH_SMOKE_MATRIX_2026-05-19.json").exists()
    assert report["batch_row_count"] == 2
