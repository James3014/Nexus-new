"""#2952: the reproduction phase's legacy auto-heal acts on a model-written script's output.

That output may not pick the package the host installs, nor make the host build (setup.py
build_ext and its shim / compat retries) sources the script could write. Allowlisted build
dependencies are still installed; everything else runs no command at all.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nexus.services.local_heal.context import GovernanceContext, HealContext, OperationalContext
from nexus.services.local_heal.env_denoiser import EnvDenoiser
from nexus.services.local_heal.phases.reproduction import ReproductionPhase

_ASTROPY_CHECKOUT = (
    "ImportError: You appear to be trying to import astropy from within "
    "a source checkout without building the extension modules first. "
    "Run python setup.py build_ext --inplace"
)


def _denoiser(repo: Path, calls: list) -> EnvDenoiser:
    (repo / "setup.py").write_text("print('model-written setup')\n", encoding="utf-8")

    def run_command(cmd, cwd, timeout):
        calls.append(cmd)
        return 0, "ok"

    return EnvDenoiser(repo, run_command=run_command)


@pytest.mark.parametrize(
    "output",
    [
        "ModuleNotFoundError: No module named 'evilpkg'",
        "ModuleNotFoundError: No module named 'evilpkg.sub'",
        "ImportError: No module named evilpkg",
        "ModuleNotFoundError: No module named '--index-url=http://x/'",
    ],
)
def test_a_model_named_package_is_not_installed(tmp_path, output):
    calls: list = []
    result = _denoiser(tmp_path, calls).prepare_from_evidence(output, model_output=True)
    assert calls == []
    assert result.attempted is False and result.reason == "MODULE_NOT_ALLOWLISTED"
    assert "evilpkg" not in result.reason


@pytest.mark.parametrize(
    "output",
    [
        _ASTROPY_CHECKOUT,
        "ImportError: circular import",
        "error: incompatible function pointer types; tp_traverse\n" + _ASTROPY_CHECKOUT,
        "ModuleNotFoundError: No module named 'astropy'",
    ],
)
def test_no_host_build_from_model_output(tmp_path, output):
    calls: list = []
    result = _denoiser(tmp_path, calls).prepare_from_evidence(output, model_output=True)
    assert calls == []
    assert result.attempted is False and result.reason == "HOST_BUILD_REFUSED_MODEL_OUTPUT"


def test_an_allowlisted_build_dependency_is_still_installed(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    calls: list = []
    result = _denoiser(tmp_path, calls).prepare_from_evidence(
        "ModuleNotFoundError: No module named 'erfa'", model_output=True
    )
    assert calls == [["python3", "-m", "pip", "install", "pyerfa"]]
    assert result.succeeded is True


def test_trusted_evidence_keeps_the_legacy_build(tmp_path):
    # The default (not model output) is unchanged; it has no production caller left.
    calls: list = []
    result = _denoiser(tmp_path, calls).prepare_from_evidence(_ASTROPY_CHECKOUT)
    assert calls == [["python3", "setup.py", "build_ext", "--inplace"]]
    assert result.reason == "ASTROPY_BUILD_EXT_INPLACE"


def test_the_reproduction_phase_passes_the_script_output_as_model_output(tmp_path):
    op = OperationalContext(
        instance_id="t-2952",
        repo_dir=tmp_path,
        problem_statement="bug",
        repro_script="print('ModuleNotFoundError: No module named evilpkg')",
        auto_heal_enabled=True,
    )
    ctx = HealContext(op=op, gov=GovernanceContext())
    runner = MagicMock()
    runner.run_repro.return_value = (False, "ModuleNotFoundError: No module named 'evilpkg'")
    runner.is_environment_failure.return_value = True
    calls: list = []
    phase = ReproductionPhase(
        repro_runner=runner, env_denoiser=_denoiser(tmp_path, calls), ollama_generate_fn=MagicMock()
    )
    phase.execute(ctx)
    assert calls == []
    assert ctx.op.env_denoise.get("reason") == "MODULE_NOT_ALLOWLISTED"
