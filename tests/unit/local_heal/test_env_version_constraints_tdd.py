from types import SimpleNamespace
from pathlib import Path
import pytest
from nexus.services.local_heal.env_resolver import (
    EnvResolver,
    EnvRequirement,
    EnvResolution,
)

from nexus.services.local_heal.env_denoiser import EnvDenoiser, EnvDenoiseResult

def test_env_resolver_detects_incompatible_package_version():
    def mock_import_probe(executable, imports):
        return True, "ok"

    def mock_version_probe(executable):
        return "3.9.24"

    def mock_package_version_probe(executable, package_name):
        if package_name == "numpy":
            return "2.0.0"
        return None

    requirement = EnvRequirement(
        profile="test-legacy",
        python_candidates=("python3.9",),
        allowed_python=((3, 9),),
        required_imports=("numpy",),
        package_constraints={"numpy": "<2.0.0"},
        constraint_violation_reason="NUMPY_TOO_NEW"
    )
    
    resolver = EnvResolver(
        which=lambda candidate: "/usr/bin/python3.9" if candidate == "python3.9" else None,
        version_probe=mock_version_probe,
        import_probe=mock_import_probe,
        package_version_probe=mock_package_version_probe,
    )
    
    resolution = resolver.resolve(requirement)
    assert resolution.ready is False
    assert resolution.reason == "NUMPY_TOO_NEW"
    assert resolution.probes[0]["status"] == "constraint_violation"
    assert "numpy:2.0.0 not in <2.0.0" in resolution.probes[0]["violations"]


def test_env_denoiser_heals_dependency_violation():
    # 1. 初始狀態：環境有問題 (NumPy 2.0.0, 要求 <2.0.0)
    def mock_package_version_probe(executable, package_name):
        if not hasattr(mock_package_version_probe, "called_count"):
            mock_package_version_probe.called_count = 0
        
        mock_package_version_probe.called_count += 1
        if mock_package_version_probe.called_count <= 1:
            return "2.0.0"
        return "1.24.3"

    requirement = EnvRequirement(
        profile="test-legacy",
        python_candidates=("python3.9",),
        package_constraints={"numpy": "<2.0.0"},
        constraint_violation_reason="NUMPY_TOO_NEW"
    )

    resolver = EnvResolver(
        which=lambda candidate: "/usr/bin/python3.9" if candidate == "python3.9" else None,
        version_probe=lambda e: "3.9.24",
        import_probe=lambda e, i: (True, "ok"),
        package_version_probe=mock_package_version_probe,
    )

    resolution = resolver.resolve(requirement)
    assert resolution.ready is False

    # 2. 執行修復
    denoiser = EnvDenoiser(repo_dir=Path("/tmp"))
    
    captured_commands = []
    def mock_run_command(cmd, cwd, timeout):
        captured_commands.append(" ".join(cmd))
        return 0, "Successfully installed"

    denoiser.run_command = mock_run_command
    
    # 執行修復邏輯
    result = denoiser.heal_requirement(resolution, requirement)
    assert result.succeeded is True
    # 預期會調用 pip install
    assert any("pip install" in cmd and "numpy<2.0.0" in cmd for cmd in captured_commands)

    # 3. 再次驗證：環境應該變為 Ready
    new_resolution = resolver.resolve(requirement)
    assert new_resolution.ready is True


def test_env_denoiser_skips_unhealable_attribute_probe_and_heals_later_constraint():
    resolution = EnvResolution(
        profile="astropy-legacy",
        ready=False,
        reason="ASTROPY_NUMPY_VERSION_VIOLATION",
        probes=(
            {
                "candidate": ".venv_astropy_39/bin/python",
                "path": ".venv_astropy_39/bin/python",
                "status": "missing_imports",
                "import_status": "missing_attr:importlib.metadata.packages_distributions",
            },
            {
                "candidate": ".venv_astropy/bin/python",
                "path": ".venv_astropy/bin/python",
                "status": "constraint_violation",
                "violations": "numpy:2.2.6 not in <2.0.0",
            },
        ),
    )
    requirement = EnvRequirement(
        profile="astropy-legacy",
        python_candidates=(".venv_astropy/bin/python",),
        package_constraints={"numpy": "<2.0.0"},
    )
    commands = []

    denoiser = EnvDenoiser(
        repo_dir=Path("/tmp"),
        run_command=lambda cmd, cwd, timeout: commands.append(cmd) or (0, "installed"),
    )

    result = denoiser.heal_requirement(resolution, requirement)

    assert result.succeeded is True
    assert result.python_executable == ".venv_astropy/bin/python"
    assert commands
    assert "numpy<2.0.0" in commands[0]
