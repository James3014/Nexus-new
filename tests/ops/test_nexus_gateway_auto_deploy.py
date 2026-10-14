"""Hermetic tests for the health-gated Gateway auto-deployer (#2153).

Every process, launchd and network effect goes through fakes; nothing here
touches a real Gateway, LaunchAgent or GitHub.
"""

from __future__ import annotations

import contextlib
import hashlib
import http.server
import json
import os
import plistlib
import shutil
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
    _fixture_git(repo, "add", ".")
    _fixture_git(repo, "commit", "-q", "-m", "core two")
    CORE.path, CORE.pin = repo, _fixture_git(repo, "rev-parse", "HEAD")


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
        self.core_fetch_fails = False

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

    def run(self, argv, *, cwd=None, env=None, timeout=1800):  # type: ignore[override]
        self.calls.append(list(argv))
        self.envs.append(env)
        if argv[:1] == ["git"] and any("gateway-direct/core" in str(a) for a in argv):
            return self.core_git(argv, cwd, timeout)
        if argv[:1] == ["uv"]:
            if self.sync_fails:
                return _done(code=1, stderr="network down")
            venv = Path(env["UV_PROJECT_ENVIRONMENT"])
            (venv / "bin").mkdir(parents=True, exist_ok=True)
            (venv / "bin" / "python").write_text("")
            if self.dirty_after_sync:
                (Path(cwd) / ".venv").mkdir()
            return _done()
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


def _health(commit: str, *, status: str = "ok") -> dict[str, Any]:
    return {
        "status": status,
        "server": "nexus-mcp-gateway",
        "reload_required": False,
        "git_head": commit,
        "repo_head_at_start": commit,
        "repo_head_current": commit,
        "repo_root": "/srv/a1",
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
    assert result["status"] == "RECONCILED_JOURNAL_CORRUPT"
    assert "RECONCILE_FAILED:RuntimeError" in result["receipt"]["reason"]
    assert cfg.hold_file.exists() and not cfg.journal.exists()
    assert cycle(cfg, FakeHost(), FakeProber())["status"] == "HELD"


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
    assert receipt["core"] == {
        "revision": CORE.pin,
        "root": str(checkout),
        "repository": ad.CORE_REPOSITORY_URL,
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
        (checkout / "product" / "__pycache__").mkdir()
        (checkout / "product" / "__pycache__" / "two.cpython-312.pyc").write_bytes(b"x")
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
    assert 'export NEXUS_CORE_REPO_ROOT="/g/core/abc" ; exec ' in command
    with pytest.raises(ad.DeployError, match="WRAPPER_PATH_UNSAFE"):
        ad.wrapper_command(cfg, root, python, core_root=Path('/g/core/"; rm -rf ~'))


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
    with fake_gateway(_health(NEW), 3, False) as port:
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


# Opt-in: collected only when NEXUS_CORE_REPO_ROOT names a real nexus-core, so the
# exact-base impact gate never sees a newly added test id that merely skips.
if os.environ.get("NEXUS_CORE_REPO_ROOT"):

    def test_real_transport_reports_pinned_for_a_real_core_checkout(tmp_path: Path) -> None:
        """Positive control with real nexus-core; skipped where none is available offline."""
        pin = ad.read_core_pin(REPO_ROOT)
        checkout = _real_core_checkout(tmp_path, pin)
        if checkout is None:
            pytest.skip("no local nexus-core with the pinned tree (set NEXUS_CORE_REPO_ROOT)")
        check = ad.Prober(ad.Host()).core_provenance(
            root=REPO_ROOT,
            python=Path(sys.executable),
            core={"revision": pin, "root": str(checkout)},
        )
        assert check["status"] == "CORE_REVISION_PINNED", check
        assert check["ok"] is True and check["observed_commit"] == pin


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
        if "check-runs" in path and "Trusted" in path:
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
