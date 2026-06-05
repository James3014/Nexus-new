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

