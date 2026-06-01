from nexus.services.local_heal.env_denoiser import EnvDenoiser


ASTROPY_ENV_FAILURE = (
    "ImportError: You appear to be trying to import astropy from within "
    "a source checkout without building the extension modules first. "
    "Run python setup.py build_ext --inplace"
)


def test_env_denoiser_runs_bounded_astropy_build_ext(tmp_path):
    (tmp_path / "setup.py").write_text("print('setup')\n", encoding="utf-8")
    calls = []

    def run_command(cmd, cwd, timeout):
        calls.append((cmd, cwd, timeout))
        return 0, "built extensions"

    denoiser = EnvDenoiser(tmp_path, run_command=run_command, timeout_seconds=42)

    result = denoiser.prepare_from_evidence(ASTROPY_ENV_FAILURE)

    assert result.attempted is True
    assert result.succeeded is True
    assert result.reason == "ASTROPY_BUILD_EXT_INPLACE"
    assert result.commands == ["python3 setup.py build_ext --inplace"]
    assert result.python_executable == "python3"
    assert calls == [(["python3", "setup.py", "build_ext", "--inplace"], tmp_path, 42)]


def test_env_denoiser_skips_unknown_failures(tmp_path):
    calls = []
    denoiser = EnvDenoiser(
        tmp_path,
        run_command=lambda cmd, cwd, timeout: calls.append(cmd) or (0, ""),
    )

    result = denoiser.prepare_from_evidence("AssertionError: semantic bug")

    assert result.attempted is False
    assert result.succeeded is False
    assert result.reason == "UNSUPPORTED"
    assert calls == []


def test_env_denoiser_retries_legacy_setuptools_dep_util_shim(tmp_path):
    (tmp_path / "setup.py").write_text("print('setup')\n", encoding="utf-8")
    calls = []

    def run_command(cmd, cwd, timeout):
        calls.append((cmd, cwd, timeout))
        if len(calls) == 1:
            return 1, "ModuleNotFoundError: No module named 'setuptools.dep_util'"
        return 0, "built with shim"

    denoiser = EnvDenoiser(tmp_path, run_command=run_command, timeout_seconds=42)

    result = denoiser.prepare_from_evidence(ASTROPY_ENV_FAILURE)

    assert result.attempted is True
    assert result.succeeded is True
    assert result.reason == "ASTROPY_BUILD_EXT_WITH_SETUPTOOLS_DEP_UTIL_SHIM"
    assert len(result.commands) == 2
    assert calls[0][0] == ["python3", "setup.py", "build_ext", "--inplace"]
    assert calls[1][0][:2] == ["python3", "-c"]
    assert "setuptools.dep_util" in calls[1][0][2]


def test_env_denoiser_uses_configured_python_for_astropy_build(tmp_path):
    (tmp_path / "setup.py").write_text("print('setup')\n", encoding="utf-8")
    calls = []

    def run_command(cmd, cwd, timeout):
        calls.append(cmd)
        return 0, "built"

    denoiser = EnvDenoiser(
        tmp_path,
        run_command=run_command,
        python_executable="/opt/python3.11",
    )

    result = denoiser.prepare_from_evidence(ASTROPY_ENV_FAILURE)

    assert result.succeeded is True
    assert result.python_executable == "/opt/python3.11"
    assert calls[0][0] == "/opt/python3.11"


def test_env_denoiser_retries_compat_python_after_abi_failure(tmp_path):
    (tmp_path / "setup.py").write_text("print('setup')\n", encoding="utf-8")
    calls = []

    def run_command(cmd, cwd, timeout):
        calls.append(cmd)
        if len(calls) == 1:
            return 1, "ModuleNotFoundError: No module named 'setuptools.dep_util'"
        if len(calls) == 2:
            return 1, "error: incompatible function pointer types"
        return 0, "built with compat python"

    denoiser = EnvDenoiser(
        tmp_path,
        run_command=run_command,
        python_executable="python3",
        compat_python_executable="python3.12",
        support_site_packages="/support/site-packages",
    )

    result = denoiser.prepare_from_evidence(ASTROPY_ENV_FAILURE)

    assert result.succeeded is True
    assert result.reason == "ASTROPY_BUILD_EXT_WITH_COMPAT_PYTHON"
    assert result.python_executable == "python3.12"
    assert len(result.commands) == 3
    assert calls[2][:2] == ["python3.12", "-c"]
    assert "/support/site-packages" in calls[2][2]


def test_env_denoiser_discovers_extension_helpers_support_path(tmp_path, monkeypatch):
    site_packages = tmp_path / "py3.14" / "site-packages"
    origin = site_packages / "extension_helpers" / "__init__.py"
    origin.parent.mkdir(parents=True)
    origin.write_text("", encoding="utf-8")

    class FakeSpec:
        pass

    FakeSpec.origin = str(origin)

    def find_spec(name):
        if name == "extension_helpers":
            return FakeSpec()
        return None

    monkeypatch.setattr(
        "nexus.services.local_heal.env_denoiser.importlib.util.find_spec",
        find_spec,
    )

    denoiser = EnvDenoiser(
        tmp_path,
        run_command=lambda cmd, cwd, timeout: (0, ""),
    )

    assert denoiser.support_site_packages == str(site_packages)


def test_env_denoiser_classifies_compat_python_abi_failure(tmp_path):
    (tmp_path / "setup.py").write_text("print('setup')\n", encoding="utf-8")
    calls = []

    def run_command(cmd, cwd, timeout):
        calls.append(cmd)
        if len(calls) == 1:
            return 1, "ModuleNotFoundError: No module named 'setuptools.dep_util'"
        if len(calls) == 2:
            return 1, "error: incompatible function pointer types"
        return 1, "PyWtbarr_traverse incompatible function pointer types"

    denoiser = EnvDenoiser(
        tmp_path,
        run_command=run_command,
        compat_python_executable="python3.12",
    )

    result = denoiser.prepare_from_evidence(ASTROPY_ENV_FAILURE)

    assert result.succeeded is False
    assert result.reason == "ASTROPY_COMPAT_BUILD_ABI_FAILURE"
    assert result.python_executable == "python3.12"
