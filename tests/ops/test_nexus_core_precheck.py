"""Behavioral contract for scripts/ops/nexus-core-precheck and its Stop hook."""

from __future__ import annotations

import base64
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-core-precheck"
HOOK = ROOT / ".claude" / "hooks" / "core-precheck-on-stop.sh"
SLUG = "James3014/demo"
WORKFLOW_TEXT = "on:\n  repository_dispatch:\n    types: [nexus-core-precheck]\n"

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("bash") is None,
    reason="git and bash required",
)

FAKE_GH = r"""#!/usr/bin/env python3
import json, os, re, sys
state = json.load(open(os.environ["FAKE_GH_STATE"]))
args = sys.argv[1:]
stdin = sys.stdin.read() if "--input" in args else None
with open(os.environ["FAKE_GH_CALLS"], "a") as fh:
    fh.write(json.dumps({"args": args, "stdin": stdin}) + "\n")
if state.get("offline"):
    sys.stderr.write("error connecting to api.github.com\n"); sys.exit(1)
def out(obj):
    print(json.dumps(obj)); sys.exit(0)
if args[:2] == ["pr", "view"]:
    pr = state.get("pr")
    if pr is None:
        sys.stderr.write("no pull requests found\n"); sys.exit(1)
    out(pr)
if args[:2] == ["issue", "view"]:
    out({"state": state.get("issues", {}).get(args[2], "OPEN")})
if args[0] == "api":
    path = [a for a in args[1:] if a.startswith("repos/")][0]
    if path.endswith("/dispatches"):
        sys.exit(state.get("dispatch_rc", 0))
    if "/contents/" in path:
        wf = state.get("workflow")
        if wf is None:
            sys.stderr.write("gh: Not Found (HTTP 404)\n"); sys.exit(1)
        out({"content": wf})
    m = re.search(r"/actions/runs/(\d+)/artifacts", path)
    if m:
        out({"artifacts": [{"name": n} for n in state.get("artifacts", {}).get(m.group(1), [])]})
    if "/actions/workflows/" in path:
        out({"workflow_runs": state.get("runs", [])})
    out({"default_branch": "main"})
sys.exit(3)
"""


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


class Env:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.bare = tmp / "origin.git"
        self.repo = tmp / "work"
        self.bin = tmp / "bin"
        self.state_file = tmp / "gh-state.json"
        self.calls = tmp / "gh-calls.jsonl"
        self.state: dict = {
            "workflow": base64.b64encode(WORKFLOW_TEXT.encode()).decode(),
        }
        subprocess.run(["git", "init", "-q", "--bare", str(self.bare)], check=True)
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "user.email", "t@example.invalid")
        _git(self.repo, "config", "user.name", "t")
        _git(self.repo, "remote", "add", "origin", f"https://github.com/{SLUG}.git")
        _git(self.repo, "config", f"url.{self.bare}.insteadOf", f"https://github.com/{SLUG}.git")
        (self.repo / "a.txt").write_text("a\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "init")
        _git(self.repo, "push", "-q", "origin", "main")
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)

    def branch(self, name: str, *, push: bool = True) -> str:
        _git(self.repo, "checkout", "-q", "-b", name)
        (self.repo / "b.txt").write_text(name + "\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "work")
        if push:
            _git(self.repo, "push", "-q", "origin", name)
        return _git(self.repo, "rev-parse", "HEAD")

    def env(self, **extra: str) -> dict[str, str]:
        self.state_file.write_text(json.dumps(self.state))
        env = {k: v for k, v in os.environ.items() if k != "NEXUS_CORE_ISSUE"}
        env.update(
            PATH=f"{self.bin}{os.pathsep}{env.get('PATH', '')}",
            FAKE_GH_STATE=str(self.state_file),
            FAKE_GH_CALLS=str(self.calls),
            GIT_CONFIG_NOSYSTEM="1",
        )
        env.update(extra)
        return env

    def run(self, *args: str, **extra: str) -> tuple[int, dict]:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), *args, "--repo-root", str(self.repo)],
            capture_output=True,
            text=True,
            env=self.env(**extra),
        )
        return proc.returncode, json.loads(proc.stdout)

    def gh_calls(self) -> list[dict]:
        if not self.calls.exists():
            return []
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def dispatches(self) -> list[dict]:
        return [
            json.loads(c["stdin"])
            for c in self.gh_calls()
            if any(a.endswith("/dispatches") for a in c["args"])
        ]


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def test_dispatch_payload_has_exact_head_and_integer_issue(env: Env) -> None:
    head = env.branch("feat/2018-core-precheck")
    code, out = env.run("dispatch")
    assert code == 0, out
    assert out["schema"] == "nexus.core_precheck.v1"
    assert out["status"] == "DISPATCHED"
    assert (out["repo"], out["head"], out["issue"]) == (SLUG, head, 2018)
    assert env.dispatches() == [
        {
            "event_type": "nexus-core-precheck",
            "client_payload": {"head_sha": head, "issue_number": 2018},
        }
    ]
    assert isinstance(env.dispatches()[0]["client_payload"]["issue_number"], int)
    post = [c["args"] for c in env.gh_calls() if f"repos/{SLUG}/dispatches" in c["args"]][0]
    assert post[:4] == ["api", "--method", "POST", f"repos/{SLUG}/dispatches"]


def test_issue_resolution_order(env: Env) -> None:
    env.branch("fix/11-thing")
    env.state["pr"] = {"number": 5, "state": "OPEN", "body": "x <!-- NEXUS_CORE_ISSUE: 22 -->"}
    assert env.run("dispatch", "--issue", "33", "--force")[1]["issue"] == 33
    assert env.run("dispatch", "--force", NEXUS_CORE_ISSUE="44")[1]["issue"] == 22
    env.state["pr"] = None
    assert env.run("dispatch", "--force", NEXUS_CORE_ISSUE="44")[1]["issue"] == 44
    code, out = env.run("dispatch", "--force")
    assert (code, out["issue"], out["issue_source"]) == (0, 11, "branch")


@pytest.mark.parametrize(
    "branch,expected",
    [("issue-123", 123), ("claude/issue-77-fix", 77), ("feat/9-x", 9), ("fix/12", 12)],
)
def test_branch_patterns(env: Env, branch: str, expected: int) -> None:
    env.branch(branch)
    assert env.run("dispatch")[1]["issue"] == expected


def test_no_or_ambiguous_issue(env: Env) -> None:
    env.branch("topic-without-number")
    code, out = env.run("dispatch", "--auto")
    assert (code, out["status"]) == (0, "SKIPPED_NO_ISSUE")
    code, out = env.run("dispatch")
    assert (code, out["status"]) == (2, "SKIPPED_NO_ISSUE")
    env.state["pr"] = {
        "number": 5,
        "state": "OPEN",
        "body": "<!-- NEXUS_CORE_ISSUE: 1 --> <!-- NEXUS_CORE_ISSUE: 2 -->",
    }
    code, out = env.run("dispatch", "--auto")
    assert (code, out["status"]) == (0, "SKIPPED_NO_ISSUE")
    assert env.dispatches() == []


def test_skip_cases(env: Env) -> None:
    code, out = env.run("dispatch", "--issue", "5")
    assert (code, out["status"]) == (0, "SKIPPED_DEFAULT_BRANCH")
    env.branch("feat/5-local", push=False)
    assert env.run("dispatch")[1]["status"] == "SKIPPED_NOT_PUSHED"
    _git(env.repo, "push", "-q", "origin", "feat/5-local")
    env.state["issues"] = {"5": "CLOSED"}
    assert env.run("dispatch")[1]["status"] == "SKIPPED_ISSUE_NOT_OPEN"
    env.state["issues"] = {}
    env.state["workflow"] = base64.b64encode(b"on: pull_request_target\n").decode()
    assert env.run("dispatch")[1]["status"] == "SKIPPED_REPO_NOT_ENROLLED"
    env.state["workflow"] = None
    assert env.run("dispatch")[1]["status"] == "SKIPPED_REPO_NOT_ENROLLED"
    assert env.dispatches() == []


def test_untrusted_owner_skipped_in_auto(env: Env) -> None:
    env.branch("feat/5-x")
    _git(env.repo, "remote", "set-url", "origin", "https://github.com/someone/demo.git")
    _git(env.repo, "config", f"url.{env.bare}.insteadOf", "https://github.com/someone/demo.git")
    assert env.run("dispatch", "--auto")[1]["status"] == "SKIPPED_UNTRUSTED_REPO"
    _git(env.repo, "remote", "set-url", "origin", str(env.bare))
    assert env.run("dispatch", "--auto")[1]["status"] == "SKIPPED_NOT_GITHUB"
    assert env.dispatches() == []


def test_dedupe_and_force(env: Env) -> None:
    head = env.branch("feat/7-x")
    assert env.run("dispatch")[1]["status"] == "DISPATCHED"
    record = Path(_git(env.repo, "rev-parse", "--git-common-dir"))
    record = (env.repo / record if not record.is_absolute() else record) / (
        f"nexus-core-precheck/{head}-7.json"
    )
    assert json.loads(record.read_text())["head"] == head
    code, out = env.run("dispatch")
    assert (code, out["status"]) == (0, "SKIPPED_ALREADY_DISPATCHED")
    assert out["previous"]["issue"] == 7
    assert env.run("dispatch", "--force")[1]["status"] == "DISPATCHED"
    stale = json.loads(record.read_text())
    stale["dispatched_at_epoch"] = time.time() - 7 * 3600
    record.write_text(json.dumps(stale))
    assert env.run("dispatch")[1]["status"] == "DISPATCHED"
    assert len(env.dispatches()) == 3


def test_auto_prefilter_skips_offline_when_local_tracking_ref_differs(env: Env) -> None:
    env.branch("feat/2018-core-precheck", push=False)
    code, out = env.run("dispatch", "--auto")
    assert (code, out["status"]) == (0, "SKIPPED_NOT_PUSHED")
    assert env.gh_calls() == []


def test_auto_prefilter_skips_offline_when_head_already_dispatched(env: Env) -> None:
    env.branch("feat/2018-core-precheck")
    assert env.run("dispatch", "--auto")[1]["status"] == "DISPATCHED"
    env.calls.unlink()
    code, out = env.run("dispatch", "--auto")
    assert (code, out["status"]) == (0, "SKIPPED_ALREADY_DISPATCHED")
    assert env.gh_calls() == []


def test_tool_failure_is_error(env: Env) -> None:
    env.branch("feat/7-x")
    env.state["offline"] = True
    code, out = env.run("dispatch", "--auto")
    assert (code, out["status"]) == (2, "ERROR")


def _run(run_id: int, status: str, conclusion: str | None, title: str, created: str) -> dict:
    return {
        "id": run_id,
        "status": status,
        "conclusion": conclusion,
        "display_title": title,
        "created_at": created,
        "html_url": f"https://github.com/{SLUG}/actions/runs/{run_id}",
    }


def test_status_classification(env: Env) -> None:
    head = "b" * 40
    art = f"nexus-core-receipts-{head}-run{{}}-attempt1"
    code, out = env.run("status", "--head", head)
    assert (code, out["status"]) == (0, "NOT_FOUND")

    env.state["runs"] = [
        _run(1, "completed", "success", "Nexus Core issue completion", "2026-10-13T01:00:00Z"),
        _run(2, "completed", "failure", "other", "2026-10-13T00:00:00Z"),
    ]
    env.state["artifacts"] = {"1": [art.format(1)], "2": [art.format(2)]}
    code, out = env.run("status", "--head", head)
    assert (code, out["status"], out["run_id"]) == (0, "VERIFIED", 1)

    env.state["artifacts"] = {"1": ["unrelated"], "2": [art.format(2)]}
    code, out = env.run("status", "--head", head)
    assert (code, out["status"], out["run_id"]) == (1, "FAILED", 2)

    env.state["runs"].insert(
        0, _run(3, "in_progress", None, f"Core precheck {head[:12]} #9", "2026-10-13T02:00:00Z")
    )
    code, out = env.run("status", "--head", head, "--issue", "9")
    assert (code, out["status"], out["run_id"]) == (0, "PENDING", 3)

    # The title is only a hint: a mismatched artifact head must not verify.
    env.state["runs"] = [_run(4, "completed", "success", "x", "2026-10-13T03:00:00Z")]
    env.state["artifacts"] = {"4": [f"nexus-core-receipts-{'c' * 40}-run4-attempt1"]}
    assert env.run("status", "--head", head)[1]["status"] == "NOT_FOUND"


def test_status_with_issue_reports_only_runs_bound_to_that_issue(env: Env) -> None:
    head = "b" * 40
    env.state["runs"] = [
        _run(5, "completed", "success", f"Core precheck {head} #5", "2026-11-01T01:00:00Z"),
    ]
    env.state["artifacts"] = {"5": [f"nexus-core-receipts-{head}-run5-attempt1"]}
    code, out = env.run("status", "--head", head, "--issue", "7")
    assert (code, out["status"]) == (0, "NOT_FOUND"), out

    # Same head, same Issue: still VERIFIED.
    code, out = env.run("status", "--head", head, "--issue", "5")
    assert (code, out["status"], out["run_id"]) == (0, "VERIFIED", 5), out

    # Without --issue the head alone decides, as before.
    code, out = env.run("status", "--head", head)
    assert (code, out["status"], out["run_id"]) == (0, "VERIFIED", 5), out


def test_status_with_issue_skips_newer_run_for_other_issue(env: Env) -> None:
    head = "b" * 40
    env.state["runs"] = [
        _run(6, "completed", "success", f"Core precheck {head} #5", "2026-11-01T02:00:00Z"),
        _run(4, "completed", "failure", f"Core precheck {head} #7", "2026-11-01T01:00:00Z"),
    ]
    env.state["artifacts"] = {
        "6": [f"nexus-core-receipts-{head}-run6-attempt1"],
        "4": [f"nexus-core-receipts-{head}-run4-attempt1"],
    }
    code, out = env.run("status", "--head", head, "--issue", "7")
    assert (code, out["status"], out["run_id"]) == (1, "FAILED", 4), out


def test_status_with_issue_matches_the_whole_issue_number(env: Env) -> None:
    head = "b" * 40
    env.state["runs"] = [
        _run(8, "completed", "success", f"Core precheck {head} #12", "2026-11-01T01:00:00Z"),
    ]
    env.state["artifacts"] = {"8": [f"nexus-core-receipts-{head}-run8-attempt1"]}
    assert env.run("status", "--head", head, "--issue", "1")[1]["status"] == "NOT_FOUND"
    assert env.run("status", "--head", head, "--issue", "2")[1]["status"] == "NOT_FOUND"
    code, out = env.run("status", "--head", head, "--issue", "12")
    assert (code, out["status"], out["run_id"]) == (0, "VERIFIED", 8), out


def test_status_with_issue_needs_the_issue_in_the_run_title(env: Env) -> None:
    head = "b" * 40
    env.state["runs"] = [
        _run(9, "completed", "success", f"Core precheck {head}", "2026-11-01T01:00:00Z"),
    ]
    env.state["artifacts"] = {"9": [f"nexus-core-receipts-{head}-run9-attempt1"]}
    assert env.run("status", "--head", head, "--issue", "7")[1]["status"] == "NOT_FOUND"
    code, out = env.run("status", "--head", head)
    assert (code, out["status"], out["run_id"]) == (0, "VERIFIED", 9), out


def _hook(env: Env, payload: dict, **extra: str) -> subprocess.CompletedProcess[str]:
    work = env.repo
    (work / "scripts" / "ops").mkdir(parents=True, exist_ok=True)
    shutil.copy2(SCRIPT, work / "scripts" / "ops" / "nexus-core-precheck")
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env.env(CLAUDE_PROJECT_DIR=str(work), **extra),
        cwd=work,
    )


def test_hook_blocks_once_when_dispatched(env: Env) -> None:
    head = env.branch("feat/31-x")
    proc = _hook(env, {"session_id": "s", "stop_hook_active": False})
    assert proc.returncode == 2, proc.stderr
    assert head[:12] in proc.stderr and "Issue #31" in proc.stderr
    assert "status --issue 31" in proc.stderr and "VERIFIED" in proc.stderr
    # Already dispatched: never blocks again.
    assert _hook(env, {"session_id": "s"}).returncode == 0
    assert len(env.dispatches()) == 1


def test_hook_stop_hook_active_never_runs(env: Env) -> None:
    env.branch("feat/31-x")
    proc = _hook(env, {"stop_hook_active": True})
    assert proc.returncode == 0
    assert env.gh_calls() == []


def test_hook_tool_errors_exit_zero(env: Env) -> None:
    env.branch("feat/31-x")
    env.state["offline"] = True
    assert _hook(env, {}).returncode == 0
    env.state["offline"] = False
    env.state["dispatch_rc"] = 1
    assert _hook(env, {}).returncode == 0
    minimal = env.tmp / "minimal-bin"
    minimal.mkdir()
    for tool in ("bash", "python3", "cat", "grep", "git"):
        found = shutil.which(tool)
        if found:
            (minimal / tool).symlink_to(found)
    proc = subprocess.run(
        [shutil.which("bash") or "bash", str(HOOK)],
        input="{}",
        capture_output=True,
        text=True,
        env={**env.env(), "PATH": str(minimal), "CLAUDE_PROJECT_DIR": str(env.repo)},
        cwd=env.repo,
    )
    assert proc.returncode == 0


def test_settings_register_core_precheck_stop_hook() -> None:
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
    commands = [h["command"] for entry in settings["hooks"]["Stop"] for h in entry["hooks"]]
    assert any("handoff-check.sh" in c for c in commands)
    assert any("core-precheck-on-stop.sh" in c for c in commands)
    assert os.access(HOOK, os.X_OK) and os.access(SCRIPT, os.X_OK)
