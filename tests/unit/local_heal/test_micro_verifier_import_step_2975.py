"""#2975 R1/R2: the MicroVerifier's import step on test modules when pytest is absent.

#2996 made the *test* step record a skip when the interpreter has no pytest, but the import step
before it still imported ``*_test.py`` / ``tests/test_*.py`` with the same interpreter. A test
module that does ``import pytest`` (nearly all real ones) then failed as ``IMPORT_ERROR`` and the
patch was dropped (independent verification of #2996, residual R1). Now that one failure, and
only that one, is recorded as a skipped import (``import_skipped`` in the result and receipt,
``false_pass_risk``); every other import failure still fails closed. R2: the import error now
keeps the exception line (the cause) instead of the first 200 characters of the traceback.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.services.local_heal import micro_verifier as mv
from nexus.services.local_heal.interface import PhaseResult
from nexus.services.local_heal.micro_verifier import MicroVerifier, MicroVerifyResult
from tests.model_sandbox_passthrough import model_exec_without_barrier_runs_unconfined  # noqa: F401

pytestmark = pytest.mark.usefixtures("model_exec_without_barrier_runs_unconfined")

ORACLE = "def sub(a, b):\n    return a - b\n\ndef add(a, b):\n    return a + b\n"
PYTEST_TEST_MODULE = "import pytest\n\n" + ORACLE + "\ndef test_sub():\n    assert sub(5, 3) == 2\n"


@pytest.fixture(scope="module")
def _venv_python(tmp_path_factory) -> str:
    venv = tmp_path_factory.mktemp("nopytest_import") / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True, timeout=120
    )
    return str(venv / "bin" / "python")


@pytest.fixture
def python_without_pytest(_venv_python, monkeypatch) -> str:
    """An interpreter that cannot import pytest. CI's PYTHONPATH would hand it pytest, and the
    MicroVerifier inherits this environment, so drop it (as in the #2996 tests)."""
    for name in ("PYTHONPATH", "PYTHONHOME"):
        monkeypatch.delenv(name, raising=False)
    probe = subprocess.run(
        [_venv_python, "-c", "import pytest"], capture_output=True, text=True, timeout=60
    )
    assert probe.returncode != 0, "fixture venv unexpectedly has pytest"
    return _venv_python


def _write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.parent != repo:
        (p.parent / "__init__.py").write_text("")
    p.write_text(text)


def _verify(repo: Path, patched: list[str], interpreter: str, **meta):
    return MicroVerifier.verify(
        patch_content="",
        repo_dir=repo,
        patched_files=patched,
        verifier_env_metadata={"interpreter": interpreter, **meta},
    )


# --- R1: a test module that only fails because pytest is missing -> recorded skip ------------


@pytest.mark.parametrize("path", ["oracle_test.py", "tests/test_feature.py", "pkg/a_test.py"])
def test_test_module_importing_pytest_is_recorded_skip_not_import_error(
    tmp_path, python_without_pytest, path
):
    _write(tmp_path, path, PYTEST_TEST_MODULE)
    res = _verify(tmp_path, [path], python_without_pytest)
    assert res.passed is True, (res.error_message, res.details)
    assert res.error_message == ""
    assert res.import_skipped == [path]
    assert res.import_ok is False  # like test_ok: True only when the step really ran
    assert res.test_step == "skipped" and res.test_skip_reason == "pytest_unavailable"
    assert res.test_ok is False
    for c in ("import_step_skipped", "test_step_skipped", "pytest_unavailable", "false_pass_risk"):
        assert c in res.classifications
    assert "import_failed" not in res.classifications
    assert "import check skipped (pytest_unavailable)" in res.details
    fields = res.receipt_fields()
    assert fields["import_skipped"] == [path]
    assert fields["test_step"] == "skipped"
    assert "false_pass_risk" in fields["classifications"]


def test_skip_is_scoped_to_the_test_module_other_files_still_imported(
    tmp_path, python_without_pytest
):
    _write(tmp_path, "oracle_test.py", PYTEST_TEST_MODULE)
    _write(tmp_path, "lib.py", "import non_existent_module_r1_xyz\n")
    res = _verify(tmp_path, ["oracle_test.py", "lib.py"], python_without_pytest)
    assert res.passed is False and res.error_message == "IMPORT_ERROR"
    assert res.import_skipped == ["oracle_test.py"]
    assert (
        "lib.py: ModuleNotFoundError: No module named 'non_existent_module_r1_xyz'" in res.details
    )


# --- Counter-examples: everything else still fails closed -----------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "import non_existent_module_r1_xyz\nimport pytest\n",
        "import pytest_nonexistent_plugin_r1\n",  # a pytest-named plugin is not pytest itself
        "from _pytest_lookalike_r1 import x\n",
    ],
    ids=["other_module_first", "pytest_prefixed_plugin", "underscore_lookalike"],
)
def test_test_module_with_other_missing_import_still_fails(tmp_path, python_without_pytest, body):
    _write(tmp_path, "oracle_test.py", body + ORACLE)
    res = _verify(tmp_path, ["oracle_test.py"], python_without_pytest)
    assert res.passed is False and res.error_message == "IMPORT_ERROR"
    assert res.import_skipped == []
    assert "import_failed" in res.classifications


def test_test_module_with_other_missing_import_fails_when_pytest_present(tmp_path):
    _write(tmp_path, "oracle_test.py", "import pytest\nimport non_existent_module_r1_xyz\n")
    res = _verify(tmp_path, ["oracle_test.py"], sys.executable)
    assert res.passed is False and res.error_message == "IMPORT_ERROR"
    assert res.import_skipped == []


def test_missing_pytest_submodule_with_pytest_installed_still_fails(tmp_path):
    # e.name is "pytest.<x>" but pytest itself is importable: not an absent-pytest environment.
    _write(tmp_path, "oracle_test.py", "import pytest.no_such_submodule_r1\n")
    res = _verify(tmp_path, ["oracle_test.py"], sys.executable)
    assert res.passed is False and res.error_message == "IMPORT_ERROR"
    assert res.import_skipped == []


@pytest.mark.parametrize("path", ["helpers.py", "conftest.py", "pkg/fixtures.py"])
def test_non_test_module_importing_pytest_still_fails(tmp_path, python_without_pytest, path):
    _write(tmp_path, path, "import pytest\n\nX = 1\n")
    res = _verify(tmp_path, [path], python_without_pytest)
    assert res.passed is False and res.error_message == "IMPORT_ERROR"
    assert res.import_skipped == []
    assert "No module named 'pytest'" in res.details


def test_model_printed_marker_cannot_skip_a_failing_test(tmp_path):
    """A test module that prints the marker itself is only recorded as a skipped import; the test
    step still probes pytest (present here), runs the file and fails closed."""
    _write(
        tmp_path,
        "oracle_test.py",
        f"print({mv._PYTEST_IMPORT_MISSING_MARKER!r})\n\ndef test_x():\n    assert False\n",
    )
    res = _verify(tmp_path, ["oracle_test.py"], sys.executable)
    assert res.passed is False and res.error_message == "TEST_FAILURE"
    assert res.test_step == "failed"
    assert res.import_skipped == ["oracle_test.py"]


def test_marker_on_a_non_test_module_is_ignored(tmp_path, monkeypatch):
    def fake(argv, **kw):
        return subprocess.CompletedProcess(argv, 0, mv._PYTEST_IMPORT_MISSING_MARKER + "\n", "")

    monkeypatch.setattr(mv, "run_model_argv", fake)
    _write(tmp_path, "lib.py", "X = 1\n")
    res = _verify(tmp_path, ["lib.py"], "/usr/bin/python3")
    assert res.passed is True and res.import_skipped == [] and res.import_ok is True
    assert "import_skipped" not in res.receipt_fields()


def test_only_test_modules_get_the_tolerant_probe(tmp_path, monkeypatch):
    seen: list[str] = []

    def fake(argv, **kw):
        if argv[1] == "-c" and len(argv) > 3:
            seen.append(argv[4] + ("|test" if argv[2] == mv._TEST_IMPORT_PROBE else "|plain"))
        return subprocess.CompletedProcess(argv, 0, "1 passed", "")

    monkeypatch.setattr(mv, "run_model_argv", fake)
    for rel in ("lib.py", "oracle_test.py", "tests/test_feature.py"):
        _write(tmp_path, rel, "X = 1\n")
    _verify(tmp_path, ["lib.py", "oracle_test.py", "tests/test_feature.py"], "/usr/bin/python3")
    assert seen == ["lib|plain", "oracle_test|test", "tests.test_feature|test"]


# --- R2: the import error keeps the cause -----------------------------------------------------


def test_import_error_keeps_exception_line_from_a_long_traceback(tmp_path, monkeypatch):
    frames = "".join(
        f'  File "/very/long/path/to/site-packages/pkg/mod{i}.py", line {i}, in <module>\n'
        f"    import mod{i + 1}\n"
        for i in range(40)
    )
    stderr = (
        "Traceback (most recent call last):\n"
        + frames
        + "ModuleNotFoundError: No module named 'the_real_cause'\n"
    )

    def fake(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, "", stderr)

    monkeypatch.setattr(mv, "run_model_argv", fake)
    _write(tmp_path, "lib.py", "X = 1\n")
    res = _verify(tmp_path, ["lib.py"], "/usr/bin/python3")
    assert res.error_message == "IMPORT_ERROR"
    # The cause leads, so the patch_synthesis error_reason (details[:200]) carries it too.
    assert res.details.startswith("lib.py: ModuleNotFoundError: No module named 'the_real_cause'")
    assert len(res.details) < 800  # bounded: cause line + a short traceback tail


def test_import_error_with_empty_stderr_is_still_described(tmp_path, monkeypatch):
    monkeypatch.setattr(
        mv, "run_model_argv", lambda argv, **kw: subprocess.CompletedProcess(argv, 1, "", "")
    )
    _write(tmp_path, "lib.py", "X = 1\n")
    res = _verify(tmp_path, ["lib.py"], "/usr/bin/python3")
    assert res.passed is False and res.details == "lib.py: (no stderr)"


# --- Receipts: shapes and hashes of attempts without a skipped import are unchanged ----------


def _record(op, name="patch_attempt_1", ok=True, reason=""):
    from nexus.services.local_heal.world_c_receipt import record_world_c_phase_result

    record_world_c_phase_result(
        SimpleNamespace(op=op), name, PhaseResult(success=ok, failure_reason=reason)
    )
    return op._world_c_phase_attempts[-1]


def test_attempt_without_micro_verify_evidence_hash_unchanged():
    # Pinned on the pre-#2996 base and on main 50014942 (identical there too).
    cases = [
        (
            "patch_attempt_1",
            True,
            "--- a/x\n+++ b/x\n",
            "",
            "sha256:4cade512b1ab9ca7622af4cd64d293dc43502c7d9b5adacb6a625ea7ccd7a51c",
        ),
        (
            "patch_attempt_2",
            False,
            "",
            "MICRO_VERIFY_TEST_FAILURE:x",
            "sha256:f7cc412189bad3f3b7994e459ae71bf99e1d9342f8a5f11649e7653b954c2c9f",
        ),
        (
            "verify_attempt_1",
            True,
            "p",
            "",
            "sha256:ea851d6a5e99d53a79a247e07750b683ededb363b11d4ac61d342b3e6711a642",
        ),
    ]
    for name, ok, patch, reason, expected in cases:
        att = _record(SimpleNamespace(final_patch=patch), name, ok, reason)
        assert "micro_verify" not in att
        assert att["evidence_hash"] == expected, name


def test_micro_verify_without_skipped_import_keeps_main_receipt_shape_and_hash():
    res = MicroVerifyResult(
        passed=True,
        syntax_ok=True,
        import_ok=True,
        interpreter_used="/x/python3",
        classifications=[
            "syntax_parse_check",
            "task_scoped_import_check",
            "test_step_skipped",
            "pytest_unavailable",
            "false_pass_risk",
        ],
        test_step="skipped",
        test_skip_reason="pytest_unavailable",
        test_files=["oracle_test.py"],
    )
    fields = res.receipt_fields()
    assert set(fields) == {
        "passed",
        "error_message",
        "interpreter",
        "test_step",
        "test_skip_reason",
        "test_files",
        "no_tests_collected",
        "classifications",
    }
    att = _record(SimpleNamespace(final_patch="--- a/x\n+++ b/x\n", micro_verify=fields))
    # Same value with main's (50014942) micro_verifier.py.
    assert att["evidence_hash"] == (
        "sha256:ab62c7e77dce0740f516ec1bcae84abe16b698565845f04b05271fe62cf81c4b"
    )


def test_skipped_import_is_inside_the_attempt_hash():
    base = MicroVerifyResult(
        passed=True, test_step="skipped", test_skip_reason="pytest_unavailable"
    )
    skipped = MicroVerifyResult(
        passed=True,
        test_step="skipped",
        test_skip_reason="pytest_unavailable",
        import_skipped=["oracle_test.py"],
    )
    a = _record(SimpleNamespace(final_patch="p", micro_verify=base.receipt_fields()))
    b = _record(SimpleNamespace(final_patch="p", micro_verify=skipped.receipt_fields()))
    assert b["micro_verify"]["import_skipped"] == ["oracle_test.py"]
    assert a["evidence_hash"] != b["evidence_hash"]


def test_patch_synthesis_keeps_a_test_module_needing_pytest(tmp_path, python_without_pytest):
    """Through PatchSynthesisPhase.execute: the candidate is kept (it was dropped as
    MICRO_VERIFY_IMPORT_ERROR) and the skipped import is on the attempt record."""
    from unittest.mock import MagicMock

    from nexus.services.local_heal.context import (
        GovernanceContext,
        HealContext,
        OperationalContext,
    )
    from nexus.services.local_heal.patch_applier import PatchApplicationResult
    from nexus.services.local_heal.patcher import Patcher
    from nexus.services.local_heal.phases.patch_synthesis import PatchSynthesisPhase
    from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol

    _write(tmp_path, "oracle_test.py", PYTEST_TEST_MODULE)

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
            instance_id="r2975",
            repo_dir=tmp_path,
            problem_statement="add sub",
            python_executable=python_without_pytest,
        ),
        gov=GovernanceContext(),
    )
    result = phase.execute(ctx)
    assert result.success is True, result.failure_reason
    assert ctx.op.micro_verify["import_skipped"] == ["oracle_test.py"]
    assert ctx.op.micro_verify["test_skip_reason"] == "pytest_unavailable"
    assert "false_pass_risk" in ctx.op.micro_verify["classifications"]
    assert ctx.op.model_decisions[-1]["micro_verify"]["import_skipped"] == ["oracle_test.py"]
