"""#3008: pin the fail-closed and truthful-report behaviour of MicroVerifier and EvaluationGate.

Each test kills a single-line mutant that survived the existing suite (mutation run on
origin/main 93f152f18, re-checked after #3006): exception branches of a test run or import
probe must stay failures, a run with no test files is never a clean pass, a syntax error stops
before anything runs, gate results follow the exit code, and the redacted report never claims a
hidden pass it did not see. The last two tests cover bind_affected_regression_suite, which has
no production caller yet.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from nexus.engine.model_output_sandbox import SandboxError
from nexus.services.local_heal import micro_verifier as mv
from nexus.services.local_heal import evaluation_gate as eg
from nexus.services.local_heal.micro_verifier import MicroVerifier

PY = sys.executable


def _fake_runner(calls, on_test=None, on_import=None):
    """run_model_argv stand-in: the pytest probe says 'present'; test/import runs are scripted."""

    def run(argv, **_kw):
        calls.append(list(argv))
        if argv[1:3] == ["-c", mv._PYTEST_PROBE]:
            return subprocess.CompletedProcess(argv, 0, "", "")
        if argv[1:3] == ["-c", mv._PYTEST_BOOTSTRAP]:  # pytest run of one test file
            return on_test(argv) if on_test else subprocess.CompletedProcess(argv, 0, ".", "")
        if argv[1] == "-c":  # import probe
            if on_import:
                return on_import(argv)
            return subprocess.CompletedProcess(argv, 0, "", "")
        raise AssertionError(f"unexpected sandboxed command: {argv[:2]}")

    return run


def _write(repo, rel, text="def f():\n    return 1\n"):
    (repo / rel).write_text(text)


# --- MicroVerifier: exception branches must fail closed (MV51, MV53, MV55) -------------------


@pytest.mark.parametrize(
    "error",
    [subprocess.TimeoutExpired(["pytest"], 30), SandboxError("no barrier"), OSError("boom")],
    ids=["timeout", "sandbox", "other"],
)
def test_a_test_run_that_errors_is_a_failure_even_if_another_file_passed(
    tmp_path, monkeypatch, error
):
    _write(tmp_path, "test_hangs.py")
    _write(tmp_path, "test_ok.py")

    def on_test(argv):
        if argv[-4].endswith("test_hangs.py"):
            raise error
        return subprocess.CompletedProcess(argv, 0, ".", "")

    calls: list = []
    monkeypatch.setattr(mv, "run_model_argv", _fake_runner(calls, on_test=on_test))
    res = MicroVerifier.verify(
        "", tmp_path, ["test_hangs.py", "test_ok.py"], verifier_env_metadata={"interpreter": PY}
    )
    assert res.passed is False
    assert res.test_step == "failed"
    assert res.error_message == "TEST_FAILURE"


# --- MicroVerifier: an import probe that errors fails closed (MV33) --------------------------


def test_an_import_probe_that_times_out_fails_closed(tmp_path, monkeypatch):
    _write(tmp_path, "calc.py")

    def on_import(argv):
        raise subprocess.TimeoutExpired(argv, 10)

    monkeypatch.setattr(mv, "run_model_argv", _fake_runner([], on_import=on_import))
    res = MicroVerifier.verify("", tmp_path, ["calc.py"], verifier_env_metadata={"interpreter": PY})
    assert res.passed is False
    assert res.error_message == "IMPORT_ERROR"


# --- MicroVerifier: no test files is never a clean pass (MV62) -------------------------------


def test_no_test_files_records_false_pass_risk(tmp_path, monkeypatch):
    _write(tmp_path, "calc.py")
    monkeypatch.setattr(mv, "run_model_argv", _fake_runner([]))
    res = MicroVerifier.verify("", tmp_path, ["calc.py"], verifier_env_metadata={"interpreter": PY})
    assert res.passed is True
    assert res.test_step == "not_applicable"
    assert "false_pass_risk" in res.classifications
    assert "false_pass_risk" in res.receipt_fields()["classifications"]


# --- MicroVerifier: the syntax step fails before anything runs (MV23) ------------------------


def test_syntax_error_is_reported_as_such_and_runs_nothing(tmp_path, monkeypatch):
    _write(tmp_path, "calc.py", "def f(:\n    return 1\n")
    calls: list = []
    monkeypatch.setattr(
        mv,
        "run_model_argv",
        _fake_runner(
            calls, on_import=lambda a: subprocess.CompletedProcess(a, 1, "", "SyntaxError")
        ),
    )
    res = MicroVerifier.verify("", tmp_path, ["calc.py"], verifier_env_metadata={"interpreter": PY})
    assert res.passed is False
    assert res.syntax_ok is False
    assert res.error_message == "SYNTAX_ERROR"
    assert "calc.py:1" in res.details
    assert calls == []


# --- EvaluationGate: pass/fail follows the exit code (EG31, EG35, EG36) ----------------------


@pytest.mark.parametrize("rc,expected", [(0, True), (1, False), (5, False)])
def test_gate_results_follow_the_exit_code(tmp_path, monkeypatch, rc, expected):
    gate = eg.EvaluationGate(tmp_path)
    monkeypatch.setattr(
        gate,
        "_run_confined",
        lambda cmd, timeout: subprocess.CompletedProcess(cmd, rc, "out", "err"),
    )
    [visible] = gate.run_visible_tests([["python", "t.py"]])
    [hidden] = gate.run_hidden_verifier([["python", "h.py"]])
    assert (visible.passed, hidden.passed) == (expected, expected)
    assert (visible.is_hidden, hidden.is_hidden) == (False, True)
    assert visible.output == "outerr"


# --- EvaluationGate: the redacted report never claims a hidden pass it did not see -----------
# (EG39, EG40; EG38 rides along: a passing visible test prints no output)


def test_redacted_report_hidden_status_is_truthful(tmp_path):
    gate = eg.EvaluationGate(tmp_path)
    ok = eg.TestResult(test_id="v", passed=True, output="visible-ok-output")
    hidden_fail = eg.TestResult(test_id="h", passed=False, output="hidden-secret", is_hidden=True)

    not_requested = gate.get_redacted_report([ok], [])
    assert "[NOT_CONFIGURED]" in not_requested
    assert "[PASS] All hidden" not in not_requested

    failed = gate.get_redacted_report([ok], [hidden_fail])
    assert "[FAIL] 1 hidden verifier(s) failed" in failed
    assert "[PASS] All hidden" not in failed
    assert "hidden-secret" not in failed
    assert "visible-ok-output" not in failed


# --- bind_affected_regression_suite (no production caller yet) -------------------------------
# EG05/06/07 compile-only spellings, EG08 duplicate ids, EG12 count mismatch, EG13 empty
# command, EG16 empty base sha, EG24/25 results for a different test.

_T = "tests/test_bug.py::test_boundary"
_CMD = ("python", "-m", "pytest", _T)


def _bind(manifest, *, base_sha="base", candidate_sha="cand", base=None, cand=None):
    passing = [eg.TestResult(test_id=t, passed=True, output="1 passed") for t in manifest.test_ids]
    return eg.bind_affected_regression_suite(
        manifest,
        base_sha=base_sha,
        candidate_sha=candidate_sha,
        base_results=passing if base is None else base,
        candidate_results=passing if cand is None else cand,
        affected_test_ids=manifest.test_ids,
        base_suite_hash=manifest.sha256,
        candidate_suite_hash=manifest.sha256,
    )


@pytest.mark.parametrize(
    "command",
    [
        ("python", "-m", "compileall", "."),
        ("python", "-m", "py_compile", "x.py"),
        ("python", "compile", "x"),
    ],
)
def test_binding_rejects_every_compile_only_spelling(command):
    binding = _bind(eg.AffectedSuiteManifest(test_ids=("c",), commands=(command,)))
    assert (binding.eligible, binding.reason_code) == (False, "SUITE_COMPILE_ONLY")


def test_binding_rejects_malformed_manifests_and_bindings():
    two_ids_one_cmd = eg.AffectedSuiteManifest(test_ids=(_T, "t2"), commands=(_CMD,))
    assert _bind(two_ids_one_cmd).reason_code == "SUITE_TEST_COUNT_MISMATCH"

    empty_cmd = eg.AffectedSuiteManifest(test_ids=(_T,), commands=((),))
    assert _bind(empty_cmd).reason_code == "SUITE_EMPTY"

    good = eg.AffectedSuiteManifest(test_ids=(_T,), commands=(_CMD,))
    assert _bind(good).eligible is True
    assert _bind(good, base_sha="").reason_code == "BASE_CANDIDATE_BINDING_INVALID"

    ok = eg.TestResult(test_id=_T, passed=True, output="1 passed")
    other = eg.TestResult(test_id="tests/other.py::t", passed=True, output="1 passed")
    assert _bind(good, base=[ok, ok]).reason_code == "SUITE_RESULT_MISMATCH"
    assert _bind(good, base=[other]).reason_code == "SUITE_RESULT_MISMATCH"
    assert _bind(good, cand=[other]).reason_code == "SUITE_RESULT_MISMATCH"
