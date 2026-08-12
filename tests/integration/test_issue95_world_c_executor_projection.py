from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

from nexus.services.local_heal.local_model_capability_context import LocalModelCapabilityContext
from nexus.services.local_heal.local_model_capability_executors import (
    LocalHealPipelineCapabilityExecutor,
)


def _ctx(source_root: Path, *, run_group: str = "issue95-a") -> LocalModelCapabilityContext:
    return LocalModelCapabilityContext(
        task_id="issue95",
        source_root=str(source_root),
        problem_statement="fix value",
        target_file="a.py",
        target_symbol="f",
        selected_capabilities=("repair_loop",),
        execution_topology="localheal_pipeline",
        evidence_refs=("ref1",),
        route_context={"run_group": run_group},
    )


def _prepare_workspace(source_root, _task_id, *, target_file, repro_script):
    source = Path(source_root)
    workspace = source / "world-c-workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir()
    shutil.copy2(source / target_file, workspace / target_file)
    return workspace


def _fake_pipeline_run(raw_patch: str):
    def run(_self, heal_ctx):
        target = Path(heal_ctx.repo_dir) / "a.py"
        target.write_text("def f():\n    return 2\n", encoding="utf-8")
        heal_ctx.final_patch = raw_patch
        heal_ctx.solve_eligible = True
        heal_ctx.failure_reason = ""
        heal_ctx._world_c_receipt = {"schema": "test"}
        return heal_ctx

    return run


def test_executor_uses_canonical_projection_and_passes_run_group(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    raw_patch = "RAW PIPELINE TEXT MUST NOT BE CANONICAL"

    with (
        patch(
            "nexus.services.local_heal.pipeline.HealPipeline.run",
            new=_fake_pipeline_run(raw_patch),
        ),
        patch(
            "nexus.services.local_heal.pipeline_isolation.prepare_world_c_workspace",
            new=_prepare_workspace,
        ),
        patch(
            "nexus.services.local_heal.world_c_receipt.validate_world_c_receipt",
            return_value=(True, []),
        ),
    ):
        result = LocalHealPipelineCapabilityExecutor().execute(_ctx(tmp_path))

    canonical = result.telemetries["canonical_world_c_patch_projection"]
    assert result.gate_passed is True
    assert canonical["valid"] is True
    assert canonical["patch"] != raw_patch
    assert "-    return 1" in canonical["patch"]
    assert "+    return 2" in canonical["patch"]
    assert result.telemetries["pipeline_final_patch"] == canonical["patch"]
    assert result.telemetries["canonical_run_group"] == "issue95-a"


def test_executor_rejects_unsafe_run_group_before_pipeline(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    with (
        patch("nexus.services.local_heal.pipeline.HealPipeline.run") as run,
        patch(
            "nexus.services.local_heal.pipeline_isolation.prepare_world_c_workspace",
            new=_prepare_workspace,
        ),
    ):
        result = LocalHealPipelineCapabilityExecutor().execute(
            _ctx(tmp_path, run_group="../collision")
        )

    run.assert_not_called()
    assert result.gate_passed is False
    assert "run_group" in result.failure_reason


def test_executor_distinct_run_groups_remain_distinct(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    seen: list[str] = []

    def run(_self, heal_ctx):
        seen.append(heal_ctx.run_group)
        target = Path(heal_ctx.repo_dir) / "a.py"
        target.write_text("def f():\n    return 2\n", encoding="utf-8")
        heal_ctx.final_patch = "raw"
        heal_ctx.solve_eligible = True
        heal_ctx.failure_reason = ""
        heal_ctx._world_c_receipt = {"schema": "test"}
        return heal_ctx

    with (
        patch("nexus.services.local_heal.pipeline.HealPipeline.run", new=run),
        patch(
            "nexus.services.local_heal.pipeline_isolation.prepare_world_c_workspace",
            new=_prepare_workspace,
        ),
        patch(
            "nexus.services.local_heal.world_c_receipt.validate_world_c_receipt",
            return_value=(True, []),
        ),
    ):
        first = LocalHealPipelineCapabilityExecutor().execute(_ctx(tmp_path, run_group="group-a"))
        second = LocalHealPipelineCapabilityExecutor().execute(_ctx(tmp_path, run_group="group-b"))

    assert seen == ["group-a", "group-b"]
    assert first.telemetries["canonical_run_group"] != second.telemetries["canonical_run_group"]


def test_executor_projection_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    ctx = _ctx(tmp_path)
    ctx.route_context["world_c_expected_patch_hash"] = "sha256:" + "0" * 64

    with (
        patch(
            "nexus.services.local_heal.pipeline.HealPipeline.run",
            new=_fake_pipeline_run("raw"),
        ),
        patch(
            "nexus.services.local_heal.pipeline_isolation.prepare_world_c_workspace",
            new=_prepare_workspace,
        ),
        patch(
            "nexus.services.local_heal.world_c_receipt.validate_world_c_receipt",
            return_value=(True, []),
        ),
    ):
        result = LocalHealPipelineCapabilityExecutor().execute(ctx)

    assert result.gate_passed is False
    assert "canonical_patch_projection_error" in result.failure_reason
    assert result.telemetries["pipeline_final_patch"] == ""
