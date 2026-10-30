"""Agy pool stopped (James 2026-10-30): nexus-agy-dispatch refuses every new dispatch by default.

Only NEXUS_AGY_POOL_STOPPED_OVERRIDE=1 runs the original logic; journal
maintenance on existing operations (--status, --reconcile,
--finalize-no-effect, --ack-unclean-sweep) still runs.  The CLI refuses
before the snapshot import and argument parsing; the library entry points
that reach a lease, journal or provider refuse too.
"""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ops/nexus-agy-dispatch"
os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
dispatch = SourceFileLoader("nexus_agy_dispatch_pool_stopped", str(SCRIPT)).load_module()

OVERRIDE = "NEXUS_AGY_POOL_STOPPED_OVERRIDE"


class _PassedGate(Exception):
    pass


def _forbid_everything_after_gate(monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise _PassedGate

    monkeypatch.setattr(dispatch, "_refuse_prompt_conflicts", boom)
    monkeypatch.setattr(dispatch, "AgyOperationJournal", boom)


@pytest.mark.parametrize(
    "argv",
    [
        ["hello"],
        ["--prompt", "hello", "--background"],
        ["--operation-run", "op-1", "--prompt-file", "/nonexistent"],
        ["--hcom-collab"],
    ],
)
def test_dispatch_refused_without_override_before_any_side_effect(
    monkeypatch, capsys, tmp_path, argv
):
    monkeypatch.delenv(OVERRIDE, raising=False)
    _forbid_everything_after_gate(monkeypatch)
    op_root = tmp_path / "ops"

    assert dispatch.main([*argv, "--operation-root", str(op_root)]) == 3

    err = capsys.readouterr().err
    assert err.strip() == dispatch.POOL_STOPPED_MESSAGE
    assert "Agy 帳號池已停用" in err
    assert not op_root.exists()


@pytest.mark.parametrize("value", ["", "0", "true", "yes", " 1", "1 ", "01"])
def test_only_exact_one_overrides(monkeypatch, capsys, value):
    monkeypatch.setenv(OVERRIDE, value)
    _forbid_everything_after_gate(monkeypatch)

    assert dispatch.main(["hello"]) == 3
    assert "Agy 帳號池已停用" in capsys.readouterr().err


def test_override_one_runs_original_logic(monkeypatch):
    monkeypatch.setenv(OVERRIDE, "1")
    _forbid_everything_after_gate(monkeypatch)

    with pytest.raises(_PassedGate):
        dispatch.main(["hello"])


@pytest.mark.parametrize(
    "flag", ["--status", "--reconcile", "--finalize-no-effect", "--ack-unclean-sweep"]
)
def test_journal_maintenance_still_runs_without_override(monkeypatch, flag):
    monkeypatch.delenv(OVERRIDE, raising=False)
    _forbid_everything_after_gate(monkeypatch)

    with pytest.raises(_PassedGate):
        dispatch.main([flag, "op-1"])


def test_installed_entrypoint_exits_3_with_message(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != OVERRIDE}
    op_root = tmp_path / "ops"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--operation-root", str(op_root), "hello"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert proc.returncode == 3
    assert proc.stderr.strip() == dispatch.POOL_STOPPED_MESSAGE
    assert proc.stdout == ""
    assert not op_root.exists()


@pytest.mark.parametrize(
    "entry", ["run_agy", "dispatch_hcom_collab", "dispatch_run", "_spawn_background_operation"]
)
def test_library_entry_points_refuse_without_override(monkeypatch, capsys, entry):
    monkeypatch.delenv(OVERRIDE, raising=False)

    func = getattr(dispatch, entry)
    required = {
        name: None
        for name, param in inspect.signature(func).parameters.items()
        if param.default is inspect.Parameter.empty
    }

    with pytest.raises(SystemExit) as exc:
        func(**required)  # refused before any argument is used

    assert exc.value.code == 3
    assert capsys.readouterr().err.strip() == dispatch.POOL_STOPPED_MESSAGE


@pytest.mark.parametrize(
    "argv",
    [
        ["--help"],
        ["--unknown-flag", "hello"],
        ["--timeout", "not-an-int", "hello"],
        ["--stat", "op-1"],  # argparse abbreviation of --status is not exempt
    ],
)
def test_cli_refuses_before_parsing_and_snapshot_import(tmp_path, argv):
    env = {k: v for k, v in os.environ.items() if k != OVERRIDE}
    env["NEXUS_AGY_SNAPSHOT"] = str(tmp_path / "missing-snapshot")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert proc.returncode == 3
    assert proc.stderr.strip() == dispatch.POOL_STOPPED_MESSAGE


def test_cli_maintenance_flag_reaches_snapshot_import(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != OVERRIDE}
    env["NEXUS_AGY_SNAPSHOT"] = str(tmp_path / "missing-snapshot")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--status=op-1"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert proc.returncode == 1
    assert "NEXUS_AGY_SNAPSHOT_MISSING" in proc.stderr
