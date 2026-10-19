"""#2650: environment failures in the ultra_review sandbox must not read as regressions,
and a real regression (base pass -> head fail) must still FAIL.

The review tests force the ghost lane on (``os_sandbox_available`` in the service), so on macOS
they run inside the real sandbox-exec profile and on Linux CI they run unconfined; both prove
the labelling rules, and macOS additionally proves git and shasum work under the profile."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

import nexus.engine.sandboxed_lane as lane
from nexus.engine.ultra_review_service import UltraReviewService


def _git(path, *args):
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)


def _init_app_repo(path):
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    (path / "app.py").write_text(
        "def handler(value):\n    return value.strip()\n", encoding="utf-8"
    )
    (path / "helper.py").write_text("def helps():\n    return 1\n", encoding="utf-8")
    (path / "tests").mkdir()
    (path / "tests" / "test_app.py").write_text(
        "from app import handler\n\n\ndef test_handler_strips():\n    assert handler('  a ') == 'a'\n",
        encoding="utf-8",
    )
    (path / "tests" / "test_helper.py").write_text(
        "from helper import helps\n\n\ndef test_helps():\n    assert helps() == 1\n",
        encoding="utf-8",
    )
    _git(path, "add", ".")
    _git(path, "commit", "-qm", "init")


def _allow_ghost_run(monkeypatch):
    monkeypatch.setattr("nexus.engine.ultra_review_service.os_sandbox_available", lambda: True)


def _review(path):
    return UltraReviewService(path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )


def _no_probe_failure(monkeypatch):
    monkeypatch.setattr(UltraReviewService, "_environment_probe", lambda self, root, **kw: [])


def _ghost_findings(payload):
    return {f["rule_id"]: f for f in payload["findings"] if f["lane"] == "ghost_regression"}


# --- 1. git and shasum inside the sandbox ---------------------------------------------------


def test_tool_read_roots_add_shasum_and_the_developer_dir(monkeypatch, tmp_path):
    monkeypatch.setitem(
        lane._DEVELOPER_DIR_PROBE, "developer_dir", ["/Library/Developer/CommandLineTools"]
    )
    roots = lane.tool_read_roots()
    assert "/Library/Developer/CommandLineTools" in roots
    assert ("/usr/bin/shasum" in roots) == os.path.isfile("/usr/bin/shasum")
    # The usual validation still applies: never $HOME, /Users or a temp root.
    assert all(not r.startswith(str(Path.home())) for r in lane.checked_read_roots(roots))


def test_developer_dir_is_accepted_only_under_system_toolchain_prefixes(monkeypatch, tmp_path):
    toolchain = (tmp_path / "CommandLineTools").resolve()
    toolchain.mkdir()
    answers = {"out": ""}

    def fake_run(cmd, **kwargs):
        assert cmd == [lane.XCODE_SELECT, "-p"] and kwargs.get("env") == {}
        return subprocess.CompletedProcess(cmd, 0, stdout=answers["out"] + "\n", stderr="")

    monkeypatch.setattr(lane.sys, "platform", "darwin")
    monkeypatch.setattr(lane, "XCODE_SELECT", sys.executable)
    monkeypatch.setattr(lane.subprocess, "run", fake_run)
    monkeypatch.setattr(lane, "DEVELOPER_DIR_ALLOWED_PREFIXES", (str(toolchain.parent) + "/",))
    for out, expected in (
        (str(toolchain), [str(toolchain)]),
        ("/Users/someone/fake-dev-dir", []),  # outside the allowed prefixes
        (str(toolchain) + "/../x(evil)", []),  # not safe for an SBPL literal
        ("relative/dir", []),
    ):
        lane._DEVELOPER_DIR_PROBE.clear()
        answers["out"] = out
        assert lane.developer_toolchain_read_roots() == expected, out
    lane._DEVELOPER_DIR_PROBE.clear()


def test_review_sandbox_reads_the_toolchain_and_keeps_the_xcrun_cache_inside(tmp_path, monkeypatch):
    monkeypatch.setitem(
        lane._DEVELOPER_DIR_PROBE, "developer_dir", ["/Library/Developer/CommandLineTools"]
    )
    svc = UltraReviewService(tmp_path)
    sandbox = tmp_path / "sb"
    mirror = sandbox / "worktree"
    mirror.mkdir(parents=True)
    svc._bind_sandbox(sandbox_path=sandbox, execution_root=mirror)
    assert "/Library/Developer/CommandLineTools" in svc._sandbox_read_roots()
    profile = svc._sandbox_profile()
    assert '(subpath "/Library/Developer/CommandLineTools")' in profile
    # still no write outside the sandbox
    assert "/Library/Developer" not in profile.split("(allow file-write*", 1)[1].split("\n", 1)[0]
    env = svc._sandbox_env()
    assert env["xcrun_db"].startswith(str(sandbox.resolve()))


def test_new_test_that_uses_git_and_shasum_passes_in_the_review_sandbox(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text(
        "def handler(value):\n    return value.strip()  # x\n", encoding="utf-8"
    )
    with (tmp_path / "tests" / "test_app.py").open("a", encoding="utf-8") as handle:
        handle.write(
            "\n\nimport shutil, subprocess\n\n"
            "def test_git_sees_the_mirror_head():\n"
            "    out = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True)\n"
            "    assert out.returncode == 0, out.stderr\n"
            "    assert len(out.stdout.strip()) == 40\n"
            "    status = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)\n"
            "    assert status.returncode == 0, status.stderr\n\n"
            "def test_shasum_runs(tmp_path):\n"
            "    if shutil.which('shasum') is None:\n"
            "        return\n"
            "    (tmp_path / 'f').write_text('hi')\n"
            "    out = subprocess.run(['shasum', str(tmp_path / 'f')], capture_output=True, text=True)\n"
            "    assert out.returncode == 0, out.stderr\n"
        )
    _allow_ghost_run(monkeypatch)

    payload = _review(tmp_path)

    ghost = payload["ghost_regression"]
    assert payload["status"] == "PASS", payload["findings"]
    assert ghost["failed_tests"] == [] and ghost["inconclusive_env_tests"] == []
    assert ghost["sandbox_git_dir"]["ok"] is True
    assert ghost["sandbox_git_dir"]["restore"]["restored"] is True
    # the mirror's own worktree registration was restored and then removed as before
    assert payload["worktree_cleanup"]["removed"] is True, payload["worktree_cleanup"]
    listed = subprocess.run(
        ["git", "worktree", "list"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert "sandboxes" not in listed


def test_restore_puts_back_the_worktree_git_file_whatever_the_run_left(tmp_path):
    _init_app_repo(tmp_path)
    svc = UltraReviewService(tmp_path)
    svc._git_home = (tmp_path / "gh").resolve()
    svc._git_home.mkdir()
    checkout = tmp_path / "wt"
    _git(tmp_path, "worktree", "add", "--detach", str(checkout), "HEAD")
    original = (checkout / ".git").read_text(encoding="utf-8")

    swap = svc._give_checkout_sandbox_git_dir(checkout, rev="HEAD")
    assert swap["ok"] is True, swap
    git_dir = Path(swap["git_dir"])
    # built by the reviewer outside the reviewed tree, under a fresh random name
    assert tmp_path.resolve() not in git_dir.parents
    assert (checkout / ".git").read_text(encoding="utf-8").strip() == f"gitdir: {git_dir}"
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=checkout, capture_output=True, text=True
    ).stdout
    assert head.strip() == swap["head"]
    # sandboxed code replaced .git with a directory
    (checkout / ".git").unlink()
    (checkout / ".git").mkdir()
    (checkout / ".git" / "config").write_text("[core]\n", encoding="utf-8")

    result = svc._restore_checkout_git_file(checkout, swap)

    assert result["restored"] is True
    assert (checkout / ".git").read_text(encoding="utf-8") == original
    assert not git_dir.exists()
    _git(tmp_path, "worktree", "remove", "--force", str(checkout))


# --- 3. INCONCLUSIVE_ENV, never hiding a real regression -----------------------------------


def test_new_failing_test_when_a_sandbox_probe_fails_is_inconclusive_env(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    with (tmp_path / "tests" / "test_app.py").open("a", encoding="utf-8") as handle:
        handle.write("\n\ndef test_needs_git():\n    assert False, 'git unavailable here'\n")
    _allow_ghost_run(monkeypatch)
    monkeypatch.setattr(
        UltraReviewService, "_environment_probe", lambda self, root, **kw: ["git_version"]
    )

    payload = _review(tmp_path)

    ghost = payload["ghost_regression"]
    assert payload["status"] == "INCONCLUSIVE", payload["findings"]
    assert payload["gate_passed"] is False
    assert ghost["failed_tests"] == []
    assert ghost["inconclusive_env_tests"] == [
        {
            "test": "tests/test_app.py::test_needs_git",
            "reason": "environment_probe_failed:git_version",
        }
    ]
    finding = _ghost_findings(payload)["environment_unavailable"]
    assert (finding["state"], finding["severity"]) == ("INCONCLUSIVE_ENV", "info")


def test_base_pass_head_fail_still_fails_when_a_sandbox_probe_fails(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text("def handler(value):\n    return value\n", encoding="utf-8")
    _allow_ghost_run(monkeypatch)
    monkeypatch.setattr(
        UltraReviewService, "_environment_probe", lambda self, root, **kw: ["git_version"]
    )

    payload = _review(tmp_path)

    assert payload["status"] == "FAIL", payload["findings"]
    assert payload["ghost_regression"]["failed_tests"] == ["tests/test_app.py::test_handler_strips"]
    assert payload["ghost_regression"]["inconclusive_env_tests"] == []


def test_new_test_file_needing_an_uninstalled_dependency_is_inconclusive_env(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["nexus-missing-dependency-2650>=1"]\n'
        # a pytest section, so pytest stops its ini search here (the project root above the
        # sandbox is unreadable inside it)
        "[tool.pytest.ini_options]\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", "pyproject.toml")
    _git(tmp_path, "commit", "-qm", "declare dep")
    (tmp_path / "tests" / "test_extra.py").write_text(
        "import nexus_missing_dependency_2650\n\n\ndef test_extra():\n    assert True\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", "tests/test_extra.py")
    _allow_ghost_run(monkeypatch)
    _no_probe_failure(monkeypatch)

    payload = _review(tmp_path)

    ghost = payload["ghost_regression"]
    assert payload["status"] == "INCONCLUSIVE", payload["findings"]
    assert ghost["failed_tests"] == []
    assert ghost["inconclusive_env_tests"] == [
        {
            "test": "tests/test_extra.py",
            "reason": "dependency_unavailable:nexus_missing_dependency_2650",
        }
    ]


def test_existing_test_file_broken_by_a_deleted_in_tree_module_still_fails(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "helper.py").unlink()  # the change deletes a module an existing test imports
    _allow_ghost_run(monkeypatch)
    _no_probe_failure(monkeypatch)

    payload = _review(tmp_path)

    assert payload["status"] == "FAIL", payload["findings"]
    assert payload["ghost_regression"]["failed_tests"] == ["tests/test_helper.py"]
    assert payload["ghost_regression"]["inconclusive_env_tests"] == []


def test_new_test_importing_a_module_the_change_deleted_still_fails(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "helper.py").unlink()
    (tmp_path / "tests" / "test_uses_helper.py").write_text(
        "from helper import helps\n\n\ndef test_uses():\n    assert helps() == 1\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", "-A")
    _allow_ghost_run(monkeypatch)
    _no_probe_failure(monkeypatch)

    payload = _review(tmp_path)

    assert payload["status"] == "FAIL", payload["findings"]
    assert "tests/test_uses_helper.py" in payload["ghost_regression"]["failed_tests"]
    assert payload["ghost_regression"]["inconclusive_env_tests"] == []


def test_junit_collection_error_modules_reads_the_last_module_not_found():
    junit = (
        b'<?xml version="1.0"?><testsuites><testsuite>'
        b'<testcase classname="" name="tests.test_a"><error message="collection failure">'
        b"ImportError while importing\nE   ModuleNotFoundError: No module named 'langchain_core.x'"
        b"</error></testcase>"
        b'<testcase classname="" name="tests.test_b"><error message="collection failure">'
        b"E   SyntaxError: bad</error></testcase>"
        b'<testcase classname="tests.test_c" name="test_x" file="tests/test_c.py"><failure message="m">'
        b"ModuleNotFoundError: No module named 'other'</failure></testcase>"
        b"</testsuite></testsuites>"
    )
    assert UltraReviewService._junit_collection_error_modules(junit) == {
        "tests/test_a.py": "langchain_core.x"
    }
    assert UltraReviewService._junit_collection_error_modules(b"<!DOCTYPE x>") == {}
    assert UltraReviewService._junit_collection_error_modules(None) == {}


def test_dependency_check_refuses_modules_the_reviewer_can_import_or_either_tree_has(tmp_path):
    _init_app_repo(tmp_path)
    svc = UltraReviewService(tmp_path)
    # not declared anywhere: a forgotten module, never a dependency gap
    assert svc._dependency_unavailable("nexus_missing_dependency_2650", tmp_path, "HEAD") is False
    (tmp_path / "requirements-dev.txt").write_text("app\nhelper\njson\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["Nexus.Missing-Dependency_2650 @ git+https://x"]\n',
        encoding="utf-8",
    )
    assert svc._dependency_unavailable("nexus_missing_dependency_2650", tmp_path, "HEAD") is True
    assert (
        svc._dependency_unavailable("json", tmp_path, "HEAD") is False
    )  # importable by the reviewer
    assert svc._dependency_unavailable("app.sub", tmp_path, "HEAD") is False  # head tree has it
    (tmp_path / "helper.py").unlink()
    assert svc._dependency_unavailable("helper", tmp_path, "HEAD") is False  # base tree has it
    assert svc._dependency_unavailable("bad-name", tmp_path, "HEAD") is False


# --- timeout retry and process-group kill ----------------------------------------------------


def test_head_timeout_is_retried_once_with_a_longer_budget(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text(
        "def handler(value):\n    return value.strip()  # x\n", encoding="utf-8"
    )
    _allow_ghost_run(monkeypatch)
    monkeypatch.setenv("NEXUS_ULTRA_REVIEW_TEST_TIMEOUT_SEC", "40")
    real = lane._run_in_own_process_group
    seen = []

    def first_call_times_out(command, **kwargs):
        seen.append(kwargs["timeout"])
        if len(seen) == 1:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return real(command, **kwargs)

    monkeypatch.setattr(lane, "_run_in_own_process_group", first_call_times_out)

    payload = _review(tmp_path)

    assert seen == [40.0, 80.0]
    assert payload["ghost_regression"]["head_retried_after_timeout"] is True
    assert payload["status"] == "PASS", payload["findings"]


def test_head_timeout_twice_is_inconclusive_timeout(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text(
        "def handler(value):\n    return value.strip()  # x\n", encoding="utf-8"
    )
    _allow_ghost_run(monkeypatch)
    monkeypatch.setenv("NEXUS_ULTRA_REVIEW_TEST_TIMEOUT_SEC", "40")
    seen = []

    def always_times_out(command, **kwargs):
        seen.append(kwargs["timeout"])
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(lane, "_run_in_own_process_group", always_times_out)

    payload = _review(tmp_path)

    assert seen == [40.0, 80.0]
    assert payload["status"] == "INCONCLUSIVE"
    assert _ghost_findings(payload)["regression_test_timeout"]["state"] == "INCONCLUSIVE_TIMEOUT"


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    state = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True
    ).stdout.strip()
    return bool(state) and not state.startswith("Z")


def test_timeout_kills_the_whole_process_group(tmp_path, monkeypatch):
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: False)  # the group kill only
    pid_file = tmp_path / "grandchild.pid"
    script = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(child.pid))\n"
        "time.sleep(120)\n"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        lane.run_confined(
            [sys.executable, "-I", "-c", script],
            cwd=tmp_path,
            confine_roots=(tmp_path,),
            profile=lambda: "",
            env=dict(os.environ),
            timeout=3,
            kill_process_group=True,
        )
    grandchild = int(pid_file.read_text())
    deadline = time.monotonic() + 10
    while _alive(grandchild) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not _alive(grandchild)


def test_run_confined_default_path_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: False)
    calls = []
    real_run = subprocess.run

    def spy(cmd, **kwargs):
        calls.append(kwargs.get("start_new_session"))
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(lane.subprocess, "run", spy)
    done = lane.run_confined(
        [shutil.which("true") or "/usr/bin/true"],
        cwd=tmp_path,
        confine_roots=(tmp_path,),
        profile=lambda: "",
        env=dict(os.environ),
        timeout=10,
    )
    assert done.returncode == 0 and calls == [None]


# --- reviewer repros for PR #2655 (independent review, a9893d67b) ----------------------------


def test_planted_git_dir_config_never_runs_a_filter_outside_the_sandbox(tmp_path, monkeypatch):
    """B1: code under test plants a git dir with a clean filter where the reviewer used to build
    the base git dir, and also writes a filter into the mirror's own git dir. The reviewer's git
    must never execute it (the marker sits outside the sandbox)."""
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text("def handler(value):\n    return value\n", encoding="utf-8")
    marker = tmp_path.parent / (tmp_path.name + "-PWNED")
    plant = (
        "\nimport pathlib, subprocess\n"
        "_wt = pathlib.Path(__file__).resolve().parents[1]\n"
        f"_cfg = '[filter \"evil\"]\\n\\tclean = touch {marker}\\n\\tsmudge = touch {marker}\\n'\n"
        "_targets = [_wt.parent / 'base-git-dir', _wt.parent / 'mirror-git-dir']\n"
        "try:\n"
        "    _gd = subprocess.run(['git', 'rev-parse', '--absolute-git-dir'], cwd=_wt, capture_output=True, text=True).stdout.strip()\n"
        "    if _gd:\n"
        "        _targets.append(pathlib.Path(_gd))\n"
        "except Exception:\n"
        "    pass\n"
        "for _gd in _targets:\n"
        "    try:\n"
        "        (_gd / 'info').mkdir(parents=True, exist_ok=True)\n"
        "        with open(_gd / 'config', 'a') as _fh:\n"
        "            _fh.write(_cfg)\n"
        "        (_gd / 'info' / 'attributes').write_text('* filter=evil\\n')\n"
        "    except Exception:\n"
        "        pass\n"
    )
    with (tmp_path / "tests" / "test_app.py").open("a", encoding="utf-8") as handle:
        handle.write(plant)
    _allow_ghost_run(monkeypatch)

    payload = _review(tmp_path)

    assert payload["status"] == "FAIL", payload["findings"]  # base pass -> head fail still caught
    assert not marker.exists(), "a filter planted by code under review ran outside the sandbox"
    base_git = payload["ghost_regression"]["base_comparison"].get("base_git_dir") or {}
    if base_git.get("ok"):
        assert not Path(base_git["git_dir"]).exists()
        assert Path(base_git["git_dir"]).name.startswith("nexus-ultra-gitdir-")


def test_candidate_rewriting_the_mirror_git_file_cannot_poison_the_probe(tmp_path, monkeypatch):
    """M1: the probes run before candidate code, so a test module that breaks the mirror's
    .git file cannot turn its own new failing test into INCONCLUSIVE_ENV."""
    _init_app_repo(tmp_path)
    (tmp_path / "tests" / "test_new.py").write_text(
        "import pathlib\n"
        "_p = pathlib.Path(__file__).resolve().parents[1] / '.git'\n"
        "try:\n    _p.write_text('gitdir: /nonexistent\\n')\nexcept Exception:\n    pass\n"
        "\n\ndef test_new_behaviour():\n    assert 1 == 2\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", "tests/test_new.py")
    _allow_ghost_run(monkeypatch)

    payload = _review(tmp_path)

    assert payload["status"] == "FAIL", payload["findings"]
    assert payload["ghost_regression"]["failed_tests"] == ["tests/test_new.py::test_new_behaviour"]
    assert payload["ghost_regression"]["inconclusive_env_tests"] == []
    assert payload["ghost_regression"]["environment_probe_failures"] == []


def test_copytree_mirror_new_failing_test_stays_a_regression(tmp_path, monkeypatch):
    """M2: a copytree mirror has no .git by design; the mirror git probe is not applicable
    there, so a new failing test is not excused as INCONCLUSIVE_ENV."""
    _init_app_repo(tmp_path)
    (tmp_path / "tests" / "test_new.py").write_text(
        "def test_new_behaviour():\n    assert 1 == 2\n", encoding="utf-8"
    )
    _git(tmp_path, "add", "tests/test_new.py")
    _allow_ghost_run(monkeypatch)
    monkeypatch.setattr(
        UltraReviewService,
        "_prepare_git_worktree_mirror",
        lambda self, execution_root, **kw: {"strategy": "copytree", "fallback_reason": "forced"},
    )

    payload = _review(tmp_path)

    assert payload["sandbox_mirror"]["strategy"] == "copytree"
    assert "git_rev_parse_mirror" not in payload["ghost_regression"]["environment_probe_failures"]
    assert payload["status"] == "FAIL", payload["findings"]
    assert payload["ghost_regression"]["inconclusive_env_tests"] == []


def test_forgotten_new_module_is_a_regression_not_a_dependency_gap(tmp_path, monkeypatch):
    """M3: a module the author forgot to add (not declared anywhere) stays FAIL."""
    _init_app_repo(tmp_path)
    (tmp_path / "tests" / "test_new.py").write_text(
        "from newpkg_forgot import f\n\n\ndef test_f():\n    assert f() == 1\n", encoding="utf-8"
    )
    _git(tmp_path, "add", "tests/test_new.py")
    _allow_ghost_run(monkeypatch)

    payload = _review(tmp_path)

    assert payload["status"] == "FAIL", payload["findings"]
    assert payload["ghost_regression"]["failed_tests"] == ["tests/test_new.py"]
    assert payload["ghost_regression"]["inconclusive_env_tests"] == []


def test_declared_names_cover_pep621_groups_poetry_requirements_and_namespaces():
    from nexus.engine.ultra_review_service import (
        _declared_names_from_pyproject,
        _declared_names_from_requirements,
    )

    names = _declared_names_from_pyproject(
        '[project]\ndependencies = ["langchain-core==1.5.2"]\n'
        '[project.optional-dependencies]\nx = ["Foo.Bar>=1"]\n'
        '[dependency-groups]\ndev = ["pytest>=9", {include-group = "x"}]\n'
        '[tool.poetry.dependencies]\npython = "^3.11"\nbaz-qux = "*"\n'
        '[tool.repository-intelligence]\ncanonical-namespace = "repository_intelligence"\n'
    )
    assert names == {"langchain_core", "foo_bar", "pytest", "baz_qux", "repository_intelligence"}
    assert _declared_names_from_pyproject("not toml [") == set()
    assert _declared_names_from_requirements(
        "# c\n-r other.txt\nreq-a==1 ; python_version>'3'\n\n"
    ) == {"req_a"}
