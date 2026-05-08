from __future__ import annotations

import json
from pathlib import Path

from scripts.bench.public_credibility_phase_plan import build_phase_plan, render_markdown


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_phase_plan_separates_external_swe_bench_from_internal_commercial_lanes(tmp_path: Path) -> None:
    lanes = tmp_path / "lanes.json"
    swe = tmp_path / "swe.jsonl"
    _write_json(
        lanes,
        {
            "version": "test",
            "benchmark_id": "commercial:test",
            "lanes": [
                {"id": "capability_lift", "task_refs": [{"manifest": "a.json", "task_id": "a"}]},
                {"id": "governed_delivery", "task_refs": [{"manifest": "b.json", "task_id": "b"}]},
                {"id": "cost_efficiency", "task_refs": [{"manifest": "c.json", "task_id": "c"}]},
            ],
        },
    )
    _write_jsonl(
        swe,
        [
            {
                "repo": "django/django",
                "instance_id": "django__django-1",
                "difficulty": "<15 min fix",
            },
            {
                "repo": "sympy/sympy",
                "instance_id": "sympy__sympy-2",
                "difficulty": "15 min - 1 hour",
            },
        ],
    )

    plan = build_phase_plan(commercial_lanes_path=lanes, swe_bench_path=swe, swe_max_tasks=1)

    assert plan["rules"]["same_model_ab_required_for_uplift_claim"] is True
    assert plan["rules"]["external_benchmark_claim_requires_official_harness"] is True
    assert plan["commercial_lanes"]["lane_ids"] == ["capability_lift", "cost_efficiency", "governed_delivery"]
    assert plan["swe_bench_verified"]["selected_instance_ids"] == ["django__django-1"]

    swe_phases = [phase for phase in plan["phases"] if phase["benchmark_family"] == "swe_bench_verified"]
    assert {phase["phase"] for phase in swe_phases} == {7, 8, 9}
    assert all(phase["external_benchmark"] is True for phase in swe_phases)
    assert swe_phases[0]["claim_scope"] == "external_wiring_smoke_not_public_uplift"


def test_phase_plan_contains_runnable_same_model_commands_for_public_models(tmp_path: Path) -> None:
    lanes = tmp_path / "lanes.json"
    swe = tmp_path / "swe.jsonl"
    _write_json(
        lanes,
        {
            "version": "test",
            "benchmark_id": "commercial:test",
            "lanes": [
                {"id": "capability_lift", "task_refs": []},
                {"id": "governed_delivery", "task_refs": []},
                {"id": "cost_efficiency", "task_refs": []},
            ],
        },
    )
    _write_jsonl(
        swe,
        [{"repo": "django/django", "instance_id": "django__django-1", "difficulty": "<15 min fix"}],
    )

    plan = build_phase_plan(
        commercial_lanes_path=lanes,
        swe_bench_path=swe,
        public_models=("gemini-3-flash-preview", "gemini-3.1-pro-preview"),
    )
    phase1 = next(phase for phase in plan["phases"] if phase["phase"] == 1)

    assert len(phase1["commands"]) == 2
    assert all("--without-mode gemini" in command for command in phase1["commands"])
    assert any("gemini-3-flash-preview" in command for command in phase1["commands"])
    assert any("gemini-3.1-pro-preview" in command for command in phase1["commands"])
    assert "--task-id-filter nexus-value-hidden-001,nexus-value-repair-001,nexus-value-context-001" in phase1["commands"][0]


def test_markdown_marks_swe_bench_as_external_not_headline_before_phase9(tmp_path: Path) -> None:
    lanes = tmp_path / "lanes.json"
    swe = tmp_path / "swe.jsonl"
    _write_json(
        lanes,
        {
            "version": "test",
            "benchmark_id": "commercial:test",
            "lanes": [
                {"id": "capability_lift", "task_refs": []},
                {"id": "governed_delivery", "task_refs": []},
                {"id": "cost_efficiency", "task_refs": []},
            ],
        },
    )
    _write_jsonl(
        swe,
        [{"repo": "django/django", "instance_id": "django__django-1", "difficulty": "<15 min fix"}],
    )

    markdown = render_markdown(build_phase_plan(commercial_lanes_path=lanes, swe_bench_path=swe))

    assert "P7: swe_bench_verified_wiring_smoke" in markdown
    assert "claim_scope: `external_wiring_smoke_not_public_uplift`" in markdown
    assert "official SWE-bench harness result is required" in markdown
    assert "P9: swe_bench_verified_external_headline_gate" in markdown
