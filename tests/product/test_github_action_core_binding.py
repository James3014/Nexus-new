"""Focused execution tests for the canonical Core Action binding shell."""

from __future__ import annotations

import base64
import csv
import hashlib
import os
import shutil
import subprocess
import sysconfig
import venv
from pathlib import Path

import pytest

ACTION_FILE = Path(__file__).parents[2] / ".github/actions/nexus-certify/action.yml"


def _run_script() -> str:
    lines = ACTION_FILE.read_text(encoding="utf-8").splitlines()
    start = lines.index("      run: |") + 1
    body: list[str] = []
    for line in lines[start:]:
        if line and not line.startswith("        "):
            break
        body.append(line[8:] if line else "")
    return "\n".join(body) + "\n"


def _record_digest(path: Path) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest()).rstrip(b"=").decode()
    )


@pytest.fixture
def action_fixture(tmp_path: Path) -> dict[str, Path]:
    venv_dir = tmp_path / "core-venv"
    venv.EnvBuilder(with_pip=False, clear=True, symlinks=False).create(venv_dir)
    # The managed macOS Python binary resolves libpython relative to the venv
    # executable; provide that runtime library in this disposable fixture.
    runtime_lib_name = sysconfig.get_config_var("LDLIBRARY")
    runtime_lib_dir = sysconfig.get_config_var("LIBDIR")
    runtime_lib = (
        Path(runtime_lib_dir) / str(runtime_lib_name)
        if runtime_lib_dir and runtime_lib_name
        else None
    )
    if runtime_lib and runtime_lib.is_file():
        fixture_lib = venv_dir / "lib" / runtime_lib.name
        if not fixture_lib.exists():
            fixture_lib.symlink_to(runtime_lib)
    python = venv_dir / "bin/python"
    site = next((venv_dir / "lib").glob("python*/site-packages"))
    source_product = Path(__file__).parents[2] / "product"
    shutil.copytree(source_product, site / "product")
    # Keep this fixture focused on the entrypoint: replace the runtime package
    # with stdlib-only dependency stubs so import reaches the Action guard
    # without pretending to provide canonical runtime semantics.
    shutil.rmtree(site / "product/runtime")
    (site / "product/runtime").mkdir()
    (site / "product/runtime/__init__.py").write_text("", encoding="utf-8")
    (site / "product/runtime/schemas.py").write_text(
        "def validate_certification_request(payload):\n    return []\n",
        encoding="utf-8",
    )
    (site / "product/clients/__init__.py").write_text("", encoding="utf-8")
    (site / "product/clients/cli.py").write_text(
        """def _get_token(path):
    return "fixture-token"
def _make_http_request(**kwargs):
    return 200, {}
def _map_http_status_to_exit_code(status_code, payload):
    return 0
def main(argv=None):
    return 0
""",
        encoding="utf-8",
    )
    # The Action's installed client imports auth, whose middleware annotations
    # require only the small ``aiohttp.web`` surface below.  The real Action
    # denial occurs before transport, so keep this fixture dependency-free.
    aiohttp = site / "aiohttp"
    aiohttp.mkdir()
    (aiohttp / "__init__.py").write_text(
        """class _Web:
    Request = object
    Response = object
    @staticmethod
    def middleware(fn):
        return fn
    @staticmethod
    def json_response(body, status=200):
        return (body, status)
web = _Web()
""",
        encoding="utf-8",
    )
    action_module = site / "product/clients/github_action.py"
    dist = site / "nexus_core-0.1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: nexus-core\nVersion: 0.1.0\n", encoding="utf-8"
    )
    (dist / "WHEEL").write_text("Wheel-Version: 1.0\n", encoding="utf-8")
    (dist / "top_level.txt").write_text("product\n", encoding="utf-8")
    rows = [
        [
            "product/clients/github_action.py",
            f"sha256={_record_digest(action_module)}",
            str(action_module.stat().st_size),
        ],
        ["nexus_core-0.1.0.dist-info/METADATA", "", str((dist / "METADATA").stat().st_size)],
        ["nexus_core-0.1.0.dist-info/WHEEL", "", str((dist / "WHEEL").stat().st_size)],
        [
            "nexus_core-0.1.0.dist-info/top_level.txt",
            "",
            str((dist / "top_level.txt").stat().st_size),
        ],
        ["nexus_core-0.1.0.dist-info/RECORD", "", ""],
    ]
    with (dist / "RECORD").open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)
    return {"python": python, "site": site, "dist": dist, "module": action_module}


def _invoke(
    fixture: dict[str, Path],
    tmp_path: Path,
    *,
    core_python: str,
    runner: str = "self-hosted",
    service_url: str = "http://127.0.0.1:8767",
    cwd: Path | None = None,
    shadow: bool = False,
    unset_core: bool = False,
    request_file: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.update({
        "CORE_PYTHON": core_python,
        "REQUEST_FILE": str(request_file or (tmp_path / "missing-request.json")),
        "SERVICE_URL": service_url,
        "TOKEN_FILE": str(tmp_path / "missing-token"),
        "RUNNER_ENVIRONMENT": runner,
    })
    if shadow:
        shadow_dir = tmp_path / "shadow"
        (shadow_dir / "product/clients").mkdir(parents=True)
        (shadow_dir / "product/__init__.py").write_text(
            "raise RuntimeError('shadowed')\n", encoding="utf-8"
        )
        env["PYTHONPATH"] = str(shadow_dir)
        cwd = shadow_dir
    if unset_core:
        env.pop("CORE_PYTHON", None)
    return subprocess.run(
        ["bash", "-c", _run_script()],
        cwd=str(cwd or tmp_path),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_missing_relative_directory_and_nonexec_core_python_fail_closed(action_fixture, tmp_path):
    cases = [
        ("", "CORE_PYTHON must be an absolute path"),
        ("relative/python", "CORE_PYTHON must be an absolute path"),
        (str(tmp_path), "CORE_PYTHON must be an executable regular file"),
    ]
    nonexec = tmp_path / "nonexec-python"
    nonexec.write_text("#!/bin/sh\n", encoding="utf-8")
    nonexec.chmod(0o600)
    cases.append((str(nonexec), "CORE_PYTHON must be an executable regular file"))
    for value, message in cases:
        result = _invoke(action_fixture, tmp_path, core_python=value)
        assert result.returncode == 78
        assert message in result.stderr
    result = _invoke(action_fixture, tmp_path, core_python="", unset_core=True)
    assert result.returncode == 78
    assert "CORE_PYTHON must be an absolute path" in result.stderr


def test_absent_distribution_fails_closed(action_fixture, tmp_path):
    shutil.rmtree(action_fixture["dist"])
    result = _invoke(action_fixture, tmp_path, core_python=str(action_fixture["python"]))
    assert result.returncode == 78
    assert "nexus-core distribution is not installed" in result.stderr


@pytest.mark.parametrize("owner_name", ["nexus-legacy", "other-package"])
def test_wrong_or_legacy_distribution_ownership_fails_closed(action_fixture, tmp_path, owner_name):
    dist = action_fixture["site"] / f"{owner_name.replace('-', '_')}-1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text(f"Name: {owner_name}\nVersion: 1.0\n", encoding="utf-8")
    (dist / "top_level.txt").write_text("product\n", encoding="utf-8")
    (dist / "RECORD").write_text("", encoding="utf-8")
    result = _invoke(action_fixture, tmp_path, core_python=str(action_fixture["python"]))
    assert result.returncode == 78
    assert (
        "co-install" in result.stderr or "invalid product distribution ownership" in result.stderr
    )


def test_tampered_record_and_module_fail_before_action_execution(action_fixture, tmp_path):
    record = action_fixture["dist"] / "RECORD"
    original = record.read_text(encoding="utf-8")
    record.write_text(original.replace("sha256=", "sha256=wrong", 1), encoding="utf-8")
    result = _invoke(action_fixture, tmp_path, core_python=str(action_fixture["python"]))
    assert result.returncode == 78
    assert "RECORD" in result.stderr or "hash" in result.stderr

    record.write_text(original, encoding="utf-8")
    marker = tmp_path / "imported-marker"
    action_fixture["module"].write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\n",
        encoding="utf-8",
    )
    compile(action_fixture["module"].read_text(), str(action_fixture["module"]), "exec")
    result = _invoke(action_fixture, tmp_path, core_python=str(action_fixture["python"]))
    assert result.returncode == 78
    assert "hash" in result.stderr
    assert not marker.exists()


def test_module_origin_mismatch_fails_before_shadow_import(action_fixture, tmp_path):
    shadow = tmp_path / "origin-shadow"
    shadow_module = shadow / "product/clients/github_action.py"
    shadow_module.parent.mkdir(parents=True)
    marker = tmp_path / "origin-marker"
    shadow_module.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\n",
        encoding="utf-8",
    )
    (shadow / "product/__init__.py").write_text("", encoding="utf-8")
    (shadow / "product/clients/__init__.py").write_text("", encoding="utf-8")
    (action_fixture["site"] / "00-origin-shadow.pth").write_text(
        f"import sys; sys.path.insert(0, {str(shadow)!r})\n", encoding="utf-8"
    )
    compile(shadow_module.read_text(), str(shadow_module), "exec")
    result = _invoke(action_fixture, tmp_path, core_python=str(action_fixture["python"]))
    assert result.returncode == 78
    assert "path mismatch" in result.stderr
    assert not marker.exists()


def test_action_paths_are_quoted_against_shell_metacharacters(action_fixture, tmp_path):
    result = _invoke(
        action_fixture,
        tmp_path,
        core_python=str(action_fixture["python"]),
        runner="self-hosted",
        request_file=tmp_path / "request; touch SHOULD_NOT_EXIST.json",
    )
    assert result.returncode == 2
    assert "request file not found" in result.stderr
    assert not (tmp_path / "SHOULD_NOT_EXIST.json").exists()


def test_cwd_and_pythonpath_shadowing_are_ignored_by_isolated_execution(action_fixture, tmp_path):
    result = _invoke(
        action_fixture,
        tmp_path,
        core_python=str(action_fixture["python"]),
        cwd=tmp_path,
        shadow=True,
    )
    assert result.returncode == 2
    assert "request file not found" in result.stderr
    assert "shadowed" not in result.stderr


def test_supported_binding_reaches_canonical_action_and_preserves_denial(action_fixture, tmp_path):
    result = _invoke(
        action_fixture,
        tmp_path,
        core_python=str(action_fixture["python"]),
        runner="hosted",
    )
    assert result.returncode == 78
    assert "HOSTED_RUNNER_FORBIDDEN" in result.stderr

    result = _invoke(
        action_fixture,
        tmp_path,
        core_python=str(action_fixture["python"]),
        runner="self-hosted",
    )
    assert result.returncode == 2
    assert "request file not found" in result.stderr
