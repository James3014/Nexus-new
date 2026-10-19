"""Hermetic tests for the health-gated Gateway auto-deployer (#2153).

Every process, launchd and network effect goes through fakes; nothing here
touches a real Gateway, LaunchAgent or GitHub.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import dataclasses
import hashlib
import http.server
import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import threading
import urllib.parse
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator

import pytest

from nexus.contracts import gateway_deployment as contract
from scripts.ops import check_gateway_source_drift as drift
from scripts.ops import nexus_gateway_auto_deploy as ad
from scripts.ops.gateway_health_hmac import KEY_FILE_ENV, load_or_create_key, path_hmac

OLD = "a" * 40
NEW = "b" * 40
PR_HEAD = "c" * 40
REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = 1_760_000_000.0
NOW_ISO = "2025-10-09T08:53:20Z"  # == NOW


GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_TERMINAL_PROMPT": "0",
}


def _fixture_git(cwd: Path, *args: str) -> str:
    env = {**os.environ, **GIT_ENV}
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


# Minimal stand-in for nexus-core's product/protocol/build_identity.py: the same
# public functions and digest rule, with "shipped" simplified to every *.py
# outside __pycache__.  The real module is exercised by the opt-in real-Core
# test below.
FIXTURE_BUILD_IDENTITY = """
import hashlib, os
from pathlib import Path


def _shipped(rel):
    return rel.startswith("product/") and rel.endswith(".py") and "__pycache__" not in rel


def select_shipped_paths(paths):
    return sorted((p for p in paths if _shipped(p)), key=lambda p: p.encode("utf-8"))


def source_digest_of_files(files):
    manifest = hashlib.sha256()
    for path, data in sorted(files, key=lambda item: item[0].encode("utf-8")):
        manifest.update(hashlib.sha256(data).hexdigest().encode("ascii"))
        manifest.update(b"  " + path.encode("utf-8") + b"\\n")
    return "sha256:" + manifest.hexdigest()


def source_digest(package_root):
    root = Path(package_root)
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in filenames:
            rel = "product/" + Path(dirpath, name).relative_to(root).as_posix()
            if _shipped(rel):
                found.append((rel, Path(dirpath, name).read_bytes()))
    return source_digest_of_files(found)
"""


class CoreOrigin:
    """A local stand-in for James3014/nexus-core (no network in these tests)."""

    path: Path
    pin: str
    other: str


CORE = CoreOrigin()


@pytest.fixture(autouse=True, scope="session")
def _core_origin(tmp_path_factory: pytest.TempPathFactory) -> None:
    repo = tmp_path_factory.mktemp("nexus-core-origin")
    _fixture_git(repo, "init", "-q", "-b", "main")
    (repo / "product").mkdir()
    (repo / "product" / "__init__.py").write_text("")
    (repo / ".gitignore").write_text("__pycache__/\n*.pyc\n")
    _fixture_git(repo, "add", ".")
    _fixture_git(repo, "commit", "-q", "-m", "core one")
    CORE.other = _fixture_git(repo, "rev-parse", "HEAD")
    (repo / "product" / "two.py").write_text("")
    # The pin ships Core's build_identity leaf module (#2246); "other" predates it.
    (repo / "product" / "protocol").mkdir()
    (repo / "product" / "protocol" / "__init__.py").write_text("")
    (repo / "product" / "protocol" / "build_identity.py").write_text(FIXTURE_BUILD_IDENTITY)
    _fixture_git(repo, "add", ".")
    _fixture_git(repo, "commit", "-q", "-m", "core two")
    CORE.path, CORE.pin = repo, _fixture_git(repo, "rev-parse", "HEAD")


class RieOrigin:
    """A local stand-in for James3014/repository-intelligence-engine (#1579)."""

    path: Path
    pin: str
    broken: str
    writer: str


RIE = RieOrigin()


@pytest.fixture(autouse=True, scope="session")
def _rie_origin(tmp_path_factory: pytest.TempPathFactory) -> None:
    repo = tmp_path_factory.mktemp("rie-origin")
    _fixture_git(repo, "init", "-q", "-b", "main")
    (repo / "repository_intelligence").mkdir()
    (repo / "repository_intelligence" / "__init__.py").write_text("")
    (repo / "repository_intelligence" / "cli.py").write_text("raise SystemExit('broken engine')\n")
    (repo / ".gitignore").write_text("__pycache__/\n*.pyc\n")
    _fixture_git(repo, "add", ".")
    _fixture_git(repo, "commit", "-q", "-m", "rie broken")
    RIE.broken = _fixture_git(repo, "rev-parse", "HEAD")
    (repo / "repository_intelligence" / "cli.py").write_text("def main():\n    return 0\n")
    _fixture_git(repo, "add", ".")
    _fixture_git(repo, "commit", "-q", "-m", "rie engine")
    RIE.path, RIE.pin = repo, _fixture_git(repo, "rev-parse", "HEAD")
    # An engine that writes into its own checkout when imported.
    (repo / "repository_intelligence" / "cli.py").write_text(
        "from pathlib import Path\n"
        "Path(__file__).with_name('written.txt').write_text('x')\n"
        "def main():\n    return 0\n"
    )
    _fixture_git(repo, "add", ".")
    _fixture_git(repo, "commit", "-q", "-m", "rie writer")
    RIE.writer = _fixture_git(repo, "rev-parse", "HEAD")


def _rie_pin_source(revision: str) -> str:
    return f'"""rie"""\n\nPINNED_RIE_ENGINE_REVISION = "{revision}"\nOTHER = 1\n'


def _pin_source(revision: str) -> str:
    return f'"""transport"""\n\nCANONICAL_CORE_REVISION = "{revision}"\nOTHER = 1\n'


class Crash(BaseException):
    """Simulates the deployer process dying (not an ordinary Exception)."""


def _done(stdout: str = "", code: int = 0, stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=code)


class FakeHost(ad.Host):
    def __init__(self, candidate: str = NEW, changed: tuple[str, ...] = ("nexus/x.py",)) -> None:
        self.candidate = candidate
        self.changed = changed
        self.origin = "https://github.com/James3014/Nexus-new.git"
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str] | None] = []
        self.started: list[str] = []
        self.stopped = 0
        self.reloads: list[bytes] = []
        self.clock = NOW
        self.dirty_after_sync = False
        self.sync_fails = False
        self.tool_fails: bool | str = False
        self.lock_events: list[str] = []
        self.lock_fails = False
        self.on_reload: Callable[[int], None] | None = None
        self.r1_block: str | None = None
        self.r1_checks = 0
        self.r1_guard_depth = 0
        self.r1_guard_events: list[str] = []
        self.r1_append_attempts: list[bool] = []
        self.after_r1_check: Callable[[], None] | None = None
        self.core_pin: str = CORE.pin
        # RIE engine (#1579): no pin in the candidate tree unless a test sets one.
        self.rie_pin: str | None = None
        self.rie_fetch_fails = False
        self.core_fetch_fails = False
        self.digest_runs = 0
        # Task quiescence (#2227): CLEAR unless a test says otherwise.
        self.in_flight: list[dict[str, Any]] = []
        self.real_classifier = False
        self.quiescence_checks = 0
        self.issue_comments: list[str] = []
        self.comment_issues: list[int | None] = []
        self.comment_fails = False
        # Controller worktrees (#1939): accepted unless a test says otherwise.
        self.controller_checks: list[Path] = []
        self.controller_verdicts: list[str | None] = []
        self.real_controller_check = False

    def tasks_in_flight(self, cfg: ad.Config, live_plist: bytes) -> dict[str, Any]:  # type: ignore[override]
        self.quiescence_checks += 1
        if self.real_classifier:
            # The real classifier code with this checkout's interpreter and tree.
            result = subprocess.run(
                [
                    sys.executable,
                    "-W",
                    "ignore",
                    "-c",
                    ad.TASK_QUIESCENCE_PROBE_CODE,
                    str(REPO_ROOT),
                    str(cfg.canonical_state_dir),
                ],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            return ad.classify_task_report(result.returncode, result.stdout, result.stderr)
        if self.in_flight:
            return dict(self.in_flight.pop(0) if len(self.in_flight) > 1 else self.in_flight[0])
        return {"verdict": "CLEAR", "checked": 0}

    def controller_problem(  # type: ignore[override]
        self, python: Path, root: Path, controller: Path, code_root: Path | None = None
    ) -> str | None:
        self.controller_checks.append(controller)
        if self.real_controller_check:
            return ad.Host.controller_problem(self, Path(sys.executable), REPO_ROOT, controller)
        return self.controller_verdicts.pop(0) if self.controller_verdicts else None

    def post_issue_comment(  # type: ignore[override]
        self, cfg: ad.Config, body: str, issue: int | None = None
    ) -> bool:
        if self.comment_fails:
            return False
        self.issue_comments.append(body)
        self.comment_issues.append(issue)
        return True

    def r1_recovery_block(self, cfg: ad.Config) -> str | None:  # type: ignore[override]
        self.r1_checks += 1
        block = self.r1_block
        if self.after_r1_check is not None:
            self.after_r1_check()
        return block

    @contextlib.contextmanager
    def r1_guard(self, cfg: ad.Config) -> Iterator[None]:  # type: ignore[override]
        self.r1_guard_depth += 1
        self.r1_guard_events.append("acquire")
        try:
            yield
        finally:
            self.r1_guard_depth -= 1
            self.r1_guard_events.append("release")

    def r1_try_append(self) -> bool:
        """What R1's REQUESTED append would get: refused while the guard is held."""
        accepted = self.r1_guard_depth == 0
        self.r1_append_attempts.append(accepted)
        return accepted

    def core_git(self, argv, cwd, timeout):
        """Core git effects run for real against the local fixture origin."""
        if "fetch" in argv and self.core_fetch_fails:
            return _done(code=128, stderr="fatal: unable to access github.com")
        env = {
            **GIT_ENV,
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"url.{CORE.path}.insteadOf",
            "GIT_CONFIG_VALUE_0": ad.CORE_REPOSITORY_URL,
        }
        return ad.Host.run(self, argv, cwd=cwd, env=env, timeout=timeout)

    def rie_git(self, argv, cwd, timeout):
        """RIE git effects run for real against the local fixture origin."""
        if "fetch" in argv and self.rie_fetch_fails:
            return _done(code=128, stderr="fatal: unable to access github.com")
        env = {
            **GIT_ENV,
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"url.{RIE.path}.insteadOf",
            "GIT_CONFIG_VALUE_0": ad.RIE_REPOSITORY_URL,
        }
        return ad.Host.run(self, argv, cwd=cwd, env=env, timeout=timeout)

    def run(self, argv, *, cwd=None, env=None, timeout=1800):  # type: ignore[override]
        self.calls.append(list(argv))
        self.envs.append(env)
        if argv[:1] == ["git"] and any("gateway-direct/core" in str(a) for a in argv):
            return self.core_git(argv, cwd, timeout)
        if argv[:1] == ["git"] and any("gateway-direct/rie" in str(a) for a in argv):
            return self.rie_git(argv, cwd, timeout)
        if ad.RIE_ENGINE_CHECK_CODE in argv:
            # The engine import check runs for real against the fixture checkout.
            real = [sys.executable, *argv[1:]]
            return ad.Host.run(self, real, cwd=cwd, env={**GIT_ENV, **(env or {})}, timeout=timeout)
        if argv[:1] == ["uv"]:
            if self.sync_fails:
                return _done(code=1, stderr="network down")
            venv = Path(env["UV_PROJECT_ENVIRONMENT"])
            (venv / "bin").mkdir(parents=True, exist_ok=True)
            (venv / "bin" / "python").write_text("")
            if self.dirty_after_sync:
                (Path(cwd) / ".venv").mkdir()
            return _done()
        if len(argv) > 4 and argv[4] == ad.CORE_SOURCE_DIGEST_CODE:
            # Core's digest module runs for real against the fixture checkout.
            self.digest_runs += 1
            return ad.Host.run(self, argv, cwd=cwd, env={**GIT_ENV, **(env or {})}, timeout=timeout)
        if argv[1:] == ["-c", "import sys"]:
            return _done(code=0 if Path(argv[0]).exists() else 1)
        if len(argv) > 2 and argv[1].endswith(ad.DEPLOYER):
            if self.tool_fails and (self.tool_fails is True or self.tool_fails == argv[2]):
                return _done(code=1, stderr="boom")
            return _done(json.dumps({"status": "IN_SYNC"}))
        if argv[0] != "git":
            return _done(code=1, stderr=f"unexpected {argv}")
        if argv[-3:] == ["remote", "get-url", "origin"]:
            return _done(self.origin + "\n")
        if "fetch" in argv:
            return _done()
        if argv[:2] == ["git", "-C"] and argv[3:] == ["rev-parse", "--verify", "HEAD^{commit}"]:
            # A deployment or Controller worktree is at the commit in its name.
            return _done(Path(argv[2]).name.split("-", 1)[1] + "\n")
        if "rev-parse" in argv and argv[-1].endswith("^{commit}"):
            return _done(self.candidate + "\n")
        if argv[:2] == ["git", "-C"] and argv[3:] == ["rev-parse", "HEAD"]:
            return _done(Path(argv[2]).name.split("-", 1)[1] + "\n")
        if argv[:2] == ["git", "-C"] and argv[3:] == ["status", "--porcelain"]:
            return _done("?? .venv/\n" if (Path(argv[2]) / ".venv").exists() else "")
        if "worktree" in argv and "add" in argv:
            root = Path(argv[-2])
            (root / "scripts/ops").mkdir(parents=True)
            (root / "uv.lock").write_text("lock-bytes")
            (root / ad.ENTRYPOINT).write_text("")
            (root / ad.CORE_PIN_FILE).parent.mkdir(parents=True)
            (root / ad.CORE_PIN_FILE).write_text(_pin_source(self.core_pin))
            if self.rie_pin is not None:
                (root / ad.RIE_PIN_FILE).parent.mkdir(parents=True, exist_ok=True)
                (root / ad.RIE_PIN_FILE).write_text(_rie_pin_source(self.rie_pin))
            return _done()
        if "worktree" in argv and "remove" in argv:
            return _done()
        if "diff" in argv:
            return _done("\n".join(self.changed) + "\n")
        if "rev-list" in argv:
            return _done("3\n")
        return _done(code=1, stderr=f"unexpected {argv}")

    def start(self, command, log_path):  # type: ignore[override]
        self.started.append(command)

        def stop() -> None:
            self.stopped += 1

        return stop

    def reload_service(self, plist: Path, label: str) -> None:
        assert label == ad.GATEWAY_LABEL
        self.reloads.append(plist.read_bytes())
        if self.on_reload is not None:
            self.on_reload(len(self.reloads))

    @contextlib.contextmanager
    def manager_lock(self, cfg: ad.Config) -> Iterator[None]:  # type: ignore[override]
        if self.lock_fails:
            raise ad.DeployError("MANAGER_LOCK_UNAVAILABLE:busy")
        self.lock_events.append("acquire")
        try:
            yield
        finally:
            self.lock_events.append("release")

    def free_port(self) -> int:
        return 50123

    def now(self) -> float:
        return self.clock

    def sleep(self, seconds: float) -> None:
        self.clock += seconds


class FakeProber:
    def __init__(
        self,
        results: dict[tuple[int, str], bool] | None = None,
        hook: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.results = results or {}
        self.hook = hook
        self.calls: list[dict[str, Any]] = []
        # Live /health (#2230 F2): a pre-#2232 Gateway has no controller_binding.
        self.health: Any = {"status": "ok", "git_head": OLD}
        self.health_reads = 0

    def live_health(self) -> Any:
        self.health_reads += 1
        if isinstance(self.health, BaseException):
            raise self.health
        return self.health

    def probe(self, *, port, token, commit, root, python, timeout, core=None):
        call = {"port": port, "commit": commit, "root": root, "python": python, "core": core}
        self.calls.append(call)
        if self.hook is not None:
            self.hook(call)
        ok = self.results.get((port, commit), True)
        return {"ok": ok, "checks": {"gb077": {"ok": ok}}}


SUITES = {name: 1000 + i for i, name in enumerate(ad.REQUIRED_CHECKS)}
PR_SUITE_OFFSET = 50_000  # suites >= this belong to the merged PR's head
ACTIONS_APP_ID = 15368
MERGED_PR = {
    "number": 2140,
    "ref": "feat/x",
    "created_at": "2026-10-13T20:00:00Z",
    "merged_at": "2026-10-14T00:00:00Z",
}


def _workflow_run(suite: int, path: str) -> dict[str, Any]:
    """A workflow run shaped like real data (pull_requests is empty after merge)."""
    if suite >= PR_SUITE_OFFSET:
        return {
            "path": path,
            "event": "pull_request_target",
            "head_branch": MERGED_PR["ref"],
            "head_sha": PR_HEAD,
            "head_repository": {"full_name": ad.REPOSITORY},
            "created_at": "2026-10-13T23:00:00Z",
            "pull_requests": [],
        }
    return {
        "path": path,
        "event": "push",
        "head_branch": "main",
        "head_sha": NEW,
        "head_repository": {"full_name": ad.REPOSITORY},
        "created_at": "2026-10-14T00:05:00Z",
        "pull_requests": [],
    }


def green_api(
    *,
    on_commit: bool = True,
    conclusion: str = "success",
    status: str = "completed",
    open_pulls: list[dict[str, Any]] | None = None,
    pull_files: dict[int, list[str]] | None = None,
    main_tip: str = NEW,
    relation: str = "ahead",
    extra_runs: dict[str, list[dict[str, Any]]] | None = None,
    workflow_path: Callable[[int], str] | None = None,
    pushed_at: dict[str, str] | None = None,
    timeline: dict[int, list[dict[str, Any]]] | None = None,
    required: list[str] | None = None,
):
    calls: list[str] = []

    def get(path: str) -> Any:
        calls.append(path)
        if "/rules/branches/main" in path:
            if "page=" in path and not path.endswith("page=1"):
                return []
            return _branch_rules(list(ad.REQUIRED_CHECKS) if required is None else required)
        if path.endswith("/branches/main"):
            return {"commit": {"sha": main_tip}}
        if "/compare/" in path:
            return {"status": relation}
        if "/pulls?state=open" in path:
            return (open_pulls or []) if path.endswith("page=1") else []
        if "/timeline?" in path:
            if not path.endswith("page=1"):
                return []
            number = int(path.split("/issues/")[1].split("/")[0])
            return (timeline or {}).get(number, [])
        if "/pulls/" in path and "/files?" in path:
            if not path.endswith("page=1"):
                return []
            number = int(path.split("/pulls/")[1].split("/")[0])
            return [{"filename": f} for f in (pull_files or {}).get(number, [])]
        if "/commits/" in path and "/" not in path.split("/commits/")[1]:
            sha = path.split("/commits/")[1]
            return {"commit": {"committer": {"date": (pushed_at or {}).get(sha, NOW_ISO)}}}
        if path.endswith("/pulls"):
            return [
                {
                    "merged_at": "2026-10-14T00:00:00Z",
                    "merge_commit_sha": NEW,
                    "number": MERGED_PR["number"],
                    "created_at": MERGED_PR["created_at"],
                    "base": {"ref": "main"},
                    "head": {
                        "sha": PR_HEAD,
                        "ref": MERGED_PR["ref"],
                        "repo": {"full_name": ad.REPOSITORY},
                    },
                }
            ]
        if "/actions/runs?check_suite_id=" in path:
            suite = int(path.rsplit("=", 1)[1])
            if workflow_path is not None:
                return {"workflow_runs": [_workflow_run(suite, workflow_path(suite))]}
            name = next(n for n, s in SUITES.items() if s == suite % 10_000)
            return {"workflow_runs": [_workflow_run(suite, ad.REQUIRED_CHECKS[name])]}
        name = urllib.parse.unquote_plus(path.split("check_name=")[1].split("&")[0])
        sha = path.split("/commits/")[1].split("/")[0]
        if sha == NEW and not on_commit and name == "Deletion guard":
            return {"check_runs": []}
        runs = [
            {
                "id": 1,
                "name": name,
                "status": status,
                "conclusion": conclusion,
                "started_at": "2026-10-14T00:00:00Z",
                "completed_at": "2026-10-14T00:00:00Z",
                "app": {"slug": "github-actions", "id": ACTIONS_APP_ID},
                "check_suite": {"id": SUITES[name] + (0 if sha == NEW else PR_SUITE_OFFSET)},
                "pull_requests": [],
            }
        ]
        return {"check_runs": runs + (extra_runs or {}).get(name, [])}

    get.calls = calls  # type: ignore[attr-defined]
    return get


def _branch_rules(names: list[str]) -> list[dict[str, Any]]:
    """Shape of GET repos/{repo}/rules/branches/main (integration 15368 = Actions)."""
    return [
        {"type": "deletion", "ruleset_id": 20697077},
        {
            "type": "required_status_checks",
            "ruleset_id": 20697077,
            "parameters": {
                "required_status_checks": [
                    {"context": name, "integration_id": 15368} for name in names
                ],
                "strict_required_status_checks_policy": False,
            },
        },
    ]


def live_plist(root: Path, python: str = "/shared/clone/.venv/bin/python") -> bytes:
    command = (
        f'cd "{root}" ; source "/env" ; export NEXUS_CANONICAL_SOURCE_ROOT="{root}" ; '
        f'exec {python} "{root}/scripts/ops/nexus_mcp_gateway_http.py"'
    )
    return plistlib.dumps({
        "Label": ad.GATEWAY_LABEL,
        "KeepAlive": True,
        "RunAtLoad": True,
        "ProgramArguments": ["/bin/zsh", "-c", command],
        "WorkingDirectory": str(root),
    })


@pytest.fixture
def cfg(tmp_path: Path) -> ad.Config:
    home = tmp_path / "home"
    c = ad.Config.default(home)
    c.deployments.mkdir(parents=True)
    predecessor = c.deployments / f"r1-{OLD}"
    (predecessor / "scripts/ops").mkdir(parents=True)
    (predecessor / ad.ENTRYPOINT).write_text("")
    shared_python = tmp_path / "shared/clone/.venv/bin/python"
    shared_python.parent.mkdir(parents=True)
    shared_python.write_text("")
    c.plist.parent.mkdir(parents=True)
    c.plist.write_bytes(live_plist(predecessor, str(shared_python)))
    ad.remember_plist(c, c.plist.read_bytes())  # what the installer's `adopt` does
    c.env_file.parent.mkdir(parents=True, exist_ok=True)
    c.env_file.write_text('export NEXUS_MCP_GATEWAY_TOKEN="tok-123"\nexport PATH=/bin\n')
    return c


def cycle(cfg: ad.Config, host: FakeHost, prober: FakeProber, api=None, **kw: Any) -> dict:
    kw.setdefault("tool_python", Path("/tool/python"))
    return ad.run_cycle(cfg, host, prober, api or green_api(), environ={}, **kw)


def test_constants_match_gateway_deployment_contract() -> None:
    assert ad.GATEWAY_LABEL == contract.LABEL
    assert ad.ENTRYPOINT == contract.ENTRYPOINT
    assert contract.ENDPOINT.endswith(f":{ad.LIVE_PORT}")
    assert ad.REPOSITORY == contract.REPOSITORY


def test_required_checks_are_bound_to_existing_workflows() -> None:
    for name, workflow in ad.REQUIRED_CHECKS.items():
        text = (REPO_ROOT / workflow).read_text(encoding="utf-8")
        assert f"name: {name}" in text, (name, workflow)


def test_green_candidate_is_built_probed_switched_and_receipted(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    result = cycle(cfg, host, prober)
    assert result["status"] == "DEPLOYED"
    root = cfg.deployments / f"a1-{NEW}"
    venv_python = cfg.venvs / f"a1-{NEW}" / "bin" / "python"
    # Probe on a spare port first, then on the live port, both for the exact commit.
    assert [(c["port"], c["commit"]) for c in prober.calls] == [(50123, NEW), (ad.LIVE_PORT, NEW)]
    assert host.started and "NEXUS_MCP_GATEWAY_PORT=50123" in host.started[0]
    assert host.stopped == 1
    data = plistlib.loads(cfg.plist.read_bytes())
    command = data["ProgramArguments"][2]
    assert data["WorkingDirectory"] == str(root) and data["KeepAlive"] is True
    assert f'exec "{venv_python}" "{root}/scripts/ops/nexus_mcp_gateway_http.py"' in command
    assert "NEXUS_MCP_GATEWAY_PORT" not in command
    assert f'NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR="{cfg.canonical_state_dir}"' in command
    # #2688: the fixed state root, exported after the env file so it cannot override it.
    assert f'export NEXUS_STATE_ROOT="{cfg.state_root}" ; ' in command
    assert command.index("NEXUS_STATE_ROOT=") > command.index("source ")
    assert 'NEXUS_CANONICAL_SOURCE_ROOT="' in command and command.startswith('cd "')
    assert cfg.state_root.is_dir() and stat.S_IMODE(cfg.state_root.stat().st_mode) == 0o700
    assert len(host.reloads) == 1
    assert host.lock_events == ["acquire", "release"]
    receipt = ad.last_receipt(cfg.state_dir)
    assert receipt == result["receipt"]
    assert receipt["schema"] == ad.RECEIPT_SCHEMA
    assert receipt["candidate_commit"] == NEW and receipt["previous_commit"] == OLD
    assert receipt["deployment_root"] == str(root)
    assert receipt["venv_python"] == str(venv_python)
    assert receipt["uv_lock_sha256"] == hashlib.sha256(b"lock-bytes").hexdigest()
    assert receipt["switched"] is True and receipt["rolled_back"] is False
    assert set(receipt["probes"]) == {"spare", "live"}
    assert receipt["required_checks"]["verdict"] == "GREEN"
    assert receipt["started_at"].endswith("Z") and receipt["finished_at"].endswith("Z")
    status = json.loads((cfg.state_dir / "status.json").read_text())
    assert status["status"] == "DEPLOYED"
    assert not cfg.journal.exists()
    # The plist the deployer wrote is known, so the next cycle is not FOREIGN.
    assert hashlib.sha256(cfg.plist.read_bytes()).hexdigest() in ad.known_plist_hashes(cfg)
    assert cycle(cfg, host, prober)["status"] == "IN_SYNC"


def test_per_deployment_venv_never_the_shared_clone(cfg: ad.Config) -> None:
    host = FakeHost()
    cycle(cfg, host, FakeProber())
    syncs = [(c, e) for c, e in zip(host.calls, host.envs) if c[:1] == ["uv"]]
    assert len(syncs) == 1
    argv, env = syncs[0]
    assert "--frozen" in argv and "--no-install-project" in argv and "--all-extras" in argv
    assert env == {"UV_PROJECT_ENVIRONMENT": str(cfg.venvs / f"a1-{NEW}")}
    venv = Path(env["UV_PROJECT_ENVIRONMENT"])
    assert cfg.venvs in venv.parents and cfg.deployments not in venv.parents
    command = plistlib.loads(cfg.plist.read_bytes())["ProgramArguments"][2]
    assert "/shared/clone/.venv" not in command and "Nexus-new/.venv" not in command


def test_uv_extras_can_be_narrowed(cfg: ad.Config) -> None:
    narrow = ad.Config.default(cfg.state_dir.parents[2], uv_extras="legacy")
    host = FakeHost()
    cycle(narrow, host, FakeProber())
    argv = next(c for c in host.calls if c[:1] == ["uv"])
    assert "--all-extras" not in argv and argv[argv.index("--extra") + 1] == "legacy"


def test_build_that_writes_into_source_tree_is_rejected(cfg: ad.Config) -> None:
    host = FakeHost()
    host.dirty_after_sync = True
    before = cfg.plist.read_bytes()
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "REJECTED_BUILD"
    assert cfg.plist.read_bytes() == before and host.reloads == []
    host.clock += 10 * ad.MAX_BACKOFF_SECONDS
    assert cycle(cfg, host, FakeProber())["status"] == "CANDIDATE_REJECTED_BEFORE"


@pytest.mark.parametrize(
    ("api", "expected"),
    [
        (green_api(conclusion="failure"), "CHECKS_RED"),
        (green_api(status="in_progress"), "CHECKS_PENDING"),
    ],
)
def test_checks_not_green_means_no_deploy(cfg: ad.Config, api: Any, expected: str) -> None:
    host, prober = FakeHost(), FakeProber()
    before = cfg.plist.read_bytes()
    result = cycle(cfg, host, prober, api)
    assert result["status"] == expected
    assert prober.calls == [] and host.reloads == [] and host.started == []
    assert not any(c[:1] == ["uv"] for c in host.calls)
    assert cfg.plist.read_bytes() == before
    assert ad.read_receipts(cfg.state_dir) == []


def test_checks_unknown_when_github_fails_or_check_missing(cfg: ad.Config) -> None:
    def broken(path: str) -> Any:
        if "check-runs" in path:
            raise ad.DeployError("GH_API_FAILED:boom")
        return green_api()(path)

    assert cycle(cfg, FakeHost(), FakeProber(), broken)["status"] == "CHECKS_UNKNOWN"

    def no_runs(path: str) -> Any:
        if "check-runs" in path:
            return {"check_runs": []}
        return [] if path.endswith("/pulls") else green_api()(path)

    assert cycle(cfg, FakeHost(), FakeProber(), no_runs)["status"] == "CHECKS_UNKNOWN"


def test_required_check_found_on_merged_pr_head() -> None:
    api = green_api(on_commit=False)
    result = ad.required_checks(api, NEW)
    assert result["verdict"] == "GREEN"
    assert result["checks"]["Deletion guard"]["sha"] == PR_HEAD
    assert result["checks"]["Exact-base impact gate"]["sha"] == NEW


def test_newer_queued_run_keeps_check_pending() -> None:
    """A re-run that is queued (started_at=None) must not lose to an older success."""
    queued = {
        "id": 2,
        "name": "Deletion guard",
        "status": "queued",
        "conclusion": None,
        "started_at": None,
        "app": {"slug": "github-actions", "id": ACTIONS_APP_ID},
        "check_suite": {"id": SUITES["Deletion guard"] + 10_000},
    }
    api = green_api(extra_runs={"Deletion guard": [queued]})
    result = ad.required_checks(api, NEW)
    assert result["verdict"] == "PENDING"
    assert result["checks"]["Deletion guard"]["state"] == "PENDING"


def test_newest_completed_run_decides_by_id() -> None:
    newer_failure = {
        "id": 9,
        "name": "Deletion guard",
        "status": "completed",
        "conclusion": "failure",
        "started_at": "2026-10-13T00:00:00Z",  # older timestamp, newer run
        "app": {"slug": "github-actions", "id": ACTIONS_APP_ID},
        "check_suite": {"id": SUITES["Deletion guard"] + 10_000},
    }
    api = green_api(extra_runs={"Deletion guard": [newer_failure]})
    assert ad.required_checks(api, NEW)["verdict"] == "RED"


def test_check_from_unbound_workflow_or_app_is_ignored() -> None:
    stray = green_api(workflow_path=lambda _suite: ".github/workflows/stray.yml")
    assert ad.required_checks(stray, NEW)["verdict"] == "UNKNOWN"

    def other_app(path: str) -> Any:
        payload = green_api()(path)
        for run in payload.get("check_runs", []) if isinstance(payload, dict) else []:
            run["app"] = {"slug": "some-other-app"}
        return payload

    assert ad.required_checks(other_app, NEW)["verdict"] == "UNKNOWN"


@pytest.mark.parametrize(
    ("tip", "relation", "ok"),
    [(NEW, "n/a", True), (PR_HEAD, "ahead", True), (PR_HEAD, "diverged", False)],
)
def test_candidate_must_be_on_github_main(tip: str, relation: str, ok: bool) -> None:
    assert ad.on_github_main(green_api(main_tip=tip, relation=relation), NEW)["ok"] is ok


def test_candidate_not_on_github_main_is_not_deployed(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    api = green_api(main_tip=PR_HEAD, relation="diverged")
    assert cycle(cfg, host, prober, api)["status"] == "CANDIDATE_NOT_ON_MAIN"
    assert prober.calls == [] and host.reloads == []

    def broken(path: str) -> Any:
        if path.endswith("/branches/main"):
            raise ad.DeployError("GH_API_FAILED")
        return green_api()(path)

    assert cycle(cfg, host, prober, broken)["status"] == "CANDIDATE_NOT_ON_MAIN"


def test_bare_repo_origin_must_be_nexus_new(cfg: ad.Config) -> None:
    host = FakeHost()
    host.origin = "https://github.com/someone/Nexus-new.git"
    assert cycle(cfg, host, FakeProber())["status"] == "ORIGIN_MISMATCH"
    assert not any("fetch" in c for c in host.calls)


def test_probe_failure_keeps_current_deployment(cfg: ad.Config) -> None:
    host = FakeHost()
    prober = FakeProber({(50123, NEW): False})
    before = cfg.plist.read_bytes()
    result = cycle(cfg, host, prober)
    assert result["status"] == "REJECTED_PROBE"
    assert cfg.plist.read_bytes() == before and host.reloads == []
    assert host.stopped == 1
    receipt = ad.last_receipt(cfg.state_dir)
    assert receipt["outcome"] == "REJECTED_PROBE" and receipt["switched"] is False
    # Bounded retry with backoff, then the candidate is given up.
    assert cycle(cfg, host, prober)["status"] == "BACKOFF"
    for _ in range(ad.MAX_CANDIDATE_ATTEMPTS - 1):
        host.clock += ad.MAX_BACKOFF_SECONDS
        assert cycle(cfg, host, prober)["status"] == "REJECTED_PROBE"
    host.clock += ad.MAX_BACKOFF_SECONDS
    assert cycle(cfg, host, prober)["status"] == "CANDIDATE_REJECTED_BEFORE"


def test_backoff_grows_with_failures(cfg: ad.Config) -> None:
    host = FakeHost()
    prober = FakeProber({(50123, NEW): False})
    cycle(cfg, host, prober)
    host.clock += cfg.min_interval_seconds
    assert cycle(cfg, host, prober)["status"] == "REJECTED_PROBE"
    host.clock += cfg.min_interval_seconds  # second failure doubles the wait
    result = cycle(cfg, host, prober)
    assert result["status"] == "BACKOFF" and result["retry_in_seconds"] == cfg.min_interval_seconds


def test_post_switch_failure_rolls_back_to_exact_previous_plist(cfg: ad.Config) -> None:
    host = FakeHost()
    prober = FakeProber({(ad.LIVE_PORT, NEW): False})
    before = cfg.plist.read_bytes()
    result = cycle(cfg, host, prober)
    assert result["status"] == "ROLLED_BACK"
    assert cfg.plist.read_bytes() == before
    assert len(host.reloads) == 2 and host.reloads[1] == before
    rollback_probe = prober.calls[-1]
    assert rollback_probe["port"] == ad.LIVE_PORT and rollback_probe["commit"] == OLD
    assert str(rollback_probe["python"]).endswith("/shared/clone/.venv/bin/python")
    receipt = ad.last_receipt(cfg.state_dir)
    assert receipt["switched"] is True and receipt["rolled_back"] is True
    assert set(receipt["probes"]) == {"spare", "live", "rollback"}
    assert not cfg.hold_file.exists() and not cfg.journal.exists()
    assert host.lock_events == ["acquire", "release"]


def test_failed_rollback_engages_the_kill_switch(cfg: ad.Config) -> None:
    host = FakeHost()
    prober = FakeProber({(ad.LIVE_PORT, NEW): False, (ad.LIVE_PORT, OLD): False})
    assert cycle(cfg, host, prober)["status"] == "ROLLBACK_FAILED"
    assert cfg.hold_file.exists()
    assert cycle(cfg, host, prober)["status"] == "HELD"


def test_reload_raising_during_switch_and_rollback(cfg: ad.Config) -> None:
    host = FakeHost()

    def fail_first(count: int) -> None:
        if count == 1:
            raise ad.DeployError("GATEWAY_RELOAD_FAILED:switch")

    host.on_reload = fail_first
    before = cfg.plist.read_bytes()
    assert cycle(cfg, host, FakeProber())["status"] == "ROLLED_BACK"
    assert cfg.plist.read_bytes() == before

    cfg.hold_file.unlink(missing_ok=True)
    host2 = FakeHost()

    def always(_count: int) -> None:
        raise ad.DeployError("GATEWAY_RELOAD_FAILED:all")

    host2.on_reload = always
    host2.clock += ad.MAX_BACKOFF_SECONDS
    assert cycle(cfg, host2, FakeProber())["status"] == "ROLLBACK_FAILED"
    assert cfg.plist.read_bytes() == before and cfg.hold_file.exists()


def test_kill_switch_file_and_env_pause_everything(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    assert ad.main(["hold", "--home", str(cfg.state_dir.parents[2]), "--reason", "test"]) == 0
    assert cfg.hold_file.read_text() == "test\n"
    result = cycle(cfg, host, prober)
    assert result["status"] == "HELD" and host.calls == []
    assert ad.main(["release", "--home", str(cfg.state_dir.parents[2])]) == 0
    result = ad.run_cycle(cfg, host, prober, green_api(), environ={ad.HOLD_ENV: "1"})
    assert result["status"] == "HELD" and host.calls == []
    assert cycle(cfg, host, prober)["status"] == "DEPLOYED"


def test_hold_set_during_the_cycle_aborts_before_switch(cfg: ad.Config) -> None:
    def hold_during_spare_probe(call: dict[str, Any]) -> None:
        if call["port"] == 50123:
            ad._set_hold(cfg, "owner pressed hold")

    host = FakeHost()
    before = cfg.plist.read_bytes()
    result = cycle(cfg, host, FakeProber(hook=hold_during_spare_probe))
    assert result["status"] == "HELD"
    assert result["receipt"]["outcome"] == "HELD" and result["receipt"]["switched"] is False
    assert cfg.plist.read_bytes() == before and host.reloads == []


def test_hold_env_rechecked_before_switch(cfg: ad.Config) -> None:
    env: dict[str, str] = {}

    def hold_env(call: dict[str, Any]) -> None:
        env[ad.HOLD_ENV] = "1"

    host = FakeHost()
    result = ad.run_cycle(
        cfg, host, FakeProber(hook=hold_env), green_api(), environ=env, tool_python=Path("/p")
    )
    assert result["status"] == "HELD" and host.reloads == []


def test_hold_rechecked_after_taking_the_cycle_lock(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_lock = ad._cycle_lock

    @contextlib.contextmanager
    def lock_then_hold(c: ad.Config) -> Iterator[bool]:
        with real_lock(c) as acquired:
            ad._set_hold(c, "set while waiting")
            yield acquired

    monkeypatch.setattr(ad, "_cycle_lock", lock_then_hold)
    host = FakeHost()
    assert cycle(cfg, host, FakeProber())["status"] == "HELD"
    assert host.calls == []


def test_busy_when_another_cycle_holds_the_lock(cfg: ad.Config) -> None:
    with ad._cycle_lock(cfg) as acquired:
        assert acquired
        host = FakeHost()
        assert cycle(cfg, host, FakeProber())["status"] == "BUSY"
        assert host.calls == []


def test_dry_run_prints_plan_without_effects(
    cfg: ad.Config, capsys: pytest.CaptureFixture[str]
) -> None:
    host, prober = FakeHost(), FakeProber()
    before = cfg.plist.read_bytes()
    code = ad.main(
        ["run", "--dry-run", "--home", str(cfg.state_dir.parents[2])],
        host=host,
        prober=prober,
        api_get=green_api(),
    )
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["status"] == "PLAN"
    assert out["plan"]["deployment_root"] == str(cfg.deployments / f"a1-{NEW}")
    assert host.reloads == [] and host.started == [] and prober.calls == []
    assert not any(c[:1] == ["uv"] or "worktree" in c for c in host.calls)
    assert cfg.plist.read_bytes() == before
    assert not (cfg.state_dir / "status.json").exists()


def test_irrelevant_main_movement_is_skipped_until_lag_limit(cfg: ad.Config) -> None:
    host = FakeHost(changed=("docs/a.md", "tasks/x/y.json", "tests/t.py", "README.md"))
    assert cycle(cfg, host, FakeProber())["status"] == "SKIPPED_IRRELEVANT"
    lagging = ad.Config.default(cfg.state_dir.parents[2], max_irrelevant_lag=3)
    assert cycle(lagging, host, FakeProber())["status"] == "DEPLOYED"


def test_debounce_and_in_sync(cfg: ad.Config) -> None:
    host = FakeHost()
    host.sync_fails = True
    assert cycle(cfg, host, FakeProber())["status"] == "BUILD_FAILED"
    host.sync_fails = False
    assert cycle(cfg, host, FakeProber())["status"] == "BACKOFF"
    host.clock += cfg.min_interval_seconds
    assert cycle(cfg, host, FakeProber())["status"] == "DEPLOYED"
    assert cycle(cfg, host, FakeProber())["status"] == "IN_SYNC"


def test_blocked_no_rollback_backs_off_instead_of_rebuilding(
    cfg: ad.Config, tmp_path: Path
) -> None:
    (tmp_path / "shared/clone/.venv/bin/python").unlink()
    host = FakeHost()
    assert cycle(cfg, host, FakeProber())["status"] == "BLOCKED_NO_ROLLBACK"
    builds = sum(c[:1] == ["uv"] for c in host.calls)
    assert cycle(cfg, host, FakeProber())["status"] == "BACKOFF"
    assert sum(c[:1] == ["uv"] for c in host.calls) == builds


def test_retention_keeps_newest_and_protected_never_r1(cfg: ad.Config) -> None:
    host = FakeHost()
    names = [f"a1-{c * 40}" for c in "123456"]
    for index, name in enumerate(names):
        (cfg.deployments / name).mkdir()
        (cfg.venvs / name).mkdir(parents=True)
        os.utime(cfg.deployments / name, (1000 + index, 1000 + index))
    (cfg.venvs / "a1-orphan").mkdir()
    oldest = cfg.deployments / names[0]
    cfg.plist.write_bytes(live_plist(oldest))  # the live deployment is the oldest one
    removed = ad.prune(cfg, host, [oldest])
    assert sorted(removed) == sorted(names[1:3])
    left = sorted(p.name for p in cfg.deployments.iterdir())
    assert left == sorted([f"r1-{OLD}", names[0], *names[3:]])
    assert sorted(p.name for p in cfg.venvs.iterdir()) == sorted([names[0], *names[3:]])
    removes = [c for c in host.calls if "remove" in c]
    assert len(removes) == 2 and all("--force" in c for c in removes)


def test_retention_never_follows_symlinks(cfg: ad.Config, tmp_path: Path) -> None:
    precious = tmp_path / "precious"
    precious.mkdir()
    (precious / "keep.txt").write_text("x")
    cfg.venvs.mkdir(parents=True)
    for index in range(5):
        name = f"a1-{str(index) * 40}"
        (cfg.deployments / name).mkdir()
        os.utime(cfg.deployments / name, (2000 + index, 2000 + index))
    (cfg.deployments / f"a1-{'9' * 40}").symlink_to(precious)
    (cfg.venvs / f"a1-{'8' * 40}").symlink_to(precious)
    ad.prune(ad.Config.default(cfg.state_dir.parents[2], keep=1), FakeHost(), [])
    assert (precious / "keep.txt").exists()
    assert (cfg.deployments / f"a1-{'9' * 40}").is_symlink()


def test_retention_refuses_symlinked_parent_dirs(cfg: ad.Config, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / f"a1-{'1' * 40}").mkdir(parents=True)
    (elsewhere / f"a1-{'2' * 40}").mkdir()
    cfg.venvs.symlink_to(elsewhere)
    host = FakeHost()
    assert ad.prune(ad.Config.default(cfg.state_dir.parents[2], keep=0), host, []) == []
    assert len(list(elsewhere.iterdir())) == 2 and host.calls == []


def test_retention_refuses_symlinked_gateway_root(cfg: ad.Config, tmp_path: Path) -> None:
    real = cfg.gateway_root
    for index in range(5):
        (real / "deployments" / f"a1-{str(index) * 40}").mkdir()
    alias = tmp_path / "alias-gateway-direct"
    alias.symlink_to(real)
    aliased = ad.Config.default(cfg.state_dir.parents[2], gateway_root=alias, keep=0)
    host = FakeHost()
    assert ad.prune_refusal(aliased) == f"GATEWAY_ROOT_NOT_CANONICAL:{alias}"
    assert ad.prune(aliased, host, []) == [] and host.calls == []
    assert len(list((real / "deployments").glob("a1-*"))) == 5


def test_prune_refusal_is_recorded_in_status(cfg: ad.Config, tmp_path: Path) -> None:
    alias = tmp_path / "alias-gateway-direct"
    alias.symlink_to(cfg.gateway_root)
    aliased = ad.Config.default(cfg.state_dir.parents[2], gateway_root=alias)
    host = FakeHost(candidate=OLD)  # IN_SYNC path still runs retention
    result = cycle(aliased, host, FakeProber())
    assert result["status"] == "IN_SYNC"
    assert result["prune_refused"].startswith("GATEWAY_ROOT_NOT_CANONICAL")


def test_wrapper_rejects_shell_metacharacters(cfg: ad.Config) -> None:
    with pytest.raises(ad.DeployError, match="WRAPPER_PATH_UNSAFE"):
        ad.wrapper_command(cfg, Path('/tmp/x"; rm -rf ~'), Path("/py"))


def test_wrapper_render_parse_round_trip_with_spaces(tmp_path: Path) -> None:
    """Regression: a quoted interpreter under "Application Support" must not truncate."""
    home = tmp_path / "Users" / "james"
    cfg = ad.Config.default(home)
    root = cfg.deployments / f"a1-{NEW}"
    python = cfg.venvs / f"a1-{NEW}" / "bin" / "python"
    assert " " in str(python)
    plist = ad.render_plist(live_plist(Path("/x")), ad.wrapper_command(cfg, root, python), root)
    assert ad.live_python(plist) == python
    assert ad.live_root(plist) == root
    assert ad.commit_of(ad.live_root(plist)) == NEW


def test_live_plist_shape_parses() -> None:
    root = Path(
        "/Users/james/Library/Application Support/Nexus/gateway-direct/deployments/r1-" + OLD
    )
    plist = live_plist(root, "/Users/james/workspace/Nexus-new/.venv/bin/python")
    assert ad.live_python(plist) == Path("/Users/james/workspace/Nexus-new/.venv/bin/python")
    assert ad.live_root(plist) == root


def test_second_deploy_from_a1_deployment_is_not_blocked(cfg: ad.Config) -> None:
    """After the first deploy the live python sits under "Application Support"."""
    spaced = ad.Config.default(cfg.state_dir.parents[2] / "Application Support")
    for directory in (spaced.deployments, spaced.plist.parent, spaced.env_file.parent):
        directory.mkdir(parents=True, exist_ok=True)
    first = spaced.deployments / f"a1-{OLD}"
    (first / "scripts/ops").mkdir(parents=True)
    (first / ad.ENTRYPOINT).write_text("")
    python = spaced.venvs / f"a1-{OLD}" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("")
    spaced.plist.write_bytes(
        ad.render_plist(live_plist(first), ad.wrapper_command(spaced, first, python), first)
    )
    ad.remember_plist(spaced, spaced.plist.read_bytes())
    spaced.env_file.write_text("export NEXUS_MCP_GATEWAY_TOKEN=t\n")
    assert cycle(spaced, FakeHost(), FakeProber())["status"] == "DEPLOYED"


def test_spare_probe_never_sees_live_state(cfg: ad.Config) -> None:
    seen: list[bool] = []

    def check_state(call: dict[str, Any]) -> None:
        if call["port"] == 50123:
            probe_dirs = list(cfg.probe_state_root.iterdir())
            seen.append(len(probe_dirs) == 1 and not any(probe_dirs[0].iterdir()))

    host = FakeHost()
    cycle(cfg, host, FakeProber(hook=check_state))
    spare = host.started[0]
    assert str(cfg.canonical_state_dir) not in spare
    assert f'NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR="{cfg.probe_state_root}/' in spare
    assert f'NEXUS_STATE_ROOT="{cfg.probe_state_root}/' in spare
    assert str(cfg.state_root) not in spare
    assert seen == [True]
    assert not any(cfg.probe_state_root.iterdir())  # throwaway dir cleaned up
    receipt = ad.last_receipt(cfg.state_dir)
    assert receipt["probes"]["spare"]["state_dir"].startswith(str(cfg.probe_state_root))


def test_read_env_token(tmp_path: Path) -> None:
    env = tmp_path / "e.env"
    env.write_text("export PATH=/bin\nexport NEXUS_MCP_GATEWAY_TOKEN='s3cr3t'\n")
    assert ad.read_env_token(env) == "s3cr3t"
    env.write_text("export PATH=/bin\n")
    with pytest.raises(ad.DeployError, match="GATEWAY_TOKEN_UNAVAILABLE"):
        ad.read_env_token(env)


def test_drift_check_reports_last_auto_deploy_receipt(
    cfg: ad.Config, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cycle(cfg, FakeHost(), FakeProber())
    repo = tmp_path / "clone"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@e.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@e.invalid",
    }
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "--allow-empty", "-m", "x"], check=True, env=env
    )
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    code = drift.main(
        [
            "--repo",
            str(repo),
            "--main-ref",
            "main",
            "--json",
            "--offline",
            "--auto-deploy-state",
            str(cfg.state_dir),
        ],
        fetch_health=lambda _u: {"git_head": head},
    )
    report = json.loads(capsys.readouterr().out)
    assert code == 0 and report["verdict"] == "OK"
    assert report["auto_deploy"]["outcome"] == "DEPLOYED"
    assert report["auto_deploy"]["candidate_commit"] == NEW
    assert f"last auto-deploy DEPLOYED {NEW[:12]}" in report["summary"]


# ----------------------------------------------------------------- installer


FAKE_GH = r"""#!/usr/bin/env python3
import json, os, sys
from urllib.parse import parse_qs, urlsplit
REQUIRED = json.loads(os.environ["FAKE_REQUIRED"])
path = sys.argv[2]
if sys.argv[1] != "api":
    sys.exit(2)
url = urlsplit(path)
if url.path.endswith("/rules/branches/main"):
    out = [{"type": "required_status_checks", "parameters": {"required_status_checks": [
        {"context": name, "integration_id": 15368} for name in REQUIRED]}}]
elif url.path.endswith("/branches/main"):
    out = {"commit": {"sha": os.environ["FAKE_MAIN"]}}
elif "/check-runs" in url.path:
    name = parse_qs(url.query)["check_name"][0]
    suite = 1 + list(REQUIRED).index(name)
    out = {"check_runs": [{"id": 1, "name": name, "status": "completed",
                           "conclusion": os.environ["FAKE_CONCLUSION"],
                           "app": {"slug": "github-actions", "id": 15368},
                           "check_suite": {"id": suite}}]}
elif url.path.endswith("/actions/runs"):
    suite = int(parse_qs(url.query)["check_suite_id"][0])
    out = {"workflow_runs": [{"path": list(REQUIRED.values())[suite - 1], "event": "push",
                              "head_branch": "main", "head_sha": os.environ["FAKE_MAIN"],
                              "head_repository": {"full_name": "James3014/Nexus-new"}}]}
else:
    out = []
print(json.dumps(out))
"""


def _installer_env(tmp_path: Path, tool: Path, conclusion: str = "success") -> dict[str, str]:
    gh = tmp_path / "bin" / "gh"
    gh.parent.mkdir(parents=True, exist_ok=True)
    gh.write_text(FAKE_GH.replace("#!/usr/bin/env python3", f"#!{sys.executable}"))
    gh.chmod(0o755)
    head = subprocess.run(
        ["git", "-C", str(tool), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    return {
        **os.environ,
        "HOME": str(tmp_path),
        "NEXUS_GATEWAY_AUTO_DEPLOY_PYTHON": sys.executable,
        "NEXUS_GATEWAY_AUTO_DEPLOY_GH": str(gh),
        "NEXUS_GATEWAY_AUTO_DEPLOY_TOOL_ROOT": str(tool),
        "NEXUS_GATEWAY_AUTO_DEPLOY_LAUNCHD_LOAD": "0",
        "FAKE_MAIN": head,
        "FAKE_CONCLUSION": conclusion,
        "FAKE_REQUIRED": json.dumps(ad.REQUIRED_CHECKS),
    }


@pytest.fixture
def tool_tree(tmp_path: Path) -> Path:
    """A clean clone of this checkout's HEAD, as the Owner's verified tree."""
    tool = tmp_path / "tool"
    subprocess.run(
        ["git", "clone", "-q", "--shared", "--no-checkout", str(REPO_ROOT), str(tool)], check=True
    )
    subprocess.run(["git", "-C", str(tool), "checkout", "-q", "--detach", "HEAD"], check=True)
    # Run the working-tree copies under test (identical to HEAD in CI).
    for rel in (ad.DEPLOYER, "scripts/ops/mcp_gateway_durable.py"):
        (tool / rel).write_bytes((REPO_ROOT / rel).read_bytes())
    subprocess.run(["git", "-C", str(tool), "update-index", "--refresh", "-q"], check=False)
    return tool


def _clean(tool: Path) -> bool:
    out = subprocess.run(
        ["git", "-C", str(tool), "status", "--porcelain"], capture_output=True, text=True
    ).stdout
    return not out.strip()


def test_installer_dry_run_and_plist(tmp_path: Path, tool_tree: Path) -> None:
    if not _clean(tool_tree):
        pytest.skip("working tree differs from HEAD for the deployer; commit first")
    script = REPO_ROOT / "scripts/ops/install_nexus_gateway_auto_deploy.sh"
    env = _installer_env(tmp_path, tool_tree)
    gateway_plist = tmp_path / "Library/LaunchAgents/com.nexus.mcp.gateway.direct.plist"
    gateway_plist.parent.mkdir(parents=True)
    gateway_plist.write_bytes(live_plist(Path("/srv/r1-" + OLD)))
    dry = subprocess.run(
        ["bash", str(script), "--dry-run"], env=env, capture_output=True, text=True, check=True
    )
    assert "would load" in dry.stdout
    assert not (tmp_path / "Library/Application Support").exists()
    for _ in range(2):  # idempotent
        subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, check=True)
    plist = tmp_path / "Library/LaunchAgents/com.nexus.gateway-auto-deploy.plist"
    data = plistlib.loads(plist.read_bytes())
    gateway_dir = tmp_path / "Library/Application Support/Nexus/gateway-direct"
    link = gateway_dir / "auto-deploy-current"
    assert link.is_symlink() and link.resolve() == tool_tree.resolve()
    assert sorted(p.name for p in gateway_dir.iterdir()) == ["auto-deploy-current"]
    assert not list(tool_tree.glob("auto-deploy-current*"))  # no link moved *into* the tree
    state = tmp_path / ".local/state/nexus-gateway-auto-deploy"
    assert data["ProgramArguments"] == [
        sys.executable,
        f"{link}/scripts/ops/nexus_gateway_auto_deploy.py",
        "run",
        "--gh",
        env["NEXUS_GATEWAY_AUTO_DEPLOY_GH"],
        "--state-dir",
        str(state),
    ]
    assert data["StartInterval"] == 300 and data["RunAtLoad"] is True
    assert data["EnvironmentVariables"]["PYTHONDONTWRITEBYTECODE"] == "1"
    assert data["EnvironmentVariables"]["NEXUS_GATEWAY_PLIST"] == str(gateway_plist)
    assert "NEXUS_MCP_GATEWAY_TOKEN" not in data["EnvironmentVariables"]
    adopted = json.loads((state / "known-plists.json").read_text())["sha256"]
    assert adopted == [hashlib.sha256(gateway_plist.read_bytes()).hexdigest()]


def test_installer_refuses_unverified_commit(tmp_path: Path, tool_tree: Path) -> None:
    if not _clean(tool_tree):
        pytest.skip("working tree differs from HEAD for the deployer; commit first")
    script = REPO_ROOT / "scripts/ops/install_nexus_gateway_auto_deploy.sh"
    for env in (
        _installer_env(tmp_path, tool_tree, conclusion="failure"),
        {**_installer_env(tmp_path, tool_tree), "FAKE_MAIN": "f" * 40},
    ):
        result = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)
        assert result.returncode != 0
        assert "TOOL_COMMIT_NOT_VERIFIED" in result.stderr
        assert not (tmp_path / "Library/Application Support/Nexus/gateway-direct").exists()
        assert not (tmp_path / "Library/LaunchAgents/com.nexus.gateway-auto-deploy.plist").exists()


def test_installer_rerun_refuses_unknown_live_plist_without_adopt(
    tmp_path: Path, tool_tree: Path
) -> None:
    if not _clean(tool_tree):
        pytest.skip("working tree differs from HEAD for the deployer; commit first")
    script = REPO_ROOT / "scripts/ops/install_nexus_gateway_auto_deploy.sh"
    env = _installer_env(tmp_path, tool_tree)
    gateway_plist = tmp_path / "Library/LaunchAgents/com.nexus.mcp.gateway.direct.plist"
    gateway_plist.parent.mkdir(parents=True)
    gateway_plist.write_bytes(live_plist(Path("/srv/r1-" + OLD)))
    subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, check=True)
    gateway_plist.write_bytes(live_plist(Path("/srv/r1-" + PR_HEAD)))  # manual rebind
    refused = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)
    assert refused.returncode != 0 and "--adopt" in refused.stderr
    known = tmp_path / ".local/state/nexus-gateway-auto-deploy/known-plists.json"
    assert len(json.loads(known.read_text())["sha256"]) == 1
    subprocess.run(
        ["bash", str(script), "--adopt"], env=env, capture_output=True, text=True, check=True
    )
    assert (
        hashlib.sha256(gateway_plist.read_bytes()).hexdigest()
        in json.loads(known.read_text())["sha256"]
    )


def test_adopt_if_unrecorded_cli(cfg: ad.Config, capsys: pytest.CaptureFixture[str]) -> None:
    home = str(cfg.state_dir.parents[2])
    assert ad.main(["adopt", "--adopt-if-unrecorded", "--home", home]) == 0  # already known
    cfg.plist.write_bytes(live_plist(cfg.deployments / f"r1-{PR_HEAD}"))
    assert ad.main(["adopt", "--adopt-if-unrecorded", "--home", home]) == 3
    assert ad.main(["adopt", "--home", home]) == 0
    capsys.readouterr()


# ------------------------------------------------------------- self-update


def test_successful_deploy_moves_the_deployer_link(cfg: ad.Config) -> None:
    host = FakeHost()
    result = cycle(cfg, host, FakeProber(), tool_python=Path("/agent/python3.12"))
    assert cfg.tool_link.is_symlink()
    assert Path(os.readlink(cfg.tool_link)) == cfg.deployments / f"a1-{NEW}"
    tool_runs = [c for c in host.calls if len(c) > 2 and c[1].endswith(ad.DEPLOYER)]
    assert [c[2] for c in tool_runs] == ["selftest", "status", "run"]
    assert all(c[0] == "/agent/python3.12" for c in tool_runs)
    dry = tool_runs[2]
    assert dry[3:5] == ["--dry-run", "--no-fetch"]
    assert dry[dry.index("--gh") + 1].endswith("gh-offline")
    scratch = Path(dry[dry.index("--state-dir") + 1])
    assert scratch != cfg.state_dir and not scratch.exists()  # scratch removed afterwards
    assert str(cfg.deployments / f"a1-{NEW}" / ad.DEPLOYER) == tool_runs[0][1]
    assert result["receipt"]["deployer_link"]["moved"] is True


def test_failed_deploy_keeps_the_deployer_link(cfg: ad.Config) -> None:
    cycle(cfg, FakeHost(), FakeProber({(ad.LIVE_PORT, NEW): False}))
    assert not cfg.tool_link.exists()


def test_broken_candidate_deployer_does_not_move_the_link(cfg: ad.Config, tmp_path: Path) -> None:
    old_tool = tmp_path / "old-tool"
    old_tool.mkdir()
    cfg.tool_link.symlink_to(old_tool)
    host = FakeHost()
    host.tool_fails = True
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "DEPLOYED"
    assert Path(os.readlink(cfg.tool_link)) == old_tool
    link = result["receipt"]["deployer_link"]
    assert link["moved"] is False and "selftest failed" in link["reason"]


def test_candidate_run_dry_run_failure_does_not_move_the_link(cfg: ad.Config) -> None:
    host = FakeHost()
    host.tool_fails = "run"
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "DEPLOYED" and not cfg.tool_link.exists()
    assert "run --dry-run failed" in result["receipt"]["deployer_link"]["reason"]


def test_candidate_dry_run_cli_really_parses(
    cfg: ad.Config, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exact self-update argv parses and reaches the planning path offline."""
    host = FakeHost(candidate=OLD)
    code = ad.main(
        [
            "run",
            "--dry-run",
            "--no-fetch",
            "--gh",
            "/nonexistent/gh-offline",
            "--state-dir",
            str(cfg.state_dir),
            "--gateway-root",
            str(cfg.gateway_root),
            "--plist",
            str(cfg.plist),
        ],
        host=host,
        prober=FakeProber(),
        api_get=green_api(),
    )
    assert code == 0 and json.loads(capsys.readouterr().out)["status"] == "IN_SYNC"
    assert not any("fetch" in c for c in host.calls)


def test_selftest_subcommand_reaches_the_durable_manager(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert ad.main(["selftest"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "OK"


# ------------------------------------------------------------ crash recovery


@pytest.mark.parametrize("crash_at", ["after_plist_write", "after_reload", "during_live_probe"])
@pytest.mark.parametrize("live_ok", [True, False])
def test_crash_mid_switch_is_reconciled_next_cycle(
    cfg: ad.Config, crash_at: str, live_ok: bool
) -> None:
    before = cfg.plist.read_bytes()
    host = FakeHost()

    def crash_on_reload(_count: int) -> None:
        if crash_at == "after_plist_write":
            raise Crash()

    def crash_on_probe(call: dict[str, Any]) -> None:
        if call["port"] == ad.LIVE_PORT and crash_at == "during_live_probe":
            raise Crash()

    host.on_reload = crash_on_reload
    if crash_at == "after_reload":
        host.on_reload = lambda _c: None
        crash_probe = FakeProber(
            hook=lambda c: (_ for _ in ()).throw(Crash()) if c["port"] == ad.LIVE_PORT else None
        )
    else:
        crash_probe = FakeProber(hook=crash_on_probe)
    with pytest.raises(Crash):
        cycle(cfg, host, crash_probe)
    assert cfg.journal.exists()
    assert cfg.plist.read_bytes() != before  # the crash left the candidate plist

    # Next cycle: the journal is resolved before anything else.
    host2 = FakeHost()
    prober2 = FakeProber({(ad.LIVE_PORT, NEW): live_ok})
    result = cycle(cfg, host2, prober2)
    assert not cfg.journal.exists()
    receipt = ad.last_receipt(cfg.state_dir)
    assert receipt["reconciled"] is True and receipt["candidate_commit"] == NEW
    assert not any(c[:1] == ["uv"] or "fetch" in c for c in host2.calls)
    if live_ok:
        assert result["status"] == "RECONCILED_DEPLOYED"
        assert ad.live_root(cfg.plist.read_bytes()) == cfg.deployments / f"a1-{NEW}"
    else:
        assert result["status"] == "RECONCILED_ROLLED_BACK"
        assert cfg.plist.read_bytes() == before
    assert host2.lock_events == ["acquire", "release"]


def test_crash_before_plist_write_is_reconciled_as_interrupted(cfg: ad.Config) -> None:
    before = cfg.plist.read_bytes()
    host = FakeHost()
    real_write = ad._atomic_write

    def crash_on_plist(path: Path, data: bytes, mode: int = 0o644) -> None:
        if path == cfg.plist:
            raise Crash()
        real_write(path, data, mode)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ad, "_atomic_write", crash_on_plist)
        with pytest.raises(Crash):
            cycle(cfg, host, FakeProber())
    assert cfg.journal.exists() and cfg.plist.read_bytes() == before
    host2, prober2 = FakeHost(), FakeProber()
    result = cycle(cfg, host2, prober2)
    # Equal bytes are not trusted: the previous plist is reloaded and probed.
    assert result["status"] == "RECONCILED_ROLLED_BACK"
    assert host2.reloads == [before]
    assert [(c["port"], c["commit"]) for c in prober2.calls] == [(ad.LIVE_PORT, OLD)]
    assert cfg.plist.read_bytes() == before and not cfg.journal.exists()


def test_crash_on_rollback_reload_is_reloaded_and_probed_next_cycle(cfg: ad.Config) -> None:
    before = cfg.plist.read_bytes()
    host = FakeHost()

    def crash_on_second_reload(count: int) -> None:
        if count == 2:
            raise Crash()

    host.on_reload = crash_on_second_reload
    with pytest.raises(Crash):
        cycle(cfg, host, FakeProber({(ad.LIVE_PORT, NEW): False}))
    assert cfg.journal.exists() and cfg.plist.read_bytes() == before

    host2, prober2 = FakeHost(), FakeProber()
    result = cycle(cfg, host2, prober2)
    assert result["status"] == "RECONCILED_ROLLED_BACK"
    assert host2.reloads == [before]
    assert prober2.calls[-1]["commit"] == OLD and prober2.calls[-1]["port"] == ad.LIVE_PORT


def test_reconciled_rollback_that_fails_probe_holds(cfg: ad.Config) -> None:
    host = FakeHost()
    host.on_reload = lambda count: (_ for _ in ()).throw(Crash()) if count == 2 else None
    with pytest.raises(Crash):
        cycle(cfg, host, FakeProber({(ad.LIVE_PORT, NEW): False}))
    result = cycle(cfg, FakeHost(), FakeProber({(ad.LIVE_PORT, OLD): False}))
    assert result["status"] == "RECONCILED_ROLLBACK_FAILED"
    assert cfg.hold_file.exists() and not cfg.journal.exists()
    assert ad.last_receipt(cfg.state_dir)["outcome"] == "ROLLBACK_FAILED"


def test_pending_journal_is_reconciled_even_under_hold(cfg: ad.Config) -> None:
    host = FakeHost()
    probe = FakeProber(
        hook=lambda c: (_ for _ in ()).throw(Crash()) if c["port"] == ad.LIVE_PORT else None
    )
    with pytest.raises(Crash):
        cycle(cfg, host, probe)  # crash after reload, during the live probe
    ad._set_hold(cfg, "owner pressed hold after the crash")
    host2, prober2 = FakeHost(), FakeProber()
    result = cycle(cfg, host2, prober2)
    assert result["status"] == "RECONCILED_DEPLOYED"  # live candidate passes: keep it
    assert not cfg.journal.exists() and cfg.hold_file.exists()
    assert not any(c[:1] == ["uv"] or "fetch" in c for c in host2.calls)
    # HOLD still blocks any new switch afterwards.
    assert cycle(cfg, FakeHost(), FakeProber())["status"] == "HELD"


@pytest.mark.parametrize("content", ["{not json", '{"schema": "other"}', '{"schema": "%s"}'])
def test_corrupt_journal_is_quarantined_with_hold(cfg: ad.Config, content: str) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.journal.write_text(content.replace("%s", ad.JOURNAL_SCHEMA))
    host = FakeHost()
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "RECONCILED_JOURNAL_CORRUPT"
    assert not cfg.journal.exists() and cfg.hold_file.exists()
    assert list(cfg.state_dir.glob("pending-switch.corrupt.*.json"))
    assert ad.last_receipt(cfg.state_dir)["outcome"] == "JOURNAL_CORRUPT"
    assert host.reloads == []
    assert cycle(cfg, host, FakeProber())["status"] == "HELD"  # no crash loop


# ---------------------------------------------- coordination with #526 manager


def test_foreign_plist_sets_hold_and_is_recorded(cfg: ad.Config) -> None:
    manual = cfg.deployments / f"r1-{PR_HEAD}"
    (manual / "scripts/ops").mkdir(parents=True)
    (manual / ad.ENTRYPOINT).write_text("")
    shared_python = cfg.state_dir.parents[3] / "shared/clone/.venv/bin/python"
    cfg.plist.write_bytes(live_plist(manual, str(shared_python)))  # manual #526 rebind
    host, prober = FakeHost(), FakeProber()
    result = cycle(cfg, host, prober)
    assert result["status"] == "FOREIGN_PLIST"
    assert cfg.hold_file.exists() and prober.calls == [] and host.reloads == []
    assert ad.last_receipt(cfg.state_dir)["outcome"] == "FOREIGN_PLIST"
    assert cycle(cfg, host, prober)["status"] == "HELD"
    # Owner: adopt the new plist, release, and auto-deploy resumes.
    home = str(cfg.state_dir.parents[2])
    assert ad.main(["adopt", "--home", home]) == 0
    assert ad.main(["release", "--home", home]) == 0
    host.clock += ad.MAX_BACKOFF_SECONDS
    assert cycle(cfg, host, prober)["status"] == "DEPLOYED"


def test_plist_changed_during_cycle_is_foreign(cfg: ad.Config) -> None:
    def manual_rebind(call: dict[str, Any]) -> None:
        if call["port"] == 50123:
            cfg.plist.write_bytes(live_plist(cfg.deployments / f"r1-{PR_HEAD}"))

    host = FakeHost()
    result = cycle(cfg, host, FakeProber(hook=manual_rebind))
    assert result["status"] == "FOREIGN_PLIST" and host.reloads == []
    assert cfg.hold_file.exists()


def test_manager_lock_busy_blocks_the_switch(cfg: ad.Config) -> None:
    host = FakeHost()
    host.lock_fails = True
    before = cfg.plist.read_bytes()
    assert cycle(cfg, host, FakeProber())["status"] == "BLOCKED_MANAGER_BUSY"
    assert cfg.plist.read_bytes() == before and host.reloads == []


def test_real_manager_lock_uses_the_durable_ledger_lock(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.ops import mcp_gateway_durable as durable

    entered: list[Path] = []

    class Lock:
        def __init__(self, path: Path, *, timeout: float) -> None:
            entered.append(path)

        def __enter__(self) -> "Lock":
            return self

        def __exit__(self, *_exc: object) -> None:
            entered.append(Path("released"))

    monkeypatch.setattr(durable, "InterProcessLock", Lock)
    monkeypatch.setattr(durable, "GATEWAY_STATE_ROOT", cfg.gateway_root)
    monkeypatch.setattr(durable, "GATEWAY_LOCK", cfg.gateway_root / "ledger.lock")
    with ad.Host().manager_lock(cfg):
        pass
    assert entered == [durable.GATEWAY_LOCK, Path("released")]


def test_manager_lock_path_is_the_managers_own_under_a_non_default_root(tmp_path: Path) -> None:
    root = tmp_path / "custom-gateway-root"
    code = (
        "import json, sys; from pathlib import Path\n"
        "from scripts.ops import mcp_gateway_durable as d\n"
        "from scripts.ops import nexus_gateway_auto_deploy as ad\n"
        f"cfg = ad.Config.default(Path({str(tmp_path)!r}), gateway_root=Path({str(root)!r}))\n"
        "print(json.dumps([str(ad.Host().manager_lock_path(cfg)), str(d.GATEWAY_LOCK)]))\n"
    )
    env = {**os.environ, "NEXUS_GATEWAY_STATE_ROOT": str(root), "PYTHONDONTWRITEBYTECODE": "1"}
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    deployer_path, manager_path = json.loads(out.strip().splitlines()[-1])
    assert deployer_path == manager_path == str(root / "ledger.lock")


def test_manager_lock_refuses_a_different_manager_root(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.ops import mcp_gateway_durable as durable

    monkeypatch.setattr(durable, "GATEWAY_STATE_ROOT", cfg.gateway_root.parent / "elsewhere")
    with pytest.raises(ad.DeployError, match="MANAGER_LOCK_UNAVAILABLE"):
        ad.Host().manager_lock_path(cfg)


def test_config_honours_nexus_gateway_plist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_GATEWAY_PLIST", str(tmp_path / "custom.plist"))
    assert ad.Config.default(tmp_path).plist == tmp_path / "custom.plist"
    monkeypatch.delenv("NEXUS_GATEWAY_PLIST")
    assert ad.Config.default(tmp_path).plist.name == f"{ad.GATEWAY_LABEL}.plist"


# ---------------------------------------------------------------- pin bumps


def test_no_deploy_while_a_pin_bump_pr_is_in_flight(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    pulls = [
        {
            "number": 2122,
            "title": "build(deps): pin nexus-runtime a72e223",
            "head": {"ref": "x"},
            "updated_at": NOW_ISO,
        }
    ]
    result = cycle(cfg, host, prober, green_api(open_pulls=pulls))
    assert result["status"] == "PIN_BUMP_IN_FLIGHT"
    assert result["pin_bumps"]["pull_requests"] == [2122]
    assert prober.calls == [] and not any(c[:1] == ["uv"] for c in host.calls)
    anchor = [
        {
            "number": 2125,
            "title": "ci: x",
            "head": {"ref": "ci/2123-trusted-anchor-pr2122"},
            "updated_at": NOW_ISO,
        }
    ]
    assert cycle(cfg, host, prober, green_api(open_pulls=anchor))["status"] == "PIN_BUMP_IN_FLIGHT"

    def broken(path: str) -> Any:
        if "state=open" in path:
            raise ad.DeployError("GH_API_FAILED")
        return green_api()(path)

    assert cycle(cfg, host, prober, broken)["status"] == "PIN_BUMP_UNKNOWN"


@pytest.mark.parametrize(
    "branch", ["auto/workforce-pin-glm-5-abcdef123456", "auto/workforce-anchor-x-0123456789ab"]
)
def test_autoupdater_branches_count_as_pin_bumps(branch: str) -> None:
    pulls = [{"number": 7, "title": "chore", "head": {"ref": branch}, "updated_at": NOW_ISO}]
    result = ad.pin_bumps_in_flight(green_api(open_pulls=pulls), now=NOW)
    assert result == {
        "verdict": "IN_FLIGHT",
        "pull_requests": [7],
        "ignored_stale": [],
        "ignored_draft": [],
        "ignored_parked": [],
        "parked": [],
        "warnings": [],
    }


def test_pin_bump_detected_from_changed_files() -> None:
    pulls = [{"number": 8, "title": "misc", "head": {"ref": "feat/x"}, "updated_at": NOW_ISO}]
    api = green_api(open_pulls=pulls, pull_files={8: ["uv.lock", "a.py"]})
    assert ad.pin_bumps_in_flight(api, now=NOW)["verdict"] == "IN_FLIGHT"
    clean = green_api(open_pulls=pulls, pull_files={8: ["a.py"]})
    assert ad.pin_bumps_in_flight(clean, now=NOW)["verdict"] == "CLEAR"


def test_stale_pin_bump_pr_does_not_block_forever() -> None:
    pulls = [
        {
            "number": 9,
            "title": "pin nexus-runtime old",
            "head": {"ref": "x", "sha": "9" * 40},
            "created_at": "2025-01-01T00:00:00Z",
            # A bot comment yesterday must not make an abandoned PR look fresh.
            "updated_at": NOW_ISO,
        }
    ]
    api = green_api(open_pulls=pulls, pushed_at={"9" * 40: "2025-01-01T00:00:00Z"})
    result = ad.pin_bumps_in_flight(api, now=NOW)
    assert result["verdict"] == "CLEAR" and result["ignored_stale"] == [9]
    assert result["warnings"] == ["STALE_PIN_PR_IGNORED #9"]
    fresh = green_api(open_pulls=pulls, pushed_at={"9" * 40: NOW_ISO})
    assert ad.pin_bumps_in_flight(fresh, now=NOW)["verdict"] == "IN_FLIGHT"


def test_stale_pin_pr_is_reported_in_status_and_receipt(cfg: ad.Config) -> None:
    pulls = [
        {
            "number": 9,
            "title": "pin nexus-runtime",
            "head": {"ref": "x", "sha": "9" * 40},
            "created_at": "2025-01-01T00:00:00Z",
        }
    ]
    api = green_api(open_pulls=pulls, pushed_at={"9" * 40: "2025-01-01T00:00:00Z"})
    result = cycle(cfg, FakeHost(), FakeProber(), api)
    assert result["status"] == "DEPLOYED"
    assert result["warnings"] == ["STALE_PIN_PR_IGNORED #9"]
    assert result["receipt"]["warnings"] == ["STALE_PIN_PR_IGNORED #9"]
    assert json.loads((cfg.state_dir / "status.json").read_text())["warnings"] == [
        "STALE_PIN_PR_IGNORED #9"
    ]


def test_pin_bump_files_beyond_first_page(cfg: ad.Config) -> None:
    def api(path: str) -> Any:
        if "/pulls?state=open" in path:
            return (
                [{"number": 5, "title": "big", "head": {"ref": "feat/big"}}]
                if path.endswith("page=1")
                else []
            )
        if "/pulls/5/files?" in path:
            if path.endswith("page=1"):
                return [{"filename": f"f{i}.py"} for i in range(100)]
            if path.endswith("page=2"):
                return [{"filename": "uv.lock"}]
            return []
        return green_api()(path)

    assert ad.pin_bumps_in_flight(api, now=NOW)["pull_requests"] == [5]


def test_pin_bump_pages_are_all_read() -> None:
    def api(path: str) -> Any:
        if "state=open" in path:
            page = int(path.rsplit("page=", 1)[1])
            if page == 1:
                return [
                    {"number": i, "title": "x", "head": {"ref": "y"}, "updated_at": NOW_ISO}
                    for i in range(100)
                ]
            if page == 2:
                return [
                    {
                        "number": 500,
                        "title": "pin nexus-runtime",
                        "head": {"ref": "z"},
                        "updated_at": NOW_ISO,
                    }
                ]
            return []
        return []

    assert ad.pin_bumps_in_flight(api, now=NOW)["pull_requests"] == [500]


def test_pin_bump_rechecked_right_before_switch(cfg: ad.Config) -> None:
    opened: list[dict[str, Any]] = []

    def open_pin_pr(call: dict[str, Any]) -> None:
        if call["port"] == 50123:
            opened.append({
                "number": 77,
                "title": "x",
                "head": {"ref": "auto/workforce-pin-m-0"},
                "updated_at": NOW_ISO,
            })

    def api(path: str) -> Any:
        if "/pulls?state=open" in path:
            return list(opened) if path.endswith("page=1") else []
        return green_api()(path)

    host = FakeHost()
    result = cycle(cfg, host, FakeProber(hook=open_pin_pr), api)
    assert result["status"] == "PIN_BUMP_IN_FLIGHT" and host.reloads == []


# ----------------------------------------------------------------- misc / cli


def test_launchd_reload_is_delegated_to_the_durable_manager(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.ops import mcp_gateway_durable as durable

    seen: list[Path] = []
    monkeypatch.setattr(durable, "reload_gateway_launch_agent", seen.append)
    ad.Host().reload_service(cfg.plist, ad.GATEWAY_LABEL)
    assert seen == [cfg.plist]
    with pytest.raises(ad.DeployError, match="GATEWAY_LABEL_MISMATCH"):
        ad.Host().reload_service(cfg.plist, "com.example.other")


def test_durable_reload_primitive_retries_bootstrap_and_fails_closed(tmp_path: Path) -> None:
    from scripts.ops import mcp_gateway_durable as durable

    plist = tmp_path / durable.GATEWAY_PLIST_FILENAME
    calls: list[list[str]] = []
    codes = iter([0, 5, 0])

    def run(argv, **_kw):
        calls.append(argv)
        return SimpleNamespace(returncode=next(codes), stderr="io error")

    durable.reload_gateway_launch_agent(plist, run=run, sleep=lambda _s: None)
    assert [c[1] for c in calls] == ["bootout", "bootstrap", "bootstrap"]
    assert calls[0][2].endswith(f"/{durable.GATEWAY_LABEL}") and calls[1][3] == str(plist)

    failing = iter([0, 5, 5, 5])
    with pytest.raises(durable.GatewayContractError, match="bootstrap failed"):
        durable.reload_gateway_launch_agent(
            plist,
            run=lambda argv, **_kw: SimpleNamespace(returncode=next(failing), stderr="x"),
            sleep=lambda _s: None,
        )
    with pytest.raises(durable.GatewayContractError, match="plist identity"):
        durable.reload_gateway_launch_agent(tmp_path / "other.plist", run=run)


def _git(*args: str, cwd: Path | None = None) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@e.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@e.invalid",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env
    ).stdout.strip()


@pytest.mark.parametrize("health_has_repo_root", [True, False])
def test_drift_check_reads_auto_deploy_layout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], health_has_repo_root: bool
) -> None:
    """The drift LaunchAgent's separate clone must resolve an a1-<sha> deployment."""
    origin = tmp_path / "origin"
    _git("init", "-q", "-b", "main", str(origin))
    _git("commit", "-q", "--allow-empty", "-m", "base", cwd=origin)
    clone = tmp_path / "drift-clone"
    _git("clone", "-q", str(origin), str(clone))
    _git("commit", "-q", "--allow-empty", "-m", "new main", cwd=origin)
    head = _git("rev-parse", "HEAD", cwd=origin)
    # Deployer layout: bare repository + detached worktree deployments/a1-<sha>.
    gateway = tmp_path / "gateway-direct"
    _git("clone", "-q", "--bare", str(origin), str(gateway / "repository.git"))
    root = gateway / "deployments" / f"a1-{head}"
    _git(
        "--git-dir", str(gateway / "repository.git"), "worktree", "add", "--detach", str(root), head
    )
    state = tmp_path / "state"
    state.mkdir()
    receipt = {
        "schema": ad.RECEIPT_SCHEMA,
        "outcome": "DEPLOYED",
        "candidate_commit": head,
        "deployment_root": str(root),
        "finished_at": "2026-10-14T00:00:00Z",
    }
    (state / "receipts.jsonl").write_text(json.dumps(receipt) + "\n")
    # The analysis clone has not fetched the deployed commit yet.
    assert subprocess.run(["git", "-C", str(clone), "cat-file", "-e", head]).returncode != 0
    payload = {"git_head": head, **({"repo_root": str(root)} if health_has_repo_root else {})}
    code = drift.main(
        ["--repo", str(clone), "--json", "--offline", "--auto-deploy-state", str(state)],
        fetch_health=lambda _u: payload,
    )
    report = json.loads(capsys.readouterr().out)
    assert (code, report["verdict"], report["findings"]) == (0, "OK", [])
    assert report["git_head"] == head and report["published_base"] == head
    assert report["auto_deploy"]["deployment_root"] == str(root)


def test_smoke_probe_uses_the_candidate_venv_python(cfg: ad.Config) -> None:
    prober = FakeProber()
    cycle(cfg, FakeHost(), prober)
    venv_python = cfg.venvs / f"a1-{NEW}" / "bin" / "python"
    assert [c["python"] for c in prober.calls] == [venv_python, venv_python]
    assert all("shared" not in str(c["python"]) for c in prober.calls)


@pytest.mark.parametrize(
    ("breakage", "reason"),
    [
        ("python", "PREDECESSOR_PYTHON_MISSING"),
        ("deployment", "PREDECESSOR_DEPLOYMENT_MISSING"),
    ],
)
def test_switch_refused_when_rollback_would_be_impossible(
    cfg: ad.Config, tmp_path: Path, breakage: str, reason: str
) -> None:
    if breakage == "python":
        (tmp_path / "shared/clone/.venv/bin/python").unlink()
    else:
        (cfg.deployments / f"r1-{OLD}" / ad.ENTRYPOINT).unlink()
    host = FakeHost()
    before = cfg.plist.read_bytes()
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "BLOCKED_NO_ROLLBACK"
    assert result["receipt"]["reason"] == reason and result["receipt"]["switched"] is False
    assert cfg.plist.read_bytes() == before and host.reloads == []


def test_run_refuses_inside_the_gateway_process(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(ad.TOKEN_ENV, "tok")
    host = FakeHost()
    code = ad.main(
        ["run", "--home", str(cfg.state_dir.parents[2])],
        host=host,
        prober=FakeProber(),
        api_get=green_api(),
    )
    assert code == 2 and json.loads(capsys.readouterr().out)["error"] == "IN_GATEWAY_PROCESS"
    assert host.calls == []


def test_error_path_writes_status_json(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(ad.TOKEN_ENV, raising=False)
    host = FakeHost()
    host.origin = "x"  # not reached: fetch fails first below
    host.run = lambda argv, **kw: _done(code=1, stderr="git broke")  # type: ignore[method-assign]
    code = ad.main(
        ["run", "--home", str(cfg.state_dir.parents[2])],
        host=host,
        prober=FakeProber(),
        api_get=green_api(),
    )
    assert code == 2
    status = json.loads((cfg.state_dir / "status.json").read_text())
    assert status["status"] == "ERROR" and "ORIGIN_URL_FAILED" in status["error"]


def test_verify_commit_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    assert ad.main(["verify-commit", NEW], api_get=green_api()) == 0
    assert ad.main(["verify-commit", NEW], api_get=green_api(conclusion="failure")) == 1
    assert (
        ad.main(["verify-commit", NEW], api_get=green_api(main_tip=PR_HEAD, relation="behind")) == 1
    )
    assert ad.main(["verify-commit", "nope"], api_get=green_api()) == 2


# ------------------------------------------------------- real Prober over HTTP


REPO_ROOT_FOR_GB077 = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _gateway_health_hmac_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-test host key (#2226); the GB-077 subprocess inherits the env."""
    monkeypatch.setenv(KEY_FILE_ENV, str(tmp_path / "health-hmac.key"))


def _health(commit: str, *, status: str = "ok") -> dict[str, Any]:
    return {
        "status": status,
        "server": "nexus-mcp-gateway",
        "reload_required": False,
        "git_head": commit,
        "repo_head_at_start": commit,
        "repo_head_current": commit,
        # GB-077 requires the hash of the evaluated root, i.e. this tree.
        "repo_root_hmac_sha256": path_hmac(
            "repo_root", str(REPO_ROOT_FOR_GB077), load_or_create_key()
        ),
        "server_instance_id": "i",
        "tool_manifest_revision": "r",
        "permission_policy_hash": "p",
        "full_tool_schema_hash": "f",
    }


@contextlib.contextmanager
def fake_gateway(
    health: dict[str, Any], tools: int, is_error: bool, health_delay: float = 0.0
) -> Iterator[int]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_a: Any) -> None:
            return

        def _send(self, payload: Any) -> None:
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if health_delay:
                import time

                time.sleep(health_delay)
            self._send(health)

        def do_POST(self) -> None:
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert self.headers["Authorization"] == "Bearer tok"
            if request["method"] == "tools/list":
                self._send({"result": {"tools": [{"name": f"t{i}"} for i in range(tools)]}})
            else:
                self._send({"result": {"isError": is_error}})

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    ("health_status", "tools", "is_error", "failing"),
    [
        ("ok", 3, False, set()),
        ("degraded", 3, False, {"health", "gb077"}),
        ("ok", 0, False, {"tools_list"}),
        ("ok", 3, True, {"gateway_status"}),
    ],
)
def test_real_prober_against_fake_http_gateway(
    health_status: str, tools: int, is_error: bool, failing: set[str]
) -> None:
    with fake_gateway(_health(NEW, status=health_status), tools, is_error) as port:
        result = ad.Prober(ad.Host()).probe(
            port=port,
            token="tok",
            commit=NEW,
            root=REPO_ROOT,
            python=Path(sys.executable),
            timeout=10,
        )
    assert {name for name, check in result["checks"].items() if not check["ok"]} == failing
    assert result["ok"] is (not failing)


def test_real_prober_times_out_on_wrong_commit() -> None:
    host = ad.Host()
    with fake_gateway(_health(OLD), 3, False) as port:
        result = ad.Prober(host).probe(
            port=port,
            token="tok",
            commit=NEW,
            root=REPO_ROOT,
            python=Path(sys.executable),
            timeout=0,
        )
    assert result["ok"] is False and set(result["checks"]) == {"health"}


def test_spare_wrapper_really_isolates_gateway_startup_state(tmp_path: Path) -> None:
    """Start the real Gateway entrypoint through the spare-probe wrapper for a few
    seconds: startup writes land in the probe dir, a sentinel live dir is untouched."""
    import socket
    import time

    if shutil.which("bash") is None:
        pytest.skip("bash unavailable")
    home = tmp_path / "home"
    cfg = ad.Config.default(home, canonical_state_dir=tmp_path / "live-state")
    cfg.canonical_state_dir.mkdir(parents=True)
    (cfg.canonical_state_dir / "sentinel").write_text("live")
    probe_state = tmp_path / "probe-state"
    probe_state.mkdir()
    cfg.env_file.parent.mkdir(parents=True)
    cfg.env_file.write_text("export NEXUS_MCP_GATEWAY_TOKEN=probe-token\n")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    command = ad.wrapper_command(cfg, REPO_ROOT, Path(sys.executable), port, state_dir=probe_state)
    env = {k: v for k, v in os.environ.items() if not k.startswith("NEXUS_")}
    env.update(HOME=str(home), PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.Popen(
        ["bash", "-c", command],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 120
        up = False
        while not up and time.monotonic() < deadline and proc.poll() is None:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                up = True
            except OSError:
                time.sleep(0.5)
        assert up, proc.stderr.read().decode()[-2000:] if proc.stderr else "gateway did not start"
        # The same read-only status call the smoke probe makes; it touches state.
        status = ad.Prober(ad.Host())._http(
            f"http://127.0.0.1:{port}/mcp",
            body={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "nexus_gateway_status", "arguments": {}},
            },
            token="probe-token",
        )
        assert "result" in status
        assert any(probe_state.iterdir()), "the probe instance wrote nothing into its state dir"
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, 15)
        proc.wait(timeout=30)
    assert sorted(p.name for p in cfg.canonical_state_dir.iterdir()) == ["sentinel"]
    assert (cfg.canonical_state_dir / "sentinel").read_text() == "live"


OLD_ISO = "2025-01-01T00:00:00Z"


def test_fresh_pin_pr_with_an_old_head_commit_blocks() -> None:
    """Round 3 P1: a PR opened minutes ago carrying a 4-day-old commit is in flight."""
    pulls = [
        {
            "number": 11,
            "title": "pin nexus-runtime",
            "head": {"ref": "x", "sha": "e" * 40},
            "created_at": NOW_ISO,
        }
    ]
    api = green_api(open_pulls=pulls, pushed_at={"e" * 40: OLD_ISO})
    result = ad.pin_bumps_in_flight(api, now=NOW)
    assert result["verdict"] == "IN_FLIGHT" and result["warnings"] == []


@pytest.mark.parametrize(
    "event",
    [
        {"event": "head_ref_force_pushed", "created_at": NOW_ISO},
        {"event": "committed", "committer": {"date": NOW_ISO}},
    ],
)
def test_old_pin_pr_with_a_recent_push_blocks(event: dict[str, Any]) -> None:
    pulls = [
        {
            "number": 12,
            "title": "pin nexus-runtime",
            "head": {"ref": "x", "sha": "e" * 40},
            "created_at": OLD_ISO,
        }
    ]
    api = green_api(
        open_pulls=pulls,
        pushed_at={"e" * 40: OLD_ISO},
        timeline={12: [{"event": "commented", "created_at": NOW_ISO}, event]},
    )
    assert ad.pin_bumps_in_flight(api, now=NOW)["verdict"] == "IN_FLIGHT"
    quiet = green_api(
        open_pulls=pulls,
        pushed_at={"e" * 40: OLD_ISO},
        timeline={12: [{"event": "commented", "created_at": NOW_ISO}]},
    )
    assert ad.pin_bumps_in_flight(quiet, now=NOW)["verdict"] == "CLEAR"


def _fail_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(cfg: ad.Config, reason: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(ad, "_set_hold", boom)


def _crash_on_rollback_reload(cfg: ad.Config) -> None:
    host = FakeHost()
    host.on_reload = lambda count: (_ for _ in ()).throw(Crash()) if count == 2 else None
    with pytest.raises(Crash):
        cycle(cfg, host, FakeProber({(ad.LIVE_PORT, NEW): False}))


def test_hold_write_failure_keeps_the_journal_on_rollback_failed(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    _crash_on_rollback_reload(cfg)
    _fail_hold(monkeypatch)
    with pytest.raises(OSError, match="disk full"):
        cycle(cfg, FakeHost(), FakeProber({(ad.LIVE_PORT, OLD): False}))
    assert cfg.journal.exists()  # still guarded: the next cycle reconciles again
    assert ad.read_receipts(cfg.state_dir) == []
    monkeypatch.undo()
    result = cycle(cfg, FakeHost(), FakeProber({(ad.LIVE_PORT, OLD): False}))
    assert result["status"] == "RECONCILED_ROLLBACK_FAILED"
    assert cfg.hold_file.exists() and not cfg.journal.exists()


def test_hold_write_failure_keeps_a_corrupt_journal_in_place(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.journal.write_text("{not json")
    _fail_hold(monkeypatch)
    with pytest.raises(OSError, match="disk full"):
        cycle(cfg, FakeHost(), FakeProber())
    assert cfg.journal.read_text() == "{not json"
    assert not list(cfg.state_dir.glob("pending-switch.corrupt.*.json"))
    assert ad.read_receipts(cfg.state_dir) == []


def _crash_journal(cfg: ad.Config) -> dict[str, Any]:
    host = FakeHost()
    host.on_reload = lambda _count: (_ for _ in ()).throw(Crash())
    with pytest.raises(Crash):
        cycle(cfg, host, FakeProber())
    return json.loads(cfg.journal.read_text())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda j: j["receipt"].pop("probes"),
        lambda j: j["receipt"].pop("deployment_root"),
        lambda j: j["receipt"].update(started_epoch="soon"),
        lambda j: j.update(new_plist_sha256="nope"),
        lambda j: j.pop("candidate_python"),
        lambda j: j.update(receipt=[]),
    ],
    ids=["no-probes", "no-root", "bad-epoch", "bad-sha", "no-python", "receipt-list"],
)
def test_parseable_but_incomplete_journal_is_quarantined(
    cfg: ad.Config, mutate: Callable[[dict[str, Any]], Any]
) -> None:
    journal = _crash_journal(cfg)
    mutate(journal)
    cfg.journal.write_text(json.dumps(journal))
    host = FakeHost()
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "RECONCILED_JOURNAL_CORRUPT"
    assert cfg.hold_file.exists() and not cfg.journal.exists()
    assert host.reloads == []


def test_unexpected_reconcile_error_quarantines_with_hold(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    _crash_journal(cfg)

    def explode(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(ad._Cycle, "finish_switch", explode)
    result = cycle(cfg, FakeHost(), FakeProber())
    # #2198 review: a journal that passed validation is never quarantined; it is
    # kept with HOLD so the failure does not repeat every cycle.
    assert result["status"] == "RECONCILED_RECONCILE_FAILED"
    assert "RECONCILE_FAILED:RuntimeError" in result["receipt"]["reason"]
    assert cfg.hold_file.exists() and cfg.journal.exists()
    assert not list(cfg.state_dir.glob("pending-switch.corrupt.*.json"))
    host = FakeHost()
    assert cycle(cfg, host, FakeProber())["status"] == "HELD"
    assert cfg.journal.exists() and host.reloads == []


def test_busy_manager_during_reconcile_keeps_the_journal(cfg: ad.Config) -> None:
    _crash_journal(cfg)
    host = FakeHost()
    host.lock_fails = True
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "RECONCILED_BLOCKED_MANAGER_BUSY"
    assert cfg.journal.exists() and not cfg.hold_file.exists()


# Documented timeline payload (docs.github.com/rest/using-the-rest-api/issue-event-types#committed):
# `author`/`committer` carry name/email/date; some sources omit `date`, and a
# committed event always carries the commit `sha`.
def _committed_event(sha: str, date: str | None) -> dict[str, Any]:
    person: dict[str, Any] = {"name": "alice", "email": "alice@example.invalid"}
    if date is not None:
        person["date"] = date
    return {"event": "committed", "sha": sha, "author": dict(person), "committer": person}


def _old_pin_pr(number: int) -> list[dict[str, Any]]:
    return [
        {
            "number": number,
            "title": "pin nexus-runtime",
            "head": {"ref": "x", "sha": "e" * 40},
            "created_at": OLD_ISO,
        }
    ]


def test_committed_event_without_a_date_does_not_block_forever() -> None:
    """Round 4: `committer` without `date` (e.g. {"login": "alice"}) is no timestamp."""
    for event in (
        {"event": "committed", "committer": {"login": "alice"}},
        _committed_event("d" * 40, None),
    ):
        api = green_api(
            open_pulls=_old_pin_pr(13),
            pushed_at={"e" * 40: OLD_ISO, "d" * 40: OLD_ISO},
            timeline={13: [event]},
        )
        result = ad.pin_bumps_in_flight(api, now=NOW)
        assert result["verdict"] == "CLEAR", event
        assert result["warnings"] == ["STALE_PIN_PR_IGNORED #13"]


def test_committed_event_falls_back_to_the_commit_date_via_sha() -> None:
    api = green_api(
        open_pulls=_old_pin_pr(14),
        pushed_at={"e" * 40: OLD_ISO, "d" * 40: NOW_ISO},
        timeline={14: [_committed_event("d" * 40, None)]},
    )
    assert ad.pin_bumps_in_flight(api, now=NOW)["verdict"] == "IN_FLIGHT"


def test_committed_event_reads_documented_author_or_committer_date() -> None:
    event = _committed_event("d" * 40, None)
    event["author"]["date"] = NOW_ISO
    api = green_api(
        open_pulls=_old_pin_pr(15),
        pushed_at={"e" * 40: OLD_ISO, "d" * 40: OLD_ISO},
        timeline={15: [event]},
    )
    assert ad.pin_bumps_in_flight(api, now=NOW)["verdict"] == "IN_FLIGHT"


@pytest.mark.parametrize(
    "payload",
    [
        plistlib.dumps(["not", "a", "dict"]),
        plistlib.dumps({"Label": ad.GATEWAY_LABEL, "ProgramArguments": "zsh"}),
        b"not a plist",
    ],
    ids=["plist-array", "argv-not-list", "garbage"],
)
def test_journal_with_malformed_embedded_plist_is_quarantined(
    cfg: ad.Config, payload: bytes
) -> None:
    import base64

    journal = _crash_journal(cfg)
    journal["previous_plist_b64"] = base64.b64encode(payload).decode("ascii")
    cfg.journal.write_text(json.dumps(journal))
    host = FakeHost()
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "RECONCILED_JOURNAL_CORRUPT"
    assert cfg.hold_file.exists() and not cfg.journal.exists()
    assert host.reloads == []


def test_live_root_rejects_non_dict_plist() -> None:
    with pytest.raises(ad.DeployError, match="NOT_A_DICT"):
        ad.live_root(plistlib.dumps(["x"]))


# ------------------------------------------------- pinned nexus-core (#2181)


def _core_head(checkout: Path) -> str:
    return _fixture_git(checkout, "rev-parse", "HEAD")


def test_candidate_runs_the_core_revision_its_tree_pins(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    result = cycle(cfg, host, prober)
    assert result["status"] == "DEPLOYED"
    checkout = cfg.core_checkouts / CORE.pin
    receipt = ad.last_receipt(cfg.state_dir)
    digest = receipt["core"]["source_digest"]
    assert receipt["core"] == {
        "revision": CORE.pin,
        "root": str(checkout),
        "repository": ad.CORE_REPOSITORY_URL,
        "source_digest": digest,
        "source_digest_status": "COMPUTED",
    }
    # A clean, detached checkout at exactly the pinned commit.
    assert _core_head(checkout) == CORE.pin
    assert _fixture_git(checkout, "status", "--porcelain", "--untracked-files=all") == ""
    assert _fixture_git(checkout, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"  # detached
    # Both the spare-port probe and the live wrapper export it after the env file.
    export = f'export NEXUS_CORE_REPO_ROOT="{checkout}" ; '
    live_command = plistlib.loads(cfg.plist.read_bytes())["ProgramArguments"][2]
    for command in (host.started[0], live_command):
        assert export in command
        assert command.index(export) > command.index(f'source "{cfg.env_file}"')
    # Every candidate probe demands that exact Core.
    assert [c["core"] for c in prober.calls] == [receipt["core"], receipt["core"]]


def test_core_commit_already_present_is_not_fetched_again(cfg: ad.Config) -> None:
    ad.materialize_core(cfg, FakeHost(), CORE.pin)
    host = FakeHost()
    host.core_fetch_fails = True  # would reject if a fetch were attempted
    assert cycle(cfg, host, FakeProber())["status"] == "DEPLOYED"
    assert not any("fetch" in c and str(cfg.core_bare_repo) in c for c in host.calls)


@pytest.mark.parametrize("pin", ["not-a-sha", "abc123", "A" * 40, "g" * 40, None], ids=str)
def test_bad_core_pin_rejects_the_candidate(cfg: ad.Config, pin: str | None) -> None:
    before = cfg.plist.read_bytes()
    host = FakeHost()
    host.core_pin = pin  # type: ignore[assignment]
    if pin is None:
        host.core_pin = CORE.pin + '"\nCANONICAL_CORE_REVISION = "' + CORE.other  # two pins
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "REJECTED_BUILD"
    assert result["receipt"]["reason"].startswith("DeployError:CORE_PIN_INVALID")
    assert not host.started and cfg.plist.read_bytes() == before
    assert not any(c[:1] == ["uv"] for c in host.calls)
    assert not cfg.core_checkouts.exists()
    # Deterministic: the same candidate is not rebuilt.
    assert cycle(cfg, host, FakeProber(), force=False)["status"] == "CANDIDATE_REJECTED_BEFORE"


def test_read_core_pin_parses_text_only(tmp_path: Path) -> None:
    (tmp_path / ad.CORE_PIN_FILE).parent.mkdir(parents=True)
    (tmp_path / ad.CORE_PIN_FILE).write_text("import sys\nsys.exit(3)\n" + _pin_source(CORE.pin))
    assert ad.read_core_pin(tmp_path) == CORE.pin  # parsed, never executed
    assert ad.read_core_pin(REPO_ROOT) == ad.read_core_pin(REPO_ROOT)
    from nexus.orchestrator import canonical_core_transport as transport

    assert ad.read_core_pin(REPO_ROOT) == transport.CANONICAL_CORE_REVISION
    with pytest.raises(ad.DeployError, match="CORE_PIN_INVALID"):
        ad.read_core_pin(tmp_path / "missing")


@pytest.mark.parametrize("failure", ["fetch", "unknown_commit"])
def test_core_fetch_failure_rejects_and_never_deploys_without_core(
    cfg: ad.Config, failure: str
) -> None:
    before = cfg.plist.read_bytes()
    host = FakeHost()
    if failure == "fetch":
        host.core_fetch_fails = True
        expected = "CORE_FETCH_FAILED"
    else:
        host.core_pin = "d" * 40  # not on any nexus-core branch
        expected = "CORE_COMMIT_NOT_FOUND"
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "BUILD_FAILED"
    assert expected in result["receipt"]["reason"]
    assert not host.started and not host.reloads and cfg.plist.read_bytes() == before
    assert "core" not in result["receipt"]


def _soil(checkout: Path, dirt: str) -> None:
    if dirt == "untracked":
        (checkout / "product" / "shadow.py").write_text("x = 1\n")
    elif dirt == "ignored":
        # Ignored by *.pyc, yet importable as a sourceless module (#2246: bytecode
        # inside __pycache__ alone is no longer dirt).
        (checkout / "product" / "stray.pyc").write_bytes(b"x")
    elif dirt == "modified":
        (checkout / "product" / "__init__.py").write_text("patched = True\n")
    elif dirt == "wrong_head":
        _fixture_git(checkout, "checkout", "-q", "--detach", CORE.other)
    elif dirt == "half_created":  # a `git worktree add` killed before writing .git
        shutil.rmtree(checkout)
        (checkout / "product").mkdir(parents=True)
    else:
        raise AssertionError(dirt)


@pytest.mark.parametrize("dirt", ["untracked", "modified", "ignored", "wrong_head", "half_created"])
def test_unhealthy_unused_core_checkout_is_rebuilt(cfg: ad.Config, dirt: str) -> None:
    checkout = Path(ad.materialize_core(cfg, FakeHost(), CORE.pin)["root"])
    _soil(checkout, dirt)
    host = FakeHost()
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "DEPLOYED"
    core = result["receipt"]["core"]
    assert core["root"] == str(checkout) and core["rebuilt"]
    assert ad.core_checkout_problem(ad.Host(), checkout, CORE.pin) is None
    assert any(c[-2:] == ["worktree", "prune"] for c in host.calls)
    assert not ad.hold_reason(cfg, {})


@pytest.mark.parametrize(
    ("dirt", "problem"),
    [
        pytest.param("pycache", None, id="pycache"),
        pytest.param("nested_pycache", None, id="nested_pycache"),
        pytest.param("sourceless_pyc", "CORE_TREE_DIRTY", id="sourceless_pyc"),
        pytest.param("py_in_pycache", "CORE_TREE_DIRTY", id="py_in_pycache"),
        pytest.param("symlinked_pyc", "CORE_TREE_DIRTY", id="symlinked_pyc"),
        pytest.param("pycache_and_modified", "CORE_TREE_DIRTY", id="pycache_and_modified"),
    ],
)
def test_core_in_use_check_ignores_only_bytecode_caches(
    cfg: ad.Config, tmp_path: Path, dirt: str, problem: str | None
) -> None:
    """#2246 review: a stray __pycache__ in an in-use core/<sha> is not dirt (same
    rule as the host's Core identity); every other change still is."""
    checkout = Path(ad.materialize_core(cfg, FakeHost(), CORE.pin)["root"])
    cache = checkout / "product" / "__pycache__"
    cache.mkdir()
    (cache / "two.cpython-312.pyc").write_bytes(b"x")
    if dirt == "nested_pycache":
        (checkout / "product" / "protocol" / "__pycache__").mkdir()
        (checkout / "product" / "protocol" / "__pycache__" / "b.cpython-312.pyc").write_bytes(b"x")
    elif dirt == "sourceless_pyc":
        (checkout / "product" / "stray.pyc").write_bytes(b"x")
    elif dirt == "py_in_pycache":
        (cache / "evil.py").write_text("x = 1\n")
    elif dirt == "symlinked_pyc":
        target = tmp_path / "elsewhere.pyc"
        target.write_bytes(b"x")
        (cache / "link.cpython-312.pyc").symlink_to(target)
    elif dirt == "pycache_and_modified":
        (checkout / "product" / "two.py").write_text("patched = True\n")
    assert ad.core_checkout_problem(ad.Host(), checkout, CORE.pin) == problem
    if problem is None:
        # In use and only bytecode: materialize keeps it, no rebuild, no hold.
        _live_on_core(cfg, checkout, export=True, pin_file=True)
        assert "rebuilt" not in ad.materialize_core(cfg, FakeHost(), CORE.pin)


def _live_on_core(cfg: ad.Config, checkout: Path, *, export: bool, pin_file: bool) -> None:
    """Make the live plist run deployment a1-OLD on ``checkout``."""
    live = cfg.deployments / f"a1-{OLD}"
    (live / "scripts/ops").mkdir(parents=True)
    (live / ad.ENTRYPOINT).write_text("")
    if pin_file:
        (live / ad.CORE_PIN_FILE).parent.mkdir(parents=True)
        (live / ad.CORE_PIN_FILE).write_text(_pin_source(checkout.name))
    python = cfg.venvs / f"a1-{OLD}" / "bin" / "python"
    command = ad.wrapper_command(cfg, live, python, core_root=checkout if export else None)
    cfg.plist.write_bytes(ad.render_plist(cfg.plist.read_bytes(), command, live))
    ad.remember_plist(cfg, cfg.plist.read_bytes())


@pytest.mark.parametrize(("export", "pin_file"), [(True, False), (False, True), (True, True)])
@pytest.mark.parametrize("dirt", ["untracked", "half_created"])
def test_unhealthy_core_checkout_in_use_is_held_not_modified(
    cfg: ad.Config, dirt: str, export: bool, pin_file: bool
) -> None:
    checkout = Path(ad.materialize_core(cfg, FakeHost(), CORE.pin)["root"])
    _live_on_core(cfg, checkout, export=export, pin_file=pin_file)
    _soil(checkout, dirt)
    snapshot = sorted(str(p.relative_to(checkout)) for p in checkout.rglob("*"))
    before = cfg.plist.read_bytes()
    host = FakeHost()
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "BUILD_FAILED"
    assert "CORE_IN_USE_UNHEALTHY" in result["receipt"]["reason"]
    assert sorted(str(p.relative_to(checkout)) for p in checkout.rglob("*")) == snapshot
    assert not any("remove" in c or "prune" in c for c in host.calls if "core.git" in str(c))
    assert not host.started and cfg.plist.read_bytes() == before
    # No endless retries: the deployer holds until the Owner repairs and releases.
    assert "CORE_IN_USE_UNHEALTHY" in (ad.hold_reason(cfg, {}) or "") or cfg.hold_file.exists()
    assert cycle(cfg, FakeHost(), FakeProber())["status"] == "HELD"


def test_core_in_use_unknown_when_live_pin_file_is_malformed(cfg: ad.Config) -> None:
    checkout = Path(ad.materialize_core(cfg, FakeHost(), CORE.pin)["root"])
    _live_on_core(cfg, checkout, export=False, pin_file=True)
    (cfg.deployments / f"a1-{OLD}" / ad.CORE_PIN_FILE).write_text("CANONICAL_CORE_REVISION = 1\n")
    _soil(checkout, "untracked")
    with pytest.raises(ad.DeployError, match="CORE_IN_USE_UNKNOWN"):
        ad.materialize_core(cfg, FakeHost(), CORE.pin)
    assert (checkout / "product" / "shadow.py").exists()


def test_core_bare_repo_origin_must_be_nexus_core(cfg: ad.Config) -> None:
    ad.materialize_core(cfg, FakeHost(), CORE.pin)
    _fixture_git(cfg.core_bare_repo, "remote", "set-url", "origin", "https://evil.example/c.git")
    with pytest.raises(ad.DeployError, match="CORE_ORIGIN_MISMATCH"):
        ad.materialize_core(cfg, FakeHost(), CORE.pin)


def test_wrapper_exports_core_root_and_rejects_unsafe_core_path(cfg: ad.Config) -> None:
    root, python = Path("/d/a1-x"), Path("/v/bin/python")
    assert "NEXUS_CORE_REPO_ROOT" not in ad.wrapper_command(cfg, root, python)
    command = ad.wrapper_command(cfg, root, python, core_root=Path("/g/core/abc"))
    assert 'export NEXUS_CORE_REPO_ROOT="/g/core/abc" ; ' in command
    assert command.endswith(f'exec "{python}" "{root / ad.ENTRYPOINT}"')
    with pytest.raises(ad.DeployError, match="WRAPPER_PATH_UNSAFE"):
        ad.wrapper_command(cfg, root, python, core_root=Path('/g/core/"; rm -rf ~'))


def test_wrapper_exports_agy_runtime_authorization_only(cfg: ad.Config) -> None:
    """#2318: every rendered wrapper exports the narrow Agy flag, after the env
    file (which therefore cannot switch it off), and never the broad flag."""
    root, python = Path("/d/a1-x"), Path("/v/bin/python")
    digest = ("a" * 40, "sha256:" + "b" * 64)
    commands = [
        ad.wrapper_command(cfg, root, python),
        ad.wrapper_command(cfg, root, python, core_root=Path("/g/core/abc")),
        ad.wrapper_command(cfg, root, python, core_root=Path("/g/core/abc"), core_digest=digest),
        ad.wrapper_command(cfg, root, python, 50123, state_dir=Path("/probe")),
        ad.wrapper_command(cfg, root, python, controller_root=Path("/c/a1-x")),
    ]
    for command in commands:
        assert command.count("export NEXUS_AGY_RUNTIME_AUTHORIZED=1 ; ") == 1, command
        assert command.index("NEXUS_AGY_RUNTIME_AUTHORIZED=1") > command.index(
            f'source "{cfg.env_file}"'
        )
        assert command.index("NEXUS_AGY_RUNTIME_AUTHORIZED=1") < command.index("exec ")
        assert "NEXUS_EXTERNAL_RUNTIME_AUTHORIZED" not in command
        assert command.endswith(f'exec "{python}" "{root / ad.ENTRYPOINT}"')


def test_wrapper_agy_authorization_reaches_gateway_process_env(tmp_path: Path) -> None:
    """Run the rendered wrapper for real: the exec'd process sees the Agy flag
    even when the env file sets it to 0, and no broad external flag appears."""
    if shutil.which("bash") is None:
        pytest.skip("bash unavailable")
    cfg = ad.Config.default(tmp_path / "home")
    root = tmp_path / "deploy"
    root.mkdir()
    cfg.env_file.parent.mkdir(parents=True)
    cfg.env_file.write_text("export NEXUS_AGY_RUNTIME_AUTHORIZED=0\n")
    dump = tmp_path / "env.json"
    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        f"#!{sys.executable}\n"
        "import json, os\n"
        f"open({str(dump)!r}, 'w').write(json.dumps(dict(os.environ)))\n"
    )
    fake_python.chmod(0o755)
    command = ad.wrapper_command(cfg, root, fake_python)
    env = {k: v for k, v in os.environ.items() if not k.startswith("NEXUS_")}
    subprocess.run(["bash", "-c", command], env=env, check=True, timeout=60)
    seen = json.loads(dump.read_text())
    assert seen["NEXUS_AGY_RUNTIME_AUTHORIZED"] == "1"
    assert "NEXUS_EXTERNAL_RUNTIME_AUTHORIZED" not in seen


def test_deployed_plist_and_spare_probe_export_agy_runtime_authorization(
    cfg: ad.Config,
) -> None:
    """#2318: the plist a deploy writes (and the spare-port probe it starts)
    carries the narrow Agy flag; the broad external flag is never exported."""
    host, prober = FakeHost(), FakeProber()
    result = cycle(cfg, host, prober)
    assert result["status"] == "DEPLOYED"
    command = plistlib.loads(cfg.plist.read_bytes())["ProgramArguments"][2]
    for rendered in (command, host.started[0]):
        assert "export NEXUS_AGY_RUNTIME_AUTHORIZED=1 ; " in rendered
        assert "NEXUS_EXTERNAL_RUNTIME_AUTHORIZED" not in rendered
    assert "NEXUS_AGY_RUNTIME_AUTHORIZED=1" in ad._wrapper_tokens(cfg.plist.read_bytes())


def _fixture_digest(checkout: Path) -> str:
    """The fixture Core's own digest of ``checkout`` (no deployer code involved)."""
    out = subprocess.run(
        [
            sys.executable,
            "-B",
            "-I",
            "-c",
            "import importlib.util, sys\n"
            "spec = importlib.util.spec_from_file_location('bi', sys.argv[1])\n"
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
            "print(m.source_digest(sys.argv[2]))\n",
            str(checkout / ad.CORE_BUILD_IDENTITY_FILE),
            str(checkout / "product"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def test_build_records_core_source_digest_and_exports_it(cfg: ad.Config) -> None:
    """#2246: the build computes the pinned Core's source_digest with Core's own
    module, records it in the receipt and exports it to spare and live Gateways."""
    host, prober = FakeHost(), FakeProber()
    assert cycle(cfg, host, prober)["status"] == "DEPLOYED"
    checkout = cfg.core_checkouts / CORE.pin
    core = ad.last_receipt(cfg.state_dir)["core"]
    assert core["source_digest_status"] == "COMPUTED"
    assert core["source_digest"] == _fixture_digest(checkout)
    assert ad._CORE_DIGEST.match(core["source_digest"])
    assert host.digest_runs == 1
    digest_call = next(c for c in host.calls if ad.CORE_SOURCE_DIGEST_CODE in c)
    assert digest_call[1:3] == ["-B", "-I"] and digest_call[-2:] == [str(checkout), CORE.pin]
    exports = (
        f'export NEXUS_CORE_SOURCE_DIGEST_REVISION="{CORE.pin}" ; '
        f'export NEXUS_CORE_SOURCE_DIGEST="{core["source_digest"]}" ; '
    )
    live_command = plistlib.loads(cfg.plist.read_bytes())["ProgramArguments"][2]
    for command in (host.started[0], live_command):
        assert exports in command
        assert command.index(exports) > command.index(f'source "{cfg.env_file}"')
    # Computing the digest wrote nothing into the pinned checkout.
    assert _fixture_git(checkout, "status", "--porcelain", "--ignored") == ""


def test_core_pin_without_build_identity_exports_no_digest(cfg: ad.Config) -> None:
    host = FakeHost()
    host.core_pin = CORE.other  # predates Core's core_identity()
    assert cycle(cfg, host, FakeProber())["status"] == "DEPLOYED"
    core = ad.last_receipt(cfg.state_dir)["core"]
    assert core["source_digest"] is None
    assert core["source_digest_status"] == "UNSUPPORTED_CORE"
    assert host.digest_runs == 0
    live_command = plistlib.loads(cfg.plist.read_bytes())["ProgramArguments"][2]
    unset = "unset NEXUS_CORE_SOURCE_DIGEST NEXUS_CORE_SOURCE_DIGEST_REVISION ; "
    for command in (live_command, host.started[0]):
        assert "export NEXUS_CORE_SOURCE_DIGEST" not in command
        # A stale value from the env file cannot reach the host.
        assert unset in command
        assert command.index(unset) > command.index(f'source "{cfg.env_file}"')


def _wrapper_shell() -> str:
    """launchd runs the wrapper with /bin/zsh; Linux CI runners have bash."""
    shell = "/bin/zsh" if Path("/bin/zsh").exists() else shutil.which("bash")
    assert shell, "no zsh or bash to run the real wrapper"
    return shell


def test_wrapper_exports_a_pycache_prefix_outside_core_after_the_env_file(cfg: ad.Config) -> None:
    root = cfg.deployments / f"a1-{NEW}"
    core = cfg.core_checkouts / CORE.pin
    command = ad.wrapper_command(cfg, root, Path("/v/bin/python"), core_root=core)
    prefix = cfg.pycache_prefixes / root.name
    export = f'export PYTHONPYCACHEPREFIX="{prefix}" ; '
    assert export in command
    assert command.index(export) > command.index(f'source "{cfg.env_file}"')
    assert command.index(export) < command.index("exec ")
    for tree in (core, root, cfg.controllers):
        assert tree not in prefix.parents and prefix != tree
    # Every candidate probe and live switch uses it.
    host = FakeHost()
    assert cycle(cfg, host, FakeProber())["status"] == "DEPLOYED"
    live = plistlib.loads(cfg.plist.read_bytes())["ProgramArguments"][2]
    for started in (host.started[0], live):
        assert "export PYTHONPYCACHEPREFIX=" in started
        assert started.index("PYTHONPYCACHEPREFIX") > started.index("source ")


def test_core_provenance_probe_env_carries_a_pycache_prefix(tmp_path: Path) -> None:
    core_root = tmp_path / "core" / NEW
    core_root.mkdir(parents=True)
    host = _CoreStatusHost(_pinned_status(core_root))
    ad.Prober(host).core_provenance(
        root=REPO_ROOT,
        python=Path(sys.executable),
        core={"revision": NEW, "root": str(core_root), "source_digest": None},
    )
    prefix = Path(str(host.core_envs[0]["PYTHONPYCACHEPREFIX"]))
    assert prefix.is_absolute()
    assert core_root not in prefix.parents and REPO_ROOT not in prefix.parents


def _plant_mismatched_pyc(package: Path) -> None:
    """Bytecode of other code that CPython accepts for ``mod.py`` (same mtime and size)."""
    import py_compile

    source = package / "mod.py"
    source.write_text("print('EVIL!!')\n")
    pyc = package / "__pycache__" / f"mod.{sys.implementation.cache_tag}.pyc"
    py_compile.compile(str(source), cfile=str(pyc), doraise=True)
    stamp = source.stat().st_mtime_ns
    source.write_text("print('SOURCE')\n")  # same size, real code
    os.utime(source, ns=(stamp, stamp))


def test_planted_bytecode_in_the_core_checkout_never_runs_under_the_wrapper(
    cfg: ad.Config, tmp_path: Path
) -> None:
    """#2246 review: a pyc matching mod.py's mtime/size is executed instead of
    mod.py, even with -B, unless PYTHONPYCACHEPREFIX moves the cache away."""
    core = tmp_path / "core-checkout"
    core.mkdir()
    _plant_mismatched_pyc(core)
    importer = (
        "import sys, os; sys.path.insert(0, os.environ['NEXUS_CORE_REPO_ROOT']); import mod\n"
    )
    # Positive control: without a prefix the planted bytecode wins.
    control = subprocess.run(
        [sys.executable, "-B", "-c", importer],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "NEXUS_CORE_REPO_ROOT": str(core)},
    )
    assert control.stdout.strip() == "EVIL!!"
    root = tmp_path / "deploy" / f"a1-{NEW}"
    (root / ad.ENTRYPOINT).parent.mkdir(parents=True)
    (root / ad.ENTRYPOINT).write_text(importer)
    command = ad.wrapper_command(cfg, root, Path(sys.executable), core_root=core)
    out = subprocess.run([_wrapper_shell(), "-c", command], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "SOURCE"
    # Nothing was written into the Core checkout's own cache.
    assert sorted(p.name for p in (core / "__pycache__").iterdir()) == [
        f"mod.{sys.implementation.cache_tag}.pyc"
    ]


def test_pycache_prefix_is_pruned_with_its_deployment(cfg: ad.Config) -> None:
    host = FakeHost()
    assert cycle(cfg, host, FakeProber())["status"] == "DEPLOYED"
    live = cfg.pycache_prefixes / f"a1-{NEW}"
    gone = cfg.pycache_prefixes / f"a1-{'9' * 40}"
    for cache in (live, gone):
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "x.pyc").write_bytes(b"x")
    ad.prune(cfg, host, [cfg.deployments / f"a1-{NEW}"])
    assert live.is_dir()
    assert not gone.exists()


def test_no_build_digest_never_leaks_a_stale_digest_into_the_host(
    cfg: ad.Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2246 review: without a build digest the wrapper unsets the digest env and
    the provenance probe subprocess does not inherit it from the deployer."""
    monkeypatch.setenv("NEXUS_CORE_SOURCE_DIGEST", "sha256:" + "9" * 64)
    monkeypatch.setenv("NEXUS_CORE_SOURCE_DIGEST_REVISION", NEW)
    core = {"revision": NEW, "root": str(tmp_path / "core"), "source_digest": None}
    seen: list[dict[str, str]] = []

    class EnvHost(ad.Host):
        def run(self, argv, *, cwd=None, env=None, timeout=1800):  # type: ignore[override]
            if len(argv) > 2 and argv[2] == ad.CORE_PROVENANCE_PROBE_CODE:
                argv = [
                    sys.executable,
                    "-c",
                    "import json, os; print(json.dumps(dict(os.environ)))",
                ]
                result = super().run(argv, cwd=cwd, env=env, timeout=timeout)
                seen.append(json.loads(result.stdout))
                return _done(json.dumps(_pinned_status(Path(core["root"]))) + "\n")
            return super().run(argv, cwd=cwd, env=env, timeout=timeout)

    ad.Prober(EnvHost()).core_provenance(root=REPO_ROOT, python=Path(sys.executable), core=core)
    assert "NEXUS_CORE_SOURCE_DIGEST" not in seen[0]
    assert "NEXUS_CORE_SOURCE_DIGEST_REVISION" not in seen[0]
    assert seen[0]["NEXUS_CORE_REPO_ROOT"] == core["root"]
    # With a build digest the build's values replace the stale ones.
    seen.clear()
    core["source_digest"] = "sha256:" + "1" * 64
    ad.Prober(EnvHost()).core_provenance(root=REPO_ROOT, python=Path(sys.executable), core=core)
    assert seen[0]["NEXUS_CORE_SOURCE_DIGEST"] == core["source_digest"]
    # The real wrapper, after an env file that exports a stale digest, hands the
    # Gateway process none of it.
    shell = _wrapper_shell()
    cfg.env_file.write_text(
        'export NEXUS_CORE_SOURCE_DIGEST="sha256:' + "9" * 64 + '"\n'
        f'export NEXUS_CORE_SOURCE_DIGEST_REVISION="{NEW}"\n'
    )
    root = tmp_path / "deploy"
    (root / ad.ENTRYPOINT).parent.mkdir(parents=True)
    (root / ad.ENTRYPOINT).write_text("import json, os; print(json.dumps(dict(os.environ)))\n")
    cases = [
        (tmp_path / "core", None),
        (None, None),  # no Core pin at all: still no stale digest
        (tmp_path / "core", ("c" * 40, "sha256:" + "d" * 64)),
    ]
    for core_root, digest in cases:
        command = ad.wrapper_command(
            cfg, root, Path(sys.executable), core_root=core_root, core_digest=digest
        )
        out = subprocess.run([shell, "-c", command], capture_output=True, text=True, check=True)
        environ = json.loads(out.stdout.strip().splitlines()[-1])
        if digest is None:
            assert "NEXUS_CORE_SOURCE_DIGEST" not in environ
            assert "NEXUS_CORE_SOURCE_DIGEST_REVISION" not in environ
        else:
            assert environ["NEXUS_CORE_SOURCE_DIGEST"] == digest[1]
            assert environ["NEXUS_CORE_SOURCE_DIGEST_REVISION"] == digest[0]


def test_core_source_digest_requires_disk_to_match_the_commit(cfg: ad.Config) -> None:
    checkout = Path(ad.materialize_core(cfg, FakeHost(), CORE.pin)["root"])
    host = FakeHost()
    clean = ad.core_source_digest(host, checkout, CORE.pin)
    assert clean["source_digest"] == _fixture_digest(checkout)
    # A stray __pycache__ changes neither digest.
    (checkout / "product" / "__pycache__").mkdir()
    (checkout / "product" / "__pycache__" / "two.cpython-312.pyc").write_bytes(b"junk")
    assert ad.core_source_digest(host, checkout, CORE.pin) == clean
    # A shipped source that differs from the commit rejects the candidate.
    (checkout / "product" / "two.py").write_text("tampered = True\n")
    with pytest.raises(ad.DeployError, match="CORE_SOURCE_DIGEST_MISMATCH"):
        ad.core_source_digest(host, checkout, CORE.pin)


def test_core_source_digest_failure_rejects(cfg: ad.Config) -> None:
    checkout = Path(ad.materialize_core(cfg, FakeHost(), CORE.pin)["root"])
    (checkout / ad.CORE_BUILD_IDENTITY_FILE).write_text("raise SystemExit(3)\n")
    with pytest.raises(ad.DeployError, match="CORE_SOURCE_DIGEST_FAILED"):
        ad.core_source_digest(FakeHost(), checkout, CORE.pin)


def test_wrapper_rejects_a_malformed_core_digest(cfg: ad.Config) -> None:
    root, python, core = Path("/d/a1-x"), Path("/v/bin/python"), Path("/g/core/abc")
    good = ("c" * 40, "sha256:" + "d" * 64)
    command = ad.wrapper_command(cfg, root, python, core_root=core, core_digest=good)
    assert f'export NEXUS_CORE_SOURCE_DIGEST="sha256:{"d" * 64}" ; exec ' in command
    for bad in (
        ("c" * 40, "sha256:" + "d" * 63),
        ("c" * 40, 'sha256:"; rm -rf ~'),
        ("not-a-sha", "sha256:" + "d" * 64),
    ):
        with pytest.raises(ad.DeployError, match="WRAPPER_CORE_DIGEST_INVALID"):
            ad.wrapper_command(cfg, root, python, core_root=core, core_digest=bad)
    with pytest.raises(ad.DeployError, match="WRAPPER_CORE_DIGEST_INVALID"):
        ad.wrapper_command(cfg, root, python, core_digest=good)


def test_rollback_probe_of_the_predecessor_does_not_demand_core(cfg: ad.Config) -> None:
    prober = FakeProber({(ad.LIVE_PORT, NEW): False})
    assert cycle(cfg, FakeHost(), prober)["status"] == "ROLLED_BACK"
    pin = ad.last_receipt(cfg.state_dir)["core"]
    assert [(c["commit"], c["core"]) for c in prober.calls] == [
        (NEW, pin),
        (NEW, pin),
        (OLD, None),
    ]


def test_retention_prunes_core_checkouts_with_their_deployments(cfg: ad.Config) -> None:
    host = FakeHost()
    pins = {"1": CORE.other, "2": CORE.other, "3": CORE.pin}
    for index, (char, pin) in enumerate(pins.items()):
        deployment = cfg.deployments / f"a1-{char * 40}"
        (deployment / ad.CORE_PIN_FILE).parent.mkdir(parents=True)
        (deployment / ad.CORE_PIN_FILE).write_text(_pin_source(pin))
        os.utime(deployment, (1000 + index, 1000 + index))
    for pin in (CORE.other, CORE.pin):
        ad.materialize_core(cfg, host, pin)
    stray = cfg.core_checkouts / ("e" * 40)  # pinned by nothing
    stray.mkdir()
    keep_one = ad.Config.default(cfg.state_dir.parents[2], keep=1)
    # a1-1 is protected (live): its Core survives while a1-2 is pruned.
    removed = ad.prune(keep_one, host, [cfg.deployments / f"a1-{'1' * 40}"])
    assert removed == [f"a1-{'2' * 40}"]
    assert sorted(p.name for p in cfg.core_checkouts.iterdir()) == sorted([CORE.other, CORE.pin])
    # Once no deployment pins CORE.other, its checkout and git worktree go with it.
    removed = ad.prune(keep_one, host, [])
    assert removed == [f"a1-{'1' * 40}"]
    assert [p.name for p in cfg.core_checkouts.iterdir()] == [CORE.pin]
    worktrees = _fixture_git(cfg.core_bare_repo, "worktree", "list", "--porcelain")
    assert str(cfg.core_checkouts / CORE.other) not in worktrees


def test_core_retention_keeps_everything_when_an_a1_pin_is_unreadable(cfg: ad.Config) -> None:
    host = FakeHost()
    ad.materialize_core(cfg, host, CORE.pin)
    unreadable = cfg.deployments / f"a1-{'7' * 40}"
    unreadable.mkdir()  # no pin file: we cannot tell which Core it runs
    assert ad.prune_core(cfg, host, [unreadable]) == []
    assert (cfg.core_checkouts / CORE.pin).is_dir()
    # An r1 deployment without a pin does not block (r1 never uses these checkouts).
    unreadable.rmdir()
    assert ad.prune_core(cfg, host, []) == [CORE.pin]


def test_core_retention_unprotected_a1_without_pin_pins_nothing(cfg: ad.Config) -> None:
    host = FakeHost()
    ad.materialize_core(cfg, host, CORE.pin)
    (cfg.deployments / f"a1-{'7' * 40}").mkdir()  # no pin file, not protected
    assert ad.prune_core(cfg, host, []) == [CORE.pin]


def test_core_retention_aborts_on_a_malformed_a1_pin(cfg: ad.Config) -> None:
    host = FakeHost()
    ad.materialize_core(cfg, host, CORE.pin)
    broken = cfg.deployments / f"a1-{'7' * 40}"
    (broken / ad.CORE_PIN_FILE).parent.mkdir(parents=True)
    (broken / ad.CORE_PIN_FILE).write_text('CANONICAL_CORE_REVISION = "nope"\n')
    assert ad.prune_core(cfg, host, []) == []
    assert (cfg.core_checkouts / CORE.pin).is_dir()


def test_retention_never_follows_a_symlinked_core_dir(cfg: ad.Config, tmp_path: Path) -> None:
    precious = tmp_path / "precious-core"
    (precious / ("e" * 40)).mkdir(parents=True)
    cfg.core_checkouts.symlink_to(precious)
    assert ad.prune_refusal(cfg) == f"SYMLINKED_DIRECTORY:{cfg.core_checkouts}"
    assert ad.prune_core(cfg, FakeHost(), []) == []
    assert (precious / ("e" * 40)).is_dir()
    with pytest.raises(ad.DeployError, match="CORE_PATH_SYMLINKED"):
        ad.materialize_core(cfg, FakeHost(), CORE.pin)


class _CoreStatusHost(ad.Host):
    """Real host, except the Core provenance subprocess returns a canned status."""

    def __init__(self, status: dict[str, Any] | None, code: int = 0) -> None:
        self.status, self.code = status, code
        self.core_envs: list[dict[str, str] | None] = []

    def run(self, argv, *, cwd=None, env=None, timeout=1800):  # type: ignore[override]
        if len(argv) > 2 and argv[2] == ad.CORE_PROVENANCE_PROBE_CODE:
            self.core_envs.append(env)
            out = json.dumps(self.status) if self.status is not None else "Traceback"
            return _done(out + "\n", code=self.code)
        return super().run(argv, cwd=cwd, env=env, timeout=timeout)


def _pinned_status(core_root: Path, observed: str = NEW, expected: str = NEW) -> dict[str, Any]:
    return {
        "status": "CORE_REVISION_PINNED",
        "fail_closed": False,
        "expected_revision": expected,
        "observed_commit": observed,
        "source_root": str(core_root),
    }


@pytest.mark.parametrize(
    ("case", "ok"),
    [
        ("pinned", True),
        ("mismatch", False),
        ("unavailable", False),
        ("pinned_other_commit", False),
        ("pinned_other_expectation", False),
        ("pinned_other_root", False),
        ("crashed", False),
        ("no_pin", False),
    ],
)
def test_real_prober_requires_core_revision_pinned(tmp_path: Path, case: str, ok: bool) -> None:
    core_root = tmp_path / "core" / NEW
    core_root.mkdir(parents=True)
    status: dict[str, Any] | None = _pinned_status(core_root)
    code = 0
    core: dict[str, Any] = {"revision": NEW, "root": str(core_root)}
    if case == "mismatch":
        status = {**_pinned_status(core_root, observed=OLD), "status": "CORE_REVISION_MISMATCH"}
    elif case == "unavailable":
        status = {"status": "CORE_UNAVAILABLE", "reason": "CORE_PRODUCT_SHADOWED"}
    elif case == "pinned_other_commit":
        status = _pinned_status(core_root, observed=OLD, expected=OLD)
    elif case == "pinned_other_expectation":
        status = _pinned_status(core_root, expected=OLD)
    elif case == "pinned_other_root":
        status = _pinned_status(tmp_path / "elsewhere")
    elif case == "crashed":
        status, code = None, 1
    elif case == "no_pin":
        core = {}
    host = _CoreStatusHost(status, code)
    # The running Gateway reports a healthy in-process block (#2169); only the
    # on-disk subprocess result varies here.
    health = {**_health(NEW), "core_provenance": _health_core_block(NEW)}
    with fake_gateway(health, 3, False) as port:
        result = ad.Prober(host).probe(
            port=port,
            token="tok",
            commit=NEW,
            root=REPO_ROOT,
            python=Path(sys.executable),
            timeout=10,
            core=core,
        )
    assert result["checks"]["core_provenance"]["ok"] is ok
    assert result["ok"] is ok
    if case != "no_pin":
        assert host.core_envs[0]["NEXUS_CORE_REPO_ROOT"] == str(core_root)


def test_real_core_provenance_check_rejects_a_checkout_that_is_not_core(
    tmp_path: Path,
) -> None:
    """End to end with the real transport: a checkout without Core's verification
    surface is CORE_UNAVAILABLE, so the candidate cannot pass."""
    checkout = tmp_path / "core"
    _fixture_git(tmp_path, "clone", "-q", str(CORE.path), str(checkout))
    check = ad.Prober(ad.Host()).core_provenance(
        root=REPO_ROOT,
        python=Path(sys.executable),
        core={"revision": CORE.pin, "root": str(checkout)},
    )
    assert check["ok"] is False
    assert check.get("status") == "CORE_UNAVAILABLE"


def _offline_git(cwd: Path | str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, **GIT_ENV, "GIT_NO_LAZY_FETCH": "1"}
    return subprocess.run(
        ["git", "-C", str(cwd), *args], env=env, capture_output=True, text=True, check=False
    )


def _real_core_checkout(tmp_path: Path, pin: str) -> Path | None:
    """A real nexus-core checkout at ``pin`` without any network, or None.

    NEXUS_CORE_REPO_ROOT is used as is when it is a clean checkout at the pin;
    otherwise a ``--shared`` clone of a local nexus-core repository is checked
    out at the pin (the source repository is never modified).
    """
    configured = os.environ.get("NEXUS_CORE_REPO_ROOT", "")
    if configured and (Path(configured) / ".git").exists():
        head = _offline_git(configured, "rev-parse", "HEAD").stdout.strip()
        dirty = _offline_git(configured, "status", "--porcelain", "--ignored").stdout.strip()
        if head == pin and not dirty:
            return Path(configured)
    for source in (configured, str(Path.home() / "workspace/nexus-core")):
        if not source or not (Path(source) / ".git").exists():
            continue
        checkout = tmp_path / "core" / pin
        shutil.rmtree(checkout, ignore_errors=True)
        cloned = _offline_git(
            tmp_path, "clone", "-q", "--shared", "--no-checkout", source, str(checkout)
        )
        if (
            cloned.returncode == 0
            and _offline_git(checkout, "checkout", "-q", "--detach", pin).returncode == 0
        ):
            return checkout
    return None


@pytest.mark.parametrize(
    ("case", "ok"),
    [
        pytest.param("digest_verified", True, id="digest_verified"),
        pytest.param("digest_wrong", False, id="digest_wrong"),
        pytest.param("digest_expected_wrong", False, id="digest_expected_wrong"),
        pytest.param("digest_reported_without_source", False, id="digest_reported_without_source"),
        pytest.param("build_stamp_source", False, id="build_stamp_source"),
        pytest.param("digest_but_build_has_none", False, id="digest_but_build_has_none"),
        # Part 2: a build with a digest no longer accepts a git-identity transport.
        pytest.param("legacy_transport", False, id="legacy_transport"),
        pytest.param("legacy_build_and_transport", True, id="legacy_build_and_transport"),
        pytest.param("git_free_transport_old_build", False, id="git_free_transport_old_build"),
    ],
)
def test_real_prober_requires_the_build_source_digest(tmp_path: Path, case: str, ok: bool) -> None:
    """#2246: a git-free transport passes only when it verified this build's digest."""
    core_root = tmp_path / "core" / NEW
    core_root.mkdir(parents=True)
    digest, other = "sha256:" + "1" * 64, "sha256:" + "2" * 64
    core: dict[str, Any] = {"revision": NEW, "root": str(core_root), "source_digest": digest}
    status: dict[str, Any] = {
        **_pinned_status(core_root),
        "identity_source": "source_digest",
        "observed_source_digest": digest,
        "expected_source_digest": digest,
    }
    if case == "digest_wrong":
        status["observed_source_digest"] = other
    elif case == "digest_expected_wrong":
        status["expected_source_digest"] = other
    elif case == "digest_reported_without_source":
        del status["identity_source"]
    elif case == "build_stamp_source":
        status["identity_source"] = "build_stamp"
    elif case == "digest_but_build_has_none":
        core["source_digest"] = None
    elif case == "legacy_transport":
        status = _pinned_status(core_root)
    elif case == "legacy_build_and_transport":
        # A Core pin that predates core_identity(): no digest on either side.
        core["source_digest"] = None
        status = _pinned_status(core_root)
    elif case == "git_free_transport_old_build":
        core["source_digest"] = None
        del status["observed_source_digest"], status["expected_source_digest"]
    host = _CoreStatusHost(status)
    check = ad.Prober(host).core_provenance(root=REPO_ROOT, python=Path(sys.executable), core=core)
    assert check["ok"] is ok, check
    env = host.core_envs[0]
    assert env["NEXUS_CORE_REPO_ROOT"] == str(core_root)
    if core["source_digest"] is None:
        # Explicitly removed, so no inherited value reaches the transport.
        assert env["NEXUS_CORE_SOURCE_DIGEST"] is None
        assert env["NEXUS_CORE_SOURCE_DIGEST_REVISION"] is None
    else:
        assert env["NEXUS_CORE_SOURCE_DIGEST"] == digest
        assert env["NEXUS_CORE_SOURCE_DIGEST_REVISION"] == NEW


# Opt-in: collected only when NEXUS_CORE_REPO_ROOT names a real nexus-core, so the
# exact-base impact gate never sees a newly added test id that merely skips.
if os.environ.get("NEXUS_CORE_REPO_ROOT"):

    def test_real_transport_reports_pinned_for_a_real_core_checkout(tmp_path: Path) -> None:
        """Positive control with real nexus-core; skipped where none is available offline."""
        pin = ad.read_core_pin(REPO_ROOT)
        checkout = _real_core_checkout(tmp_path, pin)
        if checkout is None:
            pytest.skip("no local nexus-core with the pinned tree (set NEXUS_CORE_REPO_ROOT)")
        core = {"revision": pin, "root": str(checkout)}
        # #2246: the transport pins a checkout by the digest the build computed.
        core.update(ad.core_source_digest(ad.Host(), checkout, pin))
        check = ad.Prober(ad.Host()).core_provenance(
            root=REPO_ROOT, python=Path(sys.executable), core=core
        )
        assert check["status"] == "CORE_REVISION_PINNED", check
        assert check["ok"] is True and check["observed_commit"] == pin
        assert check["identity_source"] == "source_digest"
        assert check["observed_source_digest"] == core["source_digest"]
        # Without the digest the same checkout is not pinned.
        unpinned = ad.Prober(ad.Host()).core_provenance(
            root=REPO_ROOT,
            python=Path(sys.executable),
            core={"revision": pin, "root": str(checkout)},
        )
        assert unpinned["ok"] is False
        assert unpinned["reason"] == "CORE_SOURCE_DIGEST_UNPINNED"

    def test_build_source_digest_equals_real_core_identity(tmp_path: Path) -> None:
        """The deployer's digest is exactly what real Core's core_identity() reports."""
        pin = ad.read_core_pin(REPO_ROOT)
        checkout = _real_core_checkout(tmp_path, pin)
        if checkout is None:
            pytest.skip("no local nexus-core with the pinned tree (set NEXUS_CORE_REPO_ROOT)")
        computed = ad.core_source_digest(ad.Host(), checkout, pin)
        assert computed["source_digest_status"] == "COMPUTED"
        reported = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                "import json, sys; sys.path.insert(0, sys.argv[1]);"
                "from product.protocol import core_identity;"
                "print(json.dumps(core_identity()))",
                str(checkout),
            ],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        identity = json.loads(reported.stdout.strip().splitlines()[-1])
        assert identity["build_identity"] == "UNSTAMPED"
        assert computed["source_digest"] == identity["source_digest"]


# ------------------------------------------------- live required-check set (#2173)


TRUSTED_DEPENDENCY = "Trusted dependency contract (default branch)"


def test_trusted_dependency_contract_is_known_and_bound() -> None:
    workflow = ad.REQUIRED_CHECKS[TRUSTED_DEPENDENCY]
    assert workflow == ".github/workflows/trusted-dependency-contract.yml"
    text = (REPO_ROOT / workflow).read_text(encoding="utf-8")
    assert f"name: {TRUSTED_DEPENDENCY}" in text and "pull_request_target" in text


def test_all_live_required_checks_are_evaluated_including_on_the_pr_head() -> None:
    """The 4th check runs on pull_request_target, so it is found on the merged PR head."""

    def api(path: str) -> Any:
        if "check-runs" in path and "/commits/" + NEW in path and "Trusted" in path:
            return {"check_runs": []}
        return green_api()(path)

    result = ad.required_checks(api, NEW)
    assert result["verdict"] == "GREEN"
    assert result["required"] == list(ad.REQUIRED_CHECKS)
    assert result["checks"][TRUSTED_DEPENDENCY]["sha"] == PR_HEAD


def test_red_trusted_dependency_contract_blocks(cfg: ad.Config) -> None:
    def api(path: str) -> Any:
        payload = green_api()(path)
        if "check-runs" in path and "Trusted" in path:
            for run in payload["check_runs"]:
                run["conclusion"] = "failure"
        return payload

    host, prober = FakeHost(), FakeProber()
    assert cycle(cfg, host, prober, api)["status"] == "CHECKS_RED"
    assert prober.calls == [] and host.reloads == []


def test_unknown_required_check_blocks_without_hold(cfg: ad.Config) -> None:
    api = green_api(required=[*ad.REQUIRED_CHECKS, "Brand new gate"])
    host, prober = FakeHost(), FakeProber()
    result = cycle(cfg, host, prober, api)
    assert result["status"] == "UNKNOWN_REQUIRED_CHECK:Brand new gate"
    assert result["required_checks"]["unknown_required"] == ["Brand new gate"]
    assert prober.calls == [] and host.reloads == [] and not cfg.hold_file.exists()
    assert ad.read_receipts(cfg.state_dir) == []
    # Retried next cycle: once main stops requiring it, the deploy proceeds.
    assert cycle(cfg, host, prober, green_api())["status"] == "DEPLOYED"


@pytest.mark.parametrize(
    "rules",
    [
        ad.DeployError("GH_API_FAILED:403"),
        {"message": "Not Found"},
        [],  # no required checks at all must never mean "green"
        [{"type": "required_status_checks", "parameters": {"required_status_checks": [{}]}}],
    ],
    ids=["api-error", "not-a-list", "no-checks", "malformed-entry"],
)
def test_ruleset_read_failure_blocks(cfg: ad.Config, rules: Any) -> None:
    def api(path: str) -> Any:
        if "/rules/branches/main" in path:
            if isinstance(rules, Exception):
                raise rules
            return rules
        return green_api()(path)

    host, prober = FakeHost(), FakeProber()
    result = cycle(cfg, host, prober, api)
    assert result["status"] == "CHECKS_UNKNOWN"
    assert result["required_checks"]["error"].startswith("RULESET:")
    assert prober.calls == [] and host.reloads == []


def test_check_no_longer_required_is_dropped() -> None:
    required = [n for n in ad.REQUIRED_CHECKS if n != TRUSTED_DEPENDENCY]

    def api(path: str) -> Any:
        if "check-runs" in path and "Trusted+dependency" in path:
            raise AssertionError("a dropped (non-floor) check must not be queried")
        return green_api(required=required)(path)

    result = ad.required_checks(api, NEW)
    assert result["verdict"] == "GREEN" and set(result["checks"]) == set(required)


def test_verify_commit_uses_the_live_required_set(capsys: pytest.CaptureFixture[str]) -> None:
    assert ad.main(["verify-commit", NEW], api_get=green_api(required=["Mystery"])) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["required_checks"]["verdict"] == "UNKNOWN_REQUIRED_CHECK"


# ------------------------------------------ #2175 review: binding, issuer, floor


def _patched_workflow_runs(**changes: Any) -> Callable[[str], Any]:
    """green_api, but the merged PR head's workflow runs carry ``changes``."""
    base = green_api(on_commit=False)

    def api(path: str) -> Any:
        payload = base(path)
        if "/actions/runs?check_suite_id=" in path and int(path.rsplit("=", 1)[1]) >= (
            PR_SUITE_OFFSET
        ):
            for run in payload["workflow_runs"]:
                run.update(changes)
        return payload

    return api


@pytest.mark.parametrize(
    "changes",
    [
        {"head_branch": "someone-elses-branch"},  # another PR sharing the head sha
        {"head_repository": {"full_name": "fork/Nexus-new"}},
        {"event": "push"},
        {"created_at": "2026-10-14T01:00:00Z"},  # after the merge
        {"pull_requests": [{"number": 9999}]},  # explicitly another PR
        {"head_branch": None},  # binding cannot be established
    ],
    ids=["other-branch", "fork", "wrong-event", "after-merge", "other-pr", "no-branch"],
)
def test_pr_head_run_from_another_pr_does_not_count(changes: dict[str, Any]) -> None:
    result = ad.required_checks(_patched_workflow_runs(**changes), NEW)
    assert result["verdict"] == "UNKNOWN"
    assert "Deletion guard" in result["missing"]


def test_pr_head_run_bound_to_the_merged_pr_counts() -> None:
    listed = _patched_workflow_runs(pull_requests=[{"number": MERGED_PR["number"]}])
    assert ad.required_checks(listed, NEW)["verdict"] == "GREEN"
    assert ad.required_checks(_patched_workflow_runs(), NEW)["verdict"] == "GREEN"


def test_commit_run_must_be_a_push_to_main() -> None:
    def api(path: str) -> Any:
        payload = green_api()(path)
        if "/actions/runs?check_suite_id=" in path:
            for run in payload["workflow_runs"]:
                if run["event"] == "push":
                    run["event"] = "pull_request_target"
        return payload

    result = ad.required_checks(api, NEW)
    # The relabelled runs on the main commit do not count; only the merged PR's
    # head runs (bound to that PR) can satisfy the checks.
    assert {c["sha"] for c in result["checks"].values()} == {PR_HEAD}


@pytest.mark.parametrize(
    "bad_rule",
    [
        {"type": "required_status_checks"},
        {"type": "required_status_checks", "parameters": None},
        {"type": "required_status_checks", "parameters": {"required_status_checks": None}},
        {"type": "required_status_checks", "parameters": {"required_status_checks": "x"}},
        {"type": "required_status_checks", "parameters": {"required_status_checks": [7]}},
        {
            "type": "required_status_checks",
            "parameters": {
                "required_status_checks": [{"context": "Deletion guard", "integration_id": "x"}]
            },
        },
    ],
    ids=["no-params", "null-params", "null-list", "str-list", "int-entry", "bad-issuer"],
)
def test_mixed_valid_and_malformed_rules_fail_closed(
    cfg: ad.Config, bad_rule: dict[str, Any]
) -> None:
    def api(path: str) -> Any:
        if "/rules/branches/main" in path:
            return (
                [*_branch_rules(list(ad.REQUIRED_CHECKS)), bad_rule]
                if path.endswith("page=1")
                else []
            )
        return green_api()(path)

    host, prober = FakeHost(), FakeProber()
    result = cycle(cfg, host, prober, api)
    assert result["status"] == "CHECKS_UNKNOWN"
    assert "BRANCH_RULES_MALFORMED" in result["required_checks"]["error"]
    assert prober.calls == [] and host.reloads == []


def test_run_from_a_different_issuer_does_not_count() -> None:
    def api(path: str) -> Any:
        if "/rules/branches/main" in path:
            if "page=" in path and not path.endswith("page=1"):
                return []
            rules = _branch_rules(list(ad.REQUIRED_CHECKS))
            for check in rules[1]["parameters"]["required_status_checks"]:
                if check["context"] == "Deletion guard":
                    check["integration_id"] = 99999
            return rules
        return green_api()(path)

    result = ad.required_checks(api, NEW)
    assert result["verdict"] == "UNKNOWN" and result["missing"] == ["Deletion guard"]


def test_required_check_issuer_is_actions_app_id() -> None:
    """The live rules name integration 15368; real runs report app.id 15368."""
    rules = _branch_rules(["Deletion guard"])
    issuer = rules[1]["parameters"]["required_status_checks"][0]["integration_id"]
    assert issuer == ACTIONS_APP_ID


def test_branch_rules_are_paged() -> None:
    def api(path: str) -> Any:
        if "/rules/branches/main" in path:
            if path.endswith("page=1"):
                return [{"type": "deletion"} for _ in range(100)]
            if path.endswith("page=2"):
                return _branch_rules([*ad.REQUIRED_CHECKS, "Page two gate"])
            return []
        return green_api()(path)

    result = ad.required_checks(api, NEW)
    assert result["verdict"] == "UNKNOWN_REQUIRED_CHECK"
    assert result["unknown_required"] == ["Page two gate"]


def test_floor_checks_stay_required_when_the_ruleset_weakens(cfg: ad.Config) -> None:
    only_secret = green_api(required=["Full published Git history secret audit"])
    result = ad.required_checks(only_secret, NEW)
    assert result["verdict"] == "GREEN"
    assert set(result["checks"]) == set(ad.FLOOR_CHECKS)
    assert result["floor_added"] == ["Deletion guard", "Exact-base impact gate"]

    def floor_red(path: str) -> Any:
        payload = only_secret(path)
        if "check-runs" in path and "Deletion+guard" in path:
            for run in payload["check_runs"]:
                run["conclusion"] = "failure"
        return payload

    assert ad.required_checks(floor_red, NEW)["verdict"] == "RED"


def test_floor_check_without_runs_is_unknown_and_recorded(cfg: ad.Config) -> None:
    def api(path: str) -> Any:
        if "check-runs" in path and "Exact-base" in path:
            return {"check_runs": []}
        return green_api(required=["Full published Git history secret audit"])(path)

    host, prober = FakeHost(), FakeProber()
    result = cycle(cfg, host, prober, api)
    assert result["status"] == "CHECKS_UNKNOWN"
    assert result["required_checks"]["missing"] == ["Exact-base impact gate"]
    assert prober.calls == []


def _pr_head_runs(*, workflow: dict[str, Any] | None = None, attempts: list[dict[str, Any]]):
    """green_api where Deletion guard exists only on the merged PR head, as ``attempts``."""
    base = green_api(on_commit=False)

    def api(path: str) -> Any:
        if "check-runs" in path and "Deletion+guard" in path and "/commits/" + PR_HEAD in path:
            return {"check_runs": attempts}
        payload = base(path)
        if workflow and "/actions/runs?check_suite_id=" in path:
            if int(path.rsplit("=", 1)[1]) >= PR_SUITE_OFFSET:
                for run in payload["workflow_runs"]:
                    run.update(workflow)
        return payload

    return api


def _attempt(run_id: int, started: str, conclusion: str = "success", **extra: Any) -> dict:
    return {
        "id": run_id,
        "name": "Deletion guard",
        "status": "completed",
        "conclusion": conclusion,
        "started_at": started,
        "completed_at": extra.pop("completed_at", started),
        "app": {"slug": "github-actions", "id": ACTIONS_APP_ID},
        "check_suite": {"id": SUITES["Deletion guard"] + PR_SUITE_OFFSET},
        "pull_requests": [],
        **extra,
    }


def test_run_from_an_earlier_pr_on_the_same_branch_and_sha_is_rejected() -> None:
    """#2100 (closed) and #2140 (merged) share branch and head sha: #2100's run is
    older than #2140 itself and must not count."""
    earlier = _attempt(1, "2026-10-12T10:00:00Z")
    api = _pr_head_runs(workflow={"created_at": "2026-10-12T09:59:00Z"}, attempts=[earlier])
    result = ad.required_checks(api, NEW)
    assert result["verdict"] == "UNKNOWN" and "Deletion guard" in result["missing"]


def test_rerun_after_merge_is_ignored_and_pre_merge_attempt_counts() -> None:
    pre_merge = _attempt(1, "2026-10-13T23:00:00Z")
    post_merge_rerun = _attempt(2, "2026-10-14T01:00:00Z", conclusion="failure")
    # The workflow run's run_started_at follows the latest (post-merge) attempt.
    api = _pr_head_runs(
        workflow={"run_started_at": "2026-10-14T01:00:00Z", "run_attempt": 2},
        attempts=[pre_merge, post_merge_rerun],
    )
    result = ad.required_checks(api, NEW)
    assert result["verdict"] == "GREEN"
    assert result["checks"]["Deletion guard"]["sha"] == PR_HEAD


def test_successful_rerun_after_merge_does_not_rescue_a_red_check() -> None:
    pre_merge_red = _attempt(1, "2026-10-13T23:00:00Z", conclusion="failure")
    post_merge_green = _attempt(2, "2026-10-14T01:00:00Z")
    api = _pr_head_runs(attempts=[pre_merge_red, post_merge_green])
    assert ad.required_checks(api, NEW)["verdict"] == "RED"


def test_attempt_completed_after_merge_does_not_count() -> None:
    straddling = _attempt(1, "2026-10-13T23:59:00Z", completed_at="2026-10-14T00:30:00Z")
    result = ad.required_checks(_pr_head_runs(attempts=[straddling]), NEW)
    assert result["verdict"] == "UNKNOWN" and "Deletion guard" in result["missing"]


def test_only_post_merge_rerun_leaves_the_check_missing() -> None:
    api = _pr_head_runs(attempts=[_attempt(2, "2026-10-14T01:00:00Z")])
    assert ad.required_checks(api, NEW)["missing"] == ["Deletion guard"]


@pytest.mark.parametrize("completed_at", [None, "", "garbage"], ids=["null", "empty", "bad"])
def test_completed_pr_head_run_without_completed_at_is_not_bound(completed_at: Any) -> None:
    run = _attempt(1, "2026-10-13T23:00:00Z", completed_at=completed_at)
    result = ad.required_checks(_pr_head_runs(attempts=[run]), NEW)
    assert result["verdict"] == "UNKNOWN" and "Deletion guard" in result["missing"]
    missing_key = {k: v for k, v in run.items() if k != "completed_at"}
    result = ad.required_checks(_pr_head_runs(attempts=[missing_key]), NEW)
    assert result["verdict"] == "UNKNOWN" and "Deletion guard" in result["missing"]


def test_gb077_waits_for_a_slow_health_endpoint() -> None:
    """Live bug 2026-10-14T13:45:50Z: a fresh candidate's /health took > 2 s and
    GB-077 failed with gateway_unreachable:TimeoutError."""
    with fake_gateway(_health(NEW), 3, False, health_delay=3.0) as port:
        result = ad.Prober(ad.Host()).probe(
            port=port,
            token="tok",
            commit=NEW,
            root=REPO_ROOT,
            python=Path(sys.executable),
            timeout=60,
        )
    gb077 = result["checks"]["gb077"]
    assert gb077["ok"] is True, gb077["detail"]
    detail = json.loads(gb077["detail"])
    assert detail["observed"]["endpoint"] == f"http://127.0.0.1:{port}/health"
    assert result["ok"] is True


def test_gb077_probe_passes_timeout_and_attempts() -> None:
    calls: list[list[str]] = []

    class Recording(ad.Host):
        def run(self, argv, **kw):  # type: ignore[override]
            calls.append(list(argv))
            return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    with fake_gateway(_health(NEW), 3, False) as port:
        ad.Prober(Recording()).probe(
            port=port, token="tok", commit=NEW, root=REPO_ROOT, python=Path("/py"), timeout=5
        )
    assert calls[0][-2:] == [str(ad.GB077_TIMEOUT_SECONDS), str(ad.GB077_ATTEMPTS)]


# ---------------------------------------- draft pin PRs and #526 R1 recovery


def _pin_pr(number: int, *, draft: bool) -> dict[str, Any]:
    return {
        "number": number,
        "title": "ci: trusted runtime identity abc1234 and transition for #2171",
        "head": {"ref": f"auto/workforce-anchor-m-{number:012d}", "sha": "f" * 40},
        "created_at": NOW_ISO,
        "draft": draft,
    }


def test_draft_pin_pr_does_not_block_and_is_reported(cfg: ad.Config) -> None:
    api = green_api(open_pulls=[_pin_pr(2172, draft=True)])
    pins = ad.pin_bumps_in_flight(api, now=NOW)
    assert pins["verdict"] == "CLEAR" and pins["ignored_draft"] == [2172]
    assert pins["warnings"] == ["DRAFT_PIN_PR_IGNORED #2172"]
    result = cycle(cfg, FakeHost(), FakeProber(), api)
    assert result["status"] == "DEPLOYED"
    assert "DRAFT_PIN_PR_IGNORED #2172" in result["warnings"]
    assert "DRAFT_PIN_PR_IGNORED #2172" in result["receipt"]["warnings"]
    status = json.loads((cfg.state_dir / "status.json").read_text())
    assert "DRAFT_PIN_PR_IGNORED #2172" in status["warnings"]


def test_same_pin_pr_once_ready_blocks() -> None:
    api = green_api(open_pulls=[_pin_pr(2172, draft=False)])
    pins = ad.pin_bumps_in_flight(api, now=NOW)
    assert pins["verdict"] == "IN_FLIGHT" and pins["pull_requests"] == [2172]


def test_draft_marked_ready_mid_cycle_blocks_the_switch(cfg: ad.Config) -> None:
    pr = _pin_pr(2172, draft=True)

    def ready_during_spare_probe(call: dict[str, Any]) -> None:
        if call["port"] == 50123:
            pr["draft"] = False

    host = FakeHost()
    before = cfg.plist.read_bytes()
    result = cycle(cfg, host, FakeProber(hook=ready_during_spare_probe), green_api(open_pulls=[pr]))
    assert result["status"] == "PIN_BUMP_IN_FLIGHT"
    assert cfg.plist.read_bytes() == before and host.reloads == []


def test_open_r1_recovery_blocks_before_build(cfg: ad.Config) -> None:
    host = FakeHost()
    host.r1_block = "R1_OPEN_RECOVERY_BLOCKS_V1_EFFECT:gen1-request:REQUESTED"
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "BLOCKED_MANAGER_BUSY"
    assert result["reason"].startswith("R1_OPEN_RECOVERY_BLOCKS_V1_EFFECT")
    assert not any(c[:1] == ["uv"] for c in host.calls) and host.reloads == []
    assert not cfg.hold_file.exists() and ad.read_receipts(cfg.state_dir) == []


def test_r1_opened_during_the_cycle_blocks_the_switch_and_retries(cfg: ad.Config) -> None:
    host = FakeHost()

    def r1_opens(call: dict[str, Any]) -> None:
        if call["port"] == 50123:
            host.r1_block = "R1_OPEN_RECOVERY_BLOCKS_V1_EFFECT:gen2:PREFLIGHTED"

    before = cfg.plist.read_bytes()
    result = cycle(cfg, host, FakeProber(hook=r1_opens))
    assert result["status"] == "BLOCKED_MANAGER_BUSY"
    receipt = result["receipt"]
    assert receipt["switched"] is False and receipt["reason"].startswith("R1_OPEN_RECOVERY")
    assert cfg.plist.read_bytes() == before and host.reloads == []
    assert not cfg.journal.exists() and not cfg.hold_file.exists()
    assert host.lock_events == ["acquire", "release"]
    # R1 finished: the next cycle after the plain debounce (no backoff growth) deploys.
    host.r1_block = None
    host.clock += cfg.min_interval_seconds
    assert cycle(cfg, host, FakeProber())["status"] == "DEPLOYED"


def _real_r1_host(cfg: ad.Config, monkeypatch: pytest.MonkeyPatch) -> FakeHost:
    from scripts.ops import mcp_gateway_durable as durable

    cfg.gateway_root.chmod(0o700)
    monkeypatch.setattr(durable, "GATEWAY_STATE_ROOT", cfg.gateway_root)
    monkeypatch.setattr(durable, "GATEWAY_LEDGER", cfg.gateway_root / "ledger.jsonl")

    class RealR1(FakeHost):
        def r1_recovery_block(self, c: ad.Config) -> str | None:  # type: ignore[override]
            return ad.Host.r1_recovery_block(self, c)

    return RealR1()


def test_real_r1_check_without_requests_lets_the_switch_proceed(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = _real_r1_host(cfg, monkeypatch)
    assert ad.Host.r1_recovery_block(host, cfg) is None
    assert cycle(cfg, host, FakeProber())["status"] == "DEPLOYED"


def test_corrupt_r1_ledger_blocks_the_switch(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = _real_r1_host(cfg, monkeypatch)
    ledger = cfg.gateway_root / "ledger.jsonl"
    ledger.write_bytes(b"not-json\n")
    ledger.chmod(0o600)
    reason = ad.Host.r1_recovery_block(host, cfg)
    assert reason is not None and reason.startswith("R1_LEDGER_CORRUPT_FAIL_CLOSED")
    before = cfg.plist.read_bytes()
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "BLOCKED_MANAGER_BUSY" and host.reloads == []
    assert cfg.plist.read_bytes() == before and not cfg.hold_file.exists()


def test_r1_check_fails_closed_for_another_state_root(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.ops import mcp_gateway_durable as durable

    monkeypatch.setattr(durable, "GATEWAY_STATE_ROOT", cfg.gateway_root.parent / "elsewhere")
    reason = ad.Host().r1_recovery_block(cfg)
    assert reason is not None and reason.startswith("R1_CHECK_FAILED")


def _crash_after_candidate_plist(cfg: ad.Config) -> bytes:
    before = cfg.plist.read_bytes()
    host = FakeHost()
    probe = FakeProber(
        hook=lambda c: (_ for _ in ()).throw(Crash()) if c["port"] == ad.LIVE_PORT else None
    )
    with pytest.raises(Crash):
        cycle(cfg, host, probe)
    assert cfg.journal.exists()
    return before


def test_reconcile_under_r1_finalizes_a_healthy_live_candidate_without_effects(
    cfg: ad.Config,
) -> None:
    _crash_after_candidate_plist(cfg)
    host = FakeHost()
    host.r1_block = "R1_OPEN_RECOVERY_BLOCKS_V1_EFFECT:gen3:REQUESTED"
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "RECONCILED_DEPLOYED"
    assert host.reloads == [] and not cfg.journal.exists()
    assert result["receipt"]["r1_block_observed"].startswith("R1_OPEN_RECOVERY")


def test_reconcile_under_r1_keeps_the_journal_instead_of_rolling_back(cfg: ad.Config) -> None:
    _crash_after_candidate_plist(cfg)
    live_before = cfg.plist.read_bytes()
    host = FakeHost()
    host.r1_block = "R1_OPEN_RECOVERY_BLOCKS_V1_EFFECT:gen3:REQUESTED"
    result = cycle(cfg, host, FakeProber({(ad.LIVE_PORT, NEW): False}))
    assert result["status"] == "RECONCILED_BLOCKED_MANAGER_BUSY"
    assert cfg.journal.exists() and cfg.plist.read_bytes() == live_before
    assert host.reloads == [] and not cfg.hold_file.exists()
    # R1 done: the next cycle rolls back normally.
    result = cycle(cfg, FakeHost(), FakeProber({(ad.LIVE_PORT, NEW): False}))
    assert result["status"] == "RECONCILED_ROLLED_BACK" and not cfg.journal.exists()


def test_reconcile_under_r1_does_not_reload_the_previous_plist(cfg: ad.Config) -> None:
    _crash_on_rollback_reload(cfg)
    host = FakeHost()
    host.r1_block = "R1_LEDGER_CORRUPT_FAIL_CLOSED:x"
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "RECONCILED_BLOCKED_MANAGER_BUSY"
    assert host.reloads == [] and cfg.journal.exists()


@contextlib.contextmanager
def scripted_health(responses: list[Any]) -> Iterator[int]:
    """/health answers from ``responses`` in order: a dict, or a float = sleep (timeout)."""
    queue = list(responses)

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_a: Any) -> None:
            return

        def do_GET(self) -> None:
            item = queue.pop(0) if queue else responses[-1]
            if isinstance(item, float):
                import time

                time.sleep(item)
                item = _health(NEW)
            body = json.dumps(item).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()


def _run_gb077(port: int, timeout: float = 1.0, attempts: int = 3) -> tuple[int, dict]:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            ad.GB077_PROBE_CODE,
            str(REPO_ROOT),
            f"http://127.0.0.1:{port}/health",
            NEW,
            str(timeout),
            str(attempts),
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=120,
    )
    return result.returncode, json.loads(result.stdout.strip().splitlines()[-1])


def test_gb077_identity_failure_is_not_retried_away() -> None:
    """Codex: wrong head then right head must FAIL, and attempt 1 stays recorded."""
    with scripted_health([_health(OLD), _health(NEW)]) as port:
        code, detail = _run_gb077(port)
    assert code == 1 and detail["result"] == "FAIL"
    assert [a["ok"] for a in detail["attempts"]] == [False]
    assert "gateway_loaded_revision_not_evaluated_revision" in detail["attempts"][0]["reasons"]


def test_gb077_retries_a_timeout_then_passes() -> None:
    with scripted_health([3.0, _health(NEW)]) as port:
        code, detail = _run_gb077(port, timeout=1.0)
    assert code == 0 and detail["result"] == "PASS"
    assert [a["ok"] for a in detail["attempts"]] == [False, True]
    assert detail["attempts"][0]["reasons"][0].startswith("gateway_unreachable:")


def test_gb077_three_timeouts_fail() -> None:
    with scripted_health([3.0, 3.0, 3.0, 3.0]) as port:
        code, detail = _run_gb077(port, timeout=1.0, attempts=3)
    assert code == 1 and len(detail["attempts"]) == 3
    assert all(not a["ok"] for a in detail["attempts"])


def test_r1_blocked_attempt_leaves_no_orphaned_core_checkout(cfg: ad.Config) -> None:
    """BLOCKED_MANAGER_BUSY after the build: the a1 deployment pins its Core, so
    retention removes both together once the deployment ages out."""
    host = FakeHost()

    def r1_opens(call: dict[str, Any]) -> None:
        if call["port"] == 50123:
            host.r1_block = "R1_OPEN_RECOVERY_BLOCKS_V1_EFFECT:gen4:REQUESTED"

    result = cycle(cfg, host, FakeProber(hook=r1_opens))
    assert result["status"] == "BLOCKED_MANAGER_BUSY"
    core_root = Path(result["receipt"]["core"]["root"])
    assert core_root.is_dir() and (cfg.deployments / f"a1-{NEW}").is_dir()
    # While the deployment exists (it is retried next cycle) its Core is kept.
    assert ad.prune_core(cfg, host, []) == []
    # Once retention drops the deployment, its Core checkout goes with it.
    gone = ad.Config.default(cfg.state_dir.parents[2], keep=0)
    assert ad.prune(gone, host, []) == [f"a1-{NEW}"]
    assert not core_root.exists()


# ------------------------------- #2198 review: R1 ledger lock across the effect


def test_r1_cannot_open_anywhere_between_check_and_end_of_switch(cfg: ad.Config) -> None:
    """A racing R1 appender tries right after the check, during the reload, during
    the live probe and during the rollback: every attempt is refused."""
    host = FakeHost()
    host.on_reload = lambda _count: host.r1_try_append()

    def during_probe(call: dict[str, Any]) -> None:
        if call["port"] == 50123:
            # From here on (the advisory pre-build check is done) R1 races every
            # authoritative check the moment it returns.
            host.after_r1_check = host.r1_try_append
        if call["port"] == ad.LIVE_PORT:
            host.r1_try_append()

    result = cycle(cfg, host, FakeProber({(ad.LIVE_PORT, NEW): False}, hook=during_probe))
    assert result["status"] == "ROLLED_BACK"
    # check (+ rollback check), 2 reloads, 2 live probes: none could append.
    assert len(host.r1_append_attempts) >= 6 and not any(host.r1_append_attempts)
    assert host.r1_guard_depth == 0 and host.r1_guard_events[-1] == "release"
    assert host.r1_try_append() is True  # free again after the switch


def test_real_r1_ledger_lock_is_held_through_the_live_probe(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.ops import mcp_gateway_durable as durable

    cfg.gateway_root.chmod(0o700)
    monkeypatch.setattr(durable, "GATEWAY_STATE_ROOT", cfg.gateway_root)
    monkeypatch.setattr(durable, "GATEWAY_LEDGER", cfg.gateway_root / "ledger.jsonl")
    lock_path = durable.GatewayLedger(cfg.gateway_root / "ledger.jsonl").lock_path

    class RealGuard(FakeHost):
        def r1_recovery_block(self, c: ad.Config) -> str | None:  # type: ignore[override]
            return ad.Host.r1_recovery_block(self, c)

        def r1_guard(self, c: ad.Config):  # type: ignore[override]
            return ad.Host.r1_guard(self, c)

    outcomes: list[str] = []

    def r1_appender() -> None:  # another thread = no re-entrancy, like R1's process
        try:
            with durable.InterProcessLock(lock_path, timeout=0.3):
                outcomes.append("appended")
        except Exception as exc:  # noqa: BLE001
            outcomes.append(type(exc).__name__)

    def during_probe(call: dict[str, Any]) -> None:
        if call["port"] == ad.LIVE_PORT:
            thread = threading.Thread(target=r1_appender)
            thread.start()
            thread.join(timeout=10)

    result = cycle(cfg, RealGuard(), FakeProber(hook=during_probe))
    assert result["status"] == "DEPLOYED"
    assert outcomes and "appended" not in outcomes
    r1_appender()
    assert outcomes[-1] == "appended"  # released after the effect


def test_r1_guard_unavailable_blocks_the_switch(cfg: ad.Config) -> None:
    class Busy(FakeHost):
        @contextlib.contextmanager
        def r1_guard(self, c: ad.Config) -> Iterator[None]:  # type: ignore[override]
            raise ad.DeployError("MANAGER_LOCK_UNAVAILABLE:r1-ledger:timeout")
            yield

    host = Busy()
    before = cfg.plist.read_bytes()
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "BLOCKED_MANAGER_BUSY"
    assert cfg.plist.read_bytes() == before and not cfg.journal.exists()


def _foreign_live_plist(cfg: ad.Config) -> None:
    cfg.plist.write_bytes(live_plist(cfg.deployments / f"r1-{PR_HEAD}"))


def test_reconcile_with_foreign_plist_waits_while_r1_is_open(cfg: ad.Config) -> None:
    _crash_after_candidate_plist(cfg)
    _foreign_live_plist(cfg)  # e.g. R1 rewrote the plist
    host = FakeHost()
    host.r1_block = "R1_OPEN_RECOVERY_BLOCKS_V1_EFFECT:gen5:EFFECT_STARTED"
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "RECONCILED_BLOCKED_MANAGER_BUSY"
    assert cfg.journal.exists() and not cfg.hold_file.exists() and host.reloads == []
    last = ad.last_receipt(cfg.state_dir)
    assert last["outcome"] == "BLOCKED_MANAGER_BUSY" and last["reconciled"] is True
    # R1 terminal and the plist still foreign: now it is FOREIGN_PLIST + HOLD.
    result = cycle(cfg, FakeHost(), FakeProber())
    assert result["status"] == "RECONCILED_FOREIGN_PLIST"
    assert cfg.hold_file.exists() and not cfg.journal.exists()


def test_cycle_start_foreign_plist_waits_while_r1_is_open(cfg: ad.Config) -> None:
    _foreign_live_plist(cfg)
    host = FakeHost()
    host.r1_block = "R1_OPEN_RECOVERY_BLOCKS_V1_EFFECT:gen6:REQUESTED"
    assert cycle(cfg, host, FakeProber())["status"] == "BLOCKED_MANAGER_BUSY"
    assert not cfg.hold_file.exists()
    assert cycle(cfg, FakeHost(), FakeProber())["status"] == "FOREIGN_PLIST"
    assert cfg.hold_file.exists()


def test_plist_changed_mid_cycle_by_r1_is_not_foreign(cfg: ad.Config) -> None:
    host = FakeHost()

    def r1_rebinds(call: dict[str, Any]) -> None:
        if call["port"] == 50123:
            _foreign_live_plist(cfg)
            host.r1_block = "R1_OPEN_RECOVERY_BLOCKS_V1_EFFECT:gen7:EFFECT_STARTED"

    result = cycle(cfg, host, FakeProber(hook=r1_rebinds))
    assert result["status"] == "BLOCKED_MANAGER_BUSY" and not cfg.hold_file.exists()


class _RaisingProber:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    def probe(self, **_kw: Any) -> dict[str, Any]:
        raise self.exc


class _CoreUnhealthyProber:
    def probe(self, **_kw: Any) -> dict[str, Any]:
        return {
            "ok": False,
            "checks": {"core_provenance": {"ok": False, "status": "CORE_UNAVAILABLE"}},
        }


@pytest.mark.parametrize(
    "prober",
    [
        _RaisingProber(TimeoutError("timed out")),
        _RaisingProber(ad.DeployError("GATEWAY_TOKEN_UNAVAILABLE")),
        _CoreUnhealthyProber(),
    ],
    ids=["timeout", "token", "core-unhealthy"],
)
def test_probe_trouble_under_r1_postpones_and_keeps_the_journal(
    cfg: ad.Config, prober: Any
) -> None:
    _crash_after_candidate_plist(cfg)
    live_before = cfg.plist.read_bytes()
    host = FakeHost()
    host.r1_block = "R1_OPEN_RECOVERY_BLOCKS_V1_EFFECT:gen8:PREFLIGHTED"
    result = ad.run_cycle(cfg, host, prober, green_api(), environ={}, tool_python=Path("/p"))
    assert result["status"] == "RECONCILED_BLOCKED_MANAGER_BUSY"
    assert cfg.journal.exists() and not cfg.hold_file.exists()
    assert cfg.plist.read_bytes() == live_before and host.reloads == []
    assert not list(cfg.state_dir.glob("pending-switch.corrupt.*.json"))


def test_missing_token_under_r1_postpones(cfg: ad.Config) -> None:
    _crash_after_candidate_plist(cfg)
    cfg.env_file.unlink()  # live_probe -> read_env_token raises
    host = FakeHost()
    host.r1_block = "R1_OPEN_RECOVERY_BLOCKS_V1_EFFECT:gen9:REQUESTED"
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "RECONCILED_BLOCKED_MANAGER_BUSY"
    assert cfg.journal.exists() and not cfg.hold_file.exists()


def test_rollback_postponed_when_r1_lock_is_unavailable_keeps_the_journal(cfg: ad.Config) -> None:
    class GuardFailsOnRollback(FakeHost):
        uses = 0

        @contextlib.contextmanager
        def r1_guard(self, c: ad.Config) -> Iterator[None]:  # type: ignore[override]
            self.uses += 1
            if self.uses > 1:  # the switch got the lock; the rollback cannot
                raise ad.DeployError("MANAGER_LOCK_UNAVAILABLE:r1-ledger:timeout")
            yield

    host = GuardFailsOnRollback()
    result = cycle(cfg, host, FakeProber({(ad.LIVE_PORT, NEW): False}))
    assert result["status"] == "BLOCKED_MANAGER_BUSY"
    assert result["receipt"]["switched"] is True and cfg.journal.exists()
    assert not cfg.hold_file.exists()


# --------------------------------------------------- #2198 review round 2


def test_cycle_start_foreign_verdict_is_taken_under_both_locks(cfg: ad.Config) -> None:
    """R1 races the HOLD write: the decision runs under GATEWAY_LOCK + ledger lock."""
    _foreign_live_plist(cfg)
    host = FakeHost()
    held_during_hold_write: list[tuple[int, int]] = []
    real_set_hold = ad._set_hold

    def recording_set_hold(c: ad.Config, reason: str) -> None:
        held_during_hold_write.append((
            host.lock_events.count("acquire") - host.lock_events.count("release"),
            host.r1_guard_depth,
        ))
        held_during_hold_write.append((0, int(host.r1_try_append())))
        real_set_hold(c, reason)

    host.after_r1_check = host.r1_try_append
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ad, "_set_hold", recording_set_hold)
        result = cycle(cfg, host, FakeProber())
    assert result["status"] == "FOREIGN_PLIST" and cfg.hold_file.exists()
    (manager_depth, guard_depth), (_, append_ok) = held_during_hold_write
    assert manager_depth == 1 and guard_depth == 1 and append_ok == 0
    # Every racing append between the R1 check and the HOLD write was refused.
    assert host.r1_append_attempts and not any(host.r1_append_attempts)


def test_cycle_start_r1_opening_before_the_guarded_decision_blocks(cfg: ad.Config) -> None:
    """R1 opens after the plist looked unknown but before the guarded decision."""
    _foreign_live_plist(cfg)

    class OpensWhenGuarded(FakeHost):
        @contextlib.contextmanager
        def r1_guard(self, c: ad.Config) -> Iterator[None]:  # type: ignore[override]
            self.r1_block = "R1_OPEN_RECOVERY_BLOCKS_V1_EFFECT:gen10:REQUESTED"
            with FakeHost.r1_guard(self, c):
                yield

    result = cycle(cfg, OpensWhenGuarded(), FakeProber())
    assert result["status"] == "BLOCKED_MANAGER_BUSY" and not cfg.hold_file.exists()


def test_cycle_start_plist_adopted_meanwhile_proceeds(cfg: ad.Config) -> None:
    _foreign_live_plist(cfg)

    class AdoptedWhenGuarded(FakeHost):
        @contextlib.contextmanager
        def r1_guard(self, c: ad.Config) -> Iterator[None]:  # type: ignore[override]
            ad.remember_plist(c, c.plist.read_bytes())  # Owner ran `adopt` meanwhile
            with FakeHost.r1_guard(self, c):
                yield

    result = cycle(cfg, AdoptedWhenGuarded(), FakeProber())
    assert result["status"] != "FOREIGN_PLIST" and not cfg.hold_file.exists()


@pytest.mark.parametrize("raised", [TimeoutError("timed out"), OSError("reset"), ValueError("x")])
def test_probe_exception_on_valid_journal_rolls_back_not_quarantined(
    cfg: ad.Config, raised: Exception
) -> None:
    """R1 terminal, the live probe of the candidate raises: normal rollback path."""
    before = _crash_after_candidate_plist(cfg)

    class RaisesForCandidate(FakeProber):
        def probe(self, **kw: Any) -> dict[str, Any]:
            if kw["commit"] == NEW:
                raise raised
            return super().probe(**kw)

    host = FakeHost()
    result = cycle(cfg, host, RaisesForCandidate())
    assert result["status"] == "RECONCILED_ROLLED_BACK"
    assert type(raised).__name__ in result["receipt"]["probes"]["live"]["error"]
    assert cfg.plist.read_bytes() == before and not cfg.journal.exists()
    assert not list(cfg.state_dir.glob("pending-switch.corrupt.*.json"))


def test_reload_exception_on_valid_journal_rolls_back(cfg: ad.Config) -> None:
    before = _crash_after_candidate_plist(cfg)
    host = FakeHost()

    def first_reload_breaks(count: int) -> None:
        if count == 1:
            raise RuntimeError("launchctl exploded")

    host.on_reload = first_reload_breaks
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "RECONCILED_ROLLED_BACK"
    assert cfg.plist.read_bytes() == before and not cfg.journal.exists()


def test_tool_link_error_does_not_fail_a_deploy(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: Any, **_k: Any) -> Any:
        raise OSError("read-only")

    monkeypatch.setattr(ad._Cycle, "_move_tool_link", boom)
    result = cycle(cfg, FakeHost(), FakeProber())
    assert result["status"] == "DEPLOYED"
    assert result["receipt"]["deployer_link"]["moved"] is False


# ------------------------------------------------------------ #2169 follow-ups


def _health_core_block(
    revision: str, *, status: str = "CORE_REVISION_PINNED", **changes: Any
) -> dict[str, Any]:
    """The unauthenticated ``/health`` ``core_provenance`` projection (#2201)."""
    return {
        "status": status,
        "expected_revision": revision,
        "observed_commit": revision,
        "fail_closed": False,
        **changes,
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2025-10-09T08:53:20Z", NOW),
        ("2025-10-09T08:53:20z", NOW),
        ("2025-10-09T08:53:20+00:00", NOW),
        ("2025-10-09T10:53:20+02:00", NOW),
        ("2025-10-09T08:53:20.000Z", NOW),
        ("2025-10-09T08:53:20.5Z", NOW + 0.5),
        ("2025-10-09T08:53:20.123456+00:00", NOW + 0.123456),
        ("2025-10-09T08:53:20", None),  # no offset: zone unknown
        ("2025-10-09", None),
        ("2025-10-09T08:53:20.1234567Z", None),
        ("2025-13-09T08:53:20Z", None),
        ("yesterday", None),
        ("", None),
        (None, None),
        (1_760_000_000, None),
    ],
    # No timestamps in ids: the impact gate normalizes datetimes in node ids.
    ids=[
        "z-upper",
        "z-lower",
        "offset-zero",
        "offset-plus2",
        "millis",
        "half-second",
        "micros",
        "naive",
        "date-only",
        "seven-digit-fraction",
        "bad-month",
        "word",
        "empty",
        "none",
        "number",
    ],
)
def test_parse_time_accepts_rfc3339_variants_only(value: Any, expected: float | None) -> None:
    parsed = ad._parse_time(value)
    if expected is None:
        assert parsed is None
    else:
        assert parsed == pytest.approx(expected)


@pytest.mark.parametrize("kind", ["head_ref_force_pushed", "head_ref_restored"])
@pytest.mark.parametrize(
    "created_at",
    [None, "", "not a date", "2025-01-01T00:00:00", 12345],
    ids=["missing", "empty", "garbage", "naive", "number"],
)
def test_head_push_event_without_a_parseable_time_counts_as_recent(
    kind: str, created_at: Any
) -> None:
    """#2169 F1: a force-push/restore of unknown age may be recent, so it blocks."""
    event: dict[str, Any] = {"event": kind}
    if created_at is not None:
        event["created_at"] = created_at
    api = green_api(
        open_pulls=_old_pin_pr(16),
        pushed_at={"e" * 40: OLD_ISO},
        timeline={16: [event]},
    )
    result = ad.pin_bumps_in_flight(api, now=NOW)
    assert result["verdict"] == "IN_FLIGHT" and result["ignored_stale"] == []


@pytest.mark.parametrize(
    ("created_at", "verdict"),
    [
        ("2025-01-01T00:00:00+00:00", "CLEAR"),
        ("2025-01-01T00:00:00.000Z", "CLEAR"),
        ("2025-10-09T08:53:20.000Z", "IN_FLIGHT"),
        ("2025-10-09T10:53:20+02:00", "IN_FLIGHT"),
    ],
    ids=["old-offset-zero", "old-millis", "recent-millis", "recent-offset-plus2"],
)
def test_head_push_event_with_an_rfc3339_variant_time_is_dated(
    created_at: str, verdict: str
) -> None:
    api = green_api(
        open_pulls=_old_pin_pr(17),
        pushed_at={"e" * 40: OLD_ISO},
        timeline={17: [{"event": "head_ref_force_pushed", "created_at": created_at}]},
    )
    assert ad.pin_bumps_in_flight(api, now=NOW)["verdict"] == verdict


def test_raising_commit_lookup_for_a_dateless_committed_event_is_unknown() -> None:
    base = green_api(
        open_pulls=_old_pin_pr(18),
        pushed_at={"e" * 40: OLD_ISO},
        timeline={18: [_committed_event("d" * 40, None)]},
    )

    def api(path: str) -> Any:
        if path.endswith("/commits/" + "d" * 40):
            raise RuntimeError("HTTP 502")
        return base(path)

    result = ad.pin_bumps_in_flight(api, now=NOW)
    assert result["verdict"] == "UNKNOWN" and "HTTP 502" in result["error"]


@pytest.mark.parametrize(
    ("block", "ok"),
    [
        (_health_core_block(NEW), True),
        (None, False),
        ("CORE_REVISION_PINNED", False),
        (_health_core_block(NEW, status="CORE_REVISION_MISMATCH"), False),
        (_health_core_block(NEW, status="CORE_PROVENANCE_PROBE_FAILED"), False),
        (_health_core_block(NEW, expected_revision=OLD), False),
        (_health_core_block(NEW, observed_commit=OLD), False),
        (_health_core_block(OLD), False),
        (_health_core_block(NEW, fail_closed=True), False),
        (_health_core_block(NEW, fail_closed=None), False),
        (_health_core_block(NEW, fail_closed="false"), False),
    ],
    ids=[
        "pinned",
        "missing",
        "not-a-dict",
        "mismatch",
        "probe-failed",
        "other-expectation",
        "other-observed",
        "other-revision",
        "fail-closed",
        "fail-closed-missing",
        "fail-closed-string",
    ],
)
def test_health_core_provenance_requires_the_pinned_revision(block: Any, ok: bool) -> None:
    health = _health(NEW)
    if block is not None:
        health["core_provenance"] = block
    check = ad.health_core_provenance(health, {"revision": NEW, "root": "/core"})
    assert check["ok"] is ok
    assert ad.health_core_provenance(health, {})["ok"] is False  # no pin: fail closed


class _OnDiskCorePinned(ad.Prober):
    """The on-disk subprocess check passes; only ``/health`` varies."""

    def core_provenance(self, *, root: Path, python: Path, core: Any) -> dict[str, Any]:  # type: ignore[override]
        return {"ok": True, "status": "CORE_REVISION_PINNED"}


@pytest.mark.parametrize(
    ("block", "ok"),
    [
        (_health_core_block(NEW), True),
        (None, False),
        (_health_core_block(NEW, observed_commit=OLD), False),
        (_health_core_block(NEW, fail_closed=True), False),
    ],
    ids=["pinned", "missing", "preload-broken", "fail-closed"],
)
def test_candidate_probe_also_reads_the_in_process_core_provenance(block: Any, ok: bool) -> None:
    """An in-process vs on-disk mismatch fails the probe (both checks are kept)."""
    health = _health(NEW)
    if block is not None:
        health["core_provenance"] = block
    with fake_gateway(health, 3, False) as port:
        result = _OnDiskCorePinned(ad.Host()).probe(
            port=port,
            token="tok",
            commit=NEW,
            root=REPO_ROOT,
            python=Path(sys.executable),
            timeout=10,
            core={"revision": NEW, "root": "/core"},
        )
    assert result["checks"]["core_provenance"]["ok"] is True
    assert result["checks"]["health_core_provenance"]["ok"] is ok
    assert result["ok"] is ok


@pytest.mark.parametrize(
    ("identity_source", "digest", "ok"),
    [
        pytest.param("source_digest", "sha256:" + "1" * 64, True, id="digest_build_digest_host"),
        pytest.param(None, "sha256:" + "1" * 64, False, id="digest_build_git_host"),
        pytest.param("build_stamp", "sha256:" + "1" * 64, False, id="digest_build_stamp_host"),
        pytest.param(None, None, True, id="old_core_pin"),
    ],
)
def test_health_core_provenance_requires_digest_identity_for_a_digest_build(
    identity_source: str | None, digest: str | None, ok: bool
) -> None:
    """#2246: the live Gateway must report it pinned Core by this build's digest."""
    block = _health_core_block(NEW)
    if identity_source is not None:
        block["identity_source"] = identity_source
    core = {"revision": NEW, "root": "/g/core/" + NEW, "source_digest": digest}
    check = ad.health_core_provenance({"core_provenance": block}, core)
    assert check["ok"] is ok, check


def test_rollback_probe_does_not_require_the_health_core_block() -> None:
    """A predecessor from before #2201 has no ``core_provenance`` in ``/health``."""
    with fake_gateway(_health(OLD), 3, False) as port:
        result = ad.Prober(ad.Host()).probe(
            port=port,
            token="tok",
            commit=OLD,
            root=REPO_ROOT,
            python=Path(sys.executable),
            timeout=10,
        )
    assert result["ok"] is True and "health_core_provenance" not in result["checks"]


def _fail_receipts(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(cfg: ad.Config, receipt: dict[str, Any]) -> None:
        raise OSError("receipts disk full")

    monkeypatch.setattr(ad, "_append_receipt", boom)


def test_receipt_failure_under_open_r1_never_writes_hold(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2169 F1: R1 open + receipt append fails: no HOLD, journal kept, retried."""
    _crash_after_candidate_plist(cfg)
    live_before = cfg.plist.read_bytes()
    _fail_receipts(monkeypatch)
    host = FakeHost()
    host.r1_block = "R1_OPEN_RECOVERY_BLOCKS_V1_EFFECT:gen10:REQUESTED"
    with pytest.raises(OSError, match="receipts disk full"):
        cycle(cfg, host, FakeProber({(ad.LIVE_PORT, NEW): False}))
    assert not cfg.hold_file.exists() and cfg.journal.exists()
    assert cfg.plist.read_bytes() == live_before and host.reloads == []
    monkeypatch.undo()
    # R1 still open, receipts writable again: an ordinary postponement.
    result = cycle(cfg, host, FakeProber({(ad.LIVE_PORT, NEW): False}))
    assert result["status"] == "RECONCILED_BLOCKED_MANAGER_BUSY"
    assert not cfg.hold_file.exists() and cfg.journal.exists()


def test_unexpected_reconcile_error_under_open_r1_postpones_without_hold(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2169 F1: any reconcile failure seen while R1 is open keeps the journal, no HOLD.

    Defence in depth: ``move_tool_link`` swallows its own errors today, so this
    stands in for any future raising step (the reachable ones are the plist read
    and the receipt write, tested separately).
    """
    _crash_after_candidate_plist(cfg)

    def explode(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("tool link exploded")

    monkeypatch.setattr(ad._Cycle, "move_tool_link", explode)
    host = FakeHost()
    host.r1_block = "R1_OPEN_RECOVERY_BLOCKS_V1_EFFECT:gen11:PREFLIGHTED"
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "RECONCILED_BLOCKED_MANAGER_BUSY"
    assert "RECONCILE_FAILED:RuntimeError" in result["receipt"]["reason"]
    assert not cfg.hold_file.exists() and cfg.journal.exists()


def test_reconcile_failed_hold_without_its_receipt_still_stops_retries(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2169 F2: the RECONCILE_FAILED receipt could not be written, only the HOLD."""
    _crash_journal(cfg)

    def explode(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("unexpected")

    with monkeypatch.context() as patch:
        patch.setattr(ad._Cycle, "finish_switch", explode)
        _fail_receipts(patch)
        with pytest.raises(OSError, match="receipts disk full"):
            cycle(cfg, FakeHost(), FakeProber())
    assert cfg.hold_file.read_text().startswith(ad.RECONCILE_FAILED_HOLD)
    assert cfg.journal.exists() and ad.read_receipts(cfg.state_dir) == []
    host, prober = FakeHost(), FakeProber()
    result = cycle(cfg, host, prober)
    assert result["status"] == "HELD"
    assert host.reloads == [] and prober.calls == [] and cfg.journal.exists()


def test_other_hold_with_a_pending_journal_is_still_reconciled(cfg: ad.Config) -> None:
    """F2 is narrow: an ordinary Owner HOLD does not stop journal reconciliation."""
    _crash_journal(cfg)
    ad._set_hold(cfg, "owner: paused for maintenance")
    result = cycle(cfg, FakeHost(), FakeProber())
    assert result["status"].startswith("RECONCILED_") and not cfg.journal.exists()


def test_deploy_error_during_reconcile_keeps_a_validated_journal(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2169 F3: a non-lock DeployError is RECONCILE_FAILED, never JOURNAL_CORRUPT."""
    _crash_journal(cfg)

    def explode(*_a: Any, **_k: Any) -> Any:
        raise ad.DeployError("GATEWAY_LABEL_MISMATCH")

    monkeypatch.setattr(ad._Cycle, "finish_switch", explode)
    result = cycle(cfg, FakeHost(), FakeProber())
    assert result["status"] == "RECONCILED_RECONCILE_FAILED"
    assert "RECONCILE_FAILED:DeployError:GATEWAY_LABEL_MISMATCH" in result["receipt"]["reason"]
    assert cfg.hold_file.read_text().startswith(ad.RECONCILE_FAILED_HOLD)
    assert cfg.journal.exists()
    assert not list(cfg.state_dir.glob("pending-switch.corrupt.*.json"))


# Real InterProcessLock (fcntl) on both #526 locks, no counting fakes.


def _real_locks_host(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> tuple[FakeHost, Path, Path]:
    from scripts.ops import mcp_gateway_durable as durable

    cfg.gateway_root.chmod(0o700)
    monkeypatch.setattr(durable, "GATEWAY_STATE_ROOT", cfg.gateway_root)
    monkeypatch.setattr(durable, "GATEWAY_LOCK", cfg.gateway_root / "ledger.lock")
    monkeypatch.setattr(durable, "GATEWAY_LEDGER", cfg.gateway_root / "ledger.jsonl")
    ledger_lock = durable.GatewayLedger(cfg.gateway_root / "ledger.jsonl").lock_path

    class RealLocks(FakeHost):
        def r1_recovery_block(self, c: ad.Config) -> str | None:  # type: ignore[override]
            block = ad.Host.r1_recovery_block(self, c)
            if self.after_r1_check is not None:
                self.after_r1_check()
            return block

        def r1_guard(self, c: ad.Config):  # type: ignore[override]
            return ad.Host.r1_guard(self, c)

        def manager_lock(self, c: ad.Config):  # type: ignore[override]
            return ad.Host.manager_lock(self, c)

    return RealLocks(), cfg.gateway_root / "ledger.lock", ledger_lock


def _other_process_gets(path: Path) -> bool:
    """Try ``path`` from another thread (no re-entrancy), as R1 or the manager would."""
    from scripts.ops import mcp_gateway_durable as durable

    got: list[bool] = []

    def attempt() -> None:
        try:
            with durable.InterProcessLock(path, timeout=0.2):
                got.append(True)
        except Exception:  # noqa: BLE001 - contention
            got.append(False)

    thread = threading.Thread(target=attempt)
    thread.start()
    thread.join(timeout=10)
    return got == [True]


@contextlib.contextmanager
def _held_elsewhere(path: Path) -> Iterator[None]:
    """Hold ``path`` from another thread until the block ends."""
    from scripts.ops import mcp_gateway_durable as durable

    taken, release = threading.Event(), threading.Event()

    def hold() -> None:
        with durable.InterProcessLock(path, timeout=5):
            taken.set()
            release.wait(timeout=30)

    thread = threading.Thread(target=hold)
    thread.start()
    assert taken.wait(timeout=10)
    try:
        yield
    finally:
        release.set()
        thread.join(timeout=10)


def test_real_locks_held_from_r1_check_through_rollback(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GATEWAY_LOCK then ledger.jsonl.lock, both real, are held at the R1 check, the
    journal + plist write, the reload, the live probe, the rollback's nested
    (re-entrant) guard and R1 re-read, its reload and its probe."""
    host, gateway_lock, ledger_lock = _real_locks_host(cfg, monkeypatch)
    host.lock_timeout_seconds = 2.0  # a re-entrancy bug fails fast, not after 30 s
    seen: list[tuple[str, bool, bool]] = []

    def contend(where: str) -> None:
        seen.append((where, _other_process_gets(gateway_lock), _other_process_gets(ledger_lock)))

    def on_reload(count: int) -> None:
        assert cfg.journal.exists()  # journal written before the plist and reload
        contend(f"reload{count}")

    host.on_reload = on_reload

    def hook(call: dict[str, Any]) -> None:
        if call["port"] == 50123:  # pre-build advisory check is done
            host.after_r1_check = lambda: contend("r1-check")
        if call["port"] == ad.LIVE_PORT:
            contend(f"live-probe-{call['commit'][:1]}")

    result = cycle(cfg, host, FakeProber({(ad.LIVE_PORT, NEW): False}, hook=hook))
    assert result["status"] == "ROLLED_BACK"
    where = [w for w, _g, _l in seen]
    assert where == ["r1-check", "reload1", "live-probe-b", "r1-check", "reload2", "live-probe-a"]
    assert all(not gw and not lg for _w, gw, lg in seen), seen
    assert _other_process_gets(gateway_lock) and _other_process_gets(ledger_lock)


def test_real_ledger_lock_held_by_r1_blocks_the_switch(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    host, _gateway_lock, ledger_lock = _real_locks_host(cfg, monkeypatch)
    host.lock_timeout_seconds = 0.2
    before = cfg.plist.read_bytes()
    stack = contextlib.ExitStack()

    def hook(call: dict[str, Any]) -> None:
        if call["port"] == 50123:  # R1 takes its ledger lock after the advisory check
            stack.enter_context(_held_elsewhere(ledger_lock))

    with stack:
        result = cycle(cfg, host, FakeProber(hook=hook))
    assert result["status"] == "BLOCKED_MANAGER_BUSY"
    assert "MANAGER_LOCK_UNAVAILABLE:r1-ledger" in result["receipt"]["reason"]
    assert cfg.plist.read_bytes() == before and not cfg.journal.exists()
    assert host.reloads == [] and not cfg.hold_file.exists()


def test_real_gateway_lock_held_by_the_manager_blocks_the_switch(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    host, gateway_lock, _ledger_lock = _real_locks_host(cfg, monkeypatch)
    host.lock_timeout_seconds = 0.2
    before = cfg.plist.read_bytes()
    with _held_elsewhere(gateway_lock):
        result = cycle(cfg, host, FakeProber())
    assert result["status"] == "BLOCKED_MANAGER_BUSY"
    assert "MANAGER_LOCK_UNAVAILABLE" in result["receipt"]["reason"]
    assert cfg.plist.read_bytes() == before and not cfg.journal.exists()
    assert host.reloads == [] and not cfg.hold_file.exists()


def test_real_locks_reconcile_journal_under_both_locks(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Journal reconciliation also runs under the real GATEWAY_LOCK -> ledger lock."""
    _crash_after_candidate_plist(cfg)
    host, gateway_lock, ledger_lock = _real_locks_host(cfg, monkeypatch)
    host.lock_timeout_seconds = 2.0
    seen: list[tuple[bool, bool]] = []

    def hook(call: dict[str, Any]) -> None:
        seen.append((_other_process_gets(gateway_lock), _other_process_gets(ledger_lock)))

    result = cycle(cfg, host, FakeProber(hook=hook))
    assert result["status"] == "RECONCILED_DEPLOYED" and not cfg.journal.exists()
    assert seen and all(not gw and not lg for gw, lg in seen)
    # Positive control: the same helper gets both locks once the cycle is over.
    assert _other_process_gets(gateway_lock) and _other_process_gets(ledger_lock)


def test_plist_read_error_under_open_r1_postpones_without_hold(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex round 1: the R1 block is recorded before the live plist is read."""
    _crash_after_candidate_plist(cfg)
    real_read = Path.read_bytes

    def flaky(self: Path) -> bytes:
        if self == cfg.plist:
            raise OSError("EIO on plist")
        return real_read(self)

    host = FakeHost()
    host.r1_block = "R1_OPEN_RECOVERY_BLOCKS_V1_EFFECT:gen12:REQUESTED"
    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", flaky)
        result = cycle(cfg, host, FakeProber())
    assert result["status"] == "RECONCILED_BLOCKED_MANAGER_BUSY"
    assert "EIO on plist" in result["receipt"]["reason"]
    assert not cfg.hold_file.exists() and cfg.journal.exists() and host.reloads == []


def test_hold_is_written_atomically(cfg: ad.Config, monkeypatch: pytest.MonkeyPatch) -> None:
    """Codex round 1: a failed HOLD write leaves no truncated HOLD text behind."""
    real_fsync = os.fsync

    def full_disk(fd: int) -> None:
        raise OSError("disk full")

    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    other = cfg.state_dir / f".HOLD.tmp.{os.getpid()}"  # a concurrent writer's file
    other.write_text("theirs")
    with monkeypatch.context() as patch:
        patch.setattr(ad.os, "fsync", full_disk)
        with pytest.raises(OSError, match="disk full"):
            ad._set_hold(cfg, f"{ad.RECONCILE_FAILED_HOLD} x; journal kept")
    assert not cfg.hold_file.exists()
    # Its own temp file is gone; another writer's is untouched.
    assert list(cfg.state_dir.glob(".HOLD*.tmp.*")) == [other]
    assert other.read_text() == "theirs"
    assert ad.os.fsync is real_fsync
    ad._set_hold(cfg, "owner: paused")
    assert cfg.hold_file.read_text() == "owner: paused\n"
    assert cfg.hold_file.stat().st_mode & 0o777 == 0o600


def test_atomic_write_never_removes_a_temp_path_it_did_not_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex round 4: a pre-existing file or symlink at the temp name is left alone."""
    monkeypatch.setattr(ad.os, "urandom", lambda n: b"\x00" * n)
    dest = tmp_path / "status.json"
    taken = tmp_path / f".status.json.tmp.{os.getpid()}.{'00' * 6}"
    victim = tmp_path / "victim"
    victim.write_text("keep")
    taken.symlink_to(victim)
    with pytest.raises(FileExistsError):
        ad._atomic_write(dest, b"new")
    assert taken.is_symlink() and victim.read_text() == "keep"
    assert not dest.exists()


# ------------------------------------------------------- task quiescence (#2227)


def _write_task(cfg: ad.Config, task_id: str, status: str | None, raw: str | None = None) -> None:
    cfg.canonical_state_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.canonical_state_dir / f"{task_id}.json"
    path.write_text(
        raw if raw is not None else json.dumps({"task_id": task_id, "status": status}),
        encoding="utf-8",
    )


def _receipts(cfg: ad.Config) -> list[dict[str, Any]]:
    return ad.read_receipts(cfg.state_dir)


def _deferrals(cfg: ad.Config) -> list[dict[str, Any]]:
    if not cfg.deferrals.exists():
        return []
    return [json.loads(line) for line in cfg.deferrals.read_text().splitlines() if line]


def test_quiescence_real_in_flight_task_defers_the_switch(cfg: ad.Config) -> None:
    """Positive control: a real WORKER_RUNNING task, classified by the real lifecycle code."""
    _write_task(cfg, "running-task", "WORKER_RUNNING")
    _write_task(cfg, "done-task", "DIRECT_COMPLETED")
    host, prober = FakeHost(), FakeProber()
    host.real_classifier = True
    result = cycle(cfg, host, prober)
    assert result["status"] == ad.DEFERRED_OUTCOME
    assert result["quiescence"]["blocking"] == ["running-task"]
    assert host.reloads == []
    assert not any(argv[:1] == ["uv"] for argv in host.calls)  # no build churn
    deferred = _deferrals(cfg)
    assert deferred and deferred[-1]["quiescence"]["blocking"] == ["running-task"]
    # Deferral records never enter receipts.jsonl (backoff, give-up, drift).
    assert not [r for r in _receipts(cfg) if r.get("outcome") == ad.DEFERRED_OUTCOME]
    assert cfg.quiescence_file.exists()


def test_quiescence_real_terminal_task_does_not_block(cfg: ad.Config) -> None:
    """Negative control: only terminal tasks, classified by the real lifecycle code."""
    _write_task(cfg, "done-task", "DIRECT_COMPLETED")
    _write_task(cfg, "old-block", "FINAL_BLOCK")
    host, prober = FakeHost(), FakeProber()
    host.real_classifier = True
    result = cycle(cfg, host, prober)
    assert result["status"] == "DEPLOYED"
    assert len(host.reloads) == 1
    assert not cfg.quiescence_file.exists()


def test_quiescence_unreadable_task_state_fails_closed(cfg: ad.Config) -> None:
    _write_task(cfg, "corrupt", None, raw="{not json")
    host, prober = FakeHost(), FakeProber()
    host.real_classifier = True
    result = cycle(cfg, host, prober)
    assert result["status"] == ad.DEFERRED_OUTCOME
    assert result["quiescence"]["blocking"] == ["corrupt:UNREADABLE"]
    assert host.reloads == []


def test_quiescence_unknown_classifier_result_fails_closed(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    host.in_flight = [{"verdict": "UNKNOWN", "reason": "CLASSIFIER_EXIT_1"}]
    result = cycle(cfg, host, prober)
    assert result["status"] == ad.DEFERRED_OUTCOME
    assert result["quiescence"]["blocking"] == ["CLASSIFIER_EXIT_1"]
    assert host.reloads == []


def test_quiescence_warns_once_after_cap_and_never_forces(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    blocked = {"verdict": "IN_FLIGHT", "task_ids": ["t-1"], "checked": 1}
    host.in_flight = [blocked]
    first = cycle(cfg, host, prober)
    assert first["status"] == ad.DEFERRED_OUTCOME
    assert first["quiescence"]["deferral_age_seconds"] == 0
    assert host.issue_comments == []
    host.clock += ad.QUIESCENCE_WARN_AFTER_SECONDS + 60
    second = cycle(cfg, host, prober)
    assert second["status"] == ad.DEFERRED_OUTCOME
    assert second["quiescence"]["deferral_age_seconds"] >= ad.QUIESCENCE_WARN_AFTER_SECONDS
    assert len(host.issue_comments) == 1
    assert "`t-1`" in host.issue_comments[0]
    assert "NEXUS_GATEWAY_QUIESCENCE_WARNING" in host.issue_comments[0]
    host.clock += 3600
    third = cycle(cfg, host, prober)
    assert third["status"] == ad.DEFERRED_OUTCOME
    assert len(host.issue_comments) == 1  # one warning per episode
    assert host.reloads == []  # never forced, however old
    # Deferral log: the episode start and the warning, not one line per cycle.
    assert len(_deferrals(cfg)) == 2
    host.in_flight = []
    host.clock += 60
    done = cycle(cfg, host, prober)
    assert done["status"] == "DEPLOYED"
    deployed = _receipts(cfg)[-1]
    assert deployed["outcome"] == "DEPLOYED"
    ended = deployed["quiescence"]["ended_deferral"]
    assert ended["deferral_age_seconds"] >= ad.QUIESCENCE_WARN_AFTER_SECONDS + 3600
    assert not cfg.quiescence_file.exists()


def test_quiescence_failed_warning_is_retried(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    host.in_flight = [{"verdict": "IN_FLIGHT", "task_ids": ["t-1"], "checked": 1}]
    cycle(cfg, host, prober)
    host.clock += ad.QUIESCENCE_WARN_AFTER_SECONDS + 1
    host.comment_fails = True
    assert cycle(cfg, host, prober)["quiescence"]["warned_at"] is None
    host.comment_fails = False
    host.clock += 300
    cycle(cfg, host, prober)
    assert len(host.issue_comments) == 1


def test_quiescence_rechecked_under_the_lock_before_the_switch(cfg: ad.Config) -> None:
    """A task that starts while the candidate builds still stops the switch."""
    host, prober = FakeHost(), FakeProber()
    host.in_flight = [
        {"verdict": "CLEAR", "checked": 0},
        {"verdict": "IN_FLIGHT", "task_ids": ["late-task"], "checked": 1},
    ]
    result = cycle(cfg, host, prober)
    assert result["status"] == ad.DEFERRED_OUTCOME
    receipt = _receipts(cfg)[-1]
    assert receipt["outcome"] == ad.DEFERRED_OUTCOME
    assert receipt["switched"] is False
    assert receipt["quiescence_before_switch"]["task_ids"] == ["late-task"]
    assert host.reloads == []
    assert ad.DEFERRED_OUTCOME not in ad.FAILED_OUTCOMES  # no backoff, no give-up


def test_quiescence_manual_override_switches_and_is_recorded(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    host.in_flight = [{"verdict": "IN_FLIGHT", "task_ids": ["orphan"], "checked": 1}]
    result = ad.run_cycle(
        cfg,
        host,
        prober,
        green_api(),
        environ={},
        tool_python=Path("/tool/python"),
        allow_in_flight=True,
    )
    assert result["status"] == "DEPLOYED"
    receipt = _receipts(cfg)[-1]
    assert receipt["quiescence_overridden"] is True
    assert receipt["quiescence"]["overridden"] is True


def test_quiescence_hold_still_wins_and_checks_nothing(cfg: ad.Config) -> None:
    ad._set_hold(cfg, "manual")
    host, prober = FakeHost(), FakeProber()
    host.in_flight = [{"verdict": "IN_FLIGHT", "task_ids": ["t"], "checked": 1}]
    assert cycle(cfg, host, prober)["status"] == "HELD"
    assert host.quiescence_checks == 0
    assert host.reloads == []


def test_real_host_classifies_with_the_live_interpreter_and_tree(tmp_path: Path) -> None:
    cfg = ad.Config.default(tmp_path / "home")
    _write_task(cfg, "running", "WORKER_RUNNING")
    plist = live_plist(REPO_ROOT, python=sys.executable)
    verdict = ad.Host().tasks_in_flight(cfg, plist)
    assert verdict == {"verdict": "IN_FLIGHT", "task_ids": ["running"], "checked": 1}
    missing = live_plist(REPO_ROOT, python=str(tmp_path / "no-python"))
    assert ad.Host().tasks_in_flight(cfg, missing)["verdict"] == "UNKNOWN"


@pytest.mark.parametrize(
    ("code", "stdout", "verdict"),
    [
        (1, '{"tasks": []}', "UNKNOWN"),
        (0, "", "UNKNOWN"),
        (0, "not json", "UNKNOWN"),
        (0, '{"tasks": "x"}', "UNKNOWN"),
        (0, '{"tasks": [1]}', "UNKNOWN"),
        (0, '{"tasks": []}', "CLEAR"),
        (0, '{"tasks": [{"task_id": "a", "action_state": "TERMINAL"}]}', "CLEAR"),
        (0, '{"tasks": [{"task_id": "a", "action_state": "ACTION_REQUIRED"}]}', "IN_FLIGHT"),
        (0, '{"tasks": [{"task_id": "a", "action_state": "SOMETHING_NEW"}]}', "IN_FLIGHT"),
    ],
)
def test_classify_task_report_fails_closed(code: int, stdout: str, verdict: str) -> None:
    assert ad.classify_task_report(code, stdout)["verdict"] == verdict


def test_classify_task_report_never_echoes_unsafe_task_ids() -> None:
    report = json.dumps({
        "tasks": [{"task_id": "x\n::warning::evil", "action_state": "IN_PROGRESS"}]
    })
    verdict = ad.classify_task_report(0, report)
    assert verdict["task_ids"] == ["<unprintable-task-id>"]


def test_quiescence_unknown_lifecycle_status_fails_closed(cfg: ad.Config) -> None:
    """The lifecycle maps an unknown status to FINAL_BLOCK; the gate must not read that as clear."""
    _write_task(cfg, "future-task", "SOME_FUTURE_STATUS")
    _write_task(cfg, "no-status", None, raw=json.dumps({"task_id": "no-status"}))
    host, prober = FakeHost(), FakeProber()
    host.real_classifier = True
    result = cycle(cfg, host, prober)
    assert result["status"] == ad.DEFERRED_OUTCOME
    assert result["quiescence"]["blocking"] == [
        "future-task:INVALID_STATUS",
        "no-status:INVALID_STATUS",
    ]
    assert host.reloads == []


def test_quiescence_late_detection_shares_the_episode_clock_and_warning(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    late = {"verdict": "IN_FLIGHT", "task_ids": ["late"], "checked": 1}
    host.in_flight = [{"verdict": "CLEAR", "checked": 0}, late]
    assert cycle(cfg, host, prober)["status"] == ad.DEFERRED_OUTCOME
    episode = json.loads(cfg.quiescence_file.read_text())
    assert episode["blocking"] == ["late"]
    assert _receipts(cfg)[-1]["quiescence_episode"]["deferral_age_seconds"] == 0
    host.clock += ad.QUIESCENCE_WARN_AFTER_SECONDS + 1
    host.in_flight = [{"verdict": "CLEAR", "checked": 0}, late]
    assert cycle(cfg, host, prober)["status"] == ad.DEFERRED_OUTCOME
    assert len(host.issue_comments) == 1
    assert "`late`" in host.issue_comments[0]


@pytest.mark.parametrize(
    "episode",
    [
        '{"since_epoch": NaN, "warned_at": null}',
        '{"since_epoch": "x", "warned_at": true}',
        '{"since_epoch": 1, "warned_at": ["not", "a", "time"]}',
        "not json",
    ],
)
def test_quiescence_corrupt_episode_never_suppresses_the_warning(
    cfg: ad.Config, episode: str
) -> None:
    host, prober = FakeHost(), FakeProber()
    host.in_flight = [{"verdict": "IN_FLIGHT", "task_ids": ["t"], "checked": 1}]
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.quiescence_file.write_text(episode)
    first = cycle(cfg, host, prober)
    assert first["status"] == ad.DEFERRED_OUTCOME
    host.clock += ad.QUIESCENCE_WARN_AFTER_SECONDS + 1
    assert cycle(cfg, host, prober)["status"] == ad.DEFERRED_OUTCOME
    assert len(host.issue_comments) == 1


def test_quiescence_clock_going_back_does_not_restart_the_episode(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    host.in_flight = [{"verdict": "IN_FLIGHT", "task_ids": ["t"], "checked": 1}]
    cycle(cfg, host, prober)
    since = json.loads(cfg.quiescence_file.read_text())["since_epoch"]
    host.clock -= 3600
    result = cycle(cfg, host, prober)
    assert result["quiescence"]["deferral_age_seconds"] == 0
    assert json.loads(cfg.quiescence_file.read_text())["since_epoch"] == since


def test_classify_task_report_sanitizes_unknown_action_states() -> None:
    report = json.dumps({"tasks": [{"task_id": "a", "action_state": "x](http://evil)\n@all"}]})
    assert ad.classify_task_report(0, report)["task_ids"] == ["a:UNKNOWN"]


def test_quiescence_flapping_tasks_still_warn(cfg: ad.Config) -> None:
    """Pre-build CLEAR, under-lock IN_FLIGHT every cycle must not restart the clock."""
    host, prober = FakeHost(), FakeProber()
    late = {"verdict": "IN_FLIGHT", "task_ids": ["flap"], "checked": 1}
    for _ in range(80):
        host.in_flight = [{"verdict": "CLEAR", "checked": 0}, late]
        assert cycle(cfg, host, prober)["status"] == ad.DEFERRED_OUTCOME
        host.clock += 700
    assert len(host.issue_comments) == 1
    assert host.reloads == []


def test_quiescence_override_ends_the_episode(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    host.in_flight = [{"verdict": "IN_FLIGHT", "task_ids": ["orphan"], "checked": 1}]
    cycle(cfg, host, prober)
    host.clock += ad.QUIESCENCE_WARN_AFTER_SECONDS + 1
    cycle(cfg, host, prober)
    assert len(host.issue_comments) == 1
    host.clock += 60
    result = ad.run_cycle(
        cfg,
        host,
        prober,
        green_api(),
        environ={},
        tool_python=Path("/tool/python"),
        allow_in_flight=True,
    )
    assert result["status"] == "DEPLOYED"
    assert not cfg.quiescence_file.exists()


def test_quiescence_running_assisted_job_defers_and_finished_one_does_not(cfg: ad.Config) -> None:
    jobs = cfg.canonical_state_dir / "assisted_provider_jobs"
    jobs.mkdir(parents=True)
    (jobs / "assist-1.json").write_text(json.dumps({"status": "RUNNING"}))
    (jobs / "assist-2.json").write_text(json.dumps({"status": "COMPLETED"}))
    host, prober = FakeHost(), FakeProber()
    host.real_classifier = True
    result = cycle(cfg, host, prober)
    assert result["status"] == ad.DEFERRED_OUTCOME
    assert result["quiescence"]["blocking"] == ["assist.assist-1:ASSIST_RUNNING"]
    (jobs / "assist-1.json").write_text(json.dumps({"status": "FAILED"}))
    host.clock += 3600
    assert cycle(cfg, host, prober)["status"] == "DEPLOYED"


def test_quiescence_unknown_reason_is_sanitized_before_any_comment(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    host.in_flight = [
        {"verdict": "UNKNOWN", "reason": "LIVE_PLIST_UNREADABLE:`x` @all\n::warning::"}
    ]
    cycle(cfg, host, prober)
    host.clock += ad.QUIESCENCE_WARN_AFTER_SECONDS + 1
    result = cycle(cfg, host, prober)
    assert result["quiescence"]["blocking"] == ["LIVE_PLIST_UNREADABLE"]
    assert "@all" not in host.issue_comments[0] and "::warning::" not in host.issue_comments[0]


def test_quiescence_old_warned_episode_does_not_mute_a_new_candidate(cfg: ad.Config) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.quiescence_file.write_text(
        json.dumps({
            "since_epoch": NOW - 10 * 3600,
            "candidate": "c" * 40,
            "blocking": ["old"],
            "warned_at": ad._iso(NOW - 3 * 3600),
        })
    )
    host, prober = FakeHost(), FakeProber()
    host.in_flight = [{"verdict": "IN_FLIGHT", "task_ids": ["new"], "checked": 1}]
    assert cycle(cfg, host, prober)["status"] == ad.DEFERRED_OUTCOME
    assert len(host.issue_comments) == 1
    assert "`new`" in host.issue_comments[0]


def test_quiescence_rewarns_daily_while_still_starved(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    host.in_flight = [{"verdict": "IN_FLIGHT", "task_ids": ["t"], "checked": 1}]
    cycle(cfg, host, prober)
    host.clock += ad.QUIESCENCE_WARN_AFTER_SECONDS + 1
    cycle(cfg, host, prober)
    host.clock += 3600
    cycle(cfg, host, prober)
    assert len(host.issue_comments) == 1
    host.clock += ad.QUIESCENCE_REWARN_SECONDS
    cycle(cfg, host, prober)
    assert len(host.issue_comments) == 2


def test_quiescence_impossible_warned_at_is_ignored(cfg: ad.Config) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.quiescence_file.write_text(
        json.dumps({
            "since_epoch": NOW - 10 * 3600,
            "candidate": NEW,
            "blocking": ["t"],
            "warned_at": "9999-99-99T99:99:99Z",
        })
    )
    host, prober = FakeHost(), FakeProber()
    host.in_flight = [{"verdict": "IN_FLIGHT", "task_ids": ["t"], "checked": 1}]
    cycle(cfg, host, prober)
    assert len(host.issue_comments) == 1


def test_quiescence_late_deferral_receipt_does_not_debounce_the_next_cycle(
    cfg: ad.Config,
) -> None:
    host, prober = FakeHost(), FakeProber()
    host.in_flight = [
        {"verdict": "CLEAR", "checked": 0},
        {"verdict": "IN_FLIGHT", "task_ids": ["late"], "checked": 1},
    ]
    assert cycle(cfg, host, prober)["status"] == ad.DEFERRED_OUTCOME
    host.in_flight = []
    host.clock += 60  # well inside min_interval_seconds
    assert cycle(cfg, host, prober)["status"] == "DEPLOYED"


@pytest.mark.parametrize(
    ("job", "label"),
    [
        ({"status": "UNKNOWN_REQUIRES_RECONCILE"}, "ASSIST_RECONCILE"),
        ({"status": "FAILED", "reconciliation_required": True}, "ASSIST_RECONCILE"),
        ({"status": "CANCELLED", "process_killed": False}, "ASSIST_UNSETTLED"),
    ],
)
def test_quiescence_unsettled_assisted_jobs_fail_closed(
    cfg: ad.Config, job: dict[str, Any], label: str
) -> None:
    jobs = cfg.canonical_state_dir / "assisted_provider_jobs"
    jobs.mkdir(parents=True)
    (jobs / "assist-9.json").write_text(json.dumps(job))
    host, prober = FakeHost(), FakeProber()
    host.real_classifier = True
    result = cycle(cfg, host, prober)
    assert result["status"] == ad.DEFERRED_OUTCOME
    assert result["quiescence"]["blocking"] == [f"assist.assist-9:{label}"]


def test_deferral_log_is_bounded(cfg: ad.Config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ad, "DEFERRALS_MAX_BYTES", 200)
    host, prober = FakeHost(), FakeProber()
    for index in range(20):
        host.in_flight = [{"verdict": "IN_FLIGHT", "task_ids": [f"t{index}"], "checked": 1}]
        cycle(cfg, host, prober)
        host.clock += 60
    assert cfg.deferrals.stat().st_size < 2000
    assert cfg.deferrals.with_name(cfg.deferrals.name + ".1").exists()


def test_quiescence_rearm_for_new_candidates_is_rate_limited(cfg: ad.Config) -> None:
    """A new candidate re-arms the warning only if the last one is at least an hour old."""

    def episode(warned_ago: float) -> None:
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        cfg.quiescence_file.write_text(
            json.dumps({
                "since_epoch": NOW - 10 * 3600,
                "candidate": "c" * 40,  # an earlier main commit
                "blocking": ["stuck"],
                "warned_at": ad._iso(NOW - warned_ago),
            })
        )

    host, prober = FakeHost(), FakeProber()
    host.in_flight = [{"verdict": "IN_FLIGHT", "task_ids": ["stuck"], "checked": 1}]
    episode(warned_ago=20 * 60)
    cycle(cfg, host, prober)
    assert host.issue_comments == []
    episode(warned_ago=ad.QUIESCENCE_REARM_MIN_SECONDS + 60)
    cycle(cfg, host, prober)
    assert len(host.issue_comments) == 1


def test_quiescence_future_warned_at_never_mutes(cfg: ad.Config) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.quiescence_file.write_text(
        json.dumps({
            "since_epoch": NOW - 10 * 3600,
            "candidate": NEW,
            "blocking": ["t"],
            "warned_at": "9999-12-31T23:59:59Z",
        })
    )
    host, prober = FakeHost(), FakeProber()
    host.in_flight = [{"verdict": "IN_FLIGHT", "task_ids": ["t"], "checked": 1}]
    cycle(cfg, host, prober)
    assert len(host.issue_comments) == 1


def test_quiescence_blocking_list_is_bounded(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    many = [f"t{index:04d}" for index in range(5000)]
    host.in_flight = [{"verdict": "IN_FLIGHT", "task_ids": many, "checked": 5000}]
    result = cycle(cfg, host, prober)
    assert len(result["quiescence"]["blocking"]) == 100
    assert len(result["quiescence"]["task_ids"]) == 100
    assert result["quiescence"]["task_count"] == 5000
    line = json.loads(cfg.deferrals.read_text().splitlines()[-1])
    assert len(line["quiescence"]["task_ids"]) == 100
    assert cfg.deferrals.stat().st_size < 20_000


def test_quiescence_candidate_arriving_inside_the_hour_still_rearms(cfg: ad.Config) -> None:
    """Warned for candidate C; NEW shows up 20 min later and must still be warned at 1 h."""
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.quiescence_file.write_text(
        json.dumps({
            "since_epoch": NOW - 10 * 3600,
            "candidate": "c" * 40,
            "blocking": ["stuck"],
            "warned_at": ad._iso(NOW - 20 * 60),
            "warned_candidate": "c" * 40,
        })
    )
    host, prober = FakeHost(), FakeProber()
    host.in_flight = [{"verdict": "IN_FLIGHT", "task_ids": ["stuck"], "checked": 1}]
    cycle(cfg, host, prober)  # NEW seen 20 min after the warning: no re-arm yet
    assert host.issue_comments == []
    assert json.loads(cfg.quiescence_file.read_text())["warned_candidate"] == "c" * 40
    host.clock += 45 * 60
    cycle(cfg, host, prober)  # 65 min after the warning: NEW gets its own
    assert len(host.issue_comments) == 1
    assert json.loads(cfg.quiescence_file.read_text())["warned_candidate"] == NEW


# ------------------------------------------------- Controller worktrees (#1939)


def _rg(cwd: Path, *args: str) -> str:
    return _fixture_git(cwd, *args)


@pytest.fixture()
def controller_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A real gateway-direct layout: bare repository.git, a live a1-OLD deployment
    with its Controller, and a NEW main commit."""
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "t")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@example.invalid")
    seed = tmp_path / "seed"
    seed.mkdir()
    _rg(seed, "init", "-q", "-b", "main")
    (seed / "README.md").write_text("base\n")
    (seed / "tasks").mkdir()
    (seed / "tasks" / "keep.md").write_text("tracked\n")
    _rg(seed, "add", ".")
    _rg(seed, "commit", "-qm", "old")
    old = _rg(seed, "rev-parse", "HEAD")
    (seed / "nexus.py").write_text("x = 1\n")
    _rg(seed, "add", ".")
    _rg(seed, "commit", "-qm", "new")
    new = _rg(seed, "rev-parse", "HEAD")
    cfg = ad.Config.default(tmp_path / "home")
    cfg.gateway_root.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", "-q", "--bare", str(seed), str(cfg.bare_repo)],
        check=True,
        env={**os.environ, **GIT_ENV},
    )
    host = ad.Host()
    deployment = cfg.deployments / f"a1-{old}"
    host.run(ad._git(cfg, "worktree", "add", "--detach", str(deployment), old))
    live_controller = ad.materialize_controller(cfg, host, old)
    plist = plistlib.dumps({
        "Label": ad.GATEWAY_LABEL,
        "KeepAlive": True,
        "RunAtLoad": True,
        "ProgramArguments": [
            "/bin/zsh",
            "-c",
            f'cd "{deployment}" ; export NEXUS_CANONICAL_SOURCE_ROOT="{live_controller}" ; '
            f'exec /usr/bin/python3 "{deployment}/scripts/ops/nexus_mcp_gateway_http.py"',
        ],
        "WorkingDirectory": str(deployment),
    })
    return {
        "cfg": cfg,
        "host": host,
        "old": old,
        "new": new,
        "deployment": deployment,
        "live_controller": live_controller,
        "plist": plist,
    }


def _bind(controller: Path, path: str, text: str) -> str:
    target = controller / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    _rg(controller, "--literal-pathspecs", "add", "--", path)
    _rg(controller, "commit", "-qm", f"chore(tasks): bind {path}")
    return _rg(controller, "rev-parse", "HEAD")


def test_controller_is_a_fresh_absolute_linked_worktree(controller_repo: dict[str, Any]) -> None:
    cfg, host, new = controller_repo["cfg"], controller_repo["host"], controller_repo["new"]
    controller = ad.materialize_controller(cfg, host, new)
    assert controller == cfg.controllers / f"a1-{new}"
    assert _rg(controller, "rev-parse", "HEAD") == new
    gitdir = Path(_rg(controller, "rev-parse", "--absolute-git-dir"))
    assert Path((gitdir / "gitdir").read_text().strip()).is_absolute()
    (controller / "stray.txt").write_text("dirty\n")
    again = ad.materialize_controller(cfg, host, new)  # recreated clean
    assert not (again / "stray.txt").exists()


def test_bound_cards_are_carried_byte_for_byte_and_accepted_by_the_gateway_check(
    controller_repo: dict[str, Any],
) -> None:
    cfg, host = controller_repo["cfg"], controller_repo["host"]
    card = "# Task Card: t\n\ntask_id: `t`\n"
    bound = _bind(controller_repo["live_controller"], "tasks/c/00-t.md", card)
    new_controller = ad.materialize_controller(cfg, host, controller_repo["new"])
    carry = ad.carry_bound_cards(
        host, controller_repo["plist"], new_controller, controller_repo["new"]
    )
    assert carry["status"] == "CARRIED"
    assert carry["from_head"] == bound
    assert carry["carried"] == ["tasks/c/00-t.md"]
    assert (new_controller / "tasks/c/00-t.md").read_bytes() == card.encode()
    assert _rg(new_controller, "rev-parse", "HEAD^") == controller_repo["new"]
    assert _rg(new_controller, "status", "--porcelain") == ""
    # The real Gateway rule (this checkout's code) accepts the carried Controller
    # for a deployment of NEW.
    deployment_new = cfg.deployments / f"a1-{controller_repo['new']}"
    host.run(
        ad._git(cfg, "worktree", "add", "--detach", str(deployment_new), controller_repo["new"])
    )
    assert (
        host.controller_problem(
            Path(sys.executable), deployment_new, new_controller, code_root=REPO_ROOT
        )
        is None
    )


def test_carry_skips_paths_main_changed_and_refuses_non_bind_controllers(
    controller_repo: dict[str, Any],
) -> None:
    cfg, host = controller_repo["cfg"], controller_repo["host"]
    live = controller_repo["live_controller"]
    _bind(live, "tasks/keep.md", "rebound\n")
    new_controller = ad.materialize_controller(cfg, host, controller_repo["new"])
    carry = ad.carry_bound_cards(
        host, controller_repo["plist"], new_controller, controller_repo["new"]
    )
    assert carry["status"] == "CARRIED"  # main did not touch tasks/keep.md since OLD
    # A code commit in the live Controller is not a bind: nothing is carried.
    (live / "nexus.py").write_text("evil = 1\n")
    _rg(live, "add", "nexus.py")
    _rg(live, "commit", "-qm", "not a bind")
    fresh = ad.materialize_controller(cfg, host, controller_repo["new"])
    refused = ad.carry_bound_cards(host, controller_repo["plist"], fresh, controller_repo["new"])
    assert refused["status"] == "SKIPPED"
    assert refused["reason"] == "LIVE_CONTROLLER_NOT_BIND_ONLY"
    assert _rg(fresh, "rev-parse", "HEAD") == controller_repo["new"]


def test_carry_skips_a_card_main_also_changed(controller_repo: dict[str, Any]) -> None:
    cfg, host = controller_repo["cfg"], controller_repo["host"]
    _bind(controller_repo["live_controller"], "tasks/keep.md", "rebound\n")
    seedless = cfg.deployments / "edit"
    host.run(ad._git(cfg, "worktree", "add", "--detach", str(seedless), controller_repo["new"]))
    (seedless / "tasks/keep.md").write_text("main changed it\n")
    _rg(seedless, "add", "tasks/keep.md")
    _rg(seedless, "commit", "-qm", "main edit")
    newer = _rg(seedless, "rev-parse", "HEAD")
    controller = ad.materialize_controller(cfg, host, newer)
    carry = ad.carry_bound_cards(host, controller_repo["plist"], controller, newer)
    assert carry["status"] == "NONE"
    assert carry["skipped_main_changed"] == ["tasks/keep.md"]
    assert (controller / "tasks/keep.md").read_text() == "main changed it\n"


def test_live_controller_moved_after_the_carry_is_detected(controller_repo: dict[str, Any]) -> None:
    cfg, host = controller_repo["cfg"], controller_repo["host"]
    live = controller_repo["live_controller"]
    _bind(live, "tasks/c/00-a.md", "a\n")
    controller = ad.materialize_controller(cfg, host, controller_repo["new"])
    carry = ad.carry_bound_cards(host, controller_repo["plist"], controller, controller_repo["new"])
    receipt = {"controller": {"root": str(controller), "carry": carry}}
    ctx = ad._Cycle(cfg, host, FakeProber(), green_api(), {}, Path("/tool/python"))
    assert ctx.live_controller_moved(controller_repo["plist"], receipt) is None
    _bind(live, "tasks/c/00-b.md", "b\n")
    assert ctx.live_controller_moved(controller_repo["plist"], receipt).startswith(
        "LIVE_CONTROLLER_MOVED:"
    )


def test_rollback_needs_the_predecessor_controller(controller_repo: dict[str, Any]) -> None:
    plist = controller_repo["plist"]
    (controller_repo["deployment"] / "scripts/ops").mkdir(parents=True, exist_ok=True)
    (controller_repo["deployment"] / ad.ENTRYPOINT).write_text("")
    host = controller_repo["host"]
    assert ad.rollback_readiness(host, plist)["ok"] is True
    shutil.rmtree(controller_repo["live_controller"])
    assert ad.rollback_readiness(host, plist)["reason"] == "PREDECESSOR_CONTROLLER_MISSING"


def test_switch_exports_the_new_controller_and_receipts_it(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    result = cycle(cfg, host, prober)
    assert result["status"] == "DEPLOYED"
    controller = cfg.controllers / f"a1-{NEW}"
    tokens = ad._wrapper_tokens(cfg.plist.read_bytes())
    assert f"NEXUS_CANONICAL_SOURCE_ROOT={controller}" in tokens
    assert ad.live_root(cfg.plist.read_bytes()) == cfg.deployments / f"a1-{NEW}"
    assert ad.live_controller(cfg.plist.read_bytes()) == controller
    receipt = ad.read_receipts(cfg.state_dir)[-1]
    assert receipt["controller"]["root"] == str(controller)
    assert any(f'NEXUS_CANONICAL_SOURCE_ROOT="{controller}"' in c for c in host.started)


def test_candidate_refusing_the_carry_falls_back_to_a_fresh_controller(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    host, prober = FakeHost(), FakeProber()
    monkeypatch.setattr(
        ad,
        "carry_bound_cards",
        lambda *args, **kwargs: {
            "status": "CARRIED",
            "from_head": "c" * 40,
            "carried": ["tasks/x.md"],
        },
    )
    host.controller_verdicts = ["CONTROLLER_CHANGES_OUTSIDE_TASKS", None]
    result = cycle(cfg, host, prober)
    assert result["status"] == "DEPLOYED"
    receipt = ad.read_receipts(cfg.state_dir)[-1]
    assert receipt["controller"]["carry"]["status"] == "DROPPED"
    assert "CONTROLLER_CHANGES_OUTSIDE_TASKS" in receipt["controller"]["carry"]["reason"]
    assert any(w.startswith("BOUND_CARDS_NOT_CARRIED:") for w in receipt["warnings"])


def test_candidate_refusing_a_fresh_controller_fails_the_build(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    host.controller_verdicts = ["CONTROLLER_NOT_A_REGISTERED_WORKTREE"]
    result = cycle(cfg, host, prober)
    assert result["status"] == "BUILD_FAILED"
    assert host.reloads == []
    assert "CONTROLLER_INVALID" in ad.read_receipts(cfg.state_dir)[-1]["reason"]


def test_prune_removes_orphan_controllers_but_never_protected_ones(cfg: ad.Config) -> None:
    host = FakeHost()
    for name in ("a1-" + "1" * 40, "a1-" + "2" * 40):
        (cfg.controllers / name).mkdir(parents=True)
    keep = cfg.deployments / ("a1-" + "2" * 40)
    keep.mkdir(parents=True)
    ad.prune(cfg, host, [keep])
    assert not (cfg.controllers / ("a1-" + "1" * 40)).exists()
    assert (cfg.controllers / ("a1-" + "2" * 40)).exists()


def test_first_run_carries_binds_from_the_live_deployment(controller_repo: dict[str, Any]) -> None:
    """The live Gateway still binds into its deployment until the first split deploy."""
    cfg, host = controller_repo["cfg"], controller_repo["host"]
    deployment = controller_repo["deployment"]
    _bind(deployment, "tasks/c/00-first.md", "first\n")
    plist = plistlib.dumps({
        "Label": ad.GATEWAY_LABEL,
        "ProgramArguments": [
            "/bin/zsh",
            "-c",
            f'cd "{deployment}" ; export NEXUS_CANONICAL_SOURCE_ROOT="{deployment}" ; '
            f'exec /usr/bin/python3 "{deployment}/x.py"',
        ],
        "WorkingDirectory": str(deployment),
    })
    controller = ad.materialize_controller(cfg, host, controller_repo["new"])
    carry = ad.carry_bound_cards(host, plist, controller, controller_repo["new"])
    assert carry["status"] == "CARRIED"
    assert carry["from"] == str(deployment)
    assert (controller / "tasks/c/00-first.md").read_text() == "first\n"


def test_non_utf8_bound_path_is_skipped_not_raised(controller_repo: dict[str, Any]) -> None:
    cfg, host = controller_repo["cfg"], controller_repo["host"]
    live = controller_repo["live_controller"]
    name = b"tasks/c/\xff.md"
    target = os.fsencode(str(live)) + b"/" + name
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(b"x\n")
    except OSError:
        pytest.skip("filesystem refuses non-UTF-8 names")
    subprocess.run(["git", "-C", str(live), "add", "-A"], check=True, env={**os.environ, **GIT_ENV})
    _rg(live, "commit", "-qm", "odd name")
    controller = ad.materialize_controller(cfg, host, controller_repo["new"])
    carry = ad.carry_bound_cards(host, controller_repo["plist"], controller, controller_repo["new"])
    assert carry["status"] == "SKIPPED"
    assert carry["lost"] is True
    assert _rg(controller, "rev-parse", "HEAD") == controller_repo["new"]


def test_carry_uses_literal_pathspecs(controller_repo: dict[str, Any]) -> None:
    """A bound file literally named ``tasks/k*`` must not drag ``tasks/keep.md`` along."""
    cfg, host = controller_repo["cfg"], controller_repo["host"]
    live = controller_repo["live_controller"]
    (live / "tasks/keep.md").write_text("live edit, not a bind of this file\n")
    _bind(live, "tasks/k*", "glob\n")
    controller = ad.materialize_controller(cfg, host, controller_repo["new"])
    carry = ad.carry_bound_cards(host, controller_repo["plist"], controller, controller_repo["new"])
    assert carry["carried"] == ["tasks/k*"]
    assert (controller / "tasks/keep.md").read_text() == "tracked\n"


def test_rollback_refuses_a_predecessor_controller_its_gateway_would_refuse(
    controller_repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    (controller_repo["deployment"] / "scripts/ops").mkdir(parents=True, exist_ok=True)
    (controller_repo["deployment"] / ad.ENTRYPOINT).write_text("")
    host = controller_repo["host"]
    monkeypatch.setattr(host, "controller_problem", lambda *a, **k: "CONTROLLER_WORKTREE_DIRTY")
    verdict = ad.rollback_readiness(host, controller_repo["plist"])
    assert verdict == {
        "ok": False,
        "reason": "PREDECESSOR_CONTROLLER_INVALID:CONTROLLER_WORKTREE_DIRTY",
    }


def test_materialize_refuses_a_symlinked_controllers_dir(cfg: ad.Config, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    (outside / ("a1-" + NEW)).mkdir(parents=True)
    cfg.gateway_root.mkdir(parents=True, exist_ok=True)
    cfg.controllers.symlink_to(outside)
    with pytest.raises(ad.DeployError, match="CONTROLLER_ROOT_UNSAFE"):
        ad.materialize_controller(cfg, FakeHost(), NEW)
    assert (outside / ("a1-" + NEW)).exists()


def test_gateway_runs_with_the_controller_as_cwd(cfg: ad.Config) -> None:
    """cwd keeps its pre-split meaning (the canonical root) for cwd-based fallbacks."""
    controller = cfg.controllers / ("a1-" + NEW)
    command = ad.wrapper_command(
        cfg, cfg.deployments / ("a1-" + NEW), Path("/py"), controller_root=controller
    )
    assert command.startswith(f'cd "{controller}" ;')
    assert f'exec "/py" "{cfg.deployments / ("a1-" + NEW) / ad.ENTRYPOINT}"' in command


def test_late_bind_after_the_check_is_reported(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    host, prober = FakeHost(), FakeProber()
    verdicts = iter([None, "LIVE_CONTROLLER_MOVED:aaaaaaaaaaaa->bbbbbbbbbbbb"])
    monkeypatch.setattr(
        ad._Cycle, "live_controller_moved", lambda self, plist, receipt: next(verdicts)
    )
    monkeypatch.setattr(
        ad,
        "carry_bound_cards",
        lambda *args, **kwargs: {
            "status": "NONE",
            "from": str(cfg.controllers / ("a1-" + OLD)),
            "from_head": OLD,
        },
    )
    assert cycle(cfg, host, prober)["status"] == "DEPLOYED"
    warnings = ad.read_receipts(cfg.state_dir)[-1]["warnings"]
    assert any(w.startswith("LATE_BIND_NOT_CARRIED:LIVE_CONTROLLER_MOVED") for w in warnings)
    # The old Controller holds the only copy of that bind: it is never pruned.
    retained = json.loads(cfg.retained_controllers.read_text())
    assert ("a1-" + OLD) in retained
    old_controller = cfg.controllers / ("a1-" + OLD)
    old_controller.mkdir(parents=True)
    ad.prune(cfg, host, [])
    assert old_controller.exists()


def test_controller_moved_defers_without_debounce(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    host, prober = FakeHost(), FakeProber()
    monkeypatch.setattr(
        ad._Cycle,
        "live_controller_moved",
        lambda self, plist, receipt: "LIVE_CONTROLLER_MOVED:x->y",
    )
    assert cycle(cfg, host, prober)["status"] == ad.CONTROLLER_MOVED_OUTCOME
    assert host.reloads == []
    monkeypatch.setattr(ad._Cycle, "live_controller_moved", lambda self, plist, receipt: None)
    host.clock += 60  # inside min_interval_seconds
    assert cycle(cfg, host, prober)["status"] == "DEPLOYED"


def test_carry_reset_failure_still_never_raises(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Exploding(FakeHost):
        def run(self, argv, **kwargs):  # type: ignore[override]
            raise OSError("disk gone")

    def boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("carry broke")

    monkeypatch.setattr(ad, "_carry_bound_cards", boom)
    result = ad.carry_bound_cards(Exploding(), b"", cfg.controllers / "a1-x", NEW)
    assert result == {"status": "SKIPPED", "reason": "CARRY_ERROR:RuntimeError", "lost": True}


def test_unreadable_retention_list_stops_pruning(cfg: ad.Config) -> None:
    host = FakeHost()
    orphan = cfg.controllers / ("a1-" + "1" * 40)
    orphan.mkdir(parents=True)
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.retained_controllers.write_text("{broken")
    assert ad.prune(cfg, host, []) == []
    assert orphan.exists()


def test_retain_failure_is_a_warning_not_a_rollback(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    host, prober = FakeHost(), FakeProber()
    verdicts = iter([None, "LIVE_CONTROLLER_MOVED:aaaaaaaaaaaa->bbbbbbbbbbbb"])
    monkeypatch.setattr(
        ad._Cycle, "live_controller_moved", lambda self, plist, receipt: next(verdicts)
    )

    def broken(self: Any, receipt: Any, reason: str) -> None:
        raise OSError("full")

    monkeypatch.setattr(ad._Cycle, "retain_controller", broken)
    assert cycle(cfg, host, prober)["status"] == "DEPLOYED"
    assert host.reloads and len(host.reloads) == 1
    warnings = ad.read_receipts(cfg.state_dir)[-1]["warnings"]
    assert any(w.startswith("RETAIN_CONTROLLER_FAILED:OSError") for w in warnings)
    # The old Controller cannot be pruned by a later cycle: everything is held.
    assert "RETAIN_CONTROLLER_FAILED" in cfg.hold_file.read_text()
    assert cycle(cfg, host, prober)["status"] == "HELD"


# ------------------------------------------------- degraded live Controller (#2230 F2)


def _degraded_health() -> dict[str, Any]:
    return {
        "status": "degraded",
        "git_head": OLD,
        "controller_binding": {
            "status": "DEGRADED",
            "reason": "NEXUS_CANONICAL_SOURCE_ROOT_MISSING",
        },
    }


def test_in_sync_degraded_controller_warns_once_and_never_holds(cfg: ad.Config) -> None:
    host, prober = FakeHost(candidate=OLD), FakeProber()
    prober.health = _degraded_health()
    result = cycle(cfg, host, prober)
    assert result["status"] == ad.LIVE_DEGRADED_OUTCOME
    assert result["status"] not in ad.FAILED_OUTCOMES  # CLI exit 0
    assert prober.health_reads == 1
    # No HOLD, and nothing restarted, switched or built.
    assert ad.hold_reason(cfg, {}) is None and not cfg.hold_file.exists()
    assert host.reloads == [] and host.started == [] and prober.calls == []
    assert not any(argv[:1] == ["uv"] for argv in host.calls)
    receipt = ad.last_receipt(cfg.state_dir)
    assert receipt == result["receipt"]
    assert receipt["outcome"] == ad.LIVE_DEGRADED_OUTCOME
    assert receipt["candidate_commit"] == OLD and receipt["switched"] is False
    assert receipt["controller_binding"]["status"] == "DEGRADED"
    assert receipt["outcome"] not in ad.FAILED_OUTCOMES  # no backoff / give-up effect
    assert receipt["previous_root"] == str(cfg.deployments / f"r1-{OLD}")
    assert len(host.issue_comments) == 1
    assert host.comment_issues == [ad.CONTROLLER_ALERT_ISSUE] and ad.CONTROLLER_ALERT_ISSUE == 2230
    assert "NEXUS_GATEWAY_LIVE_DEGRADED_CONTROLLER" in host.issue_comments[0]
    status = json.loads((cfg.state_dir / "status.json").read_text())
    assert status["status"] == ad.LIVE_DEGRADED_OUTCOME
    # Still degraded on later cycles: no second comment, no receipt per cycle.
    host.clock += 600
    again = cycle(cfg, host, prober)
    assert again["status"] == ad.LIVE_DEGRADED_OUTCOME
    assert again["warning"]["posted"] is False
    assert len(host.issue_comments) == 1
    assert len(ad.read_receipts(cfg.state_dir)) == 1
    assert not cfg.hold_file.exists()
    # A day later the warning re-arms.
    host.clock += ad.QUIESCENCE_REWARN_SECONDS
    cycle(cfg, host, prober)
    assert len(host.issue_comments) == 2
    assert len(ad.read_receipts(cfg.state_dir)) == 2


def test_in_sync_degraded_failed_comment_is_retried_next_cycle(cfg: ad.Config) -> None:
    host, prober = FakeHost(candidate=OLD), FakeProber()
    prober.health = _degraded_health()
    host.comment_fails = True
    assert cycle(cfg, host, prober)["receipt"]["warning"]["posted"] is False
    assert not cfg.controller_alert_file.exists()
    host.comment_fails = False
    host.clock += 600
    cycle(cfg, host, prober)
    assert len(host.issue_comments) == 1


def test_degraded_live_then_new_main_commit_deploys_normally(cfg: ad.Config) -> None:
    """No HOLD: the next main commit is deployed, which re-materializes the Controller."""
    host, prober = FakeHost(candidate=OLD), FakeProber()
    prober.health = _degraded_health()
    assert cycle(cfg, host, prober)["status"] == ad.LIVE_DEGRADED_OUTCOME
    host.candidate = NEW
    host.clock += 600
    result = cycle(cfg, host, prober)
    assert result["status"] == "DEPLOYED"
    assert len(host.reloads) == 1
    assert ad.last_receipt(cfg.state_dir)["outcome"] == "DEPLOYED"
    assert not cfg.hold_file.exists()


def test_in_sync_degraded_dry_run_reports_without_effects(cfg: ad.Config) -> None:
    host, prober = FakeHost(candidate=OLD), FakeProber()
    prober.health = _degraded_health()
    result = cycle(cfg, host, prober, dry_run=True)
    assert result["status"] == "IN_SYNC"
    assert result["live_controller_binding"]["status"] == "DEGRADED"
    assert not cfg.hold_file.exists() and host.issue_comments == []
    assert ad.read_receipts(cfg.state_dir) == []


@pytest.mark.parametrize(
    "binding",
    [
        None,
        {"status": "SEPARATE", "reason": None},
        {"status": "NOT_SEPARATE", "reason": None},
    ],
    ids=["field-absent", "separate", "not-separate"],
)
def test_in_sync_without_degraded_controller_is_unchanged(cfg: ad.Config, binding: Any) -> None:
    host, prober = FakeHost(candidate=OLD), FakeProber()
    if binding is not None:
        prober.health = {"status": "ok", "git_head": OLD, "controller_binding": binding}
    result = cycle(cfg, host, prober)
    assert result["status"] == "IN_SYNC"
    assert prober.health_reads == 1
    assert "warnings" not in result and "live_controller_binding" not in result
    assert not cfg.hold_file.exists()
    assert host.issue_comments == [] and ad.read_receipts(cfg.state_dir) == []


@pytest.mark.parametrize(
    "health",
    [TimeoutError("timed out"), ConnectionRefusedError(61, "refused"), "not-json-object"],
    ids=["timeout", "refused", "garbage"],
)
def test_in_sync_unreachable_live_health_never_holds(cfg: ad.Config, health: Any) -> None:
    host, prober = FakeHost(candidate=OLD), FakeProber()
    prober.health = health
    result = cycle(cfg, host, prober)
    assert result["status"] == "IN_SYNC"
    assert not cfg.hold_file.exists()
    assert host.issue_comments == [] and ad.read_receipts(cfg.state_dir) == []
    if isinstance(health, BaseException):
        assert result["warnings"] == [f"LIVE_HEALTH_UNREADABLE:{type(health).__name__}"]


def test_live_health_reads_the_live_port_with_the_probe_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def fake_http(self: ad.Prober, url: str, **_kw: Any) -> Any:
        seen.append(url)
        return {"status": "ok"}

    monkeypatch.setattr(ad.Prober, "_http", fake_http)
    assert ad.Prober(ad.Host()).live_health() == {"status": "ok"}
    assert seen == [f"http://127.0.0.1:{ad.LIVE_PORT}/health"]


def test_degraded_receipt_never_moves_the_debounce_or_backoff(cfg: ad.Config) -> None:
    """A LIVE_DEGRADED_CONTROLLER receipt is not an attempt (review F1)."""
    host, prober = FakeHost(), FakeProber()
    assert cycle(cfg, host, prober)["status"] == "DEPLOYED"
    host.clock += 60
    prober.health = _degraded_health()
    assert cycle(cfg, host, prober)["status"] == ad.LIVE_DEGRADED_OUTCOME
    assert ad.last_receipt(cfg.state_dir)["outcome"] == ad.LIVE_DEGRADED_OUTCOME
    host.clock += 60
    ctx = ad._Cycle(cfg, host, prober, green_api(), {}, Path("/tool/python"))
    failed = [{"outcome": "REJECTED_PROBE"}, {"outcome": "REJECTED_PROBE"}]
    with_degraded = (ctx.backoff_remaining([]), ctx.backoff_remaining(failed))
    assert with_degraded[0] == pytest.approx(cfg.min_interval_seconds - 120)
    lines = cfg.receipts.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if ad.LIVE_DEGRADED_OUTCOME not in line]
    assert len(kept) == len(lines) - 1
    cfg.receipts.write_text("".join(f"{line}\n" for line in kept), encoding="utf-8")
    # Neither shorter nor longer than without the degraded receipt.
    assert with_degraded == (ctx.backoff_remaining([]), ctx.backoff_remaining(failed))


@pytest.mark.parametrize("binding", [None, "DEGRADED", 5, ["DEGRADED"], {"status": ["DEGRADED"]}])
def test_in_sync_odd_controller_binding_shapes_are_not_degraded(
    cfg: ad.Config, binding: Any
) -> None:
    host, prober = FakeHost(candidate=OLD), FakeProber()
    prober.health = {"status": "ok", "git_head": OLD, "controller_binding": binding}
    result = cycle(cfg, host, prober)
    assert result["status"] == "IN_SYNC"
    assert host.issue_comments == [] and ad.read_receipts(cfg.state_dir) == []


@pytest.mark.parametrize(
    "marker",
    [
        "{not json",
        "[]",
        json.dumps({"warned_at": 12345, "reason": "X", "commit": OLD}),
        json.dumps({
            "warned_at": "2099-01-01T00:00:00Z",
            "reason": "NEXUS_CANONICAL_SOURCE_ROOT_MISSING",
            "commit": OLD,
        }),
    ],
    ids=["corrupt", "not-object", "non-string-time", "future"],
)
def test_in_sync_bad_alert_marker_never_mutes_the_alert(cfg: ad.Config, marker: str) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.controller_alert_file.write_text(marker, encoding="utf-8")
    host, prober = FakeHost(candidate=OLD), FakeProber()
    prober.health = _degraded_health()
    cycle(cfg, host, prober)
    assert len(host.issue_comments) == 1
    fresh = json.loads(cfg.controller_alert_file.read_text(encoding="utf-8"))
    assert fresh["warned_at"] == ad._iso(host.clock)
    host.clock += 600
    cycle(cfg, host, prober)
    assert len(host.issue_comments) == 1  # the fresh marker rate-limits again


@pytest.mark.parametrize(
    ("reason", "commit"),
    [
        ("NEXUS_CANONICAL_SOURCE_ROOT_SOURCE_MISMATCH", OLD),
        ("NEXUS_CANONICAL_SOURCE_ROOT_MISSING", NEW),
    ],
    ids=["reason-changed", "commit-changed"],
)
def test_in_sync_degraded_alert_rearms_after_an_hour_on_a_change(
    cfg: ad.Config, reason: str, commit: str
) -> None:
    host, prober = FakeHost(candidate=OLD), FakeProber()
    prober.health = _degraded_health()
    cfg.state_dir.mkdir(parents=True, exist_ok=True)

    def mark(age: float) -> None:
        cfg.controller_alert_file.write_text(
            json.dumps({
                "warned_at": ad._iso(host.clock - age),
                "reason": reason,
                "commit": commit,
            }),
            encoding="utf-8",
        )

    mark(ad.QUIESCENCE_REARM_MIN_SECONDS - 60)
    cycle(cfg, host, prober)
    assert host.issue_comments == []  # changed, but inside the hour
    mark(ad.QUIESCENCE_REARM_MIN_SECONDS + 60)
    cycle(cfg, host, prober)
    assert len(host.issue_comments) == 1


def test_in_sync_clean_reading_survives_an_unremovable_marker(cfg: ad.Config) -> None:
    cfg.controller_alert_file.mkdir(parents=True)  # unlink() raises a non-FileNotFound OSError
    host, prober = FakeHost(candidate=OLD), FakeProber()
    result = cycle(cfg, host, prober)
    assert result["status"] == "IN_SYNC" and "warnings" not in result


def test_in_sync_degraded_survives_unwritable_marker_and_receipt(cfg: ad.Config) -> None:
    cfg.controller_alert_file.mkdir(parents=True)  # os.replace onto a directory fails
    cfg.receipts.mkdir(parents=True)  # appending to a directory fails
    host, prober = FakeHost(candidate=OLD), FakeProber()
    prober.health = _degraded_health()
    result = cycle(cfg, host, prober)
    assert result["status"] == ad.LIVE_DEGRADED_OUTCOME
    assert result["status"] not in ad.FAILED_OUTCOMES
    assert len(host.issue_comments) == 1
    assert result["warnings"] == [
        "CONTROLLER_ALERT_MARKER_UNWRITABLE:IsADirectoryError",
        "LIVE_DEGRADED_RECEIPT_UNWRITABLE:IsADirectoryError",
    ]
    assert not cfg.hold_file.exists()


# ------------------------- #2364: Trusted impact gate replaced Exact-base on main


TRUSTED_IMPACT = "Trusted impact gate (default branch)"
# GET repos/James3014/Nexus-new/rules/branches/main on 2026-10-16, in its order.
LIVE_REQUIRED_2026_10_16 = [
    "Deletion guard",
    TRUSTED_IMPACT,
    "Full published Git history secret audit",
    TRUSTED_DEPENDENCY,
]
# pull_request_target-only workflows: on a real main push they have no run on the
# merge commit and are found only on the merged PR head (seen on main 8a583ad).
PR_TARGET_ONLY = ("Deletion guard", TRUSTED_IMPACT, TRUSTED_DEPENDENCY)


def _live_2026_10_16_api(
    *, impact_path: str | None = None, impact_event: str | None = None
) -> Callable[[str], Any]:
    """Today's ruleset; PR-target checks only on the PR head, as on real main."""
    base = green_api(required=LIVE_REQUIRED_2026_10_16)
    impact_suite = SUITES[TRUSTED_IMPACT] + PR_SUITE_OFFSET

    def api(path: str) -> Any:
        if "check-runs" in path and f"/commits/{NEW}/" in path:
            name = urllib.parse.unquote_plus(path.split("check_name=")[1].split("&")[0])
            if name in PR_TARGET_ONLY:
                return {"check_runs": []}
        payload = base(path)
        if path.endswith(f"check_suite_id={impact_suite}"):
            for run in payload["workflow_runs"]:
                if impact_path is not None:
                    run["path"] = impact_path
                if impact_event is not None:
                    run["event"] = impact_event
        return payload

    return api


def test_trusted_impact_gate_is_known_and_bound_to_its_workflow() -> None:
    workflow = ad.REQUIRED_CHECKS[TRUSTED_IMPACT]
    assert workflow == ".github/workflows/trusted-impact-gate.yml"
    text = (REPO_ROOT / workflow).read_text(encoding="utf-8")
    assert f"name: {TRUSTED_IMPACT}" in text and "pull_request_target" in text


def test_live_ruleset_2026_10_16_all_success_from_bound_workflows_is_green() -> None:
    result = ad.required_checks(_live_2026_10_16_api(), NEW)
    assert result["verdict"] == "GREEN", result
    assert set(result["checks"]) == {*LIVE_REQUIRED_2026_10_16, "Exact-base impact gate"}
    assert result["floor_added"] == ["Exact-base impact gate"]
    for name in PR_TARGET_ONLY:
        assert result["checks"][name]["sha"] == PR_HEAD
    assert result["checks"]["Full published Git history secret audit"]["sha"] == NEW
    assert result["checks"]["Exact-base impact gate"]["sha"] == NEW


def test_live_ruleset_2026_10_16_green_candidate_deploys(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    assert cycle(cfg, host, prober, _live_2026_10_16_api())["status"] == "DEPLOYED"


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/pytest.yml",  # a real workflow, but not the bound one
        ".github/workflows/trusted-dependency-contract.yml",
        ".github/workflows/stray.yml",
    ],
)
def test_trusted_impact_gate_from_another_workflow_is_not_green(path: str) -> None:
    result = ad.required_checks(_live_2026_10_16_api(impact_path=path), NEW)
    assert result["verdict"] == "UNKNOWN"
    assert result["missing"] == [TRUSTED_IMPACT]


@pytest.mark.parametrize("event", ["push", "workflow_dispatch", "schedule", "pull_request"])
def test_trusted_impact_gate_pr_head_run_with_wrong_event_is_not_green(event: str) -> None:
    result = ad.required_checks(_live_2026_10_16_api(impact_event=event), NEW)
    assert result["verdict"] == "UNKNOWN"
    assert result["missing"] == [TRUSTED_IMPACT]


def test_red_trusted_impact_gate_blocks_the_deploy(cfg: ad.Config) -> None:
    base = _live_2026_10_16_api()

    def api(path: str) -> Any:
        payload = base(path)
        if "check-runs" in path and "Trusted+impact" in path:
            for run in payload["check_runs"]:
                run["conclusion"] = "failure"
        return payload

    assert ad.required_checks(api, NEW)["verdict"] == "RED"
    host, prober = FakeHost(), FakeProber()
    assert cycle(cfg, host, prober, api)["status"] == "CHECKS_RED"
    assert prober.calls == [] and host.reloads == []


def test_live_ruleset_plus_an_unbound_name_still_fails_closed() -> None:
    api = green_api(required=[*LIVE_REQUIRED_2026_10_16, "Trusted impact gate (fork)"])
    result = ad.required_checks(api, NEW)
    assert result["verdict"] == "UNKNOWN_REQUIRED_CHECK"
    assert result["unknown_required"] == ["Trusted impact gate (fork)"]


@pytest.mark.parametrize("name", sorted(ad.PR_TARGET_ONLY_CHECKS))
def test_pull_request_event_run_of_a_pr_target_only_check_never_binds(name: str) -> None:
    """``pull_request`` runs PR-controlled workflow code under the same path and name."""
    suite = SUITES[name] + PR_SUITE_OFFSET
    base = _live_2026_10_16_api()

    def api(path: str) -> Any:
        payload = base(path)
        if path.endswith(f"check_suite_id={suite}"):
            for run in payload["workflow_runs"]:
                run["event"] = "pull_request"
        return payload

    result = ad.required_checks(api, NEW)
    assert result["verdict"] == "UNKNOWN"
    assert result["missing"] == [name]


def test_pr_target_only_checks_match_their_workflow_triggers() -> None:
    import yaml

    for name in ad.PR_TARGET_ONLY_CHECKS:
        on = yaml.safe_load((REPO_ROOT / ad.REQUIRED_CHECKS[name]).read_text("utf-8"))[True]
        assert set(on) == {"pull_request_target"}, (name, on)


# ---------------- #2364/#2365: PR-head-only commit statuses in the ruleset

BINDINGS_PREFLIGHT = "Bindings preflight (default branch)"
REVIEW_RECORD = "Review record present (advisory)"
# GET repos/James3014/Nexus-new/rules/branches/main after #2365 (2026-10-16 ~06:25Z).
LIVE_REQUIRED_2026_10_16_SIX = [*LIVE_REQUIRED_2026_10_16, BINDINGS_PREFLIGHT, REVIEW_RECORD]


def _live_six_api() -> Callable[[str], Any]:
    base = _live_2026_10_16_api()

    def api(path: str) -> Any:
        if "/rules/branches/main" in path:
            if "page=" in path and not path.endswith("page=1"):
                return []
            return _branch_rules(LIVE_REQUIRED_2026_10_16_SIX)
        if "check-runs" in path and ("Bindings" in path or "Review+record" in path):
            raise AssertionError("PR-head status contexts are not looked up as check runs")
        return base(path)

    return api


def test_pr_head_status_contexts_are_exactly_the_two_2365_statuses() -> None:
    assert ad.PR_HEAD_STATUS_CONTEXTS == {BINDINGS_PREFLIGHT, REVIEW_RECORD}
    assert not ad.PR_HEAD_STATUS_CONTEXTS & set(ad.REQUIRED_CHECKS)
    assert not ad.PR_HEAD_STATUS_CONTEXTS & set(ad.FLOOR_CHECKS)


def test_pr_head_status_contexts_are_published_by_pull_request_target_workflows() -> None:
    import yaml

    for context, workflow, owner in (
        (BINDINGS_PREFLIGHT, "pr-bindings-preflight.yml", None),
        (REVIEW_RECORD, "review-record-present.yml", "scripts/ops/review_record_check.py"),
    ):
        text = (REPO_ROOT / ".github/workflows" / workflow).read_text("utf-8")
        assert "pull_request_target" in yaml.safe_load(text)[True]
        assert "push" not in yaml.safe_load(text)[True]
        source = text if owner is None else (REPO_ROOT / owner).read_text("utf-8")
        assert context in source


def test_live_ruleset_six_checks_all_success_is_green() -> None:
    result = ad.required_checks(_live_six_api(), NEW)
    assert result["verdict"] == "GREEN", result
    assert result["merge_time_only"] == [BINDINGS_PREFLIGHT, REVIEW_RECORD]
    assert set(result["checks"]) == {*LIVE_REQUIRED_2026_10_16, "Exact-base impact gate"}


def test_live_ruleset_six_checks_green_candidate_deploys(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    assert cycle(cfg, host, prober, _live_six_api())["status"] == "DEPLOYED"


def test_live_ruleset_six_checks_still_blocks_on_a_red_bound_check() -> None:
    base = _live_six_api()

    def api(path: str) -> Any:
        payload = base(path)
        if "check-runs" in path and "Deletion+guard" in path:
            for run in payload["check_runs"]:
                run["conclusion"] = "failure"
        return payload

    assert ad.required_checks(api, NEW)["verdict"] == "RED"


def test_live_ruleset_six_plus_unknown_seventh_stays_unknown_required_check(
    cfg: ad.Config,
) -> None:
    seven = [*LIVE_REQUIRED_2026_10_16_SIX, "Bindings preflight (fork)"]
    base = _live_six_api()

    def api(path: str) -> Any:
        if "/rules/branches/main" in path:
            return [] if "page=" in path and not path.endswith("page=1") else _branch_rules(seven)
        return base(path)

    result = ad.required_checks(api, NEW)
    assert result["verdict"] == "UNKNOWN_REQUIRED_CHECK"
    assert result["unknown_required"] == ["Bindings preflight (fork)"]
    host, prober = FakeHost(), FakeProber()
    status = cycle(cfg, host, prober, api)["status"]
    assert status == "UNKNOWN_REQUIRED_CHECK:Bindings preflight (fork)"
    assert prober.calls == [] and host.reloads == []


def test_only_pr_head_statuses_required_still_enforces_the_floor() -> None:
    base = _live_six_api()

    def api(path: str) -> Any:
        if "/rules/branches/main" in path:
            if "page=" in path and not path.endswith("page=1"):
                return []
            return _branch_rules([BINDINGS_PREFLIGHT, REVIEW_RECORD])
        if "check-runs" in path and "Exact-base" in path:
            return {"check_runs": []}
        return base(path)

    result = ad.required_checks(api, NEW)
    assert result["verdict"] == "UNKNOWN"
    assert "Exact-base impact gate" in result["missing"]


# ------------------------------------------- #2402 deployer-only self-update

NEW_GATE = "Brand new gate"
SELF_UPDATE_FIXTURES = Path(__file__).parent / "fixtures" / "gateway_auto_deploy_2402"


def _deployer_source(*, checks: tuple[str, ...] = (), contexts: tuple[str, ...] = ()) -> str:
    """A candidate deployer source that knows today's names plus ``checks``/``contexts``."""
    table = {**ad.REQUIRED_CHECKS, **{name: ".github/workflows/new-gate.yml" for name in checks}}
    known = sorted({*ad.PR_HEAD_STATUS_CONTEXTS, *contexts})
    return (
        '"""candidate deployer."""\n'
        f"REQUIRED_CHECKS = {table!r}\n"
        f"PR_HEAD_STATUS_CONTEXTS = frozenset({set(known)!r})\n"
    )


class SelfUpdateHost(FakeHost):
    """FakeHost whose bare repo answers ``git show <sha>:<deployer>`` with ``source``."""

    def __init__(self, source: str | None, **kw: Any) -> None:
        super().__init__(**kw)
        self.source = source
        self.shows: list[str] = []

    def run(self, argv, *, cwd=None, env=None, timeout=1800):  # type: ignore[override]
        if argv[:1] == ["git"] and "show" in argv:
            self.calls.append(list(argv))
            self.shows.append(argv[-1])
            if self.source is None:
                return _done(code=128, stderr="fatal: path does not exist")
            return _done(self.source)
        return super().run(argv, cwd=cwd, env=env, timeout=timeout)


def _no_gateway_effect(cfg: ad.Config, host: FakeHost, prober: FakeProber, plist: bytes) -> None:
    assert cfg.plist.read_bytes() == plist
    assert host.reloads == [] and host.started == [] and prober.calls == []
    assert not any(c[:1] == ["uv"] for c in host.calls)
    assert not cfg.journal.exists() and not cfg.hold_file.exists()


def _tool_runs(host: FakeHost) -> list[list[str]]:
    return [c for c in host.calls if len(c) > 2 and c[1].endswith(ad.DEPLOYER)]


@pytest.mark.parametrize(
    "source",
    [_deployer_source(checks=(NEW_GATE,)), _deployer_source(contexts=(NEW_GATE,))],
    ids=["bound-check", "pr-head-status"],
)
def test_self_update_moves_only_the_deployer_link(cfg: ad.Config, source: str) -> None:
    """(a) unknown name + candidate knows it + bindable subset green."""
    api = green_api(required=[*ad.REQUIRED_CHECKS, NEW_GATE])
    host, prober = SelfUpdateHost(source), FakeProber()
    plist = cfg.plist.read_bytes()
    result = cycle(cfg, host, prober, api, tool_python=Path("/agent/python3.12"))
    assert result["status"] == ad.SELF_UPDATED_OUTCOME
    assert host.shows == [f"{NEW}:{ad.DEPLOYER}"]
    root = cfg.deployments / f"a1-{NEW}"
    assert Path(os.readlink(cfg.tool_link)) == root
    _no_gateway_effect(cfg, host, prober, plist)
    assert [c[2] for c in _tool_runs(host)] == ["selftest", "status", "run"]
    assert all(c[0] == "/agent/python3.12" for c in _tool_runs(host))
    receipts = ad.read_receipts(cfg.state_dir)
    assert [r["outcome"] for r in receipts] == [ad.SELF_UPDATED_OUTCOME]
    receipt = receipts[0]
    assert receipt["switched"] is False and receipt["rolled_back"] is False
    assert receipt["candidate_commit"] == NEW and receipt["deployer_link"]["moved"] is True
    update = receipt["self_update"]
    assert update["unknown_required"] == [NEW_GATE]
    subset = update["bindable_checks"]
    assert subset["verdict"] == "GREEN"
    assert set(subset["checks"]) == set(ad.REQUIRED_CHECKS)  # every bindable name, not NEW_GATE
    assert result["self_update"]["verdict"] == "UPDATED"


@pytest.mark.parametrize(
    "source, verdict",
    [
        (_deployer_source(), "CANDIDATE_DOES_NOT_KNOW"),
        (None, "CANDIDATE_SOURCE_UNREADABLE"),
        ("REQUIRED_CHECKS = compute()\n", "CANDIDATE_SOURCE_UNPARSEABLE"),
        ("REQUIRED_CHECKS = {\n", "CANDIDATE_SOURCE_UNPARSEABLE"),
    ],
    ids=["does-not-know", "unreadable", "computed-table", "syntax-error"],
)
def test_self_update_fails_closed_when_the_candidate_cannot_bind_the_name(
    cfg: ad.Config, source: str | None, verdict: str
) -> None:
    """(b) the candidate does not know the name either: stays UNKNOWN_REQUIRED_CHECK."""
    api = green_api(required=[*ad.REQUIRED_CHECKS, NEW_GATE])
    host, prober = SelfUpdateHost(source), FakeProber()
    plist = cfg.plist.read_bytes()
    result = cycle(cfg, host, prober, api)
    assert result["status"] == f"UNKNOWN_REQUIRED_CHECK:{NEW_GATE}"
    assert result["self_update"]["verdict"] == verdict
    if verdict == "CANDIDATE_DOES_NOT_KNOW":
        assert result["self_update"]["still_unknown"] == [NEW_GATE]
    assert not cfg.tool_link.exists() and _tool_runs(host) == []
    assert ad.read_receipts(cfg.state_dir) == []
    _no_gateway_effect(cfg, host, prober, plist)


@pytest.mark.parametrize(
    "api_kw, verdict",
    [
        ({"conclusion": "failure"}, "CHECKS_RED"),
        ({"status": "in_progress"}, "CHECKS_PENDING"),
        ({"on_commit": False}, "CHECKS_UNKNOWN"),
    ],
    ids=["red", "pending", "missing"],
)
def test_self_update_needs_every_bindable_check_green(
    cfg: ad.Config, api_kw: dict[str, Any], verdict: str
) -> None:
    """(c) a red, pending or missing bindable check: no link move."""
    base = green_api(required=[*ad.REQUIRED_CHECKS, NEW_GATE], **api_kw)

    def api(path: str) -> Any:
        if api_kw.get("on_commit") is False and "/pulls" in path and "state=open" not in path:
            return []  # no merged PR head to fall back to: Deletion guard has no bound run
        return base(path)

    host, prober = SelfUpdateHost(_deployer_source(checks=(NEW_GATE,))), FakeProber()
    plist = cfg.plist.read_bytes()
    result = cycle(cfg, host, prober, api)
    assert result["status"] == f"UNKNOWN_REQUIRED_CHECK:{NEW_GATE}"
    assert result["self_update"]["verdict"] == verdict
    assert not cfg.tool_link.exists() and _tool_runs(host) == []
    assert ad.read_receipts(cfg.state_dir) == []
    _no_gateway_effect(cfg, host, prober, plist)


def test_self_update_subset_never_drops_a_floor_check(cfg: ad.Config) -> None:
    """Main requiring only the unknown name still binds every FLOOR_CHECKS name."""
    api = green_api(required=[NEW_GATE])
    host = SelfUpdateHost(_deployer_source(checks=(NEW_GATE,)))
    result = cycle(cfg, host, FakeProber(), api)
    assert result["status"] == ad.SELF_UPDATED_OUTCOME
    subset = result["receipt"]["self_update"]["bindable_checks"]
    assert set(subset["checks"]) == set(ad.FLOOR_CHECKS)


def test_bindable_subset_refuses_a_name_this_file_cannot_bind() -> None:
    result = ad.bindable_subset_checks(green_api(), NEW, {NEW_GATE: None})
    assert result["verdict"] == "UNKNOWN"


@pytest.mark.parametrize(
    "tip, relation",
    [(NEW, "x"), ("d" * 40, "behind"), ("d" * 40, "diverged")],
    ids=["tip-unreadable-relation", "behind", "diverged"],
)
def test_self_update_requires_the_candidate_on_main(
    cfg: ad.Config, tip: str, relation: str
) -> None:
    """(d) a candidate not on GitHub main: no source read, no link move."""
    if tip == NEW:

        def api(path: str) -> Any:
            if path.endswith("/branches/main"):
                raise ad.DeployError("GH_API_FAILED:502")
            return green_api(required=[*ad.REQUIRED_CHECKS, NEW_GATE])(path)

    else:
        api = green_api(required=[*ad.REQUIRED_CHECKS, NEW_GATE], main_tip=tip, relation=relation)
    host, prober = SelfUpdateHost(_deployer_source(checks=(NEW_GATE,))), FakeProber()
    plist = cfg.plist.read_bytes()
    assert cycle(cfg, host, prober, api)["status"] == "CANDIDATE_NOT_ON_MAIN"
    assert host.shows == [] and not cfg.tool_link.exists()
    assert ad.read_receipts(cfg.state_dir) == []
    _no_gateway_effect(cfg, host, prober, plist)


def test_next_cycle_with_the_new_deployer_deploys_normally(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(e) self-update, then the new code (which knows the name) does a full-gate DEPLOYED."""
    api = green_api(required=[*ad.REQUIRED_CHECKS, NEW_GATE])
    host, prober = SelfUpdateHost(_deployer_source(contexts=(NEW_GATE,))), FakeProber()
    assert cycle(cfg, host, prober, api)["status"] == ad.SELF_UPDATED_OUTCOME
    # The next cycle runs the candidate deployer: same file, plus the new name.
    monkeypatch.setattr(
        ad, "PR_HEAD_STATUS_CONTEXTS", frozenset({*ad.PR_HEAD_STATUS_CONTEXTS, NEW_GATE})
    )
    host.clock += 300  # one LaunchAgent interval: the self-update is not a debounce attempt
    result = cycle(cfg, host, prober, api)
    assert result["status"] == "DEPLOYED"
    assert result["receipt"]["required_checks"]["verdict"] == "GREEN"
    assert result["receipt"]["required_checks"]["merge_time_only"][-1] == NEW_GATE
    assert host.reloads and prober.calls  # the full probe + switch path ran
    assert Path(os.readlink(cfg.tool_link)) == cfg.deployments / f"a1-{NEW}"
    worktree_adds = [c for c in host.calls if "worktree" in c and "add" in c]
    assert len([c for c in worktree_adds if str(cfg.deployments) in " ".join(c)]) == 1
    outcomes = [r["outcome"] for r in ad.read_receipts(cfg.state_dir)]
    assert outcomes == [ad.SELF_UPDATED_OUTCOME, "DEPLOYED"]


def test_self_update_never_loops_when_the_new_deployer_still_does_not_know(
    cfg: ad.Config,
) -> None:
    api = green_api(required=[*ad.REQUIRED_CHECKS, NEW_GATE])
    host, prober = SelfUpdateHost(_deployer_source(checks=(NEW_GATE,))), FakeProber()
    assert cycle(cfg, host, prober, api)["status"] == ad.SELF_UPDATED_OUTCOME
    host.clock += 300
    again = cycle(cfg, host, prober, api)
    assert again["status"] == f"UNKNOWN_REQUIRED_CHECK:{NEW_GATE}"
    assert again["self_update"]["verdict"] == "ALREADY_CURRENT"
    assert len(ad.read_receipts(cfg.state_dir)) == 1


def test_refused_self_update_keeps_the_link_backs_off_and_gives_up(
    cfg: ad.Config, tmp_path: Path
) -> None:
    old_tool = tmp_path / "old-tool"
    old_tool.mkdir()
    cfg.tool_link.symlink_to(old_tool)
    api = green_api(required=[*ad.REQUIRED_CHECKS, NEW_GATE])
    host, prober = SelfUpdateHost(_deployer_source(checks=(NEW_GATE,))), FakeProber()
    host.tool_fails = True
    plist = cfg.plist.read_bytes()
    first = cycle(cfg, host, prober, api)
    assert first["status"] == ad.SELF_UPDATE_REFUSED_OUTCOME
    assert "selftest failed" in first["receipt"]["deployer_link"]["reason"]
    assert Path(os.readlink(cfg.tool_link)) == old_tool
    assert first["receipt"]["self_update"]["previous_deployer_root"] == os.path.realpath(old_tool)
    host.clock += 300
    assert cycle(cfg, host, prober, api)["self_update"]["verdict"] == "BACKOFF"
    for _ in range(ad.MAX_CANDIDATE_ATTEMPTS - 1):
        host.clock += ad.MAX_BACKOFF_SECONDS
        assert cycle(cfg, host, prober, api)["status"] == ad.SELF_UPDATE_REFUSED_OUTCOME
    host.clock += ad.MAX_BACKOFF_SECONDS
    assert cycle(cfg, host, prober, api)["self_update"]["verdict"] == "GAVE_UP"
    outcomes = [r["outcome"] for r in ad.read_receipts(cfg.state_dir)]
    assert outcomes == [ad.SELF_UPDATE_REFUSED_OUTCOME] * ad.MAX_CANDIDATE_ATTEMPTS
    assert Path(os.readlink(cfg.tool_link)) == old_tool
    _no_gateway_effect(cfg, host, prober, plist)
    # A refused self-update is not a failed deploy attempt of the candidate.
    assert not set(outcomes) & set(ad.FAILED_OUTCOMES)


def test_self_update_dry_run_plans_without_effects(cfg: ad.Config) -> None:
    api = green_api(required=[*ad.REQUIRED_CHECKS, NEW_GATE])
    host, prober = SelfUpdateHost(_deployer_source(checks=(NEW_GATE,))), FakeProber()
    plist = cfg.plist.read_bytes()
    result = cycle(cfg, host, prober, api, dry_run=True)
    assert result["status"] == f"UNKNOWN_REQUIRED_CHECK:{NEW_GATE}"
    assert result["self_update"]["verdict"] == "PLAN"
    assert not cfg.tool_link.exists() and not cfg.deployments.joinpath(f"a1-{NEW}").exists()
    assert ad.read_receipts(cfg.state_dir) == []
    _no_gateway_effect(cfg, host, prober, plist)


def test_self_update_honours_hold_set_after_the_cycle_started(cfg: ad.Config) -> None:
    host, prober = SelfUpdateHost(_deployer_source(checks=(NEW_GATE,))), FakeProber()
    base = green_api(required=[*ad.REQUIRED_CHECKS, NEW_GATE])

    def api(path: str) -> Any:
        if "check-runs" in path:  # only the bindable-subset read gets this far
            ad._set_hold(cfg, "manual hold mid-cycle")
        return base(path)

    result = cycle(cfg, host, prober, api)
    assert result["self_update"]["verdict"] == "HELD"
    assert not cfg.tool_link.exists() and ad.read_receipts(cfg.state_dir) == []


def test_deployer_known_checks_reads_this_file() -> None:
    """Positive control: the live source yields exactly its own tables."""
    source = (REPO_ROOT / ad.DEPLOYER).read_text(encoding="utf-8")
    known = ad.deployer_known_checks(source)
    assert known is not None
    assert set(known) == set(ad.REQUIRED_CHECKS) | set(ad.PR_HEAD_STATUS_CONTEXTS)


@pytest.mark.parametrize(
    "source",
    [
        "PR_HEAD_STATUS_CONTEXTS = frozenset({'x'})\n",  # no REQUIRED_CHECKS at all
        "REQUIRED_CHECKS = {'a': 'w.yml'}\nREQUIRED_CHECKS = {'b': 'w.yml'}\n",
        "REQUIRED_CHECKS = {'a': 1}\n",
        "REQUIRED_CHECKS = ['a']\n",
        "REQUIRED_CHECKS = {'a': 'w.yml'}\nPR_HEAD_STATUS_CONTEXTS = frozenset(names())\n",
        "REQUIRED_CHECKS = {'a': 'w.yml'}\nPR_HEAD_STATUS_CONTEXTS = frozenset({1})\n",
        "REQUIRED_CHECKS = {'a': 'w.yml'}\nPR_HEAD_STATUS_CONTEXTS = set_of('b')\n",
        "REQUIRED_CHECKS = {'a': 'w.yml'}\nPR_HEAD_STATUS_CONTEXTS = 'b'\n",
    ],
    ids=[
        "missing-table",
        "two-tables",
        "non-str-value",
        "not-a-dict",
        "computed-frozenset",
        "non-str-context",
        "other-call",
        "bare-string",
    ],
)
def test_deployer_known_checks_fails_closed(source: str) -> None:
    assert ad.deployer_known_checks(source) is None


def test_deployer_known_checks_accepts_literal_shapes() -> None:
    source = (
        "REQUIRED_CHECKS: dict = {'a': 'w.yml', 'b': ('x' 'y.yml')}\n"
        "PR_HEAD_STATUS_CONTEXTS = frozenset({'c'})\n"
    )
    assert ad.deployer_known_checks(source) == ["a", "b", "c"]
    assert ad.deployer_known_checks("REQUIRED_CHECKS = {'a': 'w.yml'}\n") == ["a"]
    assert ad.deployer_known_checks(
        "REQUIRED_CHECKS = {'a': 'w.yml'}\nPR_HEAD_STATUS_CONTEXTS = frozenset()\n"
    ) == ["a"]


def _module_table(source: str, name: str) -> Any:
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            value = node.value
            if isinstance(value, ast.Call):  # frozenset({...})
                value = value.args[0]
            return ast.literal_eval(value)
    return None


def test_replay_2026_10_16_old_deployer_self_updates_to_the_2370_deployer(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replay of 10-16: the running deployer knows what 8cc1c6621 knew, main
    requires the six #2365 checks, and the candidate's deployer is 044966b2e (#2370)."""
    old = (SELF_UPDATE_FIXTURES / "deployer_8cc1c6621.py.txt").read_text(encoding="utf-8")
    new = (SELF_UPDATE_FIXTURES / "deployer_044966b2e.py.txt").read_text(encoding="utf-8")
    old_checks = _module_table(old, "REQUIRED_CHECKS")
    assert _module_table(old, "PR_HEAD_STATUS_CONTEXTS") is None  # added by #2370
    monkeypatch.setattr(ad, "REQUIRED_CHECKS", old_checks)
    monkeypatch.setattr(
        ad, "PR_TARGET_ONLY_CHECKS", frozenset(_module_table(old, "PR_TARGET_ONLY_CHECKS"))
    )
    monkeypatch.setattr(ad, "PR_HEAD_STATUS_CONTEXTS", frozenset())
    api = _live_six_api()
    # What the deployer at 8cc1c6621 saw on 10-16: stuck on the two #2365 statuses.
    stuck = ad.required_checks(api, NEW)
    assert stuck["verdict"] == "UNKNOWN_REQUIRED_CHECK"
    assert stuck["unknown_required"] == [BINDINGS_PREFLIGHT, REVIEW_RECORD]
    # The old deployer's own source does not know them: no self-update to itself.
    host_old = SelfUpdateHost(old)
    held_back = cycle(cfg, host_old, FakeProber(), api)
    assert held_back["self_update"]["verdict"] == "CANDIDATE_DOES_NOT_KNOW"
    assert not cfg.tool_link.exists()
    # The #2370 candidate does: only the deployer link moves.
    host, prober = SelfUpdateHost(new), FakeProber()
    plist = cfg.plist.read_bytes()
    result = cycle(cfg, host, prober, api)
    assert result["status"] == ad.SELF_UPDATED_OUTCOME
    assert Path(os.readlink(cfg.tool_link)) == cfg.deployments / f"a1-{NEW}"
    _no_gateway_effect(cfg, host, prober, plist)
    subset = result["receipt"]["self_update"]["bindable_checks"]
    assert subset["verdict"] == "GREEN"
    assert set(subset["checks"]) == {*LIVE_REQUIRED_2026_10_16, "Exact-base impact gate"}


# ---------------- 2026-10-17: Exact-base Pyright regression gate became required

PYRIGHT = "Exact-base Pyright regression gate"
# GET repos/James3014/Nexus-new/rulesets/20697077 after the Owner's edit (2026-10-17 08:29+08:00).
LIVE_REQUIRED_2026_10_17_SEVEN = [*LIVE_REQUIRED_2026_10_16_SIX, PYRIGHT]


def _live_seven_api() -> Callable[[str], Any]:
    base = _live_six_api()

    def api(path: str) -> Any:
        if "/rules/branches/main" in path:
            if "page=" in path and not path.endswith("page=1"):
                return []
            return _branch_rules(LIVE_REQUIRED_2026_10_17_SEVEN)
        return base(path)

    return api


def test_pyright_gate_is_known_and_bound_to_its_push_workflow() -> None:
    import yaml

    workflow = ad.REQUIRED_CHECKS[PYRIGHT]
    assert workflow == ".github/workflows/typecheck.yml"
    text = (REPO_ROOT / workflow).read_text(encoding="utf-8")
    assert f"name: {PYRIGHT}" in text
    assert "push" in yaml.safe_load(text)[True]
    assert PYRIGHT not in ad.PR_TARGET_ONLY_CHECKS
    assert PYRIGHT not in ad.PR_HEAD_STATUS_CONTEXTS


def test_live_ruleset_seven_checks_all_success_is_green() -> None:
    result = ad.required_checks(_live_seven_api(), NEW)
    assert result["verdict"] == "GREEN", result
    assert result["checks"][PYRIGHT]["sha"] == NEW


def test_live_ruleset_seven_checks_green_candidate_deploys(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    assert cycle(cfg, host, prober, _live_seven_api())["status"] == "DEPLOYED"


def test_live_ruleset_seven_checks_blocks_on_red_pyright() -> None:
    base = _live_seven_api()

    def api(path: str) -> Any:
        payload = base(path)
        if "check-runs" in path and "Pyright" in path:
            for run in payload["check_runs"]:
                run["conclusion"] = "failure"
        return payload

    assert ad.required_checks(api, NEW)["verdict"] == "RED"


def test_deployer_without_pyright_entry_reports_it_unknown_and_this_source_knows_it() -> None:
    """The live deployer before this change cannot bind the new required name; a
    candidate carrying this source is what the #2402 self-update path needs."""
    source = (REPO_ROOT / ad.DEPLOYER).read_text(encoding="utf-8")
    assert PYRIGHT in (ad.deployer_known_checks(source) or [])
    old = source.replace(
        '    "Exact-base Pyright regression gate": ".github/workflows/typecheck.yml",\n', ""
    )
    assert old != source
    assert PYRIGHT not in (ad.deployer_known_checks(old) or [])


# ------------------------------------------------- parked pin-bump PRs (#2309)

PARK_HEAD = "f" * 40
PARK_PR = 2278


def _park_api(
    pulls: list[dict[str, Any]], mergeable: dict[int, Any] | None = None
) -> Callable[[str], Any]:
    """green_api plus ``GET pulls/<n>`` (mergeable_state); unknown PRs raise like a 404."""
    base = green_api(open_pulls=pulls)

    def get(path: str) -> Any:
        tail = path.split("/pulls/")[1] if "/pulls/" in path else ""
        if tail.isdigit():
            number = int(tail)
            if number not in (mergeable or {}):
                raise ad.DeployError("GH_API_FAILED:404")
            listed = next((p for p in pulls if p["number"] == number), {})
            return {
                "number": number,
                "head": {"sha": (listed.get("head") or {}).get("sha")},
                "mergeable_state": (mergeable or {})[number],
            }
        return base(path)

    return get


def _park_cfg(cfg: ad.Config, seconds: int | None = None) -> ad.Config:
    if seconds is None:
        return cfg
    return dataclasses.replace(cfg, pin_bump_park_seconds=seconds)


def _pins(cfg: ad.Config, api: Callable[[str], Any], now: float, **kw: Any) -> dict[str, Any]:
    return ad.pin_bumps_in_flight(
        api,
        now=now,
        park_file=cfg.pin_park_file,
        park_seconds=cfg.pin_bump_park_seconds,
        **kw,
    )


def test_fresh_mergeable_pin_pr_still_blocks(cfg: ad.Config) -> None:
    """Positive control: a genuinely active pin bump stays IN_FLIGHT and is not parked."""
    api = _park_api([_pin_pr(PARK_PR, draft=False)], {PARK_PR: "clean"})
    for offset in (0, 60, ad.PIN_BUMP_PARK_SECONDS):  # exactly at the threshold still blocks
        pins = _pins(cfg, api, NOW + offset)
        assert pins["verdict"] == "IN_FLIGHT" and pins["pull_requests"] == [PARK_PR]
        assert pins["ignored_parked"] == [] and pins["parked"] == []
    host = FakeHost()
    host.clock = NOW + ad.PIN_BUMP_PARK_SECONDS
    assert cycle(cfg, host, FakeProber(), api)["status"] == "PIN_BUMP_IN_FLIGHT"
    assert host.reloads == [] and host.issue_comments == []


def test_pin_pr_holding_one_head_over_threshold_is_parked_and_deploys(cfg: ad.Config) -> None:
    api = _park_api([_pin_pr(PARK_PR, draft=False)], {PARK_PR: "blocked"})
    host, prober = FakeHost(), FakeProber()
    first = cycle(cfg, host, prober, api)
    assert first["status"] == "PIN_BUMP_IN_FLIGHT"
    host.clock = NOW + ad.PIN_BUMP_PARK_SECONDS + 1
    result = cycle(cfg, host, prober, api)
    assert result["status"] == "DEPLOYED" and len(host.reloads) == 1
    warning = f"PARKED_PIN_PR_IGNORED #{PARK_PR} (holding since {NOW_ISO})"
    assert warning in result["warnings"] and warning in result["receipt"]["warnings"]
    detail = {
        "number": PARK_PR,
        "head_sha": PARK_HEAD,
        "holding_since": NOW_ISO,
        "reason": "held>threshold",
        "threshold_seconds": ad.PIN_BUMP_PARK_SECONDS,
    }
    status = json.loads((cfg.state_dir / "status.json").read_text())
    assert status["pin_bumps"]["ignored_parked"] == [PARK_PR]
    assert status["pin_bumps"]["parked"] == [detail]
    receipt = ad.last_receipt(cfg.state_dir) or {}
    assert receipt["pin_bumps"]["ignored_parked"] == [PARK_PR]
    assert receipt["pin_bumps"]["parked"] == [detail]
    assert receipt["pin_bumps_before_switch"]["ignored_parked"] == [PARK_PR]
    assert host.comment_issues == [PARK_PR]
    assert PARK_HEAD in host.issue_comments[0]
    assert "stopped waiting for this pin-bump PR after 60 min" in host.issue_comments[0]
    assert "Mark it draft while it is parked." in host.issue_comments[0]


def test_parked_comment_is_posted_once_per_head_and_retried_on_failure(cfg: ad.Config) -> None:
    pr = _pin_pr(PARK_PR, draft=False)
    api = _park_api([pr], {PARK_PR: "blocked"})
    host = FakeHost()
    ctx = ad._Cycle(cfg, host, FakeProber(), api, {}, Path("/tool/python"))  # type: ignore[arg-type]
    assert ctx.pin_bumps(record=True)["verdict"] == "IN_FLIGHT"
    host.clock = NOW + ad.PIN_BUMP_PARK_SECONDS + 1
    host.comment_fails = True
    ctx.announce_parked(ctx.pin_bumps(record=True))
    assert host.issue_comments == []
    host.comment_fails = False
    for _ in range(3):
        pins = ctx.pin_bumps(record=True)
        assert pins["ignored_parked"] == [PARK_PR]
        ctx.announce_parked(pins)
    assert host.comment_issues == [PARK_PR]
    # A new head restarts the clock (blocks again) and earns its own comment once parked.
    pr["head"] = {**pr["head"], "sha": "e" * 40}
    pins = ctx.pin_bumps(record=True)
    assert pins["verdict"] == "IN_FLIGHT" and pins["ignored_parked"] == []
    host.clock += ad.PIN_BUMP_PARK_SECONDS + 1
    ctx.announce_parked(ctx.pin_bumps(record=True))
    assert host.comment_issues == [PARK_PR, PARK_PR]
    assert "e" * 40 in host.issue_comments[1]


def test_new_head_push_resets_the_park_clock(cfg: ad.Config) -> None:
    pr = _pin_pr(PARK_PR, draft=False)
    api = _park_api([pr], {PARK_PR: "blocked"})
    assert _pins(cfg, api, NOW)["verdict"] == "IN_FLIGHT"
    pr["head"] = {**pr["head"], "sha": "e" * 40}
    later = NOW + ad.PIN_BUMP_PARK_SECONDS + 1
    pins = _pins(cfg, api, later)
    assert pins["verdict"] == "IN_FLIGHT" and pins["ignored_parked"] == []
    pins = _pins(cfg, api, later + ad.PIN_BUMP_PARK_SECONDS + 1)
    assert pins["verdict"] == "CLEAR" and pins["ignored_parked"] == [PARK_PR]
    assert pins["parked"][0]["head_sha"] == "e" * 40
    assert pins["parked"][0]["holding_since"] == ad._iso(later)


def test_dirty_pin_pr_is_parked_immediately(cfg: ad.Config) -> None:
    api = _park_api([_pin_pr(PARK_PR, draft=False)], {PARK_PR: "dirty"})
    pins = _pins(cfg, api, NOW)
    assert pins["verdict"] == "CLEAR" and pins["ignored_parked"] == [PARK_PR]
    assert pins["parked"][0]["reason"] == "mergeable_state=dirty"
    assert pins["warnings"] == [f"PARKED_PIN_PR_IGNORED #{PARK_PR} (holding since {NOW_ISO})"]
    host = FakeHost()
    result = cycle(cfg, host, FakeProber(), api)
    assert result["status"] == "DEPLOYED"
    assert host.comment_issues == [PARK_PR] and "merge conflict" in host.issue_comments[0]


@pytest.mark.parametrize(
    "mergeable",
    ["clean", "blocked", "unstable", "unknown", None, "missing"],
    ids=["clean", "blocked", "unstable", "unknown", "null", "unreadable"],
)
def test_only_dirty_mergeable_state_parks_at_first_sight(cfg: ad.Config, mergeable: Any) -> None:
    states = {} if mergeable == "missing" else {PARK_PR: mergeable}
    pins = _pins(cfg, _park_api([_pin_pr(PARK_PR, draft=False)], states), NOW)
    assert pins["verdict"] == "IN_FLIGHT" and pins["ignored_parked"] == []


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "[]",
        json.dumps({"schema": "other", "prs": {str(PARK_PR): {"head_sha": PARK_HEAD}}}),
        json.dumps({
            "schema": ad.PIN_PARK_SCHEMA,
            "prs": {str(PARK_PR): {"head_sha": PARK_HEAD, "first_seen_epoch": "old"}},
        }),
        json.dumps({
            "schema": ad.PIN_PARK_SCHEMA,
            "prs": {str(PARK_PR): {"head_sha": PARK_HEAD, "first_seen_epoch": NOW + 99_999}},
        }),
        json.dumps({
            "schema": ad.PIN_PARK_SCHEMA,
            "prs": {str(PARK_PR): {"head_sha": "e" * 40, "first_seen_epoch": 1.0}},
        }),
    ],
    ids=["corrupt", "not-an-object", "wrong-schema", "bad-epoch", "future-epoch", "other-head"],
)
def test_untrustworthy_park_record_blocks(cfg: ad.Config, content: str) -> None:
    """A bad record means "first seen now": it can delay parking, never cause it."""
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.pin_park_file.write_text(content)
    api = _park_api([_pin_pr(PARK_PR, draft=False)], {PARK_PR: "blocked"})
    pins = _pins(cfg, api, NOW + 10 * ad.PIN_BUMP_PARK_SECONDS)
    assert pins["verdict"] == "IN_FLIGHT" and pins["ignored_parked"] == []
    record = json.loads(cfg.pin_park_file.read_text())
    assert record["prs"][str(PARK_PR)] == {
        "head_sha": PARK_HEAD,
        "first_seen_epoch": NOW + 10 * ad.PIN_BUMP_PARK_SECONDS,
    }


def test_trusted_old_park_record_parks(cfg: ad.Config) -> None:
    """Positive control for the record test above."""
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.pin_park_file.write_text(
        json.dumps({
            "schema": ad.PIN_PARK_SCHEMA,
            "prs": {str(PARK_PR): {"head_sha": PARK_HEAD, "first_seen_epoch": NOW}},
        })
    )
    api = _park_api([_pin_pr(PARK_PR, draft=False)], {PARK_PR: "blocked"})
    pins = _pins(cfg, api, NOW + ad.PIN_BUMP_PARK_SECONDS + 1)
    assert pins["verdict"] == "CLEAR" and pins["ignored_parked"] == [PARK_PR]


def test_missing_park_file_or_dry_run_never_parks_by_time(cfg: ad.Config) -> None:
    api = _park_api([_pin_pr(PARK_PR, draft=False)], {PARK_PR: "blocked"})
    for offset in (0, 10 * ad.PIN_BUMP_PARK_SECONDS):
        assert ad.pin_bumps_in_flight(api, now=NOW + offset)["verdict"] == "IN_FLIGHT"
        assert _pins(cfg, api, NOW + offset, record=False)["verdict"] == "IN_FLIGHT"
    assert not cfg.pin_park_file.exists()


def test_draft_and_stale_rules_are_unchanged_by_parking(cfg: ad.Config) -> None:
    draft = _pin_pr(10, draft=True)
    stale = {
        "number": 11,
        "title": "pin nexus-runtime old",
        "head": {"ref": "x", "sha": "9" * 40},
        "created_at": "2025-01-01T00:00:00Z",
    }
    api_base = _park_api([draft, stale], {10: "dirty", 11: "dirty"})

    def api(path: str) -> Any:
        if path.endswith("/commits/" + "9" * 40):
            return {"commit": {"committer": {"date": "2025-01-01T00:00:00Z"}}}
        return api_base(path)

    pins = _pins(cfg, api, NOW + 10 * ad.PIN_BUMP_PARK_SECONDS)
    assert pins["verdict"] == "CLEAR"
    assert pins["ignored_draft"] == [10] and pins["ignored_stale"] == [11]
    assert pins["ignored_parked"] == [] and pins["parked"] == []
    assert pins["warnings"] == ["STALE_PIN_PR_IGNORED #11", "DRAFT_PIN_PR_IGNORED #10"]


def test_park_threshold_is_configurable(cfg: ad.Config, monkeypatch: pytest.MonkeyPatch) -> None:
    assert ad.Config.default(cfg.state_dir).pin_bump_park_seconds == 3600
    monkeypatch.setenv(ad.PIN_BUMP_PARK_ENV, "120")
    assert ad.Config.default(cfg.state_dir).pin_bump_park_seconds == 120
    for bad in ("", "abc", "0", "59", "-5", "1.5"):
        monkeypatch.setenv(ad.PIN_BUMP_PARK_ENV, bad)
        assert ad.Config.default(cfg.state_dir).pin_bump_park_seconds == 3600
    assert ad._park_seconds_arg("600") == 600
    with pytest.raises(argparse.ArgumentTypeError):
        ad._park_seconds_arg("10")
    short = _park_cfg(cfg, 120)
    api = _park_api([_pin_pr(PARK_PR, draft=False)], {PARK_PR: "blocked"})
    assert _pins(short, api, NOW)["verdict"] == "IN_FLIGHT"
    assert _pins(short, api, NOW + 120)["verdict"] == "IN_FLIGHT"
    assert _pins(short, api, NOW + 121)["verdict"] == "CLEAR"


def test_new_head_before_switch_blocks_a_parked_pr(cfg: ad.Config) -> None:
    """The pre-switch re-check applies the same rule: a fresh head blocks again."""
    pr = _pin_pr(PARK_PR, draft=False)
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.pin_park_file.write_text(
        json.dumps({
            "schema": ad.PIN_PARK_SCHEMA,
            "prs": {str(PARK_PR): {"head_sha": PARK_HEAD, "first_seen_epoch": NOW - 7200}},
        })
    )

    def push_during_spare_probe(call: dict[str, Any]) -> None:
        if call["port"] == 50123:
            pr["head"] = {**pr["head"], "sha": "e" * 40}

    host = FakeHost()
    before = cfg.plist.read_bytes()
    api = _park_api([pr], {PARK_PR: "blocked"})
    result = cycle(cfg, host, FakeProber(hook=push_during_spare_probe), api)
    assert result["status"] == "PIN_BUMP_IN_FLIGHT"
    assert cfg.plist.read_bytes() == before and host.reloads == []
    assert result["receipt"]["pin_bumps"]["ignored_parked"] == [PARK_PR]
    assert result["receipt"]["pin_bumps_before_switch"]["pull_requests"] == [PARK_PR]


# ------------------------------------------- live worker-route preflight (#2345)


def _preflight(status: str, *routes: tuple[str, str, str]) -> dict[str, Any]:
    return {
        "status": status,
        "routes": [
            {"route": r, "adapter": a, "preflight": p, "reason": None if p == "OK" else f"{a} off"}
            for r, a, p in routes
        ],
    }


def test_blocked_worker_route_preflight_warns_but_never_changes_the_deploy(
    cfg: ad.Config,
) -> None:
    host, prober = FakeHost(), FakeProber()
    block = _preflight(
        "BLOCKED",
        ("fast_bounded_implementation", "agy_flash_38", "BLOCKED"),
        ("deep_review", "codex", "OK"),
    )
    prober.health = {"status": "ok", "git_head": NEW, "worker_route_preflight": block}
    result = cycle(cfg, host, prober)
    assert result["status"] == "DEPLOYED"
    receipt = result["receipt"]
    assert receipt["switched"] is True and receipt["rolled_back"] is False
    assert len(host.reloads) == 1 and not cfg.hold_file.exists()
    assert Path(os.readlink(cfg.tool_link)) == cfg.deployments / f"a1-{NEW}"
    assert receipt["worker_route_preflight"] == block
    assert [w for w in receipt["warnings"] if w.startswith("WORKER_ROUTE")] == [
        "WORKER_ROUTE_PREFLIGHT_BLOCKED fast_bounded_implementation:agy_flash_38 off"
    ]
    assert (ad.last_receipt(cfg.state_dir) or {})["worker_route_preflight"] == block


@pytest.mark.parametrize(
    "health, expected",
    [
        ({"status": "ok", "git_head": NEW}, {"status": "UNAVAILABLE"}),
        (
            {"status": "ok", "worker_route_preflight": _preflight("OK", ("r", "a", "OK"))},
            _preflight("OK", ("r", "a", "OK")),
        ),
        (
            {"status": "ok", "worker_route_preflight": {"status": "WHATEVER"}},
            {"status": "UNAVAILABLE", "reason": "MALFORMED"},
        ),
        (
            ad.DeployError("connection refused"),
            {"status": "UNAVAILABLE", "reason": "HEALTH_UNREADABLE:DeployError"},
        ),
    ],
    ids=["absent", "ok", "malformed", "unreadable"],
)
def test_worker_route_preflight_without_blocked_route_adds_no_warning(
    cfg: ad.Config, health: Any, expected: dict[str, Any]
) -> None:
    host, prober = FakeHost(), FakeProber()
    prober.health = health
    result = cycle(cfg, host, prober)
    assert result["status"] == "DEPLOYED" and result["receipt"]["rolled_back"] is False
    assert result["receipt"]["worker_route_preflight"] == expected
    assert not [w for w in result["receipt"]["warnings"] if w.startswith("WORKER_ROUTE")]


# ------------------------------------------------ self-update follow-ups (#2409)


class DirtyTreeSelfUpdateHost(SelfUpdateHost):
    """The freshly added candidate tree is dirty (an untracked file appears)."""

    def run(self, argv, *, cwd=None, env=None, timeout=1800):  # type: ignore[override]
        result = super().run(argv, cwd=cwd, env=env, timeout=timeout)
        if "worktree" in argv and "add" in argv:
            (Path(argv[-2]) / ".venv").mkdir()
        return result


def test_self_update_refuses_a_dirty_candidate_tree(cfg: ad.Config, tmp_path: Path) -> None:
    """N1: kills the mutant that drops the SOURCE_TREE_DIRTY refusal in self_update."""
    old_tool = tmp_path / "old-tool"
    old_tool.mkdir()
    cfg.tool_link.symlink_to(old_tool)
    api = green_api(required=[*ad.REQUIRED_CHECKS, NEW_GATE])
    host, prober = DirtyTreeSelfUpdateHost(_deployer_source(checks=(NEW_GATE,))), FakeProber()
    plist = cfg.plist.read_bytes()
    result = cycle(cfg, host, prober, api)
    assert result["status"] == ad.SELF_UPDATE_REFUSED_OUTCOME
    assert result["self_update"]["verdict"] == "REFUSED"
    link = result["receipt"]["deployer_link"]
    assert link["moved"] is False and "SOURCE_TREE_DIRTY" in link["reason"]
    assert Path(os.readlink(cfg.tool_link)) == old_tool
    assert _tool_runs(host) == []  # the candidate deployer never ran
    _no_gateway_effect(cfg, host, prober, plist)


@pytest.mark.parametrize(
    "mutation",
    [
        "del REQUIRED_CHECKS[{name!r}]\n",
        "REQUIRED_CHECKS.pop({name!r})\n",
        "REQUIRED_CHECKS.pop({name!r}, None)\n",
        "if True:\n    del REQUIRED_CHECKS[{name!r}]\n",
        "REQUIRED_CHECKS[{name!r}] = 'other.yml'\n",
        "REQUIRED_CHECKS |= {{}}\n",
        "REQUIRED_CHECKS.update({{}})\n",
        "PR_HEAD_STATUS_CONTEXTS = PR_HEAD_STATUS_CONTEXTS - {{{name!r}}}\n",
        "def _drop():\n    global REQUIRED_CHECKS\n    REQUIRED_CHECKS = {{}}\n",
        "def _drop():\n    REQUIRED_CHECKS.clear()\n",
        "del REQUIRED_CHECKS\n",
    ],
    ids=[
        "del-item",
        "pop",
        "pop-default",
        "nested-del",
        "setitem",
        "augassign",
        "update",
        "rebind",
        "global-rebind",
        "clear-in-function",
        "del-name",
    ],
)
def test_deployer_known_checks_rejects_tables_mutated_after_the_literal(mutation: str) -> None:
    """N2: a name removed (or changed) after the literal must not be counted: fail closed."""
    source = _deployer_source(checks=(NEW_GATE,))
    assert NEW_GATE in (ad.deployer_known_checks(source) or [])  # positive control
    assert ad.deployer_known_checks(source + mutation.format(name=NEW_GATE)) is None


def test_deployer_known_checks_allows_reads_of_the_tables() -> None:
    """Reads (lookups, iteration, membership) are not writes: still parsed."""
    source = _deployer_source(checks=(NEW_GATE,)) + (
        "X = REQUIRED_CHECKS[" + repr(NEW_GATE) + "]\n"
        "Y = [n for n in REQUIRED_CHECKS if n in PR_HEAD_STATUS_CONTEXTS]\n"
        "Z = REQUIRED_CHECKS.get('a')\n"
    )
    assert NEW_GATE in (ad.deployer_known_checks(source) or [])


def test_this_deployer_keeps_check_tables_as_literals_the_reader_parses() -> None:
    """N6: REQUIRED_CHECKS and PR_HEAD_STATUS_CONTEXTS stay plain literals in this file."""
    source = (REPO_ROOT / ad.DEPLOYER).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assigned: dict[str, list[ast.expr]] = {name: [] for name in ad._KNOWN_CHECK_TABLES}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in assigned:
                    assigned[target.id].append(node.value)
    assert len(assigned["REQUIRED_CHECKS"]) == 1
    table = assigned["REQUIRED_CHECKS"][0]
    assert isinstance(table, ast.Dict)
    assert all(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in table.keys)
    assert all(isinstance(v, ast.Constant) and isinstance(v.value, str) for v in table.values)
    assert len(assigned["PR_HEAD_STATUS_CONTEXTS"]) == 1
    contexts = assigned["PR_HEAD_STATUS_CONTEXTS"][0]
    assert isinstance(contexts, ast.Call) and isinstance(contexts.func, ast.Name)
    assert contexts.func.id == "frozenset" and len(contexts.args) == 1
    assert isinstance(contexts.args[0], ast.Set)
    assert all(
        isinstance(e, ast.Constant) and isinstance(e.value, str) for e in contexts.args[0].elts
    )
    assert not ad._check_tables_mutated(tree)
    known = ad.deployer_known_checks(source)
    assert known == list(ad.REQUIRED_CHECKS) + sorted(
        set(ad.PR_HEAD_STATUS_CONTEXTS) - set(ad.REQUIRED_CHECKS)
    )


def test_dirty_detail_for_an_older_head_does_not_park_the_new_head(cfg: ad.Config) -> None:
    """A lagging PR detail (dirty at the old head) must not park the listed new head."""
    pr = _pin_pr(PARK_PR, draft=False)
    pr["head"] = {**pr["head"], "sha": "e" * 40}
    base = green_api(open_pulls=[pr])

    def api(path: str) -> Any:
        if path.endswith(f"/pulls/{PARK_PR}"):
            return {"number": PARK_PR, "head": {"sha": PARK_HEAD}, "mergeable_state": "dirty"}
        return base(path)

    pins = _pins(cfg, api, NOW)
    assert pins["verdict"] == "IN_FLIGHT" and pins["ignored_parked"] == []
    # Positive control: the same dirty detail for the listed head parks it.
    pr["head"] = {**pr["head"], "sha": PARK_HEAD}
    assert _pins(cfg, api, NOW)["ignored_parked"] == [PARK_PR]


@pytest.mark.parametrize(
    "bad",
    ["2h", "\u00b2", "\u0663\u0666\u0660\u0660", "abc", "59", "0"],
    ids=["unit-suffix", "superscript-two", "arabic-indic-3600", "letters", "below-minimum", "zero"],
)
def test_invalid_park_env_falls_back_and_warns(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    monkeypatch.setenv(ad.PIN_BUMP_PARK_ENV, bad)
    loaded = ad.Config.default(cfg.state_dir.parents[2])
    assert loaded.pin_bump_park_seconds == ad.PIN_BUMP_PARK_SECONDS
    assert loaded.pin_bump_park_env_invalid is True
    with pytest.raises(argparse.ArgumentTypeError):
        ad._park_seconds_arg(bad)
    flagged = dataclasses.replace(cfg, pin_bump_park_env_invalid=True)
    api = _park_api([_pin_pr(9, draft=True)])
    result = cycle(flagged, FakeHost(), FakeProber(), api)
    assert result["status"] == "DEPLOYED"
    assert "PIN_PARK_SECONDS_INVALID" in result["warnings"]
    assert "PIN_PARK_SECONDS_INVALID" in result["receipt"]["warnings"]
    status = json.loads((cfg.state_dir / "status.json").read_text())
    assert "PIN_PARK_SECONDS_INVALID" in status["warnings"]


def test_valid_or_unset_park_env_does_not_warn(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Positive control for the invalid-env warning."""
    for value in (None, "", "120"):
        if value is None:
            monkeypatch.delenv(ad.PIN_BUMP_PARK_ENV, raising=False)
        else:
            monkeypatch.setenv(ad.PIN_BUMP_PARK_ENV, value)
        assert ad.Config.default(cfg.state_dir.parents[2]).pin_bump_park_env_invalid is False
    result = cycle(cfg, FakeHost(), FakeProber(), _park_api([_pin_pr(9, draft=True)]))
    assert "PIN_PARK_SECONDS_INVALID" not in result.get("warnings", [])


# --- #1579: the deployer materializes the pinned RIE engine for the Gateway -------------


def _live_command(cfg: ad.Config) -> str:
    return plistlib.loads(cfg.plist.read_bytes())["ProgramArguments"][2]


def test_rie_pin_is_read_from_the_real_applicability_module() -> None:
    from nexus.services import rie_knowledge_applicability as ka

    assert ad.read_rie_pin(REPO_ROOT) == ka.PINNED_RIE_ENGINE_REVISION
    assert ad.RIE_PIN_FILE == "nexus/services/rie_knowledge_applicability.py"
    assert (ad.RIE_ENV_ENGINE_ROOT, ad.RIE_ENV_PYTHON_BIN) == (
        ka.ENV_ENGINE_ROOT,
        ka.ENV_PYTHON_BIN,
    )


def test_rie_pin_absent_or_malformed_is_unreadable(tmp_path: Path) -> None:
    with pytest.raises(ad.DeployError, match="RIE_PIN_UNREADABLE"):
        ad.read_rie_pin(tmp_path)
    (tmp_path / ad.RIE_PIN_FILE).parent.mkdir(parents=True)
    for bad in (
        'PINNED_RIE_ENGINE_REVISION = "main"\n',
        f'PINNED_RIE_ENGINE_REVISION = "{"a" * 40}"\n' * 2,
        f'PINNED_RIE_ENGINE_REVISION = "{"A" * 40}"\n',
        "OTHER = 1\n",
    ):
        (tmp_path / ad.RIE_PIN_FILE).write_text(bad)
        with pytest.raises(ad.DeployError, match="RIE_PIN_UNREADABLE"):
            ad.read_rie_pin(tmp_path)


def test_deploy_exports_verified_rie_engine_after_the_env_file(cfg: ad.Config) -> None:
    cfg.env_file.write_text(
        cfg.env_file.read_text()
        + 'export NEXUS_RIE_ENGINE_ROOT="/elsewhere"\nexport NEXUS_RIE_PYTHON_BIN="/bin/false"\n'
    )
    host, prober = FakeHost(), FakeProber()
    host.rie_pin = RIE.pin
    assert cycle(cfg, host, prober)["status"] == "DEPLOYED"
    rie = ad.last_receipt(cfg.state_dir)["rie"]
    checkout = cfg.rie_checkouts / RIE.pin
    python = cfg.venvs / f"a1-{NEW}" / "bin" / "python"
    assert rie == {
        "status": "VERIFIED",
        "revision": RIE.pin,
        "root": str(checkout),
        "repository": ad.RIE_REPOSITORY_URL,
        "tree": _fixture_git(RIE.path, "rev-parse", f"{RIE.pin}^{{tree}}"),
        "python": str(python),
    }
    exports = (
        f'export NEXUS_RIE_ENGINE_ROOT="{checkout}" ; export NEXUS_RIE_PYTHON_BIN="{python}" ; '
    )
    for command in (host.started[0], _live_command(cfg)):
        assert exports in command
        # Exported after the env file, so the env file cannot redirect the engine.
        assert command.index(exports) > command.index(f'source "{cfg.env_file}"')
        assert command.index(exports) < command.index("exec ")
    assert _fixture_git(checkout, "rev-parse", "HEAD") == RIE.pin
    # The engine check wrote nothing into the pinned checkout.
    assert _fixture_git(checkout, "status", "--porcelain", "--ignored") == ""
    # A second deploy reuses the verified checkout without fetching again.
    assert ad.materialize_rie(cfg, host, RIE.pin)["root"] == str(checkout)


@pytest.mark.parametrize(
    ("setup", "status", "error"),
    [
        (lambda h: setattr(h, "rie_pin", None), "UNAVAILABLE", "RIE_PIN_UNREADABLE"),
        (lambda h: setattr(h, "rie_pin", "f" * 40), "UNAVAILABLE", "RIE_COMMIT_NOT_FOUND"),
        (
            lambda h: (setattr(h, "rie_pin", RIE.pin), setattr(h, "rie_fetch_fails", True)),
            "UNAVAILABLE",
            "RIE_FETCH_FAILED",
        ),
        (lambda h: setattr(h, "rie_pin", RIE.broken), "UNAVAILABLE", "RIE_ENGINE_CHECK_FAILED"),
    ],
    ids=["not-pinned", "unknown-commit", "fetch-fails", "engine-broken"],
)
def test_rie_problems_never_block_the_deploy_and_export_nothing(
    cfg: ad.Config, setup: Any, status: str, error: str | None
) -> None:
    cfg.env_file.write_text(cfg.env_file.read_text() + 'export NEXUS_RIE_ENGINE_ROOT="/stale"\n')
    host, prober = FakeHost(), FakeProber()
    setup(host)
    assert cycle(cfg, host, prober)["status"] == "DEPLOYED"
    rie = ad.last_receipt(cfg.state_dir)["rie"]
    assert rie["status"] == status
    if error is not None:
        assert rie["error"].startswith(error), rie
    unset = "unset NEXUS_RIE_ENGINE_ROOT NEXUS_RIE_PYTHON_BIN ; "
    for command in (host.started[0], _live_command(cfg)):
        assert "export NEXUS_RIE_ENGINE_ROOT" not in command
        # A stale env-file value cannot reach the Gateway either.
        assert unset in command
        assert command.index(unset) > command.index(f'source "{cfg.env_file}"')


def test_rie_bare_repo_origin_must_be_the_engine(cfg: ad.Config) -> None:
    ad.materialize_rie(cfg, FakeHost(), RIE.pin)
    _fixture_git(cfg.rie_bare_repo, "remote", "set-url", "origin", "https://evil.example/r.git")
    with pytest.raises(ad.DeployError, match="RIE_ORIGIN_MISMATCH"):
        ad.materialize_rie(cfg, FakeHost(), RIE.pin)


def test_dirty_rie_checkout_is_rebuilt_when_not_in_use(cfg: ad.Config) -> None:
    checkout = Path(ad.materialize_rie(cfg, FakeHost(), RIE.pin)["root"])
    (checkout / "repository_intelligence" / "cli.py").write_text("raise SystemExit(1)\n")
    result = ad.materialize_rie(cfg, FakeHost(), RIE.pin)
    assert result["rebuilt"].startswith("RIE_TREE_DIRTY")
    assert _fixture_git(checkout, "status", "--porcelain", "--ignored") == ""


def test_dirty_rie_checkout_in_use_by_the_live_gateway_is_not_touched(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    host.rie_pin = RIE.pin
    assert cycle(cfg, host, prober)["status"] == "DEPLOYED"
    checkout = cfg.rie_checkouts / RIE.pin
    planted = checkout / "repository_intelligence" / "planted.py"
    planted.write_text("x = 1\n")
    with pytest.raises(ad.DeployError, match="RIE_IN_USE_UNHEALTHY"):
        ad.materialize_rie(cfg, FakeHost(), RIE.pin)
    assert planted.exists()


def test_rie_paths_through_symlinks_are_refused(cfg: ad.Config, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    cfg.gateway_root.mkdir(parents=True, exist_ok=True)
    cfg.rie_checkouts.symlink_to(elsewhere)
    with pytest.raises(ad.DeployError, match="RIE_PATH_SYMLINKED"):
        ad.materialize_rie(cfg, FakeHost(), RIE.pin)


def test_wrapper_rie_export_rejects_unsafe_paths(cfg: ad.Config) -> None:
    root, python = Path("/d/a1-x"), Path("/v/bin/python")
    command = ad.wrapper_command(cfg, root, python, rie=(Path("/g/rie/abc"), python))
    assert 'export NEXUS_RIE_ENGINE_ROOT="/g/rie/abc" ; ' in command
    assert command.endswith(f'exec "{python}" "{root / ad.ENTRYPOINT}"')
    with pytest.raises(ad.DeployError, match="WRAPPER_PATH_UNSAFE"):
        ad.wrapper_command(cfg, root, python, rie=(Path('/g/rie/"; rm -rf ~'), python))


def test_wrapper_rie_engine_reaches_gateway_process_env(tmp_path: Path) -> None:
    """Run the rendered wrapper for real: the exec'd process sees the deployer's
    engine root even when the env file names another one."""
    cfg = ad.Config.default(tmp_path / "home")
    root = tmp_path / "deploy"
    root.mkdir()
    cfg.env_file.parent.mkdir(parents=True)
    cfg.env_file.write_text('export NEXUS_RIE_ENGINE_ROOT="/stale"\n')
    dump = tmp_path / "env.json"
    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        f"#!{sys.executable}\n"
        "import json, os\n"
        f"open({str(dump)!r}, 'w').write(json.dumps(dict(os.environ)))\n"
    )
    fake_python.chmod(0o755)
    engine = tmp_path / "rie" / ("a" * 40)
    env = {k: v for k, v in os.environ.items() if not k.startswith("NEXUS_")}
    command = ad.wrapper_command(cfg, root, fake_python, rie=(engine, fake_python))
    subprocess.run([_wrapper_shell(), "-c", command], env=env, check=True, timeout=60)
    seen = json.loads(dump.read_text())
    assert seen["NEXUS_RIE_ENGINE_ROOT"] == str(engine)
    assert seen["NEXUS_RIE_PYTHON_BIN"] == str(fake_python)
    subprocess.run(
        [_wrapper_shell(), "-c", ad.wrapper_command(cfg, root, fake_python)],
        env=env,
        check=True,
        timeout=60,
    )
    seen = json.loads(dump.read_text())
    assert "NEXUS_RIE_ENGINE_ROOT" not in seen and "NEXUS_RIE_PYTHON_BIN" not in seen


def test_rie_fetch_outage_reuses_the_verified_same_pin_checkout(
    cfg: ad.Config, tmp_path: Path
) -> None:
    root = tmp_path / "candidate"
    (root / ad.RIE_PIN_FILE).parent.mkdir(parents=True)
    (root / ad.RIE_PIN_FILE).write_text(_rie_pin_source(RIE.pin))
    python = Path(sys.executable)
    first = ad.rie_engine(cfg, FakeHost(), root, python)
    assert first["status"] == "VERIFIED", first
    offline = FakeHost()
    offline.rie_fetch_fails = True
    again = ad.rie_engine(cfg, offline, root, python)
    assert again["status"] == "VERIFIED" and again["root"] == first["root"]
    assert not any("fetch" in c for c in offline.calls)
    # Without a previous checkout the same outage leaves the engine unavailable.
    fresh = ad.Config.default(tmp_path / "other-home")
    missing = ad.rie_engine(fresh, offline, root, python)
    assert missing["status"] == "UNAVAILABLE" and missing["error"].startswith("RIE_FETCH_FAILED")


def test_rie_fetch_timeout_never_fails_the_deploy(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    host.rie_pin = RIE.pin
    original = host.rie_git

    def slow(argv, cwd, timeout):
        if "fetch" in argv:
            raise subprocess.TimeoutExpired(argv, timeout)
        return original(argv, cwd, timeout)

    host.rie_git = slow  # type: ignore[method-assign]
    assert cycle(cfg, host, prober)["status"] == "DEPLOYED"
    rie = ad.last_receipt(cfg.state_dir)["rie"]
    assert rie["status"] == "UNAVAILABLE"
    assert "unset NEXUS_RIE_ENGINE_ROOT NEXUS_RIE_PYTHON_BIN ; " in _live_command(cfg)


def test_prune_keeps_live_and_retained_rie_checkouts_only(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    host.rie_pin = RIE.pin
    assert cycle(cfg, host, prober)["status"] == "DEPLOYED"
    stale = Path(ad.materialize_rie(cfg, FakeHost(), RIE.broken)["root"])
    assert stale.is_dir()
    assert ad.prune_rie(cfg, FakeHost(), []) == [RIE.broken]
    assert not stale.exists()
    assert (cfg.rie_checkouts / RIE.pin).is_dir()
    # The live wrapper's engine survives even with no deployment pinning it.
    for child in cfg.deployments.iterdir():
        if (child / ad.RIE_PIN_FILE).exists():
            (child / ad.RIE_PIN_FILE).unlink()
    assert ad.prune_rie(cfg, FakeHost(), []) == []
    assert (cfg.rie_checkouts / RIE.pin).is_dir()


def test_rie_deployer_change_leaves_required_checks_and_pin_files_alone() -> None:
    assert ad.RIE_PIN_FILE not in getattr(ad, "PIN_FILES", ())
    assert not any("rie" in name.lower() for name in ad.REQUIRED_CHECKS)


def test_rie_assume_unchanged_edit_is_not_verified(cfg: ad.Config, tmp_path: Path) -> None:
    """Codex r1: an edit hidden from `git status` by an index flag never exports."""
    root = tmp_path / "candidate"
    (root / ad.RIE_PIN_FILE).parent.mkdir(parents=True)
    (root / ad.RIE_PIN_FILE).write_text(_rie_pin_source(RIE.pin))
    checkout = Path(ad.materialize_rie(cfg, FakeHost(), RIE.pin)["root"])
    for flag in ("--assume-unchanged", "--skip-worktree"):
        cli = checkout / "repository_intelligence" / "cli.py"
        _fixture_git(checkout, "update-index", flag, "repository_intelligence/cli.py")
        cli.write_text("def main():\n    return 1\n")
        assert _fixture_git(checkout, "status", "--porcelain", "--ignored") == ""
        problem = ad.rie_checkout_problem(FakeHost(), checkout, RIE.pin)
        assert problem is not None and problem.startswith("RIE_INDEX_FLAGGED")
        _fixture_git(
            checkout, "update-index", flag.replace("--", "--no-"), "repository_intelligence/cli.py"
        )
        _fixture_git(checkout, "checkout", "--", "repository_intelligence/cli.py")
    # Not in use by the live wrapper: the next materialization rebuilds it clean.
    _fixture_git(checkout, "update-index", "--assume-unchanged", "repository_intelligence/cli.py")
    rebuilt = ad.rie_engine(cfg, FakeHost(), root, Path(sys.executable))
    assert rebuilt["status"] == "VERIFIED", rebuilt
    assert ad.rie_checkout_problem(FakeHost(), checkout, RIE.pin) is None


def test_rie_fetch_never_waits_on_a_credential_prompt(cfg: ad.Config) -> None:
    host = FakeHost()
    ad.materialize_rie(cfg, host, RIE.pin)
    fetches = [
        e
        for c, e in zip(host.calls, host.envs)
        if "fetch" in c and "gateway-direct/rie" in " ".join(c)
    ]
    assert fetches and all((e or {}).get("GIT_TERMINAL_PROMPT") == "0" for e in fetches)


def test_rie_prune_failure_never_fails_the_cycle(
    cfg: ad.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: Any, **kwargs: Any) -> list[str]:
        raise subprocess.TimeoutExpired(["git", "worktree", "remove"], 60)

    monkeypatch.setattr(ad, "prune_rie", boom)
    host, prober = FakeHost(), FakeProber()
    host.rie_pin = RIE.pin
    assert cycle(cfg, host, prober)["status"] == "DEPLOYED"
    assert cycle(cfg, host, prober)["status"] == "IN_SYNC"


def test_rie_ignored_bytecode_in_the_checkout_is_dirty(cfg: ad.Config) -> None:
    checkout = Path(ad.materialize_rie(cfg, FakeHost(), RIE.pin)["root"])
    cache = checkout / "repository_intelligence" / "__pycache__"
    cache.mkdir()
    (cache / "cli.cpython-314.pyc").write_bytes(b"planted")
    assert _fixture_git(checkout, "status", "--porcelain") == ""  # ignored by .gitignore
    problem = ad.rie_checkout_problem(FakeHost(), checkout, RIE.pin)
    assert problem is not None and problem.startswith("RIE_TREE_DIRTY")


def test_rie_engine_that_writes_into_its_checkout_is_not_verified(
    cfg: ad.Config, tmp_path: Path
) -> None:
    root = tmp_path / "candidate"
    (root / ad.RIE_PIN_FILE).parent.mkdir(parents=True)
    (root / ad.RIE_PIN_FILE).write_text(_rie_pin_source(RIE.writer))
    result = ad.rie_engine(cfg, FakeHost(), root, Path(sys.executable))
    assert result["status"] == "UNAVAILABLE"
    assert result["error"].startswith("RIE_ENGINE_CHECK_WROTE"), result


def test_prune_keeps_a_retained_non_live_deployment_rie_pin(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    host.rie_pin = RIE.pin
    assert cycle(cfg, host, prober)["status"] == "DEPLOYED"
    retained = cfg.deployments / f"a1-{'c' * 40}"
    (retained / ad.RIE_PIN_FILE).parent.mkdir(parents=True)
    (retained / ad.RIE_PIN_FILE).write_text(_rie_pin_source(RIE.broken))
    kept = Path(ad.materialize_rie(cfg, FakeHost(), RIE.broken)["root"])
    assert ad.prune_rie(cfg, FakeHost(), []) == []
    assert kept.is_dir() and (cfg.rie_checkouts / RIE.pin).is_dir()


def test_cycle_retention_prunes_unreferenced_rie_checkouts(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    host.rie_pin = RIE.pin
    assert cycle(cfg, host, prober)["status"] == "DEPLOYED"
    stale = Path(ad.materialize_rie(cfg, FakeHost(), RIE.broken)["root"])
    assert cycle(cfg, host, prober)["status"] == "IN_SYNC"
    assert not stale.exists()
    assert (cfg.rie_checkouts / RIE.pin).is_dir()


def test_state_root_is_fixed_under_gateway_root(tmp_path: Path) -> None:
    """#2688: one absolute NEXUS_STATE_ROOT for every deployment."""
    home = tmp_path / "home"
    c = ad.Config.default(home)
    assert c.state_root == home / "Library/Application Support/Nexus/gateway-direct/state"
    first = ad.wrapper_command(c, c.deployments / f"a1-{OLD}", Path("/p/python"))
    second = ad.wrapper_command(
        c,
        c.deployments / f"a1-{NEW}",
        Path("/q/python"),
        controller_root=c.controllers / f"a1-{NEW}",
    )
    for command in (first, second):
        assert f'export NEXUS_STATE_ROOT="{c.state_root}" ; ' in command
    assert f'NEXUS_CANONICAL_SOURCE_ROOT="{c.controllers / f"a1-{NEW}"}"' in second
    assert second.startswith(f'cd "{c.controllers / f"a1-{NEW}"}" ; ')


def test_state_root_unsafe_path_is_refused(tmp_path: Path) -> None:
    c = ad.Config.default(tmp_path / "home", state_root=tmp_path / "bad$dir")
    with pytest.raises(ad.DeployError, match="WRAPPER_PATH_UNSAFE"):
        ad.wrapper_command(c, c.deployments / f"a1-{OLD}", Path("/p/python"))


def test_ensure_state_root_creates_0700_and_keeps_existing(tmp_path: Path) -> None:
    c = ad.Config.default(tmp_path / "home")
    assert not c.state_root.exists()
    assert ad.ensure_state_root(c) == c.state_root
    assert stat.S_IMODE(c.state_root.stat().st_mode) == 0o700
    marker = c.state_root / ".nexus" / "belief_state.json"
    marker.parent.mkdir()
    marker.write_text("{}")
    os.chmod(c.state_root, 0o750)
    ad.ensure_state_root(c)  # existing memory is kept, mode tightened
    assert marker.read_text() == "{}"
    assert stat.S_IMODE(c.state_root.stat().st_mode) == 0o700


@pytest.mark.parametrize("kind", ["symlink", "file", "relative", "parent_symlink"])
def test_ensure_state_root_refuses_non_directories(tmp_path: Path, kind: str) -> None:
    target = tmp_path / "elsewhere"
    target.mkdir()
    state_root = tmp_path / "home" / "state"
    state_root.parent.mkdir(parents=True)
    if kind == "symlink":
        state_root.symlink_to(target)
    elif kind == "file":
        state_root.write_text("x")
    elif kind == "parent_symlink":
        (tmp_path / "home" / "link").symlink_to(target)
        state_root = tmp_path / "home" / "link" / "state"
    else:
        state_root = Path("relative/state")
    c = ad.Config.default(tmp_path / "home", state_root=state_root)
    with pytest.raises(ad.DeployError, match="STATE_ROOT_"):
        ad.ensure_state_root(c)


def test_bad_state_root_fails_before_live_switch(cfg: ad.Config) -> None:
    bad = ad.Config.default(cfg.state_dir.parents[2], state_root=Path("relative/state"))
    before = bad.plist.read_bytes()
    host = FakeHost()
    result = cycle(bad, host, FakeProber())
    assert result["status"] == "BUILD_FAILED"
    assert "STATE_ROOT_NOT_ABSOLUTE" in result["receipt"]["reason"]
    assert bad.plist.read_bytes() == before and host.reloads == []


def test_ensure_state_root_creates_no_runtime_writer_markers(tmp_path: Path) -> None:
    """#2689: receipts under $NEXUS_STATE_ROOT/.nexus/reports/run are refused when
    the state root carries a writer hold, a state-owner manifest or a writer
    generation; the deployer creates only the empty directory."""
    c = ad.Config.default(tmp_path / "home")
    ad.ensure_state_root(c)
    assert list(c.state_root.iterdir()) == []
    for marker in (
        ".nexus/writer-quiescence-hold.json",
        ".nexus/events/state_owner.manifest.v1.json",
        ".nexus/events/event_log.generation.v1.json",
    ):
        assert not (c.state_root / marker).exists()
        assert not (c.gateway_root / marker).exists()
