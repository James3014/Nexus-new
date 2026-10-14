"""PR-2: test_hidden.py leaves the workspace for the whole with-Nexus row (strict/counted lane).

It goes to ``$BENCH_ROOT/hidden/<task>/``, is put back only while the runner's own hidden
verifier runs, and is restored at row end even when the row raises.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import pytest

import scripts.bench.capability_ab_runner as runner
from scripts.bench import hidden_test_staging as staging_mod
from scripts.bench.capability_ab_runner import CapabilityTask, _materialize_fixture, run_with_nexus

NEXUS_CLI_PREFIX = ["uv", "run", "scripts/engine/nexus_cli.py"]
HIDDEN_TEXT = "def test_hidden_contract():\n    assert True\n"


@pytest.fixture(autouse=True)
def _restore_environ():
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


def _case(tmp_path: Path) -> tuple[Path, Path, Path]:
    workspace = tmp_path / "nn"
    case = workspace / "bench_fixtures" / "online_ab_hard_v1" / "demo"
    case.mkdir(parents=True)
    (case / "target.py").write_text("x = 1\n", encoding="utf-8")
    (case / "test_visible.py").write_text("def test_v():\n    assert True\n", encoding="utf-8")
    (case / "test_hidden.py").write_text(HIDDEN_TEXT, encoding="utf-8")
    return workspace, case / "test_visible.py", case / "test_hidden.py"


def _staged(workspace: Path, visible: Path, *, enabled: bool = True):
    return staging_mod.staged_hidden_test(
        enabled=enabled,
        repo_root=workspace,
        test_file=str(visible),
        task_id="oabh-demo",
        trial_index=1,
    )


def test_hidden_test_is_outside_the_workspace_for_the_row_and_restored(
    tmp_path, monkeypatch
) -> None:
    workspace, visible, hidden = _case(tmp_path)
    monkeypatch.setenv("BENCH_ROOT", str(tmp_path))

    with _staged(workspace, visible) as staging:
        assert staging is not None
        assert not hidden.exists()
        staged = tmp_path / "hidden" / "oabh-demo__t1" / "test_hidden.py"
        assert staged.read_text(encoding="utf-8") == HIDDEN_TEXT
        assert not staged.resolve().is_relative_to(workspace.resolve())
        # The runner still names the hidden verifier while it is staged.
        assert runner._hidden_test_for_visible_test(str(visible)) == str(hidden)
    assert hidden.read_text(encoding="utf-8") == HIDDEN_TEXT
    fields = staging.row_fields()
    assert fields["hidden_staged"] is True
    assert fields["hidden_staging_violations"] == []
    assert fields["hidden_absent_checks"] >= 2
    assert runner._hidden_test_for_visible_test(str(visible)) == str(hidden)


def test_hidden_restored_when_the_row_crashes(tmp_path, monkeypatch) -> None:
    workspace, visible, hidden = _case(tmp_path)
    monkeypatch.setenv("BENCH_ROOT", str(tmp_path))

    with pytest.raises(RuntimeError, match="row crashed"):
        with _staged(workspace, visible):
            assert not hidden.exists()
            raise RuntimeError("row crashed")

    assert hidden.read_text(encoding="utf-8") == HIDDEN_TEXT
    assert staging_mod.active_staging_for(hidden) is None


def test_stale_staging_from_a_killed_run_is_recovered(tmp_path, monkeypatch) -> None:
    workspace, visible, hidden = _case(tmp_path)
    monkeypatch.setenv("BENCH_ROOT", str(tmp_path))
    stale = tmp_path / "hidden" / "oabh-demo__t1" / "test_hidden.py"
    stale.parent.mkdir(parents=True)
    hidden.replace(stale)  # a SIGKILLed runner left it staged

    with _staged(workspace, visible):
        assert not hidden.exists()
    assert hidden.read_text(encoding="utf-8") == HIDDEN_TEXT


def test_hidden_file_reappearing_during_the_row_is_flagged_and_replaced(
    tmp_path, monkeypatch
) -> None:
    workspace, visible, hidden = _case(tmp_path)
    monkeypatch.setenv("BENCH_ROOT", str(tmp_path))

    with _staged(workspace, visible) as staging:
        hidden.write_text("planted\n", encoding="utf-8")
    assert "hidden_present_during_run:row_end" in staging.violations
    assert hidden.read_text(encoding="utf-8") == HIDDEN_TEXT


def test_staging_disabled_or_missing_hidden_is_a_no_op(tmp_path, monkeypatch) -> None:
    workspace, visible, hidden = _case(tmp_path)
    monkeypatch.setenv("BENCH_ROOT", str(tmp_path))

    with _staged(workspace, visible, enabled=False) as staging:
        assert staging is None and hidden.exists()
    hidden.unlink()
    with _staged(workspace, visible) as staging:
        assert staging is None


def test_staging_root_inside_the_workspace_is_refused(tmp_path, monkeypatch) -> None:
    workspace, visible, hidden = _case(tmp_path)
    monkeypatch.setenv("BENCH_ROOT", str(workspace / "sub"))

    with pytest.raises(staging_mod.HiddenTestStagingError, match="staging_root_inside_workspace"):
        with _staged(workspace, visible):
            pass
    assert hidden.read_text(encoding="utf-8") == HIDDEN_TEXT


def test_process_group_restores_hidden_only_for_a_verifier_naming_it(tmp_path, monkeypatch) -> None:
    workspace, visible, hidden = _case(tmp_path)
    monkeypatch.setenv("BENCH_ROOT", str(tmp_path))
    seen: list[tuple[str, bool]] = []

    def fake_unstaged(cmd, *, cwd, env, timeout_sec):
        seen.append((cmd[-1], hidden.exists()))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(runner, "_run_process_group_unstaged", fake_unstaged)
    with _staged(workspace, visible) as staging:
        runner._run_process_group(
            ["nexus", "research:auto-flow", str(visible)], cwd=workspace, env={}, timeout_sec=5
        )
        runner._run_process_group(
            runner._pytest_verifier_cmd(str(hidden)), cwd=workspace, env={}, timeout_sec=5
        )
        assert not hidden.exists()
    assert seen == [(str(visible), False), (str(hidden), True)]
    assert staging.verify_windows == 1
    assert hidden.read_text(encoding="utf-8") == HIDDEN_TEXT


def _success_payload() -> str:
    return json.dumps({
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "nexus_usage_trace": {
            "model_uses_nexus": True,
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "capabilities": {"delivery_gate": True},
            "pillars": {"artifact": {"active": True}},
            "phase_trace": {"P": "route_built", "R": "patched", "A": "verified"},
        },
        "result": {
            "elapsed_sec": 0.1,
            "report": {
                "attempt_count": 1,
                "model_calls": 1,
                "model_name": "gemini-3-flash-preview",
                "model_patch_generated": True,
                "total_tokens": 10,
                "token_capture_status": "measured",
            },
        },
    })


def test_with_nexus_row_runs_without_hidden_and_verifies_with_it(tmp_path, monkeypatch) -> None:
    task = CapabilityTask(
        id="model-required-repair-001",
        difficulty="hard",
        task_type="public_test_repair",
        category="test_repair",
        repo_kind="neutral_fixture",
        task_desc="Repair async timeout tests without hiding the timeout contract.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="pytest_async_repair",
        eligibility_class="model_required",
    )
    target_file, visible_test_file = _materialize_fixture(tmp_path / "nn", task)
    hidden = Path(visible_test_file).with_name("test_hidden.py")
    hidden_text = hidden.read_text(encoding="utf-8")
    observed: list[tuple[str, bool]] = []

    def fake_unstaged(cmd, *, cwd, env, timeout_sec):
        observed.append(("nexus" if cmd[:3] == NEXUS_CLI_PREFIX else cmd[-1], hidden.exists()))
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=_success_payload() if cmd[:3] == NEXUS_CLI_PREFIX else "1 passed",
            stderr="",
        )

    monkeypatch.setenv("BENCH_ROOT", str(tmp_path))
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_BENCH_DISABLE_DETERMINISTIC_RESCUE", "1")
    monkeypatch.setattr(runner, "_run_process_group_unstaged", fake_unstaged)
    with staging_mod.staged_hidden_test(
        enabled=True,
        repo_root=tmp_path / "nn",
        test_file=visible_test_file,
        task_id=task.id,
        trial_index=0,
    ) as staging:
        row = run_with_nexus(
            repo_root=tmp_path / "nn",
            task=task,
            target_file=target_file,
            test_file=visible_test_file,
            timeout_sec=10,
            force_flow=None,
            runner_mode="subprocess",
            with_llm_mode="all",
            strict_llm_baseline=True,
        )
    assert ("nexus", False) in observed
    assert (str(hidden), True) in observed
    assert all(present is False for name, present in observed if name != str(hidden))
    assert row["hidden_verifier_passed"] is True
    assert staging.row_fields()["hidden_staging_violations"] == []
    assert hidden.read_text(encoding="utf-8") == hidden_text


def test_hidden_staging_lane_switch() -> None:
    def ns(**kw):
        return argparse.Namespace(**{
            "strict_llm_baseline": False,
            "counted_first_attempt": False,
            **kw,
        })

    assert runner._hidden_staging_enabled(ns(strict_llm_baseline=True)) is True
    assert runner._hidden_staging_enabled(ns(counted_first_attempt=True)) is True
    assert runner._hidden_staging_enabled(ns()) is False
