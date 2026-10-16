"""Characterization tests for the gateway's GitHub observer and Core provenance helpers.

Pins the current behaviour of ``_resolve_github_cli``, ``github_observer_runtime_identity``,
``observe_github_issue``, ``observe_github_repository_default_head``,
``gateway_core_provenance``, ``public_core_provenance``, ``preload_core_transport`` and
``_canonical_remote_matches`` before they move out of ``unified_mcp_gateway.py``
(big-file split G3, Issue #2441).  Every name is read and patched through the gateway
facade, so the tests also prove that facade patches of ``_resolve_github_cli``,
``CANONICAL_SOURCE_ROOT``, ``SERVER_INSTANCE_ID``, ``subprocess.run`` and
``shutil.which`` keep reaching the helpers after the move.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import nexus.orchestrator.canonical_core_transport as transport
from nexus.orchestrator import unified_mcp_gateway as gateway_module

REPO = "James3014/Nexus-new"
HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("NEXUS_GITHUB_CLI", raising=False)
    monkeypatch.delenv("NEXUS_CORE_REPO_ROOT", raising=False)
    saved = dict(gateway_module._core_provenance_cache)
    gateway_module._core_provenance_cache.clear()
    yield
    gateway_module._core_provenance_cache.clear()
    gateway_module._core_provenance_cache.update(saved)


def _executable(tmp_path: Path, name: str = "gh") -> Path:
    path = tmp_path / name
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _fake_cli(monkeypatch: pytest.MonkeyPatch, path: str = "/fake/gh") -> None:
    monkeypatch.setattr(gateway_module, "_resolve_github_cli", lambda: (path, None))


def _record_run(monkeypatch: pytest.MonkeyPatch, respond):
    calls: list[tuple[list[str], dict]] = []

    def fake_run(command, **kwargs):
        calls.append((list(command), kwargs))
        outcome = respond(command)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(gateway_module.subprocess, "run", fake_run)
    return calls


def _completed(command, stdout: str = "", returncode: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


# --- _resolve_github_cli -------------------------------------------------------------


def test_resolver_uses_discovered_cli_when_not_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cli = _executable(tmp_path)
    monkeypatch.setattr(gateway_module.shutil, "which", lambda name: str(cli))
    assert gateway_module._resolve_github_cli() == (str(cli.resolve()), None)


def test_resolver_reports_unresolvable_configured_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("NEXUS_GITHUB_CLI", str(tmp_path / "missing-gh"))
    executable, error = gateway_module._resolve_github_cli()
    assert executable is None
    assert error.startswith("GitHub CLI executable could not be resolved: ")


@pytest.mark.parametrize("kind", ["directory", "not_executable"])
def test_resolver_rejects_non_executable_targets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str
) -> None:
    target = tmp_path / "gh"
    if kind == "directory":
        target.mkdir()
    else:
        target.write_text("#!/bin/sh\n", encoding="utf-8")
        target.chmod(0o644)
    monkeypatch.setenv("NEXUS_GITHUB_CLI", str(target))
    assert gateway_module._resolve_github_cli() == (
        None,
        "GitHub CLI resolved path is not an executable file",
    )


# --- github_observer_runtime_identity ----------------------------------------------


def test_runtime_identity_unavailable_when_resolver_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gateway_module, "_resolve_github_cli", lambda: (None, "nope"))
    assert gateway_module.github_observer_runtime_identity() == {
        "schema": "nexus.github_observer_dependency.v1",
        "ready": False,
        "executable_path": None,
        "executable_sha256": None,
        "failure_code": "GITHUB_OBSERVER_EXECUTABLE_UNAVAILABLE",
    }


def test_runtime_identity_unavailable_when_executable_is_unreadable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = str(tmp_path / "gone")
    _fake_cli(monkeypatch, missing)
    assert gateway_module.github_observer_runtime_identity() == {
        "schema": "nexus.github_observer_dependency.v1",
        "ready": False,
        "executable_path": missing,
        "executable_sha256": None,
        "failure_code": "GITHUB_OBSERVER_EXECUTABLE_UNAVAILABLE",
    }


# --- observe_github_issue ------------------------------------------------------------


def test_issue_observer_default_detail_when_resolver_gives_no_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gateway_module, "_resolve_github_cli", lambda: (None, None))
    assert gateway_module.observe_github_issue(REPO, 7) == {
        "ok": False,
        "blocker": "GITHUB_OBSERVER_EXECUTABLE_UNAVAILABLE",
        "detail": "GitHub CLI executable unavailable",
    }


def test_issue_observer_runs_bounded_command_in_canonical_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fake_cli(monkeypatch)
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", tmp_path)
    calls = _record_run(
        monkeypatch, lambda command: _completed(command, '{"number": 7, "state": "OPEN"}')
    )
    result = gateway_module.observe_github_issue(REPO, 7)
    assert result["ok"] is True
    assert result["issue"] == {"number": 7, "state": "OPEN"}
    assert result["observed_at"].endswith("+00:00")
    assert calls == [
        (
            [
                "/fake/gh",
                "issue",
                "view",
                "7",
                "--repo",
                REPO,
                "--json",
                "number,state,updatedAt,url",
            ],
            {
                "cwd": tmp_path,
                "capture_output": True,
                "text": True,
                "timeout": 5,
                "check": False,
            },
        )
    ]


def test_issue_observer_oserror_is_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_cli(monkeypatch)
    _record_run(monkeypatch, lambda command: OSError("exec format error"))
    assert gateway_module.observe_github_issue(REPO, 7) == {
        "ok": False,
        "blocker": "GITHUB_OBSERVER_EXECUTABLE_UNAVAILABLE",
        "detail": "exec format error",
    }


def test_issue_observer_nonzero_exit_falls_back_to_stdout_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_cli(monkeypatch)
    _record_run(
        monkeypatch, lambda command: _completed(command, " set GH_TOKEN first ", returncode=1)
    )
    assert gateway_module.observe_github_issue(REPO, 7) == {
        "ok": False,
        "blocker": "GITHUB_OBSERVER_AUTH_UNAVAILABLE",
        "detail": "set GH_TOKEN first",
    }


@pytest.mark.parametrize("stdout", ['{"number": 8}', "[7]"])
def test_issue_observer_rejects_identity_mismatch(
    monkeypatch: pytest.MonkeyPatch, stdout: str
) -> None:
    _fake_cli(monkeypatch)
    _record_run(monkeypatch, lambda command: _completed(command, stdout))
    assert gateway_module.observe_github_issue(REPO, 7) == {
        "ok": False,
        "blocker": "GITHUB_OBSERVER_MALFORMED_RESPONSE",
        "detail": "issue identity mismatch",
    }


# --- observe_github_repository_default_head ------------------------------------------


def _api_responder(repo_payload: str, branch_payload: str):
    def respond(command):
        path = command[-1]
        if path == f"repos/{REPO}":
            return _completed(command, repo_payload)
        if path == f"repos/{REPO}/branches/main":
            return _completed(command, branch_payload)
        raise AssertionError(path)

    return respond


def test_default_head_rejects_non_canonical_repository() -> None:
    assert gateway_module.observe_github_repository_default_head("someone/else") == {
        "ok": False,
        "blocker": "MUTATION_ADMISSION_REPOSITORY_NOT_CANONICAL",
        "detail": "someone/else",
    }


def test_default_head_reports_resolver_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway_module, "_resolve_github_cli", lambda: (None, "no gh"))
    assert gateway_module.observe_github_repository_default_head(REPO) == {
        "ok": False,
        "blocker": "GITHUB_OBSERVER_EXECUTABLE_UNAVAILABLE",
        "detail": "no gh",
    }


def test_default_head_observes_repository_then_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fake_cli(monkeypatch)
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", tmp_path)
    calls = _record_run(
        monkeypatch,
        _api_responder(
            f'{{"full_name": "{REPO}", "default_branch": "main"}}',
            f'{{"name": "main", "commit": {{"sha": "{HEAD_SHA}"}}}}',
        ),
    )
    result = gateway_module.observe_github_repository_default_head(REPO)
    observed_at = result.pop("observed_at")
    assert observed_at.endswith("+00:00")
    assert result == {
        "ok": True,
        "repository": REPO,
        "default_branch": "main",
        "head_sha": HEAD_SHA,
    }
    assert [command for command, _ in calls] == [
        ["/fake/gh", "api", f"repos/{REPO}"],
        ["/fake/gh", "api", f"repos/{REPO}/branches/main"],
    ]
    assert all(kwargs["cwd"] == tmp_path and kwargs["timeout"] == 5 for _, kwargs in calls)


@pytest.mark.parametrize(
    ("repo_payload", "branch_payload", "detail"),
    [
        ('{"full_name": "x/y", "default_branch": "main"}', "{}", "repository identity mismatch"),
        (f'{{"full_name": "{REPO}", "default_branch": " "}}', "{}", "default branch missing"),
        (
            f'{{"full_name": "{REPO}", "default_branch": "main"}}',
            f'{{"name": "dev", "commit": {{"sha": "{HEAD_SHA}"}}}}',
            "default branch head identity mismatch",
        ),
        (
            f'{{"full_name": "{REPO}", "default_branch": "main"}}',
            '{"name": "main", "commit": {"sha": "ABC"}}',
            "default branch head identity mismatch",
        ),
        (
            f'{{"full_name": "{REPO}", "default_branch": "main"}}',
            '{"name": "main", "commit": "not-a-mapping"}',
            "default branch head identity mismatch",
        ),
        ("[1]", "{}", "GitHub response must be an object"),
    ],
)
def test_default_head_rejects_malformed_identities(
    monkeypatch: pytest.MonkeyPatch, repo_payload: str, branch_payload: str, detail: str
) -> None:
    _fake_cli(monkeypatch)
    _record_run(monkeypatch, _api_responder(repo_payload, branch_payload))
    assert gateway_module.observe_github_repository_default_head(REPO) == {
        "ok": False,
        "blocker": "GITHUB_OBSERVER_MALFORMED_RESPONSE",
        "detail": detail,
    }


@pytest.mark.parametrize(
    ("outcome", "blocker", "detail"),
    [
        (
            subprocess.TimeoutExpired(cmd=["gh"], timeout=5),
            "GITHUB_OBSERVER_TIMEOUT",
            "Command '['gh']' timed out after 5 seconds",
        ),
        (OSError("boom"), "GITHUB_OBSERVER_EXECUTABLE_UNAVAILABLE", "boom"),
        (
            ("", 1, "please run gh auth login"),
            "GITHUB_OBSERVER_AUTH_UNAVAILABLE",
            "please run gh auth login",
        ),
        (("", 1, "HTTP 502"), "GITHUB_OBSERVER_REQUEST_FAILED", "HTTP 502"),
        (("{oops", 0, ""), "GITHUB_OBSERVER_MALFORMED_RESPONSE", None),
    ],
)
def test_default_head_api_failures_are_typed(
    monkeypatch: pytest.MonkeyPatch, outcome, blocker: str, detail
) -> None:
    _fake_cli(monkeypatch)

    def respond(command):
        if isinstance(outcome, BaseException):
            return outcome
        stdout, returncode, stderr = outcome
        return _completed(command, stdout, returncode, stderr)

    _record_run(monkeypatch, respond)
    result = gateway_module.observe_github_repository_default_head(REPO)
    assert (result["ok"], result["blocker"]) == (False, blocker)
    if detail is not None:
        assert result["detail"] == detail


def test_default_head_branch_lookup_failure_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_cli(monkeypatch)

    def respond(command):
        if command[-1] == f"repos/{REPO}":
            return _completed(command, f'{{"full_name": "{REPO}", "default_branch": "main"}}')
        return _completed(command, "", 1, "HTTP 404: Branch not found")

    _record_run(monkeypatch, respond)
    assert gateway_module.observe_github_repository_default_head(REPO) == {
        "ok": False,
        "blocker": "GITHUB_OBSERVER_REQUEST_FAILED",
        "detail": "HTTP 404: Branch not found",
    }


# --- Core provenance -----------------------------------------------------------------


def test_core_provenance_is_cached_per_process_and_refreshable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def status():
        calls.append(1)
        return {"status": "CORE_REVISION_PINNED", "fail_closed": False, "n": len(calls)}

    monkeypatch.setattr(transport, "core_provenance_status", status)
    monkeypatch.setattr(gateway_module, "SERVER_INSTANCE_ID", "instance-under-test")
    first = gateway_module.gateway_core_provenance()
    assert first == {
        "status": "CORE_REVISION_PINNED",
        "fail_closed": False,
        "n": 1,
        "observed_in_pid": os.getpid(),
        "server_instance_id": "instance-under-test",
    }
    first["status"] = "mutated by caller"
    assert gateway_module.gateway_core_provenance()["n"] == 1
    assert gateway_module.gateway_core_provenance()["status"] == "CORE_REVISION_PINNED"
    assert gateway_module._core_provenance_cache["value"]["n"] == 1
    assert gateway_module.gateway_core_provenance(refresh=True)["n"] == 2
    assert len(calls) == 2


def test_core_provenance_rechecks_after_the_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = iter(range(1, 100))
    monkeypatch.setattr(
        transport, "core_provenance_status", lambda: {"status": "S", "n": next(counter)}
    )
    clock = [1000.0]
    monkeypatch.setattr(gateway_module.time, "monotonic", lambda: clock[0])
    assert gateway_module.gateway_core_provenance()["n"] == 1
    clock[0] += gateway_module.CORE_PROVENANCE_RECHECK_SECONDS - 1
    assert gateway_module.gateway_core_provenance()["n"] == 1
    clock[0] += 1
    assert gateway_module.gateway_core_provenance()["n"] == 2
    assert gateway_module._core_provenance_cache["checked_at"] == clock[0]


def test_core_provenance_probe_failure_is_reported_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode():
        raise ValueError("probe broke")

    monkeypatch.setattr(transport, "core_provenance_status", explode)
    result = gateway_module.gateway_core_provenance(refresh=True)
    assert {key: result[key] for key in ("status", "fail_closed", "reason")} == {
        "status": "CORE_PROVENANCE_PROBE_FAILED",
        "fail_closed": True,
        "reason": "ValueError: probe broke",
    }


def test_public_core_provenance_projects_only_public_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        transport,
        "core_provenance_status",
        lambda: {"status": "S", "fail_closed": False, "path": "/secret", "reason": "x"},
    )
    assert gateway_module._CORE_PROVENANCE_PUBLIC_FIELDS == (
        "status",
        "expected_revision",
        "observed_commit",
        "fail_closed",
        "identity_source",
    )
    assert gateway_module.public_core_provenance() == {
        "status": "S",
        "expected_revision": None,
        "observed_commit": None,
        "fail_closed": False,
        "identity_source": None,
    }


def test_core_provenance_cache_and_lock_identity() -> None:
    assert isinstance(gateway_module._core_provenance_cache, dict)
    with gateway_module._core_provenance_lock:
        assert gateway_module._core_provenance_lock.locked()
    assert gateway_module.CORE_PROVENANCE_RECHECK_SECONDS == 300.0


@pytest.mark.parametrize(("value", "expected"), [("", False), ("  ", False), ("/core", True)])
def test_preload_core_transport_only_with_core_root(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: bool
) -> None:
    monkeypatch.setenv("NEXUS_CORE_REPO_ROOT", value)
    assert gateway_module.preload_core_transport() is expected


# --- _canonical_remote_matches -------------------------------------------------------


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        (f"git@github.com:{REPO}.git", True),
        (f"git@github.com:{REPO}", True),
        (f"git@GitHub.com:{REPO}.git", True),
        ("git@github.com:other/repo.git", False),
        (f"git@gitlab.com:{REPO}.git", False),
        (f"git@github.com/{REPO}.git", False),
        (f"https://github.com/{REPO}.git", True),
        (f" https://github.com/{REPO}/ ", True),
        (f"HTTPS://GITHUB.COM/{REPO}", True),
        (f"http://github.com/{REPO}.git", False),
        (f"https://user@github.com/{REPO}.git", False),
        (f"https://user:pw@github.com/{REPO}.git", False),
        (f"https://github.com/{REPO}.git?x=1", False),
        (f"https://github.com/{REPO}.git#frag", False),
        (f"https://example.com/{REPO}.git", False),
        ("", False),
    ],
)
def test_canonical_remote_matches(origin: str, expected: bool) -> None:
    assert bool(gateway_module._canonical_remote_matches(origin, REPO)) is expected
