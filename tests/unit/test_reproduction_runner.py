import hashlib
import subprocess

from nexus.services.local_heal.reproduction import ReproductionRunner, SyntaxValidator


def test_generate_repro_script_extracts_python_fence(tmp_path):
    runner = ReproductionRunner(tmp_path)
    problem = """
    The task fails with the following reproducer:

    ```python
    import pytest

    raise AssertionError("bug reproduced")
    ```
    """

    script = runner.generate_repro_script(problem)

    assert "raise AssertionError" in script
    assert "```" not in script


def test_generate_repro_script_uses_model_when_no_embedded_script(tmp_path):
    calls = []

    def generate(system, prompt, model=None, timeout=None):
        calls.append((system, prompt, model, timeout))
        return "```python\nraise AssertionError('model repro')\n```"

    runner = ReproductionRunner(
        tmp_path,
        generate_fn=generate,
        model_name="qwen2.5-coder:7b",
        timeout_seconds=120,
    )

    script = runner.generate_repro_script("SWE issue with no direct file reference")

    assert script == "raise AssertionError('model repro')"
    assert calls[0][2] == "qwen2.5-coder:7b"
    assert calls[0][3] == 120


def test_generate_repro_script_ignores_doc_example_without_failure_or_assertion(tmp_path):
    calls = []

    def generate(system, prompt, model=None, timeout=None):
        calls.append(prompt)
        return "raise AssertionError('model repro')\n"

    runner = ReproductionRunner(tmp_path, generate_fn=generate)
    problem = """
    Example from the issue:

    ```python
    from astropy.modeling import models as m
    from astropy.modeling.separable import separability_matrix

    cm = m.Linear1D(10) & m.Linear1D(5)
    ```
    """

    script = runner.generate_repro_script(problem)

    assert script == "raise AssertionError('model repro')"
    assert calls


def test_run_repro_rejects_astropy_source_checkout_import_failure(tmp_path):
    runner = ReproductionRunner(tmp_path)
    script = (
        "raise ImportError('You appear to be trying to import astropy from within "
        "a source checkout without building the extension modules first')\n"
    )

    reproduced, evidence = runner.run_repro(script)

    assert reproduced is False
    assert "source checkout" in evidence
    assert runner.is_environment_failure(evidence) is True


def test_syntax_validator_detects_invalid_syntax():
    # 正確語法
    valid_code = "import os\nprint('hello')\n"
    ok, err = SyntaxValidator.validate_syntax(valid_code)
    assert ok is True
    assert err is None

    # 錯誤語法 1
    invalid_code = "import os\nif True\n    print('hello')\n"
    ok, err = SyntaxValidator.validate_syntax(invalid_code)
    assert ok is False
    assert "SyntaxError" in err

    # 錯誤語法 2 (IndentationError)
    indent_error = "def foo():\n  print(1)\n    print(2)"
    ok, err = SyntaxValidator.validate_syntax(indent_error)
    assert ok is False
    assert "IndentationError" in err


def test_run_repro_rejects_syntax_errors_immediately(tmp_path, monkeypatch):
    runner = ReproductionRunner(tmp_path)

    # 語法錯誤的腳本
    bad_script = "class Foo\n  pass"

    # Mock subprocess.run 確保絕對不會被執行
    called_subprocess = False

    def mock_run(*args, **kwargs):
        nonlocal called_subprocess
        called_subprocess = True
        import subprocess

        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    import subprocess

    monkeypatch.setattr(subprocess, "run", mock_run)

    reproduced, evidence = runner.run_repro(bad_script)

    assert reproduced is False
    assert "SyntaxError" in evidence
    assert called_subprocess is False
    assert runner.last_exit_status is None
    assert runner.last_reason_code == "pre_subprocess_failure"


def test_run_repro_preserves_actual_nonzero_exit_status(tmp_path):
    runner = ReproductionRunner(tmp_path)
    reproduced, evidence = runner.run_repro("raise AssertionError('bug')")
    assert reproduced is True
    assert "AssertionError: bug" in evidence
    assert runner.last_exit_status == 1
    assert runner.last_reason_code == "physical_fail"
    assert runner.last_command == ("python3", "reproduce_bug.py")
    assert (
        runner.last_script_sha256
        == hashlib.sha256((tmp_path / "reproduce_bug.py").read_bytes()).hexdigest()
    )


def test_run_repro_rejects_arbitrary_nonzero_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 9, stdout="", stderr="RuntimeError: unrelated crash"
        ),
    )
    runner = ReproductionRunner(tmp_path)
    reproduced, evidence = runner.run_repro("raise RuntimeError('unrelated crash')")
    assert reproduced is False
    assert evidence == "RuntimeError: unrelated crash"
    assert runner.last_exit_status == 9
    assert runner.last_reason_code == "unclassified_nonzero_exit"


def test_run_repro_rejects_dormant_assert_with_unrelated_runtime_error(tmp_path):
    runner = ReproductionRunner(tmp_path)
    script = "if False:\n    assert False, 'dormant'\nraise RuntimeError('unrelated crash')"
    reproduced, evidence = runner.run_repro(script)
    assert reproduced is False
    assert "RuntimeError: unrelated crash" in evidence
    assert runner.last_exit_status == 1
    assert runner.last_reason_code == "unclassified_nonzero_exit"


def test_run_repro_ignores_forged_failure_marker_from_script(tmp_path):
    runner = ReproductionRunner(tmp_path)
    script = (
        "import hashlib, json, sys\n"
        "token = hashlib.sha256(_nexus_source.encode('utf-8')).hexdigest()\n"
        "payload = {'exception_type': 'AssertionError', 'filename': "
        "'nexus_repro_contract.py', 'lineno': 1, 'exit_code': None}\n"
        "print('__NEXUS_REPRO_FAILURE__:' + token + ':' + "
        "json.dumps(payload, sort_keys=True), file=sys.stderr)\n"
        "raise RuntimeError('unrelated crash')\n"
    )
    reproduced, evidence = runner.run_repro(script)
    assert reproduced is False
    assert "RuntimeError: unrelated crash" in evidence
    assert runner.last_exit_status == 1
    assert runner.last_reason_code == "unclassified_nonzero_exit"


def test_run_repro_preserves_explicit_fault_reproduction(tmp_path):
    runner = ReproductionRunner(tmp_path)
    reproduced, _ = runner.run_repro("import sys\nprint('ERROR: expected fault')\nsys.exit(2)")
    assert reproduced is True
    assert runner.last_exit_status == 2
    assert runner.last_reason_code == "physical_fail"


def test_run_repro_rejects_bool_system_exit(tmp_path):
    runner = ReproductionRunner(tmp_path)
    reproduced, evidence = runner.run_repro(
        "import sys\nprint('ERROR: bool is not an exit contract')\nsys.exit(True)"
    )
    assert reproduced is False
    assert "ERROR: bool is not an exit contract" in evidence
    assert runner.last_exit_status == 1
    assert runner.last_reason_code == "unclassified_nonzero_exit"


def test_run_repro_timeout_is_not_physical(tmp_path, monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], timeout=5)

    monkeypatch.setattr(subprocess, "run", raise_timeout)
    runner = ReproductionRunner(tmp_path)
    reproduced, _ = runner.run_repro("assert False")
    assert reproduced is False
    assert runner.last_exit_status is None
    assert runner.last_reason_code == "execution_timeout"


def test_run_repro_exception_is_not_physical(tmp_path, monkeypatch):
    def raise_exception(*args, **kwargs):
        raise OSError("cannot execute")

    monkeypatch.setattr(subprocess, "run", raise_exception)
    runner = ReproductionRunner(tmp_path)
    reproduced, evidence = runner.run_repro("assert False")
    assert reproduced is False
    assert "cannot execute" in evidence
    assert runner.last_exit_status is None
    assert runner.last_reason_code == "execution_exception"


def test_workspace_identity_binds_head_and_tamper_sensitive_state(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    source = tmp_path / "source.py"
    source.write_text("return 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=tmp_path, check=True)
    runner = ReproductionRunner(tmp_path)
    before, before_bound = runner.workspace_identity()
    source.write_text("return 2\n", encoding="utf-8")
    after, after_bound = runner.workspace_identity()
    assert before_bound is True and after_bound is True
    assert before != after
    assert "HEAD=" in before and "WORKSPACE_SHA256=" in before
