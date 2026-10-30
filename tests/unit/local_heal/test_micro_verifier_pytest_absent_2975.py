"""#2975: the MicroVerifier's test step on an interpreter without pytest, and on test-named
files that collect no tests.

Live (w2966-realentry-run1): the task-scoped interpreter was Homebrew python3.14 with no pytest,
the patch touched ``oracle_test.py``, and every attempt failed with
``MICRO_VERIFY_TEST_FAILURE: ... No module named pytest`` although the import check passed.
The test step must now be recorded as skipped (with the reason, in the result and in the
World C receipt) instead of failing, and a real test failure must still fail closed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nexus.services.local_heal.micro_verifier import MicroVerifier, is_test_file
from tests.model_sandbox_passthrough import model_exec_without_barrier_runs_unconfined  # noqa: F401

pytestmark = pytest.mark.usefixtures("model_exec_without_barrier_runs_unconfined")


@pytest.fixture(scope="module")
def python_without_pytest(tmp_path_factory) -> str:
    """An interpreter that cannot import pytest (a fresh venv without pip or system site)."""
    venv = tmp_path_factory.mktemp("nopytest") / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True, timeout=120
    )
    python = venv / "bin" / "python"
    probe = subprocess.run(
        [str(python), "-c", "import pytest"], capture_output=True, text=True, timeout=60
    )
    assert probe.returncode != 0, "fixture venv unexpectedly has pytest"
    return str(python)


def _verify(repo: Path, patched: list[str], interpreter: str):
    return MicroVerifier.verify(
        patch_content="",
        repo_dir=repo,
        patched_files=patched,
        verifier_env_metadata={"interpreter": interpreter},
    )


def test_pytest_absent_test_step_recorded_as_skipped_not_failed(tmp_path, python_without_pytest):
    # The live shape: a module named *_test.py with no test functions, patched correctly.
    (tmp_path / "oracle_test.py").write_text(
        "def sub(a, b):\n    return a - b\n\ndef add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    res = _verify(tmp_path, ["oracle_test.py"], python_without_pytest)
    assert res.passed is True, res.details
    assert res.import_ok is True
    assert res.test_ok is False  # no test ran: never reported as a passed test
    assert res.test_step == "skipped"
    assert res.test_skip_reason == "pytest_unavailable"
    assert res.test_files == ["oracle_test.py"]
    assert "test_step_skipped" in res.classifications
    assert "pytest_unavailable" in res.classifications
    assert "false_pass_risk" in res.classifications
    assert "No module named pytest" not in res.details


def test_pytest_absent_skip_is_visible_in_receipt_fields(tmp_path, python_without_pytest):
    (tmp_path / "test_feature.py").write_text("def test_x():\n    assert False\n")
    res = _verify(tmp_path, ["test_feature.py"], python_without_pytest)
    fields = res.receipt_fields()
    assert fields["passed"] is True
    assert fields["test_step"] == "skipped"
    assert fields["test_skip_reason"] == "pytest_unavailable"
    assert fields["interpreter"] == python_without_pytest
    assert fields["test_files"] == ["test_feature.py"]


def test_pytest_present_failing_test_still_fails_closed(tmp_path):
    (tmp_path / "calc_test.py").write_text("def test_sub():\n    assert 5 - 3 == 3\n")
    res = _verify(tmp_path, ["calc_test.py"], sys.executable)
    assert res.passed is False
    assert res.error_message == "TEST_FAILURE"
    assert res.test_step == "failed"
    assert "test_failed" in res.classifications


def test_pytest_present_passing_test_runs(tmp_path):
    (tmp_path / "calc_test.py").write_text("def test_sub():\n    assert 5 - 3 == 2\n")
    res = _verify(tmp_path, ["calc_test.py"], sys.executable)
    assert res.passed is True
    assert res.test_ok is True
    assert res.test_step == "ran"
    assert "verifier_command_check" in res.classifications
    assert "false_pass_risk" not in res.classifications


def test_pytest_present_no_tests_collected_is_skipped_not_failed(tmp_path):
    # pytest exits 5 when a *_test.py module defines no tests; that is not a failing test.
    (tmp_path / "oracle_test.py").write_text("def sub(a, b):\n    return a - b\n")
    res = _verify(tmp_path, ["oracle_test.py"], sys.executable)
    assert res.passed is True, res.details
    assert res.test_ok is False
    assert res.test_step == "skipped"
    assert res.test_skip_reason == "no_tests_collected"
    assert "false_pass_risk" in res.classifications


def test_mixed_collected_and_empty_test_files_counts_as_ran(tmp_path):
    (tmp_path / "oracle_test.py").write_text("def sub(a, b):\n    return a - b\n")
    (tmp_path / "test_real.py").write_text("def test_ok():\n    assert True\n")
    res = _verify(tmp_path, ["oracle_test.py", "test_real.py"], sys.executable)
    assert res.passed is True
    assert res.test_ok is True
    assert res.test_step == "ran"
    # The file that collected nothing is still on record (never reported as having run).
    assert res.no_tests_collected == ["oracle_test.py"]
    assert res.receipt_fields()["no_tests_collected"] == ["oracle_test.py"]
    assert "no_tests_collected" in res.classifications
    assert "false_pass_risk" in res.classifications


def test_probe_sandbox_refusal_still_fails_closed(tmp_path, python_without_pytest, monkeypatch):
    # No OS barrier: the pytest probe itself must not run, and the step fails closed.
    monkeypatch.setenv("NEXUS_DISABLE_OS_SANDBOX", "1")
    from nexus.engine import model_output_sandbox
    from nexus.services.local_heal import micro_verifier

    calls = []

    def refuse(argv, **kwargs):
        calls.append(list(argv))
        if "-m" in argv and "pytest" in argv:
            raise AssertionError("pytest must not run when the probe was refused")
        if len(calls) == 1:  # import probe: let it pass so the test step is reached
            return subprocess.CompletedProcess(argv, 0, "", "")
        raise model_output_sandbox.SandboxError("no_os_barrier")

    monkeypatch.setattr(micro_verifier, "run_model_argv", refuse)
    (tmp_path / "oracle_test.py").write_text("x = 1\n")
    res = _verify(tmp_path, ["oracle_test.py"], python_without_pytest)
    assert res.passed is False
    assert res.error_message == "TEST_FAILURE"
    assert "verifier_unavailable" in res.classifications
    assert "no_os_barrier" in res.details


def test_probe_unexpected_exit_fails_closed(tmp_path, monkeypatch):
    from nexus.services.local_heal import micro_verifier

    def crash(argv, **kwargs):
        if "-c" in argv and "find_spec" in argv[argv.index("-c") + 1]:
            return subprocess.CompletedProcess(argv, 134, "", "Abort trap")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(micro_verifier, "run_model_argv", crash)
    (tmp_path / "oracle_test.py").write_text("x = 1\n")
    res = _verify(tmp_path, ["oracle_test.py"], sys.executable)
    assert res.passed is False
    assert res.error_message == "TEST_FAILURE"
    assert "verifier_unavailable" in res.classifications


@pytest.mark.parametrize(
    "error",
    [subprocess.TimeoutExpired(["python"], 10), PermissionError("denied"), FileNotFoundError()],
)
def test_probe_errors_fail_closed_never_skip(tmp_path, monkeypatch, error):
    from nexus.services.local_heal import micro_verifier

    def probe_raises(argv, **kwargs):
        if "-c" in argv and "find_spec" in argv[argv.index("-c") + 1]:
            raise error
        if "-m" in argv and "pytest" in argv:
            raise AssertionError("pytest must not run when the probe failed")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(micro_verifier, "run_model_argv", probe_raises)
    (tmp_path / "oracle_test.py").write_text("x = 1\n")
    res = _verify(tmp_path, ["oracle_test.py"], sys.executable)
    assert res.passed is False
    assert res.error_message == "TEST_FAILURE"
    assert res.test_skip_reason == ""
    assert "verifier_unavailable" in res.classifications


@pytest.mark.parametrize(
    "path,expected",
    [
        ("test_x.py", True),
        ("oracle_test.py", True),
        ("tests/test_x.py", True),
        ("pkg/sub/calc_test.py", True),
        ("x.py", False),
        ("testing.py", False),
        ("test_dir/helper.py", False),
        ("latest.py", False),
        ("my_test.py.orig", False),
        ("a_test.pyi", False),
        ("test_x.txt", False),
    ],
)
def test_is_test_file_matches_pytest_default_names_only(path, expected):
    assert is_test_file(path) is expected


def test_world_c_patch_attempt_carries_micro_verify_fields():
    from nexus.services.local_heal.interface import PhaseResult
    from nexus.services.local_heal.world_c_receipt import record_world_c_phase_result

    op = MagicMock(spec=[])
    op.final_patch = "diff"
    op.micro_verify = {
        "passed": True,
        "test_step": "skipped",
        "test_skip_reason": "pytest_unavailable",
    }
    record_world_c_phase_result(op, "patch_attempt_1", PhaseResult(success=True))
    attempt = op._world_c_phase_attempts[-1]
    assert attempt["micro_verify"]["test_skip_reason"] == "pytest_unavailable"

    # A phase with no micro verification keeps the old attempt shape (hashes unchanged).
    op2 = MagicMock(spec=[])
    op2.final_patch = "diff"
    record_world_c_phase_result(op2, "patch_attempt_1", PhaseResult(success=True))
    assert "micro_verify" not in op2._world_c_phase_attempts[-1]


def test_patch_synthesis_forwards_skip_to_output_and_context(tmp_path, python_without_pytest):
    from nexus.services.local_heal.context import (
        GovernanceContext,
        HealContext,
        OperationalContext,
    )
    from nexus.services.local_heal.patch_applier import PatchApplicationResult
    from nexus.services.local_heal.patcher import Patcher
    from nexus.services.local_heal.phases.patch_synthesis import PatchSynthesisPhase
    from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol

    (tmp_path / "oracle_test.py").write_text("def sub(a, b):\n    return a - b\n")

    class MockLLM:
        def generate(self, **kwargs):
            return "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE"

    phase = PatchSynthesisPhase(SolidSearchReplaceProtocol(), Patcher(), llm_client=MockLLM())
    phase.patch_applier.apply_and_validate = MagicMock(
        return_value=PatchApplicationResult(
            success=True, applied_diffs=["+++ b/oracle_test.py\nnew\n"], error_reason=""
        )
    )
    ctx = HealContext(
        op=OperationalContext(
            instance_id="w2975",
            repo_dir=tmp_path,
            problem_statement="add sub",
            python_executable=python_without_pytest,
        ),
        gov=GovernanceContext(),
    )
    result = phase.execute(ctx)
    assert result.success is True, result.failure_reason
    assert ctx.op.micro_verify["test_step"] == "skipped"
    assert ctx.op.micro_verify["test_skip_reason"] == "pytest_unavailable"
    assert ctx.op.model_decisions[-1]["micro_verify"]["test_skip_reason"] == "pytest_unavailable"


def test_world_c_micro_verify_is_not_inherited_by_a_later_attempt():
    from nexus.services.local_heal.interface import PhaseResult
    from nexus.services.local_heal.world_c_receipt import record_world_c_phase_result

    op = MagicMock(spec=[])
    op.final_patch = "diff"
    op.micro_verify = {"test_step": "skipped", "test_skip_reason": "pytest_unavailable"}
    record_world_c_phase_result(op, "patch_attempt_1", PhaseResult(success=True))
    # Attempt 2 is produced by a path that never runs the MicroVerifier (e.g. a backend).
    record_world_c_phase_result(op, "patch_attempt_2", PhaseResult(success=True))
    first, second = op._world_c_phase_attempts
    assert "micro_verify" in first
    assert "micro_verify" not in second


def test_failed_micro_verify_attempt_is_recorded_on_context(tmp_path):
    from nexus.services.local_heal.context import (
        GovernanceContext,
        HealContext,
        OperationalContext,
    )
    from nexus.services.local_heal.patch_applier import PatchApplicationResult
    from nexus.services.local_heal.patcher import Patcher
    from nexus.services.local_heal.phases.patch_synthesis import PatchSynthesisPhase
    from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol

    (tmp_path / "calc_test.py").write_text("def test_sub():\n    assert 5 - 3 == 3\n")

    class MockLLM:
        def generate(self, **kwargs):
            return "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE"

    phase = PatchSynthesisPhase(SolidSearchReplaceProtocol(), Patcher(), llm_client=MockLLM())
    phase.patch_applier.apply_and_validate = MagicMock(
        return_value=PatchApplicationResult(
            success=True, applied_diffs=["+++ b/calc_test.py\nnew\n"], error_reason=""
        )
    )
    ctx = HealContext(
        op=OperationalContext(
            instance_id="w2975-fail",
            repo_dir=tmp_path,
            problem_statement="fix sub",
            python_executable=sys.executable,
        ),
        gov=GovernanceContext(),
    )
    result = phase.execute(ctx)
    assert result.success is False
    assert result.failure_reason.startswith("MICRO_VERIFY_TEST_FAILURE:")
    assert ctx.op.micro_verify["test_step"] == "failed"
    assert ctx.op.micro_verify["passed"] is False


def test_patch_synthesis_execute_clears_a_previous_attempts_record(tmp_path):
    from nexus.services.local_heal.context import (
        GovernanceContext,
        HealContext,
        OperationalContext,
    )
    from nexus.services.local_heal.patcher import Patcher
    from nexus.services.local_heal.phases.patch_synthesis import PatchSynthesisPhase
    from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol

    phase = PatchSynthesisPhase(SolidSearchReplaceProtocol(), Patcher(), llm_client=MagicMock())
    # The attempt dies before producing an output (PhaseRunner records it as failed).
    phase.run = MagicMock(side_effect=RuntimeError("model down"))
    ctx = HealContext(
        op=OperationalContext(instance_id="w2975-stale", repo_dir=tmp_path, problem_statement="x"),
        gov=GovernanceContext(),
    )
    ctx.op.micro_verify = {"test_step": "skipped", "test_skip_reason": "pytest_unavailable"}
    try:
        phase.execute(ctx)
    except RuntimeError:
        pass
    assert ctx.op.micro_verify == {}
