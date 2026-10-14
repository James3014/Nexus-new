"""Hermetic tests for the health-gated Gateway auto-deployer (#2153).

Every process, launchd and network effect goes through fakes; nothing here
touches a real Gateway, LaunchAgent or GitHub.
"""

from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from nexus.contracts import gateway_deployment as contract
from scripts.ops import check_gateway_source_drift as drift
from scripts.ops import nexus_gateway_auto_deploy as ad

OLD = "a" * 40
NEW = "b" * 40
PR_HEAD = "c" * 40
REPO_ROOT = Path(__file__).resolve().parents[2]


def _done(stdout: str = "", code: int = 0, stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=code)


class FakeHost(ad.Host):
    def __init__(self, candidate: str = NEW, changed: tuple[str, ...] = ("nexus/x.py",)) -> None:
        self.candidate = candidate
        self.changed = changed
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str] | None] = []
        self.started: list[str] = []
        self.stopped = 0
        self.reloads: list[bytes] = []
        self.clock = 1_760_000_000.0
        self.dirty_after_sync = False
        self.sync_fails = False

    def run(self, argv, *, cwd=None, env=None, timeout=1800):  # type: ignore[override]
        self.calls.append(list(argv))
        self.envs.append(env)
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
        if argv[0] != "git":
            return _done(code=1, stderr=f"unexpected {argv}")
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
            root.mkdir(parents=True)
            (root / "uv.lock").write_text("lock-bytes")
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

    def free_port(self) -> int:
        return 50123

    def now(self) -> float:
        return self.clock

    def sleep(self, seconds: float) -> None:
        self.clock += seconds


class FakeProber:
    def __init__(self, results: dict[tuple[int, str], bool] | None = None) -> None:
        self.results = results or {}
        self.calls: list[dict[str, Any]] = []

    def probe(self, *, port, token, commit, root, python, timeout):
        self.calls.append({"port": port, "commit": commit, "root": root, "python": python})
        ok = self.results.get((port, commit), True)
        return {"ok": ok, "checks": {"gb077": {"ok": ok}}}


def green_api(
    *,
    on_commit: bool = True,
    conclusion: str = "success",
    status: str = "completed",
    open_pulls: list[dict[str, Any]] | None = None,
):
    calls: list[str] = []

    def get(path: str) -> Any:
        calls.append(path)
        if "/pulls?state=open" in path:
            return open_pulls or []
        if path.endswith("/pulls"):
            return [
                {
                    "merged_at": "2026-10-14T00:00:00Z",
                    "merge_commit_sha": NEW,
                    "base": {"ref": "main"},
                    "head": {"sha": PR_HEAD},
                }
            ]
        name = path.split("check_name=")[1].split("&")[0].replace("+", " ")
        sha = path.split("/commits/")[1].split("/")[0]
        if sha == NEW and not on_commit and name == "Deletion guard":
            return {"check_runs": []}
        return {
            "check_runs": [
                {
                    "id": 1,
                    "name": name,
                    "status": status,
                    "conclusion": conclusion,
                    "started_at": "2026-10-14T00:00:00Z",
                }
            ]
        }

    get.calls = calls  # type: ignore[attr-defined]
    return get


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
    c.env_file.parent.mkdir(parents=True, exist_ok=True)
    c.env_file.write_text('export NEXUS_MCP_GATEWAY_TOKEN="tok-123"\nexport PATH=/bin\n')
    return c


def cycle(cfg: ad.Config, host: FakeHost, prober: FakeProber, api=None, **kw: Any) -> dict:
    return ad.run_cycle(cfg, host, prober, api or green_api(), environ={}, **kw)


def test_constants_match_gateway_deployment_contract() -> None:
    assert ad.GATEWAY_LABEL == contract.LABEL
    assert ad.ENTRYPOINT == contract.ENTRYPOINT
    assert contract.ENDPOINT.endswith(f":{ad.LIVE_PORT}")
    assert ad.REPOSITORY == contract.REPOSITORY


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
    assert len(host.reloads) == 1
    receipt = ad.last_receipt(cfg.state_dir)
    assert receipt == result["receipt"]
    assert receipt["schema"] == ad.RECEIPT_SCHEMA
    assert receipt["candidate_commit"] == NEW and receipt["previous_commit"] == OLD
    assert receipt["deployment_root"] == str(root)
    assert receipt["venv_python"] == str(venv_python)
    assert receipt["uv_lock_sha256"] == __import__("hashlib").sha256(b"lock-bytes").hexdigest()
    assert receipt["switched"] is True and receipt["rolled_back"] is False
    assert set(receipt["probes"]) == {"spare", "live"}
    assert receipt["required_checks"]["verdict"] == "GREEN"
    assert receipt["started_at"].endswith("Z") and receipt["finished_at"].endswith("Z")
    status = json.loads((cfg.state_dir / "status.json").read_text())
    assert status["status"] == "DEPLOYED"


def test_per_deployment_venv_never_the_shared_clone(cfg: ad.Config) -> None:
    host = FakeHost()
    cycle(cfg, host, FakeProber())
    syncs = [(c, e) for c, e in zip(host.calls, host.envs) if c[:1] == ["uv"]]
    assert len(syncs) == 1
    argv, env = syncs[0]
    assert "--frozen" in argv and "--no-install-project" in argv
    assert env == {"UV_PROJECT_ENVIRONMENT": str(cfg.venvs / f"a1-{NEW}")}
    venv = Path(env["UV_PROJECT_ENVIRONMENT"])
    assert cfg.venvs in venv.parents and cfg.deployments not in venv.parents
    command = plistlib.loads(cfg.plist.read_bytes())["ProgramArguments"][2]
    assert "/shared/clone/.venv" not in command and "Nexus-new/.venv" not in command


def test_build_that_writes_into_source_tree_is_rejected(cfg: ad.Config) -> None:
    host = FakeHost()
    host.dirty_after_sync = True
    before = cfg.plist.read_bytes()
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "REJECTED_BUILD"
    assert cfg.plist.read_bytes() == before and host.reloads == []


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
    def broken(_path: str) -> Any:
        raise ad.DeployError("GH_API_FAILED:boom")

    assert cycle(cfg, FakeHost(), FakeProber(), broken)["status"] == "CHECKS_UNKNOWN"

    def no_runs(path: str) -> Any:
        return [] if path.endswith("/pulls") else {"check_runs": []}

    assert cycle(cfg, FakeHost(), FakeProber(), no_runs)["status"] == "CHECKS_UNKNOWN"


def test_required_check_found_on_merged_pr_head() -> None:
    api = green_api(on_commit=False)
    result = ad.required_checks(api, NEW)
    assert result["verdict"] == "GREEN"
    assert result["checks"]["Deletion guard"]["sha"] == PR_HEAD
    assert result["checks"]["Exact-base impact gate"]["sha"] == NEW


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
    # The same candidate is not retried on the next poll.
    host.clock += 10_000
    assert cycle(cfg, host, prober)["status"] == "CANDIDATE_REJECTED_BEFORE"


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
    assert not cfg.hold_file.exists()


def test_failed_rollback_engages_the_kill_switch(cfg: ad.Config) -> None:
    host = FakeHost()
    prober = FakeProber({(ad.LIVE_PORT, NEW): False, (ad.LIVE_PORT, OLD): False})
    assert cycle(cfg, host, prober)["status"] == "ROLLBACK_FAILED"
    assert cfg.hold_file.exists()
    assert cycle(cfg, host, prober)["status"] == "HELD"


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
    assert cycle(cfg, host, FakeProber())["status"] == "DEBOUNCED"
    host.clock += cfg.min_interval_seconds
    assert cycle(cfg, host, FakeProber())["status"] == "DEPLOYED"
    assert cycle(cfg, host, FakeProber())["status"] == "IN_SYNC"


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


def test_wrapper_rejects_shell_metacharacters(cfg: ad.Config) -> None:
    with pytest.raises(ad.DeployError, match="WRAPPER_PATH_UNSAFE"):
        ad.wrapper_command(cfg, Path('/tmp/x"; rm -rf ~'), Path("/py"))


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


def test_installer_dry_run_and_plist(tmp_path: Path) -> None:
    script = REPO_ROOT / "scripts/ops/install_nexus_gateway_auto_deploy.sh"
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "NEXUS_GATEWAY_AUTO_DEPLOY_PYTHON": sys.executable,
        "NEXUS_GATEWAY_AUTO_DEPLOY_GH": "/opt/gh",
        "NEXUS_GATEWAY_AUTO_DEPLOY_TOOL_ROOT": str(REPO_ROOT),
        "NEXUS_GATEWAY_AUTO_DEPLOY_LAUNCHD_LOAD": "0",
    }
    dry = subprocess.run(
        ["bash", str(script), "--dry-run"], env=env, capture_output=True, text=True, check=True
    )
    assert "would load" in dry.stdout
    assert not (tmp_path / "Library").exists()
    subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, check=True)
    plist = tmp_path / "Library/LaunchAgents/com.nexus.gateway-auto-deploy.plist"
    data = plistlib.loads(plist.read_bytes())
    link = tmp_path / "Library/Application Support/Nexus/gateway-direct/auto-deploy-current"
    assert link.is_symlink() and link.resolve() == REPO_ROOT.resolve()
    assert data["ProgramArguments"] == [
        sys.executable,
        f"{link}/scripts/ops/nexus_gateway_auto_deploy.py",
        "run",
        "--gh",
        "/opt/gh",
        "--state-dir",
        str(tmp_path / ".local/state/nexus-gateway-auto-deploy"),
    ]
    assert data["StartInterval"] == 300 and data["RunAtLoad"] is True
    assert data["EnvironmentVariables"]["PYTHONDONTWRITEBYTECODE"] == "1"
    assert data["EnvironmentVariables"]["NEXUS_GATEWAY_PLIST"] == str(
        tmp_path / "Library/LaunchAgents/com.nexus.mcp.gateway.direct.plist"
    )
    assert "NEXUS_MCP_GATEWAY_TOKEN" not in data["EnvironmentVariables"]


def test_successful_deploy_moves_the_deployer_link(cfg: ad.Config) -> None:
    cycle(cfg, FakeHost(), FakeProber())
    assert cfg.tool_link.is_symlink()
    assert Path(os.readlink(cfg.tool_link)) == cfg.deployments / f"a1-{NEW}"


def test_failed_deploy_keeps_the_deployer_link(cfg: ad.Config) -> None:
    cycle(cfg, FakeHost(), FakeProber({(ad.LIVE_PORT, NEW): False}))
    assert not cfg.tool_link.exists()


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


def test_no_deploy_while_a_pin_bump_pr_is_in_flight(cfg: ad.Config) -> None:
    host, prober = FakeHost(), FakeProber()
    pulls = [
        {"number": 2122, "title": "build(deps): pin nexus-runtime a72e223", "head": {"ref": "x"}}
    ]
    result = cycle(cfg, host, prober, green_api(open_pulls=pulls))
    assert result["status"] == "PIN_BUMP_IN_FLIGHT"
    assert result["pin_bumps"]["pull_requests"] == [2122]
    assert prober.calls == [] and not any(c[:1] == ["uv"] for c in host.calls)
    anchor = [{"number": 2125, "title": "ci: x", "head": {"ref": "ci/2123-trusted-anchor-pr2122"}}]
    assert cycle(cfg, host, prober, green_api(open_pulls=anchor))["status"] == "PIN_BUMP_IN_FLIGHT"

    def broken(path: str) -> Any:
        if "state=open" in path:
            raise ad.DeployError("GH_API_FAILED")
        return green_api()(path)

    assert cycle(cfg, host, prober, broken)["status"] == "PIN_BUMP_UNKNOWN"


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
