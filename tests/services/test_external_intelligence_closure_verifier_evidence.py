"""EIA closure verifier: positive pytest evidence, hardened invocation, minimal env (#2793).

Each test builds a tiny git repository with a base and a candidate commit and runs the
closure's verifier runner against the candidate checkout.  The fake-pass routes from
Issue #2793 (``os._exit(0)`` at import, a module-level skip, ``addopts=--co`` in config,
a root ``pytest.py``) must all be reported as not passed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from nexus.services.external_intelligence_closure import (
    UNIT_VERIFICATION_SCHEMA,
    VERIFIER_DECLARED_TESTS_NOT_PASSED,
    VERIFIER_ENV_ALLOWLIST,
    VERIFIER_EVIDENCE_EXIT_CODE_ONLY,
    VERIFIER_EVIDENCE_PYTEST_JUNIT,
    VERIFIER_JUNIT_MISSING,
    VERIFIER_JUNIT_SKIPPED,
    VERIFIER_ROOT_SHADOWING_REFUSED,
    _root_shadowing_paths,
    _run_verifier_specs,
)

# Set by pytest itself inside the verifier process, not inherited from the daemon.
_PYTEST_RUNTIME_ENV = {"PYTEST_CURRENT_TEST", "PYTEST_VERSION"}
# Injected into every process by macOS CoreFoundation at exec time, not forwarded.
_PLATFORM_ENV = {"__CF_USER_TEXT_ENCODING"} if sys.platform == "darwin" else set()

_BASE_SRC = "VALUE = 1\n"
_TEST_NEEDS_TWO = "from src_mod import VALUE\n\n\ndef test_value():\n    assert VALUE == 2\n"

# A root pytest.py that forges a passing JUnit file at the path pytest was asked to
# write, then exits 0, without running any test.
_FORGING_PYTEST = (
    "import sys\n"
    "for arg in sys.argv:\n"
    "    if arg.startswith('--junitxml='):\n"
    "        open(arg.split('=', 1)[1], 'w').write(\n"
    '            \'<testsuites><testsuite name="pytest" tests="1" failures="0" \'\n'
    '            \'errors="0" skipped="0"><testcase classname="tests.test_mod" \'\n'
    "            'name=\"test_value\"/></testsuite></testsuites>')\n"
    "raise SystemExit(0)\n"
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout.strip()


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _repo(
    tmp_path: Path, candidate: dict[str, str], base: dict[str, str] | None = None
) -> tuple[Path, str, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "nexus-test@example.invalid")
    _git(root, "config", "user.name", "Nexus Test")
    _git(root, "config", "commit.gpgsign", "false")
    _write(root, {"src_mod.py": _BASE_SRC, "tests/test_mod.py": _TEST_NEEDS_TWO, **(base or {})})
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    base_sha = _git(root, "rev-parse", "HEAD")
    _write(root, candidate)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "candidate")
    return root, base_sha, _git(root, "rev-parse", "HEAD")


def _pytest_spec(*args: str, verifier_id: str = "pytest") -> dict:
    return {"id": verifier_id, "argv": [sys.executable, "-m", "pytest", "-q", *args]}


def _verify(
    root: Path, base: str, candidate: str, specs: list[dict], authorized: list[str]
) -> dict:
    return _run_verifier_specs(
        task_id="t-2793",
        unit_id="u-2793",
        workspace_path=str(root),
        candidate_commit=candidate,
        specs=specs,
        schema=UNIT_VERIFICATION_SCHEMA,
        scope="UNIT",
        base_sha=base,
        authorized_paths=authorized,
        deletable_paths=(),
    )


def _row(verification: dict) -> dict:
    assert len(verification["results"]) == 1
    return verification["results"][0]


def test_genuine_passing_pytest_verifier_passes_with_junit_evidence(tmp_path):
    root, base, cand = _repo(tmp_path, {"src_mod.py": "VALUE = 2\n"})
    verification = _verify(root, base, cand, [_pytest_spec("tests/test_mod.py")], ["src_mod.py"])
    row = _row(verification)
    assert row["passed"] is True, row
    assert verification["status"] == "PASS"
    assert row["evidence"] == VERIFIER_EVIDENCE_PYTEST_JUNIT
    assert row["junit"]["present"] is True
    assert row["junit"]["tests"] == 1
    assert row["junit"]["failures"] == row["junit"]["errors"] == row["junit"]["skipped"] == 0
    executed = row["executed_argv"]
    assert executed[:2] == [sys.executable, "-P"]
    for flag in ("-c", "--rootdir", "--confcutdir"):
        assert flag in executed
    assert executed[executed.index("--rootdir") + 1] == str(root.resolve())
    assert executed[executed.index("--confcutdir") + 1] == str(root.resolve())
    assert "no:cacheprovider" in executed
    assert any(part.startswith("--junitxml=<verifier-sandbox>") for part in executed)


def test_genuine_failing_pytest_verifier_fails(tmp_path):
    root, base, cand = _repo(tmp_path, {"src_mod.py": "VALUE = 3\n"})
    verification = _verify(root, base, cand, [_pytest_spec("tests/test_mod.py")], ["src_mod.py"])
    row = _row(verification)
    assert row["passed"] is False
    assert row["returncode"] == 1
    assert row["junit"]["failures"] == 1
    assert verification["status"] == "FAIL"


def test_os_exit_zero_at_import_of_authorized_module_is_not_passed(tmp_path):
    root, base, cand = _repo(tmp_path, {"src_mod.py": "import os\n\nos._exit(0)\n"})
    verification = _verify(root, base, cand, [_pytest_spec("tests/test_mod.py")], ["src_mod.py"])
    row = _row(verification)
    assert row["returncode"] == 0
    assert row["error"] == VERIFIER_JUNIT_MISSING
    assert row["passed"] is False
    assert verification["status"] == "FAIL"


def test_module_level_skip_is_not_passed(tmp_path):
    skipped = (
        "import pytest\n\npytest.skip('not today', allow_module_level=True)\n\n"
        "def test_value():\n    assert False\n"
    )
    # Another (trivially passing) test file keeps pytest's exit code at 0, so only the
    # JUnit evidence shows that the declared tests never ran.
    root, base, cand = _repo(
        tmp_path,
        {
            "tests/test_mod.py": skipped,
            "tests/test_other.py": "def test_trivial():\n    assert True\n",
        },
    )
    spec = _pytest_spec("tests/test_mod.py", "tests/test_other.py")
    row = _row(_verify(root, base, cand, [spec], ["tests"]))
    assert row["returncode"] == 0
    assert row["error"] == VERIFIER_JUNIT_SKIPPED
    assert row["junit"]["skipped"] >= 1
    assert row["passed"] is False


def test_module_level_skip_alone_is_not_passed(tmp_path):
    skipped = "import pytest\n\npytest.skip('not today', allow_module_level=True)\n"
    root, base, cand = _repo(tmp_path, {"tests/test_mod.py": skipped})
    row = _row(_verify(root, base, cand, [_pytest_spec("tests/test_mod.py")], ["tests"]))
    assert row["passed"] is False


def test_module_level_xfail_marker_is_not_passed(tmp_path):
    xfailed = (
        "import pytest\n\npytestmark = pytest.mark.xfail(reason='hide')\n\n"
        "def test_value():\n    assert False\n"
    )
    root, base, cand = _repo(tmp_path, {"tests/test_mod.py": xfailed})
    row = _row(_verify(root, base, cand, [_pytest_spec("tests/test_mod.py")], ["tests"]))
    assert row["returncode"] == 0
    assert row["error"] == VERIFIER_JUNIT_SKIPPED
    assert row["passed"] is False


def test_collect_only_addopts_in_authorized_setup_cfg_is_not_passed(tmp_path):
    root, base, cand = _repo(tmp_path, {"setup.cfg": "[tool:pytest]\naddopts = --co\n"})
    row = _row(
        _verify(root, base, cand, [_pytest_spec("tests/test_mod.py")], ["setup.cfg", "src_mod.py"])
    )
    # The candidate's config is never read: the real (failing) test runs.
    assert row["passed"] is False
    assert row["returncode"] == 1
    assert row["junit"]["failures"] == 1
    assert row["root_shadowing_authorized_paths"] == ["setup.cfg"]
    assert row["root_shadowing_refused_paths"] == []


def test_unauthorized_root_pytest_py_is_refused(tmp_path):
    root, base, cand = _repo(tmp_path, {"pytest.py": _FORGING_PYTEST})
    verification = _verify(root, base, cand, [_pytest_spec("tests/test_mod.py")], ["."])
    row = _row(verification)
    assert row["error"] == VERIFIER_ROOT_SHADOWING_REFUSED
    assert row["passed"] is False
    assert row["returncode"] is None
    assert row["root_shadowing_refused_paths"] == ["pytest.py"]
    assert verification["status"] == "FAIL"


def test_root_shadowing_refusal_applies_to_exit_code_verifiers_too(tmp_path):
    root, base, cand = _repo(tmp_path, {"sitecustomize.py": "X = 1\n"})
    spec = {"id": "noop", "argv": [sys.executable, "-c", "raise SystemExit(0)"]}
    row = _row(_verify(root, base, cand, [spec], ["src_mod.py"]))
    assert row["error"] == VERIFIER_ROOT_SHADOWING_REFUSED
    assert row["passed"] is False


def test_authorized_root_pytest_py_cannot_shadow_pytest(tmp_path):
    root, base, cand = _repo(tmp_path, {"pytest.py": _FORGING_PYTEST})
    row = _row(
        _verify(root, base, cand, [_pytest_spec("tests/test_mod.py")], ["pytest.py", "src_mod.py"])
    )
    # ``python -P`` keeps the cwd off sys.path, so the real pytest runs the failing test.
    assert row["root_shadowing_authorized_paths"] == ["pytest.py"]
    assert row["passed"] is False
    assert row["returncode"] == 1
    assert row["junit"]["failures"] == 1


def test_root_shadowing_paths_only_flag_root_level_files(tmp_path):
    root, base, cand = _repo(
        tmp_path,
        {
            "tests/conftest.py": "",
            "pkg/setup.cfg": "",
            "Conftest.py": "",
            "pytest/__init__.py": "",
            "src_mod.py": "VALUE = 2\n",
        },
    )
    paths, error = _root_shadowing_paths(root, base, cand)
    assert error == ""
    assert paths == ["Conftest.py", "pytest/__init__.py"]


def test_declared_node_ids_must_all_pass(tmp_path):
    two_tests = "def test_one():\n    assert True\n\n\ndef test_two():\n    assert True\n"
    root, base, cand = _repo(tmp_path, {"tests/test_mod.py": two_tests})
    spec = _pytest_spec(
        "tests/test_mod.py::test_one",
        "tests/test_mod.py::test_two",
        "--deselect",
        "tests/test_mod.py::test_one",
    )
    row = _row(_verify(root, base, cand, [spec], ["tests"]))
    assert row["returncode"] == 0
    assert row["error"] == VERIFIER_DECLARED_TESTS_NOT_PASSED
    assert row["junit"]["declared_node_ids_not_passed"] == ["tests/test_mod.py::test_one"]
    assert row["passed"] is False

    ok = _row(_verify(root, base, cand, [_pytest_spec("tests/test_mod.py::test_two")], ["tests"]))
    assert ok["passed"] is True, ok


def test_non_pytest_verifier_is_recorded_as_exit_code_only(tmp_path):
    root, base, cand = _repo(tmp_path, {"src_mod.py": "VALUE = 2\n"})
    spec = {"id": "noop", "argv": [sys.executable, "-c", "raise SystemExit(0)"]}
    row = _row(_verify(root, base, cand, [spec], ["src_mod.py"]))
    assert row["passed"] is True
    assert row["evidence"] == VERIFIER_EVIDENCE_EXIT_CODE_ONLY
    assert row["junit"] is None
    assert row["executed_argv"] == spec["argv"]


def test_pytest_console_script_is_rewritten_to_isolated_interpreter(tmp_path):
    script = Path(sys.executable).parent / "pytest"
    assert script.is_file(), "the test venv must provide the pytest console script"
    root, base, cand = _repo(tmp_path, {"src_mod.py": "VALUE = 2\n"})
    spec = {"id": "console", "argv": [str(script), "-q", "tests/test_mod.py"]}
    row = _row(_verify(root, base, cand, [spec], ["src_mod.py"]))
    assert row["passed"] is True, row
    assert row["executed_argv"][1:4] == ["-P", "-m", "pytest"]


def test_base_pytest_config_is_replicated_without_addopts(tmp_path):
    base_ini = "[pytest]\nasyncio_mode = auto\naddopts = --co --import-mode=importlib\n"
    async_test = (
        "import asyncio\n\nfrom src_mod import VALUE\n\n\n"
        "async def test_value():\n    await asyncio.sleep(0)\n    assert VALUE == 2\n"
    )
    root, base, cand = _repo(
        tmp_path,
        {"src_mod.py": "VALUE = 2\n", "tests/test_mod.py": async_test},
        base={"pytest.ini": base_ini},
    )
    row = _row(
        _verify(root, base, cand, [_pytest_spec("tests/test_mod.py")], ["src_mod.py", "tests"])
    )
    # asyncio_mode comes from the BASE config and pytest-asyncio is loaded explicitly;
    # ``--co`` from addopts is dropped, ``--import-mode`` is kept.
    assert row["passed"] is True, row
    assert row["junit"]["tests"] == 1
    assert "--import-mode=importlib" in row["executed_argv"]
    assert "--co" not in row["executed_argv"]


def test_verifier_env_contains_only_allow_listed_variables(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_fake_2793")
    monkeypatch.setenv("NEXUS_FAKE_SECRET_2793", "secret")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "evil"))
    monkeypatch.setenv("PYTEST_ADDOPTS", "--co")
    exit_dump = tmp_path / "exit-env.json"
    pytest_dump = tmp_path / "pytest-env.json"
    dump_test = (
        "import json\nimport os\n\n\n"
        "def test_dump():\n"
        f"    with open({str(pytest_dump)!r}, 'w') as f:\n"
        "        json.dump(dict(os.environ), f)\n"
    )
    root, base, cand = _repo(tmp_path, {"tests/test_mod.py": dump_test})
    specs = [
        {
            "id": "dump-env",
            "argv": [
                sys.executable,
                "-c",
                "import json, os, sys; json.dump(dict(os.environ), open(sys.argv[1], 'w'))",
                str(exit_dump),
            ],
        },
        _pytest_spec("tests/test_mod.py", verifier_id="dump-env-pytest"),
    ]
    verification = _verify(root, base, cand, specs, ["tests"])
    assert [row["passed"] for row in verification["results"]] == [True, True], verification
    exit_env = json.loads(exit_dump.read_text(encoding="utf-8"))
    pytest_env = json.loads(pytest_dump.read_text(encoding="utf-8"))
    exit_extra = set(exit_env) - VERIFIER_ENV_ALLOWLIST - _PLATFORM_ENV
    pytest_extra = set(pytest_env) - VERIFIER_ENV_ALLOWLIST - _PLATFORM_ENV - _PYTEST_RUNTIME_ENV
    assert exit_extra == set(), exit_extra
    assert pytest_extra == set(), pytest_extra
    for env in (exit_env, pytest_env):
        assert "GH_TOKEN" not in env
        assert "NEXUS_FAKE_SECRET_2793" not in env
        assert "PYTHONPATH" not in env
        assert "PYTEST_ADDOPTS" not in env
        assert env["HOME"] != os.environ.get("HOME")
        assert env["TMPDIR"] != os.environ.get("TMPDIR")
        assert not Path(env["HOME"]).resolve().is_relative_to(root.resolve())
        assert env["PYTHONDONTWRITEBYTECODE"] == "1"
        assert env["NEXUS_BASE_SHA"] == base
        assert env["NEXUS_CANDIDATE_SHA"] == cand
    assert pytest_env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    for row in verification["results"]:
        assert set(row["env_keys"]) <= VERIFIER_ENV_ALLOWLIST
