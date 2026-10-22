"""The macOS job must run and verify the Claude measurement Seatbelt witnesses (#2747)."""

from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
import yaml

from scripts.ci import verify_physical_witness_junit as v

ROOT = Path(__file__).resolve().parents[2]
TEST_FILE = "tests/nexus/executors/test_claude_measurement_worker.py"
CLASSNAME = "tests.nexus.executors.test_claude_measurement_worker"
WITNESSES = {
    "test_seatbelt_denies_reads_writes_network_and_helper_tools",
    "test_seatbelt_denies_signals_to_processes_outside_the_sandbox",
    "test_git_status_works_alike_in_a_standalone_repo_and_a_p1_worktree",
}
SOURCE = (ROOT / TEST_FILE).read_text(encoding="utf-8")
ALL_TESTS, _ = v.declared_witnesses(SOURCE)


def _junit(*, missing: str | None = None, skipped: str | None = None) -> bytes:
    names = sorted(ALL_TESTS - ({missing} if missing else set()))
    suite = ET.Element(
        "testsuite",
        {
            "tests": str(len(names)),
            "errors": "0",
            "failures": "0",
            "skipped": "1" if skipped else "0",
            "hostname": "witness-host",
            "timestamp": "2026-10-10T00:05:00+00:00",
        },
    )
    for name in names:
        case = ET.SubElement(suite, "testcase", {"classname": CLASSNAME, "name": name})
        if name == skipped:
            ET.SubElement(case, "skipped")
    return ET.tostring(suite)


def _verify(junit: bytes) -> dict:
    return v.verify_junit(
        junit,
        SOURCE,
        not_before="2026-10-10T00:00:00+00:00",
        hostname="witness-host",
        now=datetime(2026, 10, 10, 1, tzinfo=timezone.utc),
        suite_name="claude-measurement",
    )


def test_claude_measurement_witness_suite_is_run_and_verified() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/pytest.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["dsh-seatbelt-physical-witness"]["steps"]
    run = next(
        step
        for step in steps
        if step.get("name") == "Run Claude measurement Seatbelt physical witnesses"
    )
    verify = next(
        step
        for step in steps
        if step.get("name") == "Verify Claude measurement physical witness receipt"
    )
    assert TEST_FILE in run["run"]
    assert "junit-claude-measurement.xml" in run["run"]
    assert "--suite claude-measurement" in verify["run"]
    assert "junit-claude-measurement.xml" in verify["run"]
    assert "--require-github-hosted" in verify["run"]
    assert "receipt-claude-measurement.json" in verify["run"]
    assert 'test "$(cat "$WITNESS_DIR/pytest-exit-claude-measurement.txt")" = 0' in verify["run"]
    assert steps.index(run) < steps.index(verify)
    assert "continue-on-error" not in run
    assert "continue-on-error" not in verify


def test_claude_measurement_junit_requires_every_declared_witness_to_pass() -> None:
    assert v.declared_witnesses(SOURCE)[1] == WITNESSES
    result = _verify(_junit())
    assert {item["node_id"] for item in result["witnesses"]} == {
        f"{TEST_FILE}::{name}" for name in WITNESSES
    }
    assert {item["outcome"] for item in result["witnesses"]} == {"passed"}

    for name in WITNESSES:
        with pytest.raises(v.WitnessError) as missing:
            _verify(_junit(missing=name))
        assert missing.value.code == "JUNIT_COLLECTION_MISMATCH"
        with pytest.raises(v.WitnessError) as skipped:
            _verify(_junit(skipped=name))
        assert skipped.value.code == "JUNIT_TESTCASE_SKIPPED"


def test_dsh_suite_remains_the_default_positive_control() -> None:
    assert v.SUITES["dsh"] == (
        v.TEST_FILE,
        v.TEST_CLASSNAME,
        v.EXPECTED_WITNESSES,
        v.SUBJECT_FILES,
    )
