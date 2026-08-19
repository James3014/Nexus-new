import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True)


def test_scripts_are_valid_and_modes_are_explicit() -> None:
    result = run(
        "bash",
        "-n",
        "scripts/ops/test_repo.sh",
        "scripts/ops/test_fast.sh",
        "scripts/ops/test_changed.sh",
    )
    assert result.returncode == 0, result.stderr
    unsupported = run("bash", "scripts/ops/test_repo.sh", "unknown")
    assert unsupported.returncode != 0
    assert "unsupported mode" in unsupported.stderr


def test_fast_prints_targets(tmp_path: Path) -> None:
    # Keep this contract test independent of a host uv cache; C3 exercises the
    # real tool in the isolated target.
    fake_uv = tmp_path / "uv"
    python_bin = shlex.quote(sys.executable)
    fake_uv.write_text(
        f'#!/bin/sh\nshift\n[ "$1" = python ] && shift && set -- {python_bin} "$@"\nexec "$@"\n'
    )
    fake_uv.chmod(0o755)
    result = subprocess.run(
        ("bash", "scripts/ops/test_repo.sh", "fast"),
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "NEXUS_TEST_FORCE_UV": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert "selected targets" in result.stdout
    assert "test_web_dom_mapper.py" in result.stdout
    assert "requires browser extra" in result.stdout


def test_changed_missing_path_fails_closed() -> None:
    result = run("bash", "scripts/ops/test_repo.sh", "changed", "tests/does-not-exist.py")
    assert result.returncode != 0
    assert "missing" in result.stderr


def test_full_requires_explicit_escalation() -> None:
    result = run("bash", "scripts/ops/test_repo.sh", "full")
    assert result.returncode != 0
    assert "escalation" in result.stderr


def test_cache_default_is_repo_local_and_explicit_value_is_preserved(tmp_path: Path) -> None:
    fake_uv = tmp_path / "uv"
    observed = tmp_path / "cache.txt"
    fake_uv.write_text(f"#!/bin/sh\nprintf '%s' \"$UV_CACHE_DIR\" > '{observed}'\nexit 0\n")
    fake_uv.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "NEXUS_TEST_FORCE_UV": "1"}
    env.pop("UV_CACHE_DIR", None)
    result = subprocess.run(
        ("bash", "scripts/ops/test_repo.sh", "fast"),
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0
    assert observed.read_text() == str(ROOT / ".tmp/uv-cache")
    env["UV_CACHE_DIR"] = str(tmp_path / "explicit-cache")
    result = subprocess.run(
        ("bash", "scripts/ops/test_repo.sh", "fast"),
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0
    assert observed.read_text() == env["UV_CACHE_DIR"]


def test_lint_rejects_missing_and_option_targets() -> None:
    for target in ("tests/does-not-exist.py", "--no-cache"):
        result = run("bash", "scripts/ops/test_repo.sh", "lint", target)
        assert result.returncode != 0
        assert "existing file" in result.stderr


def test_full_rejects_bad_confirmation() -> None:
    result = run("bash", "scripts/ops/test_repo.sh", "full", "--bad")
    assert result.returncode != 0
    result = subprocess.run(
        ("bash", "scripts/ops/test_repo.sh", "full", "--bad"),
        cwd=ROOT,
        env={**os.environ, "NEXUS_ALLOW_FULL": "1"},
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0


def test_changed_empty_or_missing_selection_fails_closed(tmp_path: Path) -> None:
    fake_uv = tmp_path / "uv"
    fake_uv.write_text(
        "#!/bin/sh\n"
        "shift; shift\n"
        'case "$1" in\n'
        " scripts/ops/select_tests.py) [ \"$UV_MODE\" = empty ] || printf '%s\\n' tests/nope.py ;;\n"
        "esac\n"
    )
    fake_uv.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "NEXUS_TEST_FORCE_UV": "1"}
    for mode in ("empty", "missing"):
        env["UV_MODE"] = mode
        result = subprocess.run(
            ("bash", "scripts/ops/test_repo.sh", "changed", "pyproject.toml"),
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
        )
        assert result.returncode != 0


def test_changed_preserves_pytest_exit_code(tmp_path: Path) -> None:
    fake_uv = tmp_path / "uv"
    fake_uv.write_text(
        "#!/bin/sh\nshift; shift\n"
        "case \"$1\" in scripts/ops/select_tests.py) printf '%s\\n' tests/services/test_policy_gate.py;; *) exit 7;; esac\n"
    )
    fake_uv.chmod(0o755)
    result = subprocess.run(
        ("bash", "scripts/ops/test_repo.sh", "changed", "pyproject.toml"),
        cwd=ROOT,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "NEXUS_TEST_FORCE_UV": "1"},
        text=True,
        capture_output=True,
    )
    assert result.returncode == 7


def test_changed_rejects_multiple_selector_lines(tmp_path: Path) -> None:
    marker = tmp_path / "pytest-called"
    fake_uv = tmp_path / "uv"
    fake_uv.write_text(
        f"#!/bin/sh\nshift; shift\ncase \"$1\" in scripts/ops/select_tests.py) printf '%s\\n%s\\n' tests/services/test_policy_gate.py NOISE;; *) touch '{marker}'; exit 7;; esac\n"
    )
    fake_uv.chmod(0o755)
    result = subprocess.run(
        ("bash", "scripts/ops/test_repo.sh", "changed", "pyproject.toml"),
        cwd=ROOT,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "NEXUS_TEST_FORCE_UV": "1"},
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert not marker.exists()


def test_changed_ignores_optional_browser_target_when_core_selected(tmp_path: Path) -> None:
    fake_uv = tmp_path / "uv"
    recorded_args = tmp_path / "pytest_args.txt"
    fake_uv.write_text(
        "#!/bin/sh\n"
        "shift; shift\n"
        'case "$1" in\n'
        "  scripts/ops/select_tests.py)\n"
        "    printf '%s\\n' 'tests/services tests/core tests/services/test_policy_gate.py'\n"
        "    ;;\n"
        "  *)\n"
        f"    printf '%s\\n' \"$@\" > '{recorded_args}'\n"
        "    exit 0\n"
        "    ;;\n"
        "esac\n"
    )
    fake_uv.chmod(0o755)
    result = subprocess.run(
        ("bash", "scripts/ops/test_repo.sh", "changed", "pyproject.toml"),
        cwd=ROOT,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "NEXUS_TEST_FORCE_UV": "1"},
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert recorded_args.exists()
    pytest_args = recorded_args.read_text().splitlines()
    assert "-m" in pytest_args
    assert "pytest" in pytest_args
    assert "tests/services" in pytest_args
    assert "tests/core" in pytest_args
    assert "tests/services/test_policy_gate.py" in pytest_args
    assert "--ignore=tests/core/test_web_dom_mapper.py" in pytest_args
