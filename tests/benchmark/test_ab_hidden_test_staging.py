"""PR-2: test_hidden.py leaves the workspace for the whole with-Nexus row (strict/counted lane).

It goes to a private per-run directory (random name, unlistable parent, file mode 0000, hash
sidecar), is put back only while the runner's own hidden verifier runs, and is restored at row
end even when the row raises. Any tampering fails closed: quarantine, row flag, run abort.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.bench.capability_ab_runner as runner
from scripts.bench import hidden_test_staging as staging_mod
from scripts.bench.capability_ab_runner import CapabilityTask, _materialize_fixture, run_with_nexus

NEXUS_CLI_PREFIX = ["uv", "run", "scripts/engine/nexus_cli.py"]
HIDDEN_MARKER = "HIDDEN_ONLY_SENTINEL_7f3a"
HIDDEN_TEXT = f"def test_hidden_contract():\n    assert '{HIDDEN_MARKER}'\n"
IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


def _unlock_tree(path: Path) -> None:
    """Make a 0300/0000 staging tree removable again (tmp_path cleanup)."""
    if path.is_symlink() or not path.exists():
        return
    if path.is_dir():
        os.chmod(path, 0o700)
        for child in path.iterdir():
            _unlock_tree(child)
    else:
        os.chmod(path, 0o600)


@pytest.fixture(autouse=True)
def _isolated_staging(tmp_path, monkeypatch):
    saved = dict(os.environ)
    parent = tmp_path / "cache" / "nexus-bench-hidden"
    monkeypatch.setattr(staging_mod, "_STAGING_PARENT", parent)
    for name in ("_ACTIVE", "_RUN_ROOTS"):
        monkeypatch.setattr(staging_mod, name, {})
    monkeypatch.setattr(staging_mod, "_QUARANTINED", set())
    monkeypatch.setattr(staging_mod, "_RUN_ABORT", [])
    monkeypatch.setattr(staging_mod, "_RUN_RECORD_PATH", [])
    monkeypatch.setattr(staging_mod, "_IN_MEMORY_SHAS", {})
    yield parent
    _unlock_tree(tmp_path / "cache")
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


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


def _plant(path: Path, text: str) -> None:
    if os.path.lexists(path):
        if not path.is_symlink():
            os.chmod(path, 0o600)
        path.unlink()
    path.write_text(text, encoding="utf-8")


def test_hidden_test_is_outside_the_workspace_for_the_row_and_restored(
    tmp_path, _isolated_staging
) -> None:
    workspace, visible, hidden = _case(tmp_path)
    original_mode = _mode(hidden)

    with _staged(workspace, visible) as staging:
        assert staging is not None
        assert not hidden.exists()
        staged = staging.staged_path
        run_root = staged.parent.parent
        assert run_root.parent == _isolated_staging and run_root.name.startswith("run-")
        assert _mode(_isolated_staging) == 0o300 and _mode(run_root) == 0o300
        assert _mode(staged) == 0o000 and os.path.lexists(staging.sidecar_path)
        assert not staged.resolve().is_relative_to(workspace.resolve())
        # The runner still names the hidden verifier while it is staged.
        assert runner._hidden_test_for_visible_test(str(visible)) == str(hidden)
    assert hidden.read_text(encoding="utf-8") == HIDDEN_TEXT
    assert _mode(hidden) == original_mode
    fields = staging.row_fields()
    assert fields["hidden_staged"] is True
    assert fields["hidden_staged_path_sha256"] == hashlib.sha256(str(staged).encode()).hexdigest()
    assert str(staged) not in json.dumps(fields) and "hidden_staged_path" not in fields
    assert fields["hidden_staging_violations"] == [] and fields["hidden_test_tampered"] is False
    assert fields["hidden_absent_checks"] >= 2
    assert staging_mod.run_abort_reason() == ""


def test_hidden_restored_when_the_row_crashes(tmp_path) -> None:
    workspace, visible, hidden = _case(tmp_path)

    with pytest.raises(RuntimeError, match="row crashed"):
        with _staged(workspace, visible):
            assert not hidden.exists()
            raise RuntimeError("row crashed")

    assert hidden.read_text(encoding="utf-8") == HIDDEN_TEXT
    assert staging_mod.active_staging_for(hidden) is None
    assert staging_mod.run_abort_reason() == ""


def _crashed_staging(workspace: Path, hidden: Path) -> staging_mod.HiddenTestStaging:
    """A row that crashed after staging: verified file + sidecar left in this run's root."""
    leftover = staging_mod.HiddenTestStaging(
        hidden_path=hidden.resolve(),
        staged_path=staging_mod.staging_root(workspace) / "oabh-demo__t1" / "test_hidden.py",
    )
    leftover.staged_path.parent.mkdir(mode=0o700, exist_ok=True)
    leftover._move_out()
    assert not hidden.exists()
    return leftover


def test_stale_staging_from_a_crashed_row_is_recovered(tmp_path) -> None:
    workspace, visible, hidden = _case(tmp_path)
    _crashed_staging(workspace, hidden)

    with _staged(workspace, visible):
        assert not hidden.exists()
    assert hidden.read_text(encoding="utf-8") == HIDDEN_TEXT


def test_planted_staged_file_without_sidecar_is_tampered(tmp_path) -> None:
    workspace, visible, hidden = _case(tmp_path)
    leftover = _crashed_staging(workspace, hidden)
    os.chmod(leftover.sidecar_path, 0o600)
    leftover.sidecar_path.unlink()
    _plant(leftover.staged_path, "def test_planted():\n    assert True\n")

    with pytest.raises(staging_mod.HiddenTestStagingError, match="hidden_test_tampered"):
        with _staged(workspace, visible):
            pass
    assert not hidden.exists()  # the planted file is never moved into the workspace


def test_staged_file_swapped_during_the_row_never_reaches_the_verifier(
    tmp_path, monkeypatch
) -> None:
    workspace, visible, hidden = _case(tmp_path)
    ran: list[list[str]] = []
    monkeypatch.setattr(
        runner,
        "_run_process_group_unstaged",
        lambda cmd, **kw: ran.append(list(cmd)) or subprocess.CompletedProcess(cmd, 0, "", ""),
    )

    with _staged(workspace, visible) as staging:
        _plant(staging.staged_path, "def test_planted():\n    assert True\n")
        out = runner._run_process_group(
            runner._pytest_verifier_cmd(str(hidden)), cwd=workspace, env={}, timeout_sec=5
        )
        assert out.returncode == 1 and "hidden_test_tampered" in out.stderr
        assert ran == []
        assert not hidden.exists()
    # Row end: still tampered -> fails closed without raising; the run is aborted.
    assert staging.row_fields()["hidden_test_tampered"] is True
    assert staging_mod.run_abort_reason().startswith("hidden_test_tampered")
    assert not hidden.exists()
    # A missing (quarantined) hidden test fails the verifier instead of using the visible test.
    assert runner._hidden_test_for_visible_test(str(visible)) == str(hidden)


def test_restage_failure_after_verifier_quarantines_and_aborts(tmp_path, monkeypatch) -> None:
    """HIGH-1: the verifier window restores, the file changes, re-staging fails -> quarantine."""
    workspace, visible, hidden = _case(tmp_path)

    def verifier_that_edits_hidden(cmd, **kw):
        hidden.write_text("def test_edited():\n    assert True\n", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "1 passed", "")

    monkeypatch.setattr(runner, "_run_process_group_unstaged", verifier_that_edits_hidden)
    with _staged(workspace, visible) as staging:
        out = runner._run_process_group(
            runner._pytest_verifier_cmd(str(hidden)), cwd=workspace, env={}, timeout_sec=5
        )
        assert out.returncode == 1 and "hidden_test_tampered" in out.stderr
        assert not os.path.lexists(hidden)  # quarantined, not left in the workspace
    staging.restore()  # idempotent, never raises
    assert not os.path.lexists(hidden)
    fields = staging.row_fields()
    assert fields["hidden_test_tampered"] is True and fields["hidden_test_quarantined"] is True
    assert "restage_failed" in staging_mod.run_abort_reason()
    assert staging_mod.is_quarantined(hidden)


def test_symlink_at_hidden_path_is_refused_and_quarantined(tmp_path) -> None:
    workspace, visible, hidden = _case(tmp_path)
    real = tmp_path / "elsewhere.py"
    hidden.replace(real)
    hidden.symlink_to(real)
    with pytest.raises(staging_mod.HiddenTestStagingError, match="symlink_refused"):
        with _staged(workspace, visible):
            pass
    assert not os.path.lexists(hidden)  # the link itself is quarantined, its target untouched
    assert real.read_text(encoding="utf-8") == HIDDEN_TEXT
    assert "symlink_refused" in staging_mod.run_abort_reason()
    assert runner._hidden_test_for_visible_test(str(visible)) == str(hidden)


def test_symlink_at_staged_path_is_tampered(tmp_path) -> None:
    workspace, visible, hidden = _case(tmp_path)
    leftover = _crashed_staging(workspace, hidden)
    target = tmp_path / "planted.py"
    target.write_text("x\n", encoding="utf-8")
    os.chmod(leftover.staged_path, 0o600)
    leftover.staged_path.unlink()
    leftover.staged_path.symlink_to(target)
    with pytest.raises(staging_mod.HiddenTestStagingError, match="hidden_test_tampered"):
        with _staged(workspace, visible):
            pass
    assert not hidden.exists()
    assert staging_mod.run_abort_reason()


def test_symlinked_staging_parent_is_refused(tmp_path, monkeypatch) -> None:
    workspace, visible, hidden = _case(tmp_path)
    (tmp_path / "real_cache").mkdir()
    (tmp_path / "link_cache").symlink_to(tmp_path / "real_cache")
    monkeypatch.setattr(
        staging_mod, "_STAGING_PARENT", tmp_path / "link_cache" / "nexus-bench-hidden"
    )
    with pytest.raises(staging_mod.HiddenTestStagingError, match="symlink_refused"):
        with _staged(workspace, visible):
            pass
    assert hidden.read_text(encoding="utf-8") == HIDDEN_TEXT


def test_hidden_file_reappearing_during_the_row_is_flagged_and_replaced(tmp_path) -> None:
    workspace, visible, hidden = _case(tmp_path)

    with _staged(workspace, visible) as staging:
        hidden.write_text("planted\n", encoding="utf-8")
    assert "hidden_present_during_run:row_end" in staging.violations
    assert hidden.read_text(encoding="utf-8") == HIDDEN_TEXT


def test_staging_disabled_is_a_no_op_and_missing_hidden_fails_closed(tmp_path) -> None:
    workspace, visible, hidden = _case(tmp_path)

    with _staged(workspace, visible, enabled=False) as staging:
        assert staging is None and hidden.exists()
    hidden.unlink()
    with pytest.raises(staging_mod.HiddenTestStagingError, match="hidden_test_missing"):
        with _staged(workspace, visible):
            pass
    assert "hidden_test_missing" in staging_mod.run_abort_reason()
    # Never "not staged": the verifier keeps naming the (missing) hidden file.
    assert runner._hidden_test_for_visible_test(str(visible)) == str(hidden)


def test_staging_root_inside_the_workspace_is_refused(tmp_path, monkeypatch) -> None:
    workspace, visible, hidden = _case(tmp_path)
    monkeypatch.setattr(staging_mod, "_STAGING_PARENT", workspace / "sub")

    with pytest.raises(staging_mod.HiddenTestStagingError, match="staging_root_inside_workspace"):
        with _staged(workspace, visible):
            pass
    assert hidden.read_text(encoding="utf-8") == HIDDEN_TEXT


def test_process_group_restores_hidden_only_for_a_verifier_and_scrubs_env(
    tmp_path, monkeypatch, _isolated_staging
) -> None:
    workspace, visible, hidden = _case(tmp_path)
    seen: list[tuple[str, bool, dict]] = []

    def fake_unstaged(cmd, *, cwd, env, timeout_sec):
        seen.append((cmd[-1], hidden.exists(), dict(env)))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(runner, "_run_process_group_unstaged", fake_unstaged)
    env = {"BENCH_ROOT": str(tmp_path), "KEEP": "1", "LEAK": str(_isolated_staging / "x")}
    with _staged(workspace, visible) as staging:
        runner._run_process_group(
            ["nexus", "research:auto-flow", str(visible)], cwd=workspace, env=env, timeout_sec=5
        )
        runner._run_process_group(
            runner._pytest_verifier_cmd(str(hidden)), cwd=workspace, env=env, timeout_sec=5
        )
        assert not hidden.exists()
    assert [(name, present) for name, present, _ in seen] == [
        (str(visible), False),
        (str(hidden), True),
    ]
    for _, _, sub_env in seen:
        assert sub_env == {"KEEP": "1"}
    assert staging.verify_windows == 1
    assert hidden.read_text(encoding="utf-8") == HIDDEN_TEXT


PROBE = r"""
import json, os, sys
marker, guess_parent, exact = sys.argv[1], sys.argv[2], sys.argv[3]
roots = [v for k, v in os.environ.items() if k not in ("PATH", "HOME") and os.path.isdir(v)]
roots += [os.environ.get("BENCH_ROOT", ""), guess_parent]
found, listed, errors = [], 0, []
for root in roots:
    if not root:
        continue
    for cur, dirs, files in os.walk(root, onerror=lambda e: errors.append(type(e).__name__)):
        listed += 1
        for name in files:
            try:
                if marker in open(os.path.join(cur, name), errors="ignore").read():
                    found.append(os.path.join(cur, name))
            except OSError as exc:
                errors.append(type(exc).__name__)
try:
    exact_read = marker in open(exact, errors="ignore").read()
except OSError as exc:
    exact_read = False
    errors.append("exact:" + type(exc).__name__)
print(json.dumps({"found": found, "exact_read": exact_read, "bench_root": os.environ.get("BENCH_ROOT"), "errors": errors}))
"""


def test_candidate_probing_env_and_bench_root_cannot_read_hidden_bytes(
    tmp_path, _isolated_staging
) -> None:
    """CRITICAL: a with-Nexus subprocess that walks $BENCH_ROOT, every env dir and the default
    staging parent, and even opens the exact staged path, never gets the hidden bytes."""
    workspace, visible, hidden = _case(tmp_path)
    probe = tmp_path / "probe.py"
    probe.write_text(PROBE, encoding="utf-8")
    bench_root = tmp_path / "bench"
    (bench_root / "captures").mkdir(parents=True)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path / "home"),
        "BENCH_ROOT": str(bench_root),
        "AGY_CAPTURE_DIR": str(bench_root / "captures"),
        "AGY_WRAP_RAW_DIR": str(bench_root / "captures"),
    }
    with _staged(workspace, visible) as staging:
        out = runner._run_process_group(
            [
                sys.executable,
                str(probe),
                HIDDEN_MARKER,
                str(_isolated_staging),
                str(staging.staged_path),
            ],
            cwd=workspace,
            env=env,
            timeout_sec=30,
        )
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["found"] == []
    assert result["bench_root"] is None
    if not IS_ROOT:
        assert result["exact_read"] is False
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


def _new_process(monkeypatch) -> None:
    """Forget in-memory staging state, as a fresh runner process would."""
    for name in ("_ACTIVE", "_RUN_ROOTS"):
        monkeypatch.setattr(staging_mod, name, {})
    monkeypatch.setattr(staging_mod, "_QUARANTINED", set())
    monkeypatch.setattr(staging_mod, "_RUN_ABORT", [])
    monkeypatch.setattr(staging_mod, "_IN_MEMORY_SHAS", {})


def _commit_fixture(workspace: Path) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    for args in (
        ["init", "-q"],
        ["add", "-A"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "fixtures"],
    ):
        subprocess.run(["git", *args], cwd=workspace, check=True, env=env, capture_output=True)


def _killed_run(
    tmp_path: Path, workspace: Path, hidden: Path
) -> tuple[staging_mod.HiddenTestStaging, Path]:
    if not (workspace / ".git").exists():
        _commit_fixture(workspace)
    record = tmp_path / "out" / "run_manifest.json"
    staging_mod.configure_run_record(record)
    killed = staging_mod.HiddenTestStaging(
        hidden_path=hidden.resolve(),
        staged_path=staging_mod.staging_root(workspace) / "oabh-demo__t1" / "test_hidden.py",
    )
    killed.stage()  # SIGKILL here: never restored
    assert not hidden.exists()
    return killed, record


def _expected_sha(record: Path) -> str:
    return json.loads(record.read_text())[staging_mod.RUN_RECORD_KEY]["run_root_sha256"]


def test_killed_run_is_recovered_and_nothing_outside_the_run_dir_names_a_path(
    tmp_path, monkeypatch, _isolated_staging
) -> None:
    workspace, visible, hidden = _case(tmp_path)
    killed, record = _killed_run(tmp_path, workspace, hidden)
    run_root = killed.staged_path.parent.parent
    # Output dir: only sha256(run_root). .last-run: only the basename.
    out = json.loads(record.read_text())
    assert out == {
        staging_mod.RUN_RECORD_KEY: {
            "run_root_sha256": hashlib.sha256(str(run_root).encode()).hexdigest()
        }
    }
    assert str(run_root) not in record.read_text() and "test_hidden" not in record.read_text()
    marker = _isolated_staging / staging_mod.LAST_RUN_NAME
    assert marker.read_text() == run_root.name and _mode(marker) == 0o600

    _new_process(monkeypatch)
    # A new run never starts over an unrecovered one.
    with pytest.raises(staging_mod.HiddenTestStagingError, match="unrecovered_previous_run"):
        staging_mod.staging_root(workspace)
    assert staging_mod.recover_last_run(_expected_sha(record), workspace_root=workspace) == [
        str(hidden.resolve())
    ]
    assert hidden.read_text(encoding="utf-8") == HIDDEN_TEXT
    assert staging_mod.run_abort_reason() == ""
    staging_mod.staging_root(workspace)  # now allowed


def test_tampered_leftover_from_a_killed_run_is_never_restored(tmp_path, monkeypatch) -> None:
    workspace, visible, hidden = _case(tmp_path)
    killed, record = _killed_run(tmp_path, workspace, hidden)
    _plant(killed.staged_path, "def test_planted():\n    assert True\n")

    _new_process(monkeypatch)
    with pytest.raises(staging_mod.HiddenTestStagingError, match="hidden_test_tampered"):
        staging_mod.recover_last_run(_expected_sha(record), workspace_root=workspace)
    assert not hidden.exists()
    assert "recovery" in staging_mod.run_abort_reason()


def test_recovery_refuses_a_run_dir_whose_sha_disagrees(tmp_path, monkeypatch) -> None:
    workspace, visible, hidden = _case(tmp_path)
    _killed_run(tmp_path, workspace, hidden)

    _new_process(monkeypatch)
    with pytest.raises(staging_mod.HiddenTestStagingError, match="recovery_run_root"):
        staging_mod.recover_last_run("0" * 64, workspace_root=workspace)
    assert not hidden.exists()
    assert staging_mod.run_abort_reason()


@pytest.mark.parametrize("attack", ["open_run_dir", "staged_outside_run_dir", "bad_marker"])
def test_recovery_treats_on_disk_state_as_untrusted(
    tmp_path, monkeypatch, _isolated_staging, attack
) -> None:
    workspace, visible, hidden = _case(tmp_path)
    killed, record = _killed_run(tmp_path, workspace, hidden)
    run_root = killed.staged_path.parent.parent
    if attack == "open_run_dir":
        os.chmod(run_root, 0o777)
    elif attack == "staged_outside_run_dir":
        rec = run_root / staging_mod.RUN_RECORD_NAME
        data = json.loads(rec.read_text())
        data["entries"][str(hidden.resolve())]["staged"] = str(tmp_path / "elsewhere.py")
        rec.write_text(json.dumps(data))
    else:
        marker = _isolated_staging / staging_mod.LAST_RUN_NAME
        marker.write_text("../../etc")

    _new_process(monkeypatch)
    with pytest.raises(staging_mod.HiddenTestStagingError, match="hidden_test_tampered"):
        staging_mod.recover_last_run(_expected_sha(record), workspace_root=workspace)
    assert not hidden.exists()
    assert staging_mod.run_abort_reason()


def test_staging_errors_never_disclose_a_path(tmp_path, monkeypatch) -> None:
    workspace, visible, hidden = _case(tmp_path)
    with _staged(workspace, visible) as staging:
        os.chmod(staging.staged_path, 0o600)
        staging.staged_path.unlink()  # restore will fail with an OSError carrying the path
    reason = staging_mod.run_abort_reason()
    assert reason and "/" not in reason
    assert all("/" not in v for v in staging.row_fields()["hidden_staging_violations"])


def test_staged_bytes_are_mode_0000_between_verifier_windows(tmp_path, monkeypatch) -> None:
    workspace, visible, hidden = _case(tmp_path)
    modes: list[int] = []

    def verifier(cmd, **kw):
        modes.append(_mode(hidden))
        return subprocess.CompletedProcess(cmd, 0, "1 passed", "")

    monkeypatch.setattr(runner, "_run_process_group_unstaged", verifier)
    with _staged(workspace, visible) as staging:
        assert _mode(staging.staged_path) == 0o000
        runner._run_process_group(
            runner._pytest_verifier_cmd(str(hidden)), cwd=workspace, env={}, timeout_sec=5
        )
        assert _mode(staging.staged_path) == 0o000
    assert modes and modes[0] & 0o400  # readable only inside the verifier window
    assert staging_mod.run_abort_reason() == ""


@pytest.mark.parametrize("failure", ["lstat", "chmod", "keyboard_interrupt"])
def test_any_error_in_the_verifier_window_fails_closed_and_never_runs_the_verifier(
    tmp_path, monkeypatch, failure
) -> None:
    workspace, visible, hidden = _case(tmp_path)
    ran: list[list[str]] = []
    monkeypatch.setattr(
        runner,
        "_run_process_group_unstaged",
        lambda cmd, **kw: ran.append(list(cmd)) or subprocess.CompletedProcess(cmd, 0, "", ""),
    )
    with _staged(workspace, visible) as staging, pytest.MonkeyPatch.context() as mp:
        if failure == "lstat":
            real_lstat = os.lstat

            def bad_lstat(path, *a, **k):
                if str(path).endswith("test_hidden.py") and staging.staged_path == Path(path):
                    raise PermissionError("lstat denied")
                return real_lstat(path, *a, **k)

            mp.setattr(staging_mod.os, "lstat", bad_lstat)
        elif failure == "chmod":
            mp.setattr(
                staging_mod.os,
                "chmod",
                lambda *a, **k: (_ for _ in ()).throw(OSError("chmod failed")),
            )
        else:
            mp.setattr(
                staging_mod,
                "_move_file",
                lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()),
            )
        if failure == "keyboard_interrupt":
            with pytest.raises(KeyboardInterrupt):
                runner._run_process_group(
                    runner._pytest_verifier_cmd(str(hidden)), cwd=workspace, env={}, timeout_sec=5
                )
        else:
            out = runner._run_process_group(
                runner._pytest_verifier_cmd(str(hidden)), cwd=workspace, env={}, timeout_sec=5
            )
            assert out.returncode == 1 and "hidden_test_tampered" in out.stderr
        mp.undo()
    assert ran == []
    assert staging.failed is True and staging.row_fields()["hidden_test_tampered"] is True
    assert staging_mod.run_abort_reason()
    # A failed staging is never "not staged": later windows refuse to run the verifier.
    with pytest.raises(staging_mod.HiddenTestStagingError):
        with staging.verify_window():
            pass


def _edit_record(run_root: Path, hidden: Path, **changes: str) -> None:
    rec = run_root / staging_mod.RUN_RECORD_NAME
    data = json.loads(rec.read_text())
    entry = data["entries"].pop(str(hidden.resolve()))
    origin = changes.pop("origin", str(hidden.resolve()))
    entry.update(changes)
    data["entries"][origin] = entry
    rec.write_text(json.dumps(data))


@pytest.mark.parametrize(
    "attack", ["outside_fixture_roots", "wrong_basename", "sha_mismatch", "symlinked_origin"]
)
def test_recovery_never_writes_outside_a_validated_fixture(tmp_path, monkeypatch, attack) -> None:
    """A tampered record is only a hint: no write to an arbitrary path, ever."""
    workspace, visible, hidden = _case(tmp_path)
    killed, record = _killed_run(tmp_path, workspace, hidden)
    run_root = killed.staged_path.parent.parent
    victim = tmp_path / "victim" / "test_hidden.py"
    victim.parent.mkdir()
    if attack == "outside_fixture_roots":
        _edit_record(run_root, hidden, origin=str(victim))
    elif attack == "wrong_basename":
        _edit_record(run_root, hidden, origin=str(hidden.resolve().with_name("conftest.py")))
    elif attack == "sha_mismatch":
        _edit_record(run_root, hidden, sha256="0" * 64)
    else:
        hidden.symlink_to(victim)  # origin now exists as a symlink pointing elsewhere

    _new_process(monkeypatch)
    with pytest.raises(staging_mod.HiddenTestStagingError, match="hidden_test_tampered"):
        staging_mod.recover_last_run(_expected_sha(record), workspace_root=workspace)
    assert "hidden_recovery_refused" in staging_mod.run_abort_reason()
    assert not victim.exists()
    assert not (hidden.resolve().with_name("conftest.py")).exists()
    if attack == "symlinked_origin":
        assert hidden.is_symlink()  # untouched, never followed or replaced
    else:
        assert not os.path.lexists(hidden)
    assert _mode(killed.staged_path) == 0o000  # bytes stay locked in the run dir


def test_recovery_without_a_trusted_hash_is_refused(tmp_path, monkeypatch) -> None:
    """No in-memory sha and no committed fixture: the record alone never authorizes a write."""
    workspace, visible, hidden = _case(tmp_path)
    (workspace / ".git").mkdir()  # skip the commit: the fixture is not in git
    killed, record = _killed_run(tmp_path, workspace, hidden)
    _new_process(monkeypatch)
    with pytest.raises(staging_mod.HiddenTestStagingError):
        staging_mod.recover_last_run(_expected_sha(record), workspace_root=workspace)
    assert not os.path.lexists(hidden)
