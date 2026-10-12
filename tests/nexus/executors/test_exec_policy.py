"""Unit rules for nexus.executors.exec_policy (#1752, #1753)."""

from __future__ import annotations

import os

import pytest

from nexus.executors.exec_policy import (
    FORWARDER_NAMES,
    is_forwarder_executable,
    program_names,
    validate_exec,
)


@pytest.mark.parametrize("name", sorted(FORWARDER_NAMES))
def test_every_forwarder_rejected(name):
    with pytest.raises(ValueError, match="forwarder"):
        validate_exec(f"/usr/bin/{name}", ("x",))


def test_forwarder_match_is_case_and_exe_insensitive():
    assert is_forwarder_executable("BASH.EXE")
    assert is_forwarder_executable("/opt/Nice")
    assert not is_forwarder_executable("/usr/bin/python3")


def test_program_names_include_realpath_of_symlink(tmp_path):
    link = tmp_path / "harmless"
    os.symlink("/bin/sh", link)
    assert "harmless" in program_names(str(link))
    assert is_forwarder_executable(str(link))


def test_dashed_git_builtin_rejected():
    with pytest.raises(ValueError, match="dashed git builtins"):
        validate_exec("/usr/lib/git-core/git-push", ("origin",))


@pytest.mark.parametrize(
    "argv",
    [
        ("-c", "alias.p=push", "p"),
        ("--config-env=a=B", "status"),
        ("--exec-path=/tmp/x", "status"),
        ("--git-dir=/x", "status"),
        ("--work-tree=/x", "status"),
        ("--namespace=x", "status"),
        ("--super-prefix=x", "status"),
        ("-p", "status"),
        ("--paginate", "log"),
        (),
        ("push",),
        ("commit", "-m", "x"),
        ("branch", "-f", "main", "abc"),
        ("update-ref", "refs/heads/main", "abc"),
        ("send-pack", "o"),
        ("cherry-pick", "abc"),
        ("diff", "--ext-diff"),
        ("diff", "--textconv"),
        ("log", "--show-signature"),
        ("show", "--textconv"),
        ("log", "-Ovim"),
        ("grep", "--open-files-in-pager=sh", "x"),
        ("status", "--upload-pack=x"),
        ("status", "--receive-pack=x"),
        ("status", "--exec=x"),
        ("status", "--exec"),
    ],
)
def test_git_rejections(argv):
    with pytest.raises(ValueError, match="cannot invoke"):
        validate_exec("git", argv)


@pytest.mark.parametrize(
    "argv",
    [
        ("status",),
        ("-C", "/tmp", "status"),
        ("-C/tmp", "log", "-1"),
        ("--no-pager", "-P", "--no-optional-locks", "--literal-pathspecs", "diff"),
        ("--no-replace-objects", "show", "HEAD"),
        ("add", "-A"),
        ("rm", "--cached", "f"),
        ("mv", "a", "b"),
        ("restore", "f"),
        ("apply", "--check", "p"),
        ("version",),
    ],
)
def test_git_allowed(argv):
    validate_exec("git", argv)


@pytest.mark.parametrize(
    "argv",
    [
        ("run", "rerun", "1"),
        ("label", "delete", "x"),
        ("gist", "create"),
        ("cache", "delete"),
        ("alias", "set", "a", "b"),
        ("api", "x"),
        ("pr", "merge", "1"),
        ("issue", "comment", "1"),
        ("--repo", "o/r", "pr", "close", "1"),
        (),
    ],
)
def test_gh_rejections(argv):
    with pytest.raises(ValueError, match="cannot invoke"):
        validate_exec("gh", argv)


@pytest.mark.parametrize(
    "argv",
    [
        ("pr", "view", "1"),
        ("pr", "list"),
        ("pr", "diff", "1"),
        ("pr", "checks", "1"),
        ("pr", "status"),
        ("issue", "view", "1"),
        ("issue", "list"),
        ("issue", "status"),
        ("repo", "view"),
        ("run", "view", "1"),
        ("run", "list"),
        ("search", "code", "x"),
        ("status",),
        ("--repo", "o/r", "pr", "view", "1"),
        ("-R", "o/r", "pr", "view", "1"),
        ("--repo=o/r", "pr", "view"),
        ("--hostname", "h", "pr", "list"),
    ],
)
def test_gh_allowed(argv):
    validate_exec("gh", argv)


@pytest.mark.parametrize(
    "flag",
    ["-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls"],
)
def test_find_action_flags_rejected(flag):
    with pytest.raises(ValueError, match="cannot invoke find"):
        validate_exec("find", (".", flag, "x"))


def test_plain_find_and_python_allowed():
    validate_exec("find", (".", "-name", "*.py"))
    validate_exec("python3", ("-c", "print(1)"))


# --- repository-config inspection (#1752, #1753) ---------------------------

import subprocess as _subprocess  # noqa: E402

from nexus.executors.exec_policy import (  # noqa: E402
    assert_git_repo_config_safe,
    git_target_directory,
)

_ISOLATED = {
    **{k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "SYSTEMROOT"}},
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _repo(path, *config):
    path.mkdir(parents=True, exist_ok=True)
    _subprocess.run(["git", "init", "-q", str(path)], check=True, env=_ISOLATED)
    for key, value in config:
        _subprocess.run(["git", "-C", str(path), "config", key, value], check=True, env=_ISOLATED)
    return path


def test_clean_repo_and_non_repo_are_safe(tmp_path):
    assert_git_repo_config_safe(str(_repo(tmp_path / "r")), _ISOLATED)
    plain = tmp_path / "plain"
    plain.mkdir()
    assert_git_repo_config_safe(str(plain), _ISOLATED)


@pytest.mark.parametrize(
    "key",
    [
        "core.fsmonitor",
        "core.pager",
        "core.hooksPath",
        "diff.external",
        "diff.x.command",
        "diff.x.textconv",
        "filter.x.clean",
        "filter.x.smudge",
        "filter.x.process",
        "merge.x.driver",
        "gpg.program",
        "gpg.x.program",
        "log.showSignature",
        "include.path",
        "includeIf.gitdir:/x/.path",
    ],
)
def test_executable_config_keys_refused_without_leaking_value(tmp_path, key):
    repo = _repo(tmp_path / "r", (key, "SECRETVALUE-123"))
    with pytest.raises(ValueError, match="executable drivers") as info:
        assert_git_repo_config_safe(str(repo), _ISOLATED)
    assert "SECRETVALUE-123" not in str(info.value)
    assert key.split(".")[0].lower() in str(info.value).lower()


def test_uninspectable_config_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="could not be inspected"):
        assert_git_repo_config_safe(str(tmp_path), _ISOLATED, "/nonexistent/git")


def test_git_target_directory_applies_c_cumulatively(tmp_path):
    base = str(tmp_path)
    assert git_target_directory(["status"], base) == base
    assert git_target_directory(["-C", "a", "-Cb", "status"], base) == os.path.join(base, "a", "b")
    assert git_target_directory(["-C", "a", "-C", "/abs", "status"], base) == "/abs"


def test_hooks_path_devnull_is_hardening_not_a_driver(tmp_path):
    repo = _repo(tmp_path / "r", ("core.hooksPath", os.devnull))
    assert_git_repo_config_safe(str(repo), _ISOLATED)
