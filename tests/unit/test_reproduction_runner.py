from nexus.services.local_heal.reproduction import ReproductionRunner


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
