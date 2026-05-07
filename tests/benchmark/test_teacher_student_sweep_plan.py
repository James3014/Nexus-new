from __future__ import annotations

from scripts.bench.teacher_student_sweep_plan import build_sweep_plan, render_markdown


def test_build_sweep_plan_groups_recommendations_into_profiles():
    payload = {
        "student_model": "flash_nexus",
        "teacher_model": "gpt55_nexus",
        "rows": [
            {"task_id": "nexus-value-gov-001", "recommendation": "compact_student_context"},
            {"task_id": "nexus-value-hidden-001", "recommendation": "slim_student_runtime_path"},
            {
                "task_id": "nexus-value-repair-002",
                "recommendation": "keep_nexus_value_but_copy_teacher_runtime_profile",
            },
        ],
    }

    out = build_sweep_plan(
        gap_payload=payload,
        tasks_file="tasks.json",
        output_dir=".nexus/reports/sweep",
        model_name="gemini-3-flash-preview",
        timeout_sec=300,
        total_timeout_sec=3600,
    )

    by_name = {profile["name"]: profile for profile in out["profiles"]}
    assert by_name["flash_compact_context"]["task_ids"] == ["nexus-value-gov-001"]
    assert by_name["flash_lite_route"]["command"][by_name["flash_lite_route"]["command"].index("--llm-candidate-cap") + 1] == "3"
    assert "--nexus-only" in by_name["flash_lite_route"]["command"]
    assert "--preflight-only" in by_name["flash_lite_route"]["preflight_command"]
    assert by_name["flash_lite_route"]["shell_command"].startswith("NEXUS_VALUE_HIDDEN_VERIFIER=1")
    assert "--enable-llm-self-heal" in by_name["flash_teacher_repair_copy"]["command"]
    assert by_name["flash_teacher_repair_copy"]["promotion_gate"]["stop_on_first_failed_task"] is True


def test_render_markdown_includes_executable_command():
    out = build_sweep_plan(
        gap_payload={"rows": [{"task_id": "task-a", "recommendation": "compact_student_context"}]},
        tasks_file="tasks.json",
        output_dir=".nexus/reports/sweep",
        model_name="gemini-3-flash-preview",
        timeout_sec=300,
        total_timeout_sec=3600,
    )

    md = render_markdown(out)

    assert "Nexus Teacher Student Sweep Plan" in md
    assert "flash_compact_context" in md
    assert "capability_ab_runner.py" in md
    assert "--always-on-eval" in md
    assert "--preflight-only" in md


def test_sweep_plan_skips_local_tool_success_rows():
    out = build_sweep_plan(
        gap_payload={
            "rows": [
                {
                    "task_id": "nexus-value-hidden-001",
                    "recommendation": "slim_student_runtime_path",
                    "student_success_source": "local_deterministic_success",
                    "student_model_uplift_eligible": False,
                },
                {
                    "task_id": "nexus-value-repair-002",
                    "recommendation": "slim_student_runtime_path",
                    "student_success_source": "model_assisted_success",
                    "student_model_uplift_eligible": True,
                },
            ]
        },
        tasks_file="tasks.json",
        output_dir=".nexus/reports/sweep",
        model_name="gemini-3-flash-preview",
        timeout_sec=300,
        total_timeout_sec=3600,
    )

    by_name = {profile["name"]: profile for profile in out["profiles"]}
    assert by_name["flash_lite_route"]["task_ids"] == ["nexus-value-repair-002"]
