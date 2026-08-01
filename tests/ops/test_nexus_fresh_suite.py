from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.ops import nexus_fresh_suite


def test_parse_nodeids_uses_stable_sorted_unique_values() -> None:
    output = """tests/z.py::test_z
tests/a.py::test_a
tests/z.py::test_z
================ 2 tests collected ================
"""
    assert nexus_fresh_suite._parse_nodeids(output) == ["tests/a.py::test_a", "tests/z.py::test_z"]


def test_junit_outcomes_classify_pass_fail_skip_and_error(tmp_path: Path) -> None:
    xml = tmp_path / "results.xml"
    xml.write_text(
        """<testsuite tests='4'>
          <testcase name='pass'/>
          <testcase name='fail'><failure/></testcase>
          <testcase name='skip'><skipped/></testcase>
          <testcase name='error'><error/></testcase>
        </testsuite>""",
        encoding="utf-8",
    )
    result = nexus_fresh_suite._junit_outcomes(xml)
    assert result["testcase_count"] == 4
    assert result["passed"] == 1
    assert result["failed"] == 1
    assert result["skipped"] == 1
    assert result["error"] == 1
    assert result["failure_domain_fingerprint"] != "none"


def test_run_fresh_suite_binds_manifest_to_head_and_cache_clear(tmp_path: Path) -> None:
    output = tmp_path / "manifest.json"
    junit_payload = "<testsuite tests='2'><testcase name='a'/><testcase name='b'/></testsuite>"

    def fake_runner(command, *, cwd, capture_output, text, check):
        assert cwd == str(tmp_path)
        assert capture_output is True and text is True and check is False
        if command[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(command, 0, "abc123\n", "")
        if command[:2] == ["git", "branch"]:
            return subprocess.CompletedProcess(command, 0, "nexus/integration/main\n", "")
        if command[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if "--collect-only" in command:
            return subprocess.CompletedProcess(command, 0, "tests/a.py::test_a\ntests/a.py::test_b\n", "")
        junit_arg = next(value for value in command if value.startswith("--junitxml="))
        Path(junit_arg.split("=", 1)[1]).write_text(junit_payload, encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "2 passed\n", "")

    manifest = nexus_fresh_suite.run_fresh_suite(tmp_path, ["tests/a.py"], output_path=output, runner=fake_runner)
    assert manifest["status"] == "PASS"
    assert manifest["head"] == "abc123"
    assert manifest["dirty"] is False
    assert manifest["collection"]["cache_clear"] is True
    assert manifest["collection"]["nodeid_count"] == 2
    assert manifest["execution"]["passed"] == 2
    assert json.loads(output.read_text(encoding="utf-8"))["schema"] == "nexus.fresh_suite_manifest.v1"


def test_run_fresh_suite_fails_when_collection_is_empty(tmp_path: Path) -> None:
    output = tmp_path / "manifest.json"

    def fake_runner(command, *, cwd, capture_output, text, check):
        if command[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(command, 0, "abc123\n", "")
        if command[:2] == ["git", "branch"]:
            return subprocess.CompletedProcess(command, 0, "main\n", "")
        if command[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 0, "collected 0 items\n", "")

    manifest = nexus_fresh_suite.run_fresh_suite(tmp_path, ["tests/none.py"], output_path=output, runner=fake_runner)
    assert manifest["status"] == "FAIL"
    assert manifest["execution"]["exit_code"] is None


def test_run_fresh_suite_rejects_dirty_checkout_even_when_tests_pass(tmp_path: Path) -> None:
    output = tmp_path / "manifest.json"

    def fake_runner(command, *, cwd, capture_output, text, check):
        if command[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(command, 0, "abc123\n", "")
        if command[:2] == ["git", "branch"]:
            return subprocess.CompletedProcess(command, 0, "main\n", "")
        if command[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(command, 0, " M tracked.py\n", "")
        if "--collect-only" in command:
            return subprocess.CompletedProcess(command, 0, "tests/a.py::test_a\n", "")
        junit_arg = next(value for value in command if value.startswith("--junitxml="))
        Path(junit_arg.split("=", 1)[1]).write_text("<testsuite tests='1'><testcase name='a'/></testsuite>", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "1 passed\n", "")

    manifest = nexus_fresh_suite.run_fresh_suite(tmp_path, ["tests/a.py"], output_path=output, runner=fake_runner)
    assert manifest["status"] == "FAIL"
    assert manifest["blockers"] == ["DIRTY_CHECKOUT"]
