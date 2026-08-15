from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_SCRIPT = REPO_ROOT / "scripts/bench/experimental/model_calibration_plan.py"
THREE_ARM_SCRIPT = REPO_ROOT / "scripts/bench/experimental/model_workforce_three_arm.py"


def _load_plan_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("model_calibration_plan_cli", PLAN_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_plan(argv: list[str], capsys) -> tuple[int, dict]:
    module = _load_plan_cli()
    code = module.main(argv)
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_plan_cli_emits_machine_readable_plan(capsys) -> None:
    code, data = _run_plan(
        [
            "plan",
            "--provider",
            "opencode",
            "--model",
            "opencode-go/deepseek-v4-flash",
            "--target-role",
            "compact_code_candidate",
            "--change-kind",
            "alias_only",
        ],
        capsys,
    )
    assert code == 0
    assert data["schema"] == "nexus.model_calibration_plan.v1"
    assert data["change_class"] == "ALIAS_ONLY"
    assert data["lineage_id"] == "deepseek-v4-flash"
    assert data["stable_floor"] == "L2"
    assert data["current_frontier"] == "L3"
    kinds = [trial["kind"] for trial in data["required_trials"]]
    assert "STABLE_FLOOR_REGRESSION" in kinds and "FRONTIER_EVALUATION" in kinds
    assert [trial["tier"] for trial in data["not_required_trials"]] == ["L0", "L0.25", "L0.5", "L1"]
    assert data["admission_authority"] == "SEPARATE_NOT_ESTABLISHED_BY_THIS_ACTION"


def test_evidence_cli_emits_calibration_bundle(capsys) -> None:
    module = _load_plan_cli()
    code = module.main([
        "evidence",
        "--provider",
        "opencode",
        "--model",
        "opencode-go/deepseek-v4-flash",
    ])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert code == 0
    assert data["schema"] == "nexus.model_calibration_evidence.v1"
    assert data["lineage_id"] == "deepseek-v4-flash"
    assert data["frontier"] == "L3"
    assert data["admission_authority"] == "SEPARATE_NOT_ESTABLISHED_BY_THIS_ACTION"


def test_evidence_cli_by_lineage_id(capsys) -> None:
    module = _load_plan_cli()
    code = module.main(["evidence", "--lineage-id", "gemini-3.7-flash-medium"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["stable_floor"] == "L3"
    assert data["frontier"] == "L4"
    assert data["frontier_experimental"] is True


def test_plan_cli_unknown_model_fails_closed(capsys) -> None:
    module = _load_plan_cli()
    code = module.main([
        "plan",
        "--provider",
        "opencode",
        "--model",
        "opencode/not-a-real-model",
        "--target-role",
        "compact_code_candidate",
        "--change-kind",
        "alias_only",
    ])
    assert code != 0
    assert "No registered lineage" in capsys.readouterr().err


def test_plan_cli_rejects_invalid_change_kind(capsys) -> None:
    module = _load_plan_cli()
    with pytest.raises(SystemExit):
        module.main([
            "plan",
            "--provider",
            "opencode",
            "--model",
            "opencode/deepseek-v4-flash-free",
            "--target-role",
            "compact_code_candidate",
            "--change-kind",
            "made_up_kind",
        ])


def test_plan_cli_does_not_mutate_filesystem(tmp_path, capsys, monkeypatch) -> None:
    snapshot_before = {
        path.relative_to(REPO_ROOT).as_posix(): (
            path.is_file(),
            path.stat().st_mtime_ns if path.exists() else None,
        )
        for path in (REPO_ROOT / "nexus/config").iterdir()
        if path.is_file()
    }
    module = _load_plan_cli()
    module.main([
        "plan",
        "--provider",
        "opencode",
        "--model",
        "opencode/deepseek-v4-flash-free",
        "--target-role",
        "compact_code_candidate",
        "--change-kind",
        "transport_only",
    ])
    capsys.readouterr()
    for path in (REPO_ROOT / "nexus/config").iterdir():
        if not path.is_file():
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        assert relative in snapshot_before
        assert snapshot_before[relative] == (True, path.stat().st_mtime_ns)


def test_plan_cli_never_calls_provider(capsys, monkeypatch) -> None:
    def _fail(*args, **kwargs):
        raise AssertionError("calibration CLI must never spawn a subprocess")

    monkeypatch.setattr(subprocess, "Popen", _fail)
    monkeypatch.setattr(subprocess, "run", _fail)
    module = _load_plan_cli()
    code = module.main([
        "plan",
        "--provider",
        "opencode",
        "--model",
        "opencode/deepseek-v4-flash-free",
        "--target-role",
        "compact_code_candidate",
        "--change-kind",
        "alias_only",
    ])
    assert code == 0


def test_new_lineage_plan_requires_full_baseline(capsys) -> None:
    code, data = _run_plan(
        [
            "plan",
            "--provider",
            "opencode",
            "--model",
            "opencode/brand-new-lineage",
            "--target-role",
            "compact_code_candidate",
            "--change-kind",
            "new_lineage",
        ],
        capsys,
    )
    assert code == 0
    assert data["plan_status"] == "PLANNED_FULL_BASELINE"
    assert {trial["tier"] for trial in data["required_trials"]} == {
        "L0",
        "L0.25",
        "L0.5",
        "L1",
        "L2",
        "L3",
    }
    assert {trial["kind"] for trial in data["required_trials"]} == {"FULL_BASELINE"}


def test_three_arm_benchmark_stays_narrow_diagnostic() -> None:
    assert THREE_ARM_SCRIPT.is_file()
    text = THREE_ARM_SCRIPT.read_text(encoding="utf-8")
    assert "baseline" in text.lower() or "diagnostic" in text.lower()
    assert "calibration instrument" in text.lower()


def test_plan_cli_frontier_plus_one_exploratory_tier_is_next_formal_tier(capsys) -> None:
    code, data = _run_plan(
        [
            "plan",
            "--provider",
            "opencode",
            "--model",
            "opencode-go/deepseek-v4-flash",
            "--target-role",
            "compact_code_candidate",
            "--change-kind",
            "alias_only",
        ],
        capsys,
    )
    assert code == 0
    assert data["current_frontier"] == "L3"
    exploratory = [
        trial
        for trial in data["required_trials"]
        if trial["kind"] == "FRONTIER_PLUS_ONE_EXPLORATORY"
    ]
    assert len(exploratory) == 1
    assert exploratory[0]["tier"] == "L4"
    assert exploratory[0]["optional"] is True


def test_plan_cli_no_exploratory_probe_at_l4_frontier(capsys) -> None:
    code, data = _run_plan(
        [
            "plan",
            "--provider",
            "agy",
            "--model",
            "gemini-3.7-flash-medium",
            "--target-role",
            "focused_verification",
            "--change-kind",
            "model_revision_or_backend_change",
        ],
        capsys,
    )
    assert code == 0
    assert data["current_frontier"] == "L4"
    assert not any(
        trial["kind"] == "FRONTIER_PLUS_ONE_EXPLORATORY" for trial in data["required_trials"]
    )
