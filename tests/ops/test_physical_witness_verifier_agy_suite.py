"""Issue #2260: the physical-witness verifier also gates the agy dispatch suite.

The macOS job runs ``tests/nexus/executors/test_agy_dispatch_seatbelt_physical_
witness.py`` as its own pytest step; these tests pin that the verifier accepts
exactly that file's two witness nodes (never a skip), still verifies the DSH
suite unchanged, and that the workflow step cannot hide a pytest failure.
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
SUITE = "agy-dispatch"
AGY_SOURCE = (ROOT / v.AGY_TEST_FILE).read_text(encoding="utf-8")
HOST = "witness-host"
NOT_BEFORE = "2026-10-10T00:00:00+00:00"
NOW = datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc)
ALL_TESTS = sorted(v.declared_witnesses(AGY_SOURCE)[0])


def _junit(cases=None, *, classname=v.AGY_TEST_CLASSNAME, skipped=0) -> bytes:
    cases = [(name, None) for name in ALL_TESTS] if cases is None else cases
    body = ""
    for name, outcome in cases:
        child = f"<{outcome} message='x'/>" if outcome else ""
        body += f'<testcase classname="{classname}" name="{name}" time="0.1">{child}</testcase>'
    flagged = sum(1 for _, outcome in cases if outcome == "skipped") or skipped
    return (
        '<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests">'
        f'<testsuite name="pytest" errors="0" failures="0" skipped="{flagged}" '
        f'tests="{len(cases)}" timestamp="2026-10-10T00:05:00+00:00" hostname="{HOST}">'
        f"{body}</testsuite></testsuites>"
    ).encode()


def _verify(junit: bytes, source: str = AGY_SOURCE, suite: str = SUITE):
    return v.verify_junit(
        junit, source, not_before=NOT_BEFORE, hostname=HOST, now=NOW, suite_name=suite
    )


def test_source_declares_exactly_the_two_expected_witnesses() -> None:
    tests, witnesses = v.declared_witnesses(AGY_SOURCE)
    assert witnesses == set(v.AGY_EXPECTED_WITNESSES)
    assert len(witnesses) == 2
    assert witnesses <= tests


def test_well_formed_junit_yields_the_two_passed_agy_witnesses() -> None:
    result = _verify(_junit())
    assert [w["node_id"] for w in result["witnesses"]] == [
        f"{v.AGY_TEST_FILE}::{name}" for name in sorted(v.AGY_EXPECTED_WITNESSES)
    ]
    assert {w["outcome"] for w in result["witnesses"]} == {"passed"}


@pytest.mark.parametrize("witness", v.AGY_EXPECTED_WITNESSES)
@pytest.mark.parametrize("outcome", ["skipped", "error", "failure"])
def test_non_passing_agy_witness_is_rejected(witness: str, outcome: str) -> None:
    cases = [(n, outcome if n == witness else None) for n in ALL_TESTS]
    with pytest.raises(v.WitnessError) as exc:
        _verify(_junit(cases))
    assert exc.value.code == f"JUNIT_TESTCASE_{outcome.upper()}"


@pytest.mark.parametrize("witness", v.AGY_EXPECTED_WITNESSES)
def test_missing_agy_witness_is_rejected(witness: str) -> None:
    cases = [(n, None) for n in ALL_TESTS if n != witness]
    with pytest.raises(v.WitnessError) as exc:
        _verify(_junit(cases))
    assert exc.value.code == "JUNIT_COLLECTION_MISMATCH"


def test_linux_shaped_empty_collection_is_rejected() -> None:
    with pytest.raises(v.WitnessError):
        _verify(_junit([]))


def test_dsh_junit_is_not_accepted_for_the_agy_suite_and_vice_versa() -> None:
    with pytest.raises(v.WitnessError) as exc:
        _verify(_junit(classname=v.TEST_CLASSNAME))
    assert exc.value.code == "JUNIT_FOREIGN_TESTCASES"
    dsh_source = (ROOT / v.TEST_FILE).read_text(encoding="utf-8")
    with pytest.raises(v.WitnessError) as exc:
        _verify(_junit(), source=dsh_source, suite="dsh")
    assert exc.value.code in {"JUNIT_FOREIGN_TESTCASES", "JUNIT_COLLECTION_MISMATCH"}


def test_third_declared_witness_in_agy_source_is_rejected() -> None:
    extra = AGY_SOURCE + "\n\n@physical_seatbelt_witness\ndef test_third() -> None:\n    pass\n"
    with pytest.raises(v.WitnessError) as exc:
        _verify(_junit(), source=extra)
    assert exc.value.code == "WITNESS_DECLARATION_MISMATCH"


def test_suites_name_existing_files_and_subject_files() -> None:
    assert set(v.SUITES) == {"dsh", "agy-dispatch", "sandbox-runner-rundir"}
    for test_file, classname, witnesses, subject in v.SUITES.values():
        assert (ROOT / test_file).is_file()
        assert classname == test_file[:-3].replace("/", ".")
        assert len(witnesses) == 2
        assert test_file in subject.values()
        for rel in subject.values():
            assert (ROOT / rel).is_file(), rel


def test_default_suite_remains_dsh() -> None:
    assert v.SUITES["dsh"][0] == v.TEST_FILE
    assert v.SUITES["dsh"][2] == v.EXPECTED_WITNESSES


def _witness_job() -> dict:
    workflow = yaml.safe_load((ROOT / ".github/workflows/pytest.yml").read_text(encoding="utf-8"))
    return workflow["jobs"]["dsh-seatbelt-physical-witness"]


def _step(name: str) -> dict:
    (step,) = [s for s in _witness_job()["steps"] if s.get("name") == name]
    return step


def test_workflow_collects_the_agy_witness_file_and_verifies_its_suite() -> None:
    run = _step("Run agy dispatch Seatbelt physical witnesses")["run"]
    assert v.AGY_TEST_FILE in run
    verify = _step("Verify agy dispatch physical witness receipt")["run"]
    assert "--suite agy-dispatch" in verify
    assert "--require-github-hosted" in verify
    names = [s.get("name") for s in _witness_job()["steps"]]
    assert names.index("Run agy dispatch Seatbelt physical witnesses") < names.index(
        "Verify agy dispatch physical witness receipt"
    )
    for step in _witness_job()["steps"]:
        assert "continue-on-error" not in step, step.get("name")


@pytest.mark.parametrize("pytest_status", [0, 1, 137])
def test_agy_witness_pytest_step_propagates_the_pytest_exit_status(
    tmp_path: Path, pytest_status: int
) -> None:
    step = _step("Run agy dispatch Seatbelt physical witnesses")
    stub = tmp_path / ".venv" / "bin" / "python"
    stub.parent.mkdir(parents=True)
    stub.write_text(f"#!/bin/sh\necho '2 passed'\nexit {pytest_status}\n", encoding="utf-8")
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
    exit_file = witness_dir / "pytest-exit-agy-dispatch.txt"
    assert exit_file.read_text(encoding="utf-8").strip() == str(pytest_status)
