from types import SimpleNamespace

from nexus.services.local_heal.env_resolver import (
    EnvResolver,
    apply_env_resolution,
    requirement_for_profile,
)


def test_astropy_legacy_env_blocks_without_version_parity_python():
    resolver = EnvResolver(which=lambda candidate: None, uv_find=lambda candidate: None)

    resolution = resolver.resolve(requirement_for_profile("astropy-legacy"))

    assert resolution.ready is False
    assert resolution.reason == "ASTROPY_VERSION_PARITY_MISSING"
    assert resolution.python_executable == ""
    assert [probe["candidate"] for probe in resolution.probes] == [
        ".venv_astropy_39/bin/python",
        ".venv_astropy/bin/python",
        "python3.9",
        "python3.10",
    ]


def test_astropy_legacy_env_accepts_python39():
    resolver = EnvResolver(
        which=lambda candidate: "/opt/python3.9" if candidate == "python3.9" else None,
        uv_find=lambda candidate: None,
        version_probe=lambda executable: "3.9.10",
        import_probe=lambda executable, imports: (True, ""),
        attribute_probe=lambda executable, attrs: (True, "ok"),
        package_version_probe=lambda executable, package_name: "1.24.0",
    )

    resolution = resolver.resolve(requirement_for_profile("astropy-legacy"))

    assert resolution.ready is True
    assert resolution.reason == "READY"
    assert resolution.python_executable == "/opt/python3.9"
    accepted_probe = next(probe for probe in resolution.probes if probe["status"] == "accepted")
    assert accepted_probe["version"] == "3.9.10"


def test_astropy_legacy_env_rejects_wrong_minor_version():
    resolver = EnvResolver(
        which=lambda candidate: "/opt/python3.12" if candidate == "python3.12" else None,
        version_probe=lambda executable: "3.12.8",
    )
    requirement = requirement_for_profile("astropy-legacy").with_python_candidates(("python3.12",))

    resolution = resolver.resolve(requirement)

    assert resolution.ready is False
    assert resolution.reason == "ASTROPY_VERSION_PARITY_MISSING"
    assert resolution.probes[0]["status"] == "unsupported_version"


def test_astropy_legacy_env_blocks_missing_required_imports():
    resolver = EnvResolver(
        which=lambda candidate: "/opt/python3.10" if candidate == "python3.10" else None,
        uv_find=lambda candidate: None,
        version_probe=lambda executable: "3.10.19",
        import_probe=lambda executable, imports: (False, "missing:numpy"),
    )

    resolution = resolver.resolve(requirement_for_profile("astropy-legacy"))

    assert resolution.ready is False
    assert resolution.reason == "ASTROPY_DEPENDENCY_MISSING"
    failed_probe = next(probe for probe in resolution.probes if probe["status"] == "missing_imports")
    assert failed_probe["import_status"] == "missing:numpy"


def test_astropy_legacy_env_blocks_missing_required_stdlib_attribute():
    resolver = EnvResolver(
        which=lambda candidate: "/opt/python3.9" if candidate == "python3.9" else None,
        uv_find=lambda candidate: None,
        version_probe=lambda executable: "3.9.24",
        import_probe=lambda executable, imports: (True, "ok"),
        attribute_probe=lambda executable, attrs: (
            False,
            "missing_attr:importlib.metadata.packages_distributions",
        ),
    )

    resolution = resolver.resolve(requirement_for_profile("astropy-legacy"))

    assert resolution.ready is False
    assert resolution.reason == "ASTROPY_DEPENDENCY_MISSING"
    failed_probe = next(probe for probe in resolution.probes if probe["status"] == "missing_imports")
    assert "packages_distributions" in failed_probe["import_status"]


def test_astropy_legacy_env_uses_env_override(monkeypatch):
    monkeypatch.setenv("NEXUS_ASTROPY_LEGACY_PYTHON", "/opt/python3.10")
    resolver = EnvResolver(
        which=lambda candidate: None,
        uv_find=lambda candidate: None,
        version_probe=lambda executable: "3.10.19",
        import_probe=lambda executable, imports: (True, ""),
        attribute_probe=lambda executable, attrs: (True, "ok"),
        package_version_probe=lambda executable, package_name: "1.24.0",
    )

    resolution = resolver.resolve(requirement_for_profile("astropy-legacy"))

    assert resolution.ready is True
    assert resolution.python_executable == "/opt/python3.10"
    assert resolution.probes[0]["candidate"] == "NEXUS_ASTROPY_LEGACY_PYTHON"


def test_apply_env_resolution_sets_blocked_context_receipt_fields():
    ctx = SimpleNamespace(
        runner_completed=False,
        solve_eligible=True,
        reproduced=True,
        failure_reason="",
    )
    resolution = EnvResolver(
        which=lambda candidate: None,
        uv_find=lambda candidate: None,
    ).resolve(requirement_for_profile("astropy-legacy"))

    should_continue = apply_env_resolution(ctx, resolution)

    assert should_continue is False
    assert ctx.runner_completed is True
    assert ctx.solve_eligible is False
    assert ctx.reproduced is False
    assert ctx.failure_reason == "ASTROPY_VERSION_PARITY_MISSING"
    assert ctx.env_resolution["ready"] is False


def test_apply_env_resolution_sets_ready_python_executable():
    ctx = SimpleNamespace(python_executable="", env_resolution={})
    resolution = EnvResolver(
        which=lambda candidate: "/opt/python3.9" if candidate == "python3.9" else None,
        uv_find=lambda candidate: None,
        version_probe=lambda executable: "3.9.10",
        import_probe=lambda executable, imports: (True, ""),
        attribute_probe=lambda executable, attrs: (True, "ok"),
        package_version_probe=lambda executable, package_name: "1.24.0",
    ).resolve(requirement_for_profile("astropy-legacy"))

    should_continue = apply_env_resolution(ctx, resolution)

    assert should_continue is True
    assert ctx.python_executable == "/opt/python3.9"
    assert ctx.env_resolution["reason"] == "READY"
