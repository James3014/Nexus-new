"""#2665 P6/P7: two more sandbox environment gaps must not read as regressions, and a real
regression (base pass -> head fail) must still FAIL.

P6: ``/usr/share/i18n`` (system iconv tables) is readable, so ``git status`` works in a repo
    with a non-ASCII path; a ``git status`` capability probe runs before candidate code.
P7: a head-failing test with NO base result whose junit failure text carries git's
    missing-object error is INCONCLUSIVE_ENV ``git_history_unavailable`` (never a pass);
    ``python3`` in the sandbox resolves to the reviewer's interpreter.

Like the #2650 tests, review runs force the ghost lane on: on macOS they run inside the real
sandbox-exec profile, on Linux CI unconfined; both prove the labelling rules."""

import os
import subprocess
import sys

import nexus.engine.sandboxed_lane as lane
from nexus.engine.ultra_review_service import UltraReviewService


def _git(path, *args):
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)


def _init_app_repo(path, extra=None):
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    (path / "app.py").write_text(
        "def handler(value):\n    return value.strip()\n", encoding="utf-8"
    )
    (path / "tests").mkdir()
    (path / "tests" / "test_app.py").write_text(
        "from app import handler\n\n\ndef test_handler_strips():\n    assert handler('  a ') == 'a'\n",
        encoding="utf-8",
    )
    for rel, text in (extra or {}).items():
        (path / rel).write_text(text, encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-qm", "init")


def _allow_ghost_run(monkeypatch):
    monkeypatch.setattr("nexus.engine.ultra_review_service.os_sandbox_available", lambda: True)


def _no_probe_failure(monkeypatch):
    monkeypatch.setattr(UltraReviewService, "_environment_probe", lambda self, root, **kw: [])


def _review(path):
    return UltraReviewService(path).run(
        dry_run=False, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )


def _bound(tmp_path):
    svc = UltraReviewService(tmp_path)
    sandbox = tmp_path / "sb"
    mirror = sandbox / "worktree"
    mirror.mkdir(parents=True)
    svc._bind_sandbox(sandbox_path=sandbox, execution_root=mirror)
    return svc, sandbox, mirror


_GIT_MISSING_OBJECT = "fatal: git cat-file: could not get object info"


# --- P6 ---------------------------------------------------------------------------------------


def test_2665_i18n_is_a_read_only_system_subpath_and_nothing_wider(tmp_path):
    svc, sandbox, _ = _bound(tmp_path)
    profile = svc._sandbox_profile()
    roots = svc._sandbox_read_roots()

    assert "/usr/share/i18n" in lane.SANDBOX_SYSTEM_READ_SUBPATHS
    assert ("/usr/share/i18n" in roots) == os.path.exists("/usr/share/i18n")
    # Never the whole of /usr/share, never writable.
    assert '(subpath "/usr/share")' not in profile
    writes = [line for line in profile.splitlines() if "file-write" in line]
    assert writes and not any("/usr/share" in line for line in writes)


def test_2665_git_status_with_non_ascii_path_runs_in_review_sandbox(tmp_path, monkeypatch):
    # The #1890 shape: a tracked non-ASCII file name makes git (precomposeunicode on macOS)
    # open iconv, which needs /usr/share/i18n inside the sandbox.
    _init_app_repo(tmp_path, {"café.txt": "x\n"})
    with (tmp_path / "tests" / "test_app.py").open("a", encoding="utf-8") as handle:
        handle.write(
            "\n\nimport subprocess\n\n"
            "def test_git_status_sees_the_mirror():\n"
            "    out = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)\n"
            "    assert out.returncode == 0, out.stderr\n"
        )
    _allow_ghost_run(monkeypatch)

    payload = _review(tmp_path)

    ghost = payload["ghost_regression"]
    assert payload["status"] == "PASS", payload["findings"]
    assert ghost["failed_tests"] == [] and ghost["inconclusive_env_tests"] == []
    assert "git_status_mirror" not in ghost["environment_probe_failures"]


def test_2665_git_status_probe_runs_only_with_a_mirror_git_dir(tmp_path, monkeypatch):
    svc, _, mirror = _bound(tmp_path)
    seen = []

    def fake_run(self, cmd, **kwargs):
        seen.append(cmd)
        failed = "status" in cmd
        return subprocess.CompletedProcess(cmd, 128 if failed else 0, stdout="", stderr="")

    monkeypatch.setattr(UltraReviewService, "_sandboxed_run", fake_run)

    assert svc._environment_probe(mirror, mirror_git_ok=True) == ["git_status_mirror"]
    status_cmd = next(cmd for cmd in seen if "status" in cmd)
    assert status_cmd[:2] == ["git", "--no-optional-locks"] and status_cmd[-1] == "--porcelain"
    seen.clear()
    assert svc._environment_probe(mirror, mirror_git_ok=False) == []
    assert not any("status" in cmd for cmd in seen)


# --- P7: git history unavailable --------------------------------------------------------------


def test_2665_new_test_failing_on_missing_git_object_is_inconclusive_env(tmp_path, monkeypatch):
    _init_app_repo(tmp_path)
    (tmp_path / "tests" / "test_history.py").write_text(
        f"def test_reads_an_old_commit():\n    raise RuntimeError({_GIT_MISSING_OBJECT!r})\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", "tests/test_history.py")
    _allow_ghost_run(monkeypatch)
    _no_probe_failure(monkeypatch)

    payload = _review(tmp_path)

    ghost = payload["ghost_regression"]
    assert payload["status"] == "INCONCLUSIVE", payload["findings"]
    assert payload["gate_passed"] is False
    assert ghost["failed_tests"] == []
    assert ghost["inconclusive_env_tests"] == [
        {
            "test": "tests/test_history.py::test_reads_an_old_commit",
            "reason": "git_history_unavailable",
        }
    ]


def test_2665_base_pass_head_fail_with_git_signature_still_fails(tmp_path, monkeypatch):
    # Fail-open guard: the message carries a git missing-object line, but the test passes on
    # base, so it is a regression whatever the text says.
    _init_app_repo(tmp_path)
    (tmp_path / "app.py").write_text(
        "def handler(value):\n"
        "    raise RuntimeError('fatal: bad object 1234567890abcdef1234567890abcdef12345678')\n",
        encoding="utf-8",
    )
    _allow_ghost_run(monkeypatch)
    _no_probe_failure(monkeypatch)

    payload = _review(tmp_path)

    assert payload["status"] == "FAIL", payload["findings"]
    assert payload["gate_passed"] is False
    assert payload["ghost_regression"]["failed_tests"] == ["tests/test_app.py::test_handler_strips"]
    assert payload["ghost_regression"]["inconclusive_env_tests"] == []


def test_2665_new_test_with_plain_or_look_alike_failure_stays_a_regression(tmp_path, monkeypatch):
    # No base result, but the failure is not git's error: "bad object" in prose, or a plain
    # assertion, is the change's own failure.
    _init_app_repo(tmp_path)
    (tmp_path / "tests" / "test_new.py").write_text(
        "def test_prose():\n    assert False, 'the parser returned a bad object for shallow input'\n\n\n"
        "def test_plain():\n    assert 1 == 2\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", "tests/test_new.py")
    _allow_ghost_run(monkeypatch)
    _no_probe_failure(monkeypatch)

    payload = _review(tmp_path)

    assert payload["status"] == "FAIL", payload["findings"]
    assert sorted(payload["ghost_regression"]["failed_tests"]) == [
        "tests/test_new.py::test_plain",
        "tests/test_new.py::test_prose",
    ]
    assert payload["ghost_regression"]["inconclusive_env_tests"] == []


def test_2665_junit_failure_texts_use_the_outcome_ids():
    junit = (
        b'<?xml version="1.0"?><testsuites><testsuite>'
        b'<testcase classname="tests.test_a" name="test_x" file="tests/test_a.py">'
        b'<failure message="boom">fatal: bad object abcdef1</failure></testcase>'
        b'<testcase classname="tests.test_a.TestK" name="test_y[p]" file="tests/test_a.py">'
        b'<error message="e">trace</error></testcase>'
        b'<testcase classname="tests.test_a" name="test_ok" file="tests/test_a.py"/>'
        b"</testsuite></testsuites>"
    )
    texts = UltraReviewService._junit_failure_texts(junit)
    outcomes = UltraReviewService._junit_outcomes_from_bytes(junit)

    assert set(texts) == {k for k, v in outcomes.items() if v == "failed"}
    assert "fatal: bad object abcdef1" in texts["tests/test_a.py::test_x"]
    assert "trace" in texts["tests/test_a.py::TestK::test_y[p]"]
    assert UltraReviewService._junit_failure_texts(b"<!DOCTYPE x><a/>") == {}
    assert UltraReviewService._junit_failure_texts(None) == {}


# --- P7: python3 resolves to the reviewer's interpreter ----------------------------------------


def test_2665_sandbox_path_starts_with_the_reviewer_interpreter(tmp_path, monkeypatch):
    svc, _, _ = _bound(tmp_path)
    interpreter_bin = os.path.dirname(sys.executable)

    path = svc._sandbox_env()["PATH"].split(os.pathsep)

    assert path[0] == interpreter_bin
    assert path.count(interpreter_bin) == 1


def test_2665_interpreter_inside_the_reviewed_tree_is_not_put_on_path(tmp_path, monkeypatch):
    svc, _, _ = _bound(tmp_path)
    planted = tmp_path / ".venv" / "bin"
    planted.mkdir(parents=True)
    monkeypatch.setattr(sys, "executable", str(planted / "python"))

    path = svc._sandbox_env()["PATH"].split(os.pathsep)

    assert str(planted) not in path
    assert not any(part.startswith(str(tmp_path.resolve())) for part in path)


# --- SBPL paths with a space (live Gateway root: ~/Library/Application Support/...) -------------


def test_2665_sbpl_path_accepts_a_space_and_the_profile_quotes_it(tmp_path):
    spaced = tmp_path / "Application Support" / "Nexus"
    spaced.mkdir(parents=True)
    resolved = lane.sbpl_path(spaced)

    assert resolved == str(spaced.resolve()) and " " in resolved
    profile = lane.build_sandbox_profile(writable=[resolved], read_roots=[resolved])
    # One whole quoted literal per use; the space never splits it.
    assert f'(subpath "{resolved}")' in profile
    assert profile.count('"') % 2 == 0


def test_2665_sbpl_path_still_rejects_quote_backslash_control_and_non_ascii(tmp_path):
    import pytest

    for bad in (
        tmp_path / 'Application "Support"',
        tmp_path / "back\\slash",
        tmp_path / "new\nline",
        tmp_path / "tab\tname",
        tmp_path / "par(en)",
        tmp_path / "café",
        tmp_path / 'x") (allow default) ("',
    ):
        with pytest.raises(lane.SandboxError, match="sandbox_path_unsafe_for_policy"):
            lane.sbpl_path(bad)
    # ``..`` never reaches the policy: the path is resolved first.
    dotted = lane.sbpl_path(f"{tmp_path}/Application Support/../x")
    assert ".." not in dotted.split("/")


def test_2665_review_runs_from_a_directory_whose_path_has_a_space(tmp_path, monkeypatch):
    # The live-deployment shape: before #2665 every run was BLOCKED sandbox_path_unsafe_for_policy
    # with no lane executed. On macOS this runs inside the real sandbox-exec profile.
    repo = tmp_path / "Application Support" / "repo"
    repo.mkdir(parents=True)
    _init_app_repo(repo)
    (repo / "app.py").write_text(
        "def handler(value):\n    return value.strip()  # x\n", encoding="utf-8"
    )
    _allow_ghost_run(monkeypatch)

    payload = _review(repo)

    assert "unsafe_for_policy" not in str(payload.get("blocked_reason"))
    assert payload["status"] == "PASS", (payload.get("blocked_reason"), payload["findings"])
    assert payload["ghost_regression"]["executed_tests"] == ["tests/test_app.py"]
    assert payload["security_sentry"]["executed_checks"]


def _pythonpath_entries(argv):
    import shlex

    value = next(arg for arg in argv if arg.startswith("pythonpath="))
    return shlex.split(value[len("pythonpath=") :])  # how pytest reads a ``paths`` ini value


def test_2665_pythonpath_override_keeps_a_spaced_root_whole(tmp_path):
    from nexus.committee import execution_verifier as ev

    root = tmp_path / "Application Support" / "worktree"
    root.mkdir(parents=True)
    ghost = UltraReviewService._ghost_pytest_cmd(
        root, ["tests/test_app.py"], root / "j.xml", root / "w.json"
    )
    committee = ev.build_argv(
        ev.parse_command(["python3", "-m", "pytest", "-q"]), mirror=root, interpreter=sys.executable
    )

    assert _pythonpath_entries(ghost) == [str(root.resolve())]
    assert _pythonpath_entries(committee) == [str(root.resolve())]
