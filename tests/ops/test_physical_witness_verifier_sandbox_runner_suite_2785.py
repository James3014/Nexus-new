"""Issue #2785: the physical-witness verifier also gates the sandbox runner run_dir suite.

The macOS job runs ``tests/engine/test_sandbox_runner_rundir_seatbelt_witness_2785.py``
as its own pytest step.  These tests pin that the verifier accepts exactly that file's
two witness nodes (never a skip), that the other suites are not accepted for it, and
that the workflow step cannot hide a pytest failure.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from scripts.ci import verify_physical_witness_junit as v

ROOT = Path(__file__).resolve().parents[2]
SUITE = "sandbox-runner-rundir"
SOURCE = (ROOT / v.SANDBOX_RUNNER_TEST_FILE).read_text(encoding="utf-8")
HOST = "witness-host"
NOT_BEFORE = "2026-10-10T00:00:00+00:00"
NOW = datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc)
ALL_TESTS = sorted(v.declared_witnesses(SOURCE)[0])
RUN_STEP = "Run sandbox runner run_dir Seatbelt physical witnesses"
VERIFY_STEP = "Verify sandbox runner run_dir physical witness receipt"


def _junit(cases=None, *, classname=v.SANDBOX_RUNNER_TEST_CLASSNAME) -> bytes:
    cases = [(name, None) for name in ALL_TESTS] if cases is None else cases
    body = ""
    for name, outcome in cases:
        child = f"<{outcome} message='x'/>" if outcome else ""
        body += f'<testcase classname="{classname}" name="{name}" time="0.1">{child}</testcase>'
    flagged = sum(1 for _, outcome in cases if outcome == "skipped")
    return (
        '<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests">'
        f'<testsuite name="pytest" errors="0" failures="0" skipped="{flagged}" '
        f'tests="{len(cases)}" timestamp="2026-10-10T00:05:00+00:00" hostname="{HOST}">'
        f"{body}</testsuite></testsuites>"
    ).encode()


def _verify(junit: bytes, source: str = SOURCE, suite: str = SUITE):
    return v.verify_junit(
        junit, source, not_before=NOT_BEFORE, hostname=HOST, now=NOW, suite_name=suite
    )


def test_source_declares_exactly_the_two_expected_rundir_witnesses() -> None:
    tests, witnesses = v.declared_witnesses(SOURCE)
    assert witnesses == set(v.SANDBOX_RUNNER_EXPECTED_WITNESSES)
    assert len(witnesses) == 2
    assert witnesses <= tests
    assert v.SUITES[SUITE][0] == v.SANDBOX_RUNNER_TEST_FILE
    assert "nexus/engine/sandbox_runner.py" in v.SUITES[SUITE][3].values()


def test_well_formed_junit_yields_the_two_passed_rundir_witnesses() -> None:
    result = _verify(_junit())
    assert [w["node_id"] for w in result["witnesses"]] == [
        f"{v.SANDBOX_RUNNER_TEST_FILE}::{name}"
        for name in sorted(v.SANDBOX_RUNNER_EXPECTED_WITNESSES)
    ]
    assert {w["outcome"] for w in result["witnesses"]} == {"passed"}


@pytest.mark.parametrize("witness", v.SANDBOX_RUNNER_EXPECTED_WITNESSES)
@pytest.mark.parametrize("outcome", ["skipped", "error", "failure"])
def test_non_passing_rundir_witness_is_rejected(witness: str, outcome: str) -> None:
    cases = [(n, outcome if n == witness else None) for n in ALL_TESTS]
    with pytest.raises(v.WitnessError) as exc:
        _verify(_junit(cases))
    assert exc.value.code == f"JUNIT_TESTCASE_{outcome.upper()}"


@pytest.mark.parametrize("witness", v.SANDBOX_RUNNER_EXPECTED_WITNESSES)
def test_missing_rundir_witness_is_rejected(witness: str) -> None:
    # A Linux-shaped run collects only the declaration test.
    cases = [(n, None) for n in ALL_TESTS if n != witness]
    with pytest.raises(v.WitnessError) as exc:
        _verify(_junit(cases))
    assert exc.value.code == "JUNIT_COLLECTION_MISMATCH"


def test_other_suites_junit_is_not_accepted_for_the_rundir_suite() -> None:
    for classname in (v.TEST_CLASSNAME, v.AGY_TEST_CLASSNAME):
        with pytest.raises(v.WitnessError) as exc:
            _verify(_junit(classname=classname))
        assert exc.value.code == "JUNIT_FOREIGN_TESTCASES"
    with pytest.raises(v.WitnessError):
        _verify(_junit(), suite="agy-dispatch")


def _witness_job() -> dict:
    workflow = yaml.safe_load((ROOT / ".github/workflows/pytest.yml").read_text(encoding="utf-8"))
    return workflow["jobs"]["dsh-seatbelt-physical-witness"]


def _step(name: str) -> dict:
    (step,) = [s for s in _witness_job()["steps"] if s.get("name") == name]
    return step


def test_workflow_collects_the_rundir_witness_file_and_verifies_its_suite() -> None:
    job = _witness_job()
    assert "if" not in job and "continue-on-error" not in job
    run = _step(RUN_STEP)["run"]
    assert v.SANDBOX_RUNNER_TEST_FILE in run
    verify = _step(VERIFY_STEP)["run"]
    assert f"--suite {SUITE}" in verify
    assert "--require-github-hosted" in verify
    assert 'test "$(cat "$WITNESS_DIR/pytest-exit-sandbox-runner-rundir.txt")" = 0' in verify
    names = [s.get("name") for s in job["steps"]]
    assert names.index("Fail closed without physical Seatbelt") < names.index(RUN_STEP)
    assert names.index(RUN_STEP) < names.index(VERIFY_STEP)
    for name in (RUN_STEP, VERIFY_STEP):
        assert "if" not in _step(name), name
        assert "continue-on-error" not in _step(name), name


@pytest.mark.parametrize("pytest_status", [0, 1, 137])
def test_rundir_witness_pytest_step_propagates_the_pytest_exit_status(
    tmp_path: Path, pytest_status: int
) -> None:
    step = _step(RUN_STEP)
    stub = tmp_path / ".venv" / "bin" / "python"
    stub.parent.mkdir(parents=True)
    stub.write_text(f"#!/bin/sh\necho '3 passed'\nexit {pytest_status}\n", encoding="utf-8")
    stub.chmod(0o755)
    witness_dir = tmp_path / "witness"
    witness_dir.mkdir()
    proc = subprocess.run(
        ["bash", "-e", "-c", step["run"]],
        cwd=tmp_path,
        env={"PATH": os.environ["PATH"], "WITNESS_DIR": str(witness_dir), **step["env"]},
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == pytest_status, proc.stdout + proc.stderr
    exit_file = witness_dir / "pytest-exit-sandbox-runner-rundir.txt"
    assert exit_file.read_text(encoding="utf-8").strip() == str(pytest_status)
