"""Unit tests for scripts/ops/eia_nightly.py.

gh, launchctl, ssh, osascript and network git (push / ls-remote / fetch) are faked; local git
runs for real in a temporary repository so the daemon's own validators see real blobs.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import plistlib
import subprocess
from pathlib import Path
from typing import Any

import pytest

from nexus.services.external_intelligence_automation import IssueWorkItem, parse_issue_contract
from nexus.services.external_intelligence_closure import INTEGRITY_CHECK_IDS
from nexus.services.external_intelligence_closure import _canonical_json as closure_canonical_json
from nexus.services.external_intelligence_closure import _sha256 as closure_sha256
from scripts.ops import eia_nightly as en

NIGHT = "20261016"
GH = "/fake/bin/gh"
ORIGIN = "https://github.com/James3014/Nexus-new.git"


def _git(repo: Path, *args: str, input: str | None = None) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, input=input
    ).stdout.strip()


def _cp(argv: list[str], rc: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv, rc, out, err)


class FakeGitHub:
    def __init__(self, remote: dict[str, str]):
        self.remote = remote
        self.issues: dict[int, dict[str, Any]] = {}
        self.prs: dict[int, dict[str, Any]] = {}
        self.labels: set[str] = set()
        self.writes: list[list[str]] = []
        self.next_number = 500

    def add_issue(
        self,
        number: int,
        body: str,
        labels=("eia:queue",),
        title: str = "Fix it",
        labeler: str = "James3014",
        author: dict[str, str] | None = None,
    ):
        self.issues[number] = {
            "number": number,
            "title": title,
            "body": body,
            "labels": set(labels),
            "state": "OPEN",
            "comments": [],
            "events": [
                {"event": "labeled", "label": n, "actor": labeler, "at": "2026-10-16T08:00:00Z"}
                for n in labels
            ],
            "edits": [],
            "author": author or {"login": "James3014", "__typename": "User"},
            "foreign_comments": [],
        }

    def _issue_json(self, issue: dict[str, Any]) -> dict[str, Any]:
        hidden = {"comments": None, "events": None, "edits": None, "author": None}
        hidden["foreign_comments"] = None
        return {**issue, "labels": [{"name": n} for n in sorted(issue["labels"])], **hidden}

    def __call__(self, argv: list[str]) -> subprocess.CompletedProcess:
        args = argv[1:]
        opt = {args[i]: args[i + 1] for i in range(len(args) - 1) if args[i].startswith("--")}
        body = (
            Path(opt["--body-file"]).read_text(encoding="utf-8") if "--body-file" in opt else None
        )
        head = args[:2]
        if head == ["issue", "list"]:
            rows = [i for i in self.issues.values() if i["state"] == "OPEN"]
            if "--label" in opt:
                rows = [i for i in rows if opt["--label"] in i["labels"]]
            if "--search" in opt:
                rows = [i for i in rows if i["title"] in opt["--search"]]
            return _cp(argv, out=json.dumps([self._issue_json(i) for i in rows]))
        if head == ["issue", "view"]:
            return _cp(argv, out=json.dumps(self._issue_json(self.issues[int(args[2])])))
        if head == ["label", "list"]:
            return _cp(argv, out=json.dumps([{"name": n} for n in sorted(self.labels)]))
        if head == ["pr", "list"]:
            rows = [p for p in self.prs.values() if p["head"] == opt["--head"]]
            return _cp(argv, out=json.dumps(rows))
        if head == ["pr", "view"]:
            return _cp(argv, out=json.dumps(self.prs[int(args[2])]))
        if args[:2] == ["api", "graphql"]:
            number = int(args[-1].split("=", 1)[1])
            nodes = self.issues[number]["edits"]
            edits = {"totalCount": len(nodes), "nodes": nodes}
            issue = {"userContentEdits": edits, "author": self.issues[number]["author"]}
            data = {"data": {"repository": {"issue": issue}}}
            return _cp(argv, out=json.dumps(data))
        if args[0] == "api" and args[2].endswith("/timeline"):
            number = int(args[2].split("/")[-2])
            return _cp(argv, out="\n".join(json.dumps(e) for e in self.issues[number]["events"]))
        if args[0] == "api":
            number = int(args[2].split("/")[-2])
            bot = "james3014-nexus-agent[bot]"
            rows = [{"user": bot, "body": b} for b in self.issues[number]["comments"]]
            rows += [{"user": u, "body": b} for u, b in self.issues[number]["foreign_comments"]]
            return _cp(argv, out="\n".join(json.dumps(r) for r in rows))
        self.writes.append(args)
        if head == ["label", "create"]:
            self.labels.add(args[2])
        elif head == ["issue", "edit"]:
            issue = self.issues[int(args[2])]
            for i, part in enumerate(args):
                if part == "--add-label":
                    assert (
                        args[i + 1] in self.labels or args[i + 1] == "nexus:external-intelligence"
                    )
                    issue["labels"].add(args[i + 1])
                elif part == "--remove-label":
                    issue["labels"].discard(args[i + 1])
            if body is not None:
                issue["body"] = body
                issue["edits"].append({
                    "editedAt": "2026-10-16T20:00:00Z",
                    "editor": {"login": "james3014-nexus-agent", "__typename": "Bot"},
                })
        elif head == ["issue", "comment"]:
            self.issues[int(args[2])]["comments"].append(body)
        elif head == ["issue", "create"]:
            self.next_number += 1
            self.add_issue(self.next_number, body or "", labels=(), title=opt["--title"])
            return _cp(
                argv, out=f"https://github.com/James3014/Nexus-new/issues/{self.next_number}\n"
            )
        elif head == ["pr", "create"]:
            self.next_number += 1
            self.prs[self.next_number] = {
                "number": self.next_number,
                "head": opt["--head"],
                "headRefOid": self.remote[opt["--head"]],
                "state": "OPEN",
                "baseRefName": opt["--base"],
                "isCrossRepository": False,
                "headRepositoryOwner": {"login": "James3014"},
                "title": opt["--title"],
                "body": body,
                "mergeCommit": None,
            }
            return _cp(
                argv, out=f"https://github.com/James3014/Nexus-new/pull/{self.next_number}\n"
            )
        else:
            raise AssertionError(f"unexpected gh call {args}")
        return _cp(argv)


class FakeSystem:
    def __init__(self, gh: FakeGitHub):
        self.gh, self.remote, self.calls = gh, gh.remote, []
        self.launchctl_print = ["state = running"]
        self.healthcheck_rc = 0
        self.bridge = "Extension: connected"
        self.python3_rc = 0
        self.bootout_rc = 0
        self.launchctl_rc: dict[str, int] = {}
        self.fail_push = False

    def __call__(self, argv: list[str], **kw: Any) -> subprocess.CompletedProcess:
        self.calls.append(list(argv))
        if argv[0] == GH:
            return self.gh(argv)
        if argv[0] == "git" and ("push" in argv or "ls-remote" in argv or "fetch" in argv):
            if "push" in argv:
                if self.fail_push:
                    return _cp(argv, 1, "", "network down")
                sha, ref = argv[argv.index("--") + 1].split(":")
                self.remote[ref.removeprefix("refs/heads/")] = sha
            if "ls-remote" in argv:
                ref = argv[-1].removeprefix("refs/heads/")
                sha = self.remote.get(ref)
                return _cp(argv, out=f"{sha}\trefs/heads/{ref}\n" if sha else "")
            return _cp(argv)
        if argv[0] == "git":
            return en.default_runner(argv, **kw)
        if argv[0] == "launchctl":
            if argv[1] == "print":
                text = (
                    self.launchctl_print.pop(0)
                    if len(self.launchctl_print) > 1
                    else self.launchctl_print[0]
                )
                return _cp(argv, 113 if "Could not find" in text else 0, text)
            if argv[1] == "bootout" and self.bootout_rc:
                return _cp(argv, self.bootout_rc, "", "Boot-out failed: 5")
            if self.launchctl_rc.get(argv[1]):
                return _cp(argv, self.launchctl_rc[argv[1]], "", f"{argv[1]} failed")
            return _cp(argv)
        if argv[0] == "/usr/bin/env":
            return _cp(argv, self.python3_rc)
        if argv[0] == "ps":
            return _cp(argv, out="/usr/bin/caffeinate\n")
        if argv[0].endswith("eia-healthcheck"):
            return _cp(argv, self.healthcheck_rc)
        if argv[0].endswith("opencli"):
            return _cp(argv, out=self.bridge)
        return _cp(argv)  # ssh, osascript, open

    def coord(self) -> list[str]:
        return [c[-1] for c in self.calls if c[0] == "ssh"]


class Clock:
    def __init__(self, at: str):
        self.at = dt.datetime.fromisoformat(at)

    def __call__(self) -> dt.datetime:
        return self.at


@pytest.fixture
def env(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "user.email", "t@example.invalid")
    index = repo / "docs/agents/CAPABILITY_DISCOVERY_INDEX.v1.json"
    index.parent.mkdir(parents=True)
    index.write_text(
        json.dumps({
            "schema": "nexus.capability_discovery_index.v1",
            "capabilities": [{"id": "nexus_core_domain_runtime"}],
        })
    )
    (repo / "pkg").mkdir()
    (repo / "pkg/mod.py").write_text("X = 1\n")
    (repo / "tests").mkdir()
    (repo / "tests/test_mod.py").write_text("def test_x():\n    pass\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "remote", "add", "origin", ORIGIN)
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    eia_state = tmp_path / "eia-state"
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({
            "repository_roots": {en.REPOSITORY: str(repo)},
            "state_root": str(eia_state),
            "opencli_executable": "/fake/opencli",
        })
    )
    plist = tmp_path / "daemon.plist"
    plist.write_bytes(plistlib.dumps({"EnvironmentVariables": {"PATH": "/venv/bin:/usr/bin"}}))
    gh = FakeGitHub(remote={})
    system = FakeSystem(gh)
    clock = Clock("2026-10-16T16:00:00")
    kills: list[tuple[int, int]] = []
    app = en.Nightly(
        state_dir=tmp_path / "nightly",
        eia_config=config,
        work_repo=repo,
        runner=system,
        now=clock,
        sleep=lambda _s: None,
        spawn=lambda argv: 4242,
        kill=lambda pid, sig: kills.append((pid, sig)),
        gh=Path(GH),
        daemon_plist=plist,
        watch_seconds=0,
        launchctl=lambda *args: system(["launchctl", *args]),
    )
    return {
        "app": app,
        "gh": gh,
        "sys": system,
        "clock": clock,
        "repo": repo,
        "eia_state": eia_state,
        "kills": kills,
        "tmp": tmp_path,
        "config": config,
    }


def task_body(**over: Any) -> str:
    block = {
        "difficulty": "easy",
        "allowed_files": ["pkg/mod.py"],
        "verification": ["python3 -m pytest -q tests/test_mod.py"],
        "capability_ids": ["nexus_core_domain_runtime"],
        "summary": "Make X equal 2.",
    }
    block.update(over)
    return f"Original problem text.\n\n```eia-task\n{json.dumps(block)}\n```\n"


def _prepared(env, issues=(11,)) -> dict[str, Any]:
    for number in issues:
        env["gh"].add_issue(number, task_body())
    night = env["app"].prepare()
    pr = env["gh"].prs[night["card_pr"]["number"]]
    _git(env["repo"], "update-ref", "refs/remotes/origin/main", pr["headRefOid"])
    pr.update(state="MERGED", mergeCommit={"oid": pr["headRefOid"]})
    return night


def _started(env) -> dict[str, Any]:
    _prepared(env)
    env["clock"].at = dt.datetime.fromisoformat("2026-10-16T23:30:00")
    night = env["app"].start()
    assert night["started"]["ok"], night
    return night


def _dispatch(env, at: str) -> dict[str, Any]:
    env["clock"].at = dt.datetime.fromisoformat(at)
    return env["app"].dispatch()


def _write_daemon_state(env, issue: int, identity: str, **fields: Any) -> None:
    path = (
        env["eia_state"] / "automation" / "James3014_Nexus-new" / f"issue-{issue}-{identity}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"identity_hash": identity, "issue_number": issue, **fields}))


# ------------------------------------------------------------------------------------- pure


def test_parse_task_block_accepts_minimal_block() -> None:
    task = en.parse_task_block(task_body())
    assert task["difficulty"] == "easy"
    assert task["verifiers"] == [["python3", "-m", "pytest", "-q", "tests/test_mod.py"]]
    assert task["capability_disposition"] == "EXTEND_EXISTING"


@pytest.mark.parametrize(
    "body,code",
    [
        ("no block", "TASK_BLOCK_REQUIRED"),
        (task_body() + task_body(), "TASK_BLOCK_REQUIRED"),
        ("```eia-task\n{bad\n```", "TASK_BLOCK_JSON_INVALID"),
        (task_body(extra=1), "TASK_BLOCK_KEYS_INVALID"),
        (task_body(difficulty="trivial"), "TASK_DIFFICULTY_INVALID"),
        (task_body(allowed_files=["../x.py"]), "TASK_ALLOWED_FILES_INVALID"),
        (task_body(allowed_files=["pkg/*.py"]), "TASK_ALLOWED_FILES_INVALID"),
        (task_body(allowed_files=["tasks/x.md"]), "TASK_ALLOWED_FILES_PROTECTED"),
        (task_body(verification=["pytest -q"]), "TASK_VERIFICATION_NOT_ALLOWLISTED"),
        (task_body(verification=["python -c '`x`'"]), "TASK_VERIFICATION_NOT_ALLOWLISTED"),
        (task_body(verification=["python3 -m pytest -k x tests/a.py"]), "NOT_ALLOWLISTED"),
        (task_body(verification=["python3 -m pytest tests/../a.py"]), "NOT_ALLOWLISTED"),
        (task_body(verification=["python3 -m pytest /tmp/test_a.py"]), "NOT_ALLOWLISTED"),
        (task_body(verification=["python3 -m pytest nexus/a.py"]), "NOT_ALLOWLISTED"),
        (task_body(verification=["python3 -m pytest tests/a.py;id"]), "NOT_ALLOWLISTED"),
        (task_body(verification=["python3 -m pytest --rootdir=/ tests/a.py"]), "NOT_ALLOWLISTED"),
        (task_body(verification=["python3 -m pytest -p evil tests/a.py"]), "NOT_ALLOWLISTED"),
        (task_body(verification=["sh -c 'git diff --check; id'"]), "NOT_ALLOWLISTED"),
        (task_body(verification=["bash -c 'git diff --check'"]), "NOT_ALLOWLISTED"),
        (task_body(allowed_files=[f"pkg/f{i}.py" for i in range(11)]), "ALLOWED_FILES_INVALID"),
        (task_body(allowed_files=["/etc/passwd"]), "TASK_ALLOWED_FILES_INVALID"),
        (task_body(allowed_files=["pkg/./mod.py"]), "TASK_ALLOWED_FILES_INVALID"),
        (task_body(allowed_files=["pyproject.toml"]), "TASK_ALLOWED_FILES_PROTECTED"),
        (task_body(allowed_files=[".github/x.yml"]), "TASK_ALLOWED_FILES_INVALID"),
        (task_body(allowed_files=["scripts/ops/trusted_x.py"]), "TASK_ALLOWED_FILES_PROTECTED"),
        (task_body(allowed_files=["scripts/ops/eia_nightly.py"]), "TASK_ALLOWED_FILES_PROTECTED"),
        (
            task_body(allowed_files=["nexus/services/external_intelligence_closure.py"]),
            "TASK_ALLOWED_FILES_PROTECTED",
        ),
        (task_body(allowed_files=["docs/governance/a.md"]), "TASK_ALLOWED_FILES_PROTECTED"),
        (task_body(capability_ids=[]), "TASK_CAPABILITY_IDS_INVALID"),
        (
            task_body(capability_disposition="BLOCKED_UNKNOWN"),
            "TASK_CAPABILITY_DISPOSITION_INVALID",
        ),
        (task_body() + "```nexus-external-intelligence\n{}\n```", "TASK_BODY_HAS_FOREIGN_CONTRACT"),
    ],
)
def test_parse_task_block_rejects(body: str, code: str) -> None:
    with pytest.raises(en.NightlyError, match=code):
        en.parse_task_block(body)


@pytest.mark.parametrize(
    "state,kind",
    [
        ({"state": "COMPLETE"}, "complete"),
        ({"state": "FANOUT_DISPATCHING"}, "wait"),
        ({"state": "RECONCILIATION_REQUIRED", "prior_state": "INTELLIGENCE_DISPATCHING"}, "wait"),
        ({"state": "RECONCILIATION_REQUIRED", "prior_state": "CLOSURE_DISPATCHING"}, "infra"),
        ({"state": "BLOCKED", "error": "OPENCLI_TIMEOUT"}, "infra"),
        (
            {"state": "BLOCKED", "stage": "INTELLIGENCE", "result": {"error": "OUTCOME_UNKNOWN"}},
            "infra",
        ),
        (
            {
                "state": "BLOCKED",
                "error": "ExternalIntelligenceError",
                "semantic_dispatched": False,
            },
            "infra",
        ),
        (
            {"state": "BLOCKED", "error": "ExternalIntelligenceError", "semantic_dispatched": True},
            "model",
        ),
        ({"state": "BLOCKED", "stage": "CLOSURE", "closure_status": "WHOLE_TASK_FAIL"}, "model"),
        ({"state": "BLOCKED", "error": "WORKER_BLOCKED"}, "model"),
        ({"state": "BLOCKED", "result": {"summary": "transport looked odd"}}, "model"),
        ({"state": "UNIT_REPAIR_REQUIRED"}, "model"),
        ({"state": "SCOPE_DELTA_REQUIRED"}, "model"),
        ({"state": "SOMETHING_NEW"}, "model"),
    ],
)
def test_classify_is_conservative(state: dict[str, Any], kind: str) -> None:
    assert en.classify(state)[0] == kind


def test_classify_unproven_diagnosis_escalates_as_model() -> None:
    """#2895: a stale or under-specified task needs a human, not an infra retry."""
    state = {
        "state": "BLOCKED",
        "stage": "INTELLIGENCE",
        "error": "INTELLIGENCE_DIAGNOSIS_NOT_PROVEN",
        "diagnosis_status": "UNKNOWN",
        "semantic_dispatched": True,
    }
    assert en.classify(state) == ("model", "BLOCKED:INTELLIGENCE_DIAGNOSIS_NOT_PROVEN")


def test_night_boundaries() -> None:
    assert en.night_of(dt.datetime(2026, 10, 16, 16, 0)) == NIGHT
    assert en.night_of(dt.datetime(2026, 10, 16, 23, 30)) == NIGHT
    assert en.night_of(dt.datetime(2026, 10, 17, 8, 59)) == NIGHT
    assert en.night_clock(NIGHT, "06:00") == dt.datetime(2026, 10, 17, 6, 0)


# ------------------------------------------------------------------------------------- flows


def test_prepare_opens_one_card_pr_and_hands_it_to_merge_queue(env) -> None:
    gh, app = env["gh"], env["app"]
    gh.add_issue(11, task_body())
    gh.add_issue(12, task_body(difficulty="hard"))
    gh.add_issue(13, "no block here")
    gh.add_issue(14, task_body(), labels=("eia:queue", "eia:escalate"))
    gh.add_issue(15, task_body())
    gh.add_issue(16, task_body(), labels=())
    app.max_issues = 1
    night = app.prepare()
    assert night["order"] == [11]
    assert {"eia:needs-template"} <= gh.issues[12]["labels"] and gh.issues[12]["comments"]
    assert {"eia:needs-template"} <= gh.issues[13]["labels"] and gh.issues[13]["comments"]
    assert (
        not gh.issues[14]["comments"]
        and not gh.issues[15]["comments"]
        and not gh.issues[16]["comments"]
    )
    pr = gh.prs[night["card_pr"]["number"]]
    commit = night["card_pr"]["commit"]
    assert gh.remote[f"eia-nightly/cards-{NIGHT}"] == commit == pr["headRefOid"]
    tracking = night["card_pr"]["tracking_issue"]
    assert gh.issues[tracking]["title"] == en.TRACKING_TITLE
    assert f"<!-- NEXUS_CORE_ISSUE: {tracking} -->" in pr["body"] and "KEEP_OPEN" in pr["body"]
    assert "closes" not in pr["body"].lower()
    changed = _git(env["repo"], "diff", "--name-only", f"{commit}^", commit)
    assert changed == f"tasks/eia-nightly/{NIGHT}/issue-11.md"
    card = _git(env["repo"], "show", f"{commit}:{changed}")
    assert "\npython3 -m pytest -q tests/test_mod.py\n" in card
    (msg,) = env["sys"].coord()
    assert "msg coordinator" in msg and f"Nexus-new#{pr['number']}" in msg and commit in msg
    assert "merge-queue" not in msg
    # Idempotent: a second run opens nothing new and records the merge once it lands.
    writes = len(gh.writes)
    app.prepare()
    assert len(gh.writes) == writes
    _git(env["repo"], "update-ref", "refs/remotes/origin/main", commit)
    pr.update(state="MERGED", mergeCommit={"oid": commit})
    night = app.prepare()
    assert night["card_pr"]["merged"] and night["card_pr"]["merge_sha"] == commit
    assert night["issues"]["11"]["merged_card_blob"] == night["issues"]["11"]["card_blob"]


def test_start_skips_night_when_card_pr_not_merged(env) -> None:
    env["gh"].add_issue(11, task_body())
    env["app"].prepare()
    env["clock"].at = dt.datetime.fromisoformat("2026-10-16T23:30:00")
    night = env["app"].start()
    env["app"]._flush_outbox(night)
    assert night["status"] == "SKIPPED_CARD_PR_NOT_MERGED"
    assert not [c for c in env["sys"].calls if c[0] in ("launchctl", "open")]
    assert any(
        "msg coordinator" in m and "SKIPPED_CARD_PR_NOT_MERGED" in m for m in env["sys"].coord()
    )


def test_start_bootstraps_daemon_after_bridge(env) -> None:
    _prepared(env)
    env["sys"].launchctl_print = ["Could not find service", "state = running"]
    env["sys"].bridge = "Extension: disconnected"
    attempts = iter(["Extension: disconnected", "Extension: connected"])
    original = env["sys"].__call__

    def runner(argv, **kw):
        if argv[0].endswith("opencli"):
            return _cp(argv, out=next(attempts, "Extension: connected"))
        return original(argv, **kw)

    env["app"].run = runner
    env["clock"].at = dt.datetime.fromisoformat("2026-10-16T23:30:00")
    night = env["app"].start()
    assert night["started"]["ok"] and night["caffeinate_pid"] == 4242
    calls = env["sys"].calls
    assert any(c[:2] == ["launchctl", "bootstrap"] for c in calls)
    assert any(c[0] == "osascript" and "ibase" in c[-1] for c in calls)


def test_dispatch_arms_one_issue_with_label_last(env) -> None:
    _started(env)
    env["gh"].add_issue(12, task_body(), labels=("eia:queue",))
    night = _dispatch(env, "2026-10-17T00:30:00")
    entry = night["issues"]["11"]
    assert entry["status"] == "ARMED"
    issue = env["gh"].issues[11]
    assert issue["body"].startswith("Original problem text.")
    contract = parse_issue_contract(issue["body"])
    assert contract["revision"] == f"n{NIGHT}-a1" and contract["task_card_ref"] == entry["card_ref"]
    identity = IssueWorkItem(
        en.REPOSITORY, 11, issue["title"], issue["body"], contract
    ).identity_hash
    assert entry["attempts"][0]["identity_hash"] == identity
    last_write = [w for w in env["gh"].writes if w[:3] == ["issue", "edit", "11"]][-1]
    assert last_write[-2:] == ["--add-label", "nexus:external-intelligence"]
    assert "nexus:external-intelligence" not in env["gh"].issues[12]["labels"]
    # Something already labelled blocks arming the next issue.
    night = _dispatch(env, "2026-10-17T00:35:00")
    assert (
        night["issues"]["11"]["status"] == "ARMED" and len(night["issues"]["11"]["attempts"]) == 1
    )


def _complete(
    env,
    entry: dict[str, Any],
    *,
    path: str = "pkg/mod.py",
    extra_commits: int = 0,
    verifier_ids: list[str] | None = None,
    run_id: str = "run-1",
    symlink: bool = False,
) -> str:
    repo, att = env["repo"], entry["attempts"][-1]
    wt = env["tmp"] / "cand"
    _git(repo, "worktree", "add", "-q", "--detach", str(wt), att["main_sha"])
    (wt / path).parent.mkdir(parents=True, exist_ok=True)
    if symlink:
        (wt / path).unlink()
        (wt / path).symlink_to("/etc/passwd")
    else:
        (wt / path).write_text("X = 2\n")
    _git(wt, "add", "-A")
    _git(wt, "-c", "user.name=t", "-c", "user.email=t@e.invalid", "commit", "-qm", "candidate")
    for extra in range(extra_commits):
        (wt / f"pkg/extra{extra}.py").write_text("Y = 1\n")
        _git(wt, "add", "-A")
        _git(wt, "-c", "user.name=t", "-c", "user.email=t@e.invalid", "commit", "-qm", "more")
    sha = _git(wt, "rev-parse", "HEAD")
    ids = verifier_ids if verifier_ids is not None else [f"whole-v1-a{att['attempt']}"]
    material = {
        "status": "PASS",
        "candidate_commit": sha,
        "results": [{"verifier_id": i, "passed": True} for i in ids],
        "integrity_status": "PASS",
        "failed_integrity_check_ids": [],
        "integrity_checks": [{"check_id": check, "passed": True} for check in INTEGRITY_CHECK_IDS],
    }
    vid = closure_sha256(closure_canonical_json(material))
    packet = env["eia_state"] / "closure" / "acceptance-packets" / "packet.json"
    packet.parent.mkdir(parents=True, exist_ok=True)
    packet.write_text(
        json.dumps({
            "task_candidate": {"candidate_commit": sha},
            "task_card_hash": entry["card_hash"],
            "whole_task_status": "PASS",
            "whole_task_verification_id": vid,
        })
    )
    verification = (
        packet.parent.parent
        / "verifications"
        / (f"{entry['task_id']}--task--whole_task--{vid}.json")
    )
    verification.parent.mkdir(parents=True, exist_ok=True)
    verification.write_text(json.dumps({**material, "verification_id": vid}))
    _write_daemon_state(
        env,
        11,
        att["identity_hash"],
        state="COMPLETE",
        closure_run_id=run_id,
        publication={
            "candidate_commit": sha,
            "candidate_tree": _git(wt, "rev-parse", "HEAD^{tree}"),
            "current_gate": "PENDING_INDEPENDENT_ACCEPTANCE",
            "claim_ceiling": "TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE",
            "task_id": entry["task_id"],
            "verification_state": "WHOLE_TASK_PASS",
            "acceptance_packet_ref": str(packet),
            "acceptance_packet_sha256": hashlib.sha256(packet.read_bytes()).hexdigest(),
        },
        publication_record={"state": "COMPLETED"},
        worker_binding={"provider": "opencli_chatgpt", "model": "opencli_chatgpt/advanced"},
    )
    return sha


def test_complete_becomes_candidate_pr_for_merge_queue(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    sha = _complete(env, night["issues"]["11"])
    night = _dispatch(env, "2026-10-17T01:30:00")
    entry = night["issues"]["11"]
    assert entry["status"] == "CANDIDATE_PR"
    branch = f"eia/11-n{NIGHT}-a1"
    assert env["gh"].remote[branch] == sha
    pr = env["gh"].prs[entry["pr"]["number"]]
    assert pr["body"].startswith("Closes #11") and "<!-- NEXUS_CORE_ISSUE: 11 -->" in pr["body"]
    assert '"on_merge": "CLOSE"' in pr["body"]
    labels = env["gh"].issues[11]["labels"]
    assert "eia:candidate-pr" in labels and not labels & {
        "eia:queue",
        "nexus:external-intelligence",
    }
    assert any(
        "msg coordinator" in m and f"Nexus-new#{pr['number']} head {sha}" in m
        for m in env["sys"].coord()
    )


def test_candidate_outside_allowed_files_is_escalated(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    _complete(env, night["issues"]["11"], path="pkg/other.py")
    night = _dispatch(env, "2026-10-17T01:30:00")
    assert night["issues"]["11"]["status"] == "ESCALATED"
    assert "CANDIDATE_SCOPE_VIOLATION" in night["issues"]["11"]["escalation"]["reason"]
    assert not [b for b in env["gh"].remote if b.startswith("eia/")]


def test_infra_failures_retry_with_new_revision_then_escalate(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    seen = []
    for minute in range(3):
        att = night["issues"]["11"]["attempts"][-1]
        seen.append((att["revision"], att["unit_id"]))
        _write_daemon_state(
            env,
            11,
            att["identity_hash"],
            state="BLOCKED",
            error="ExternalIntelligenceError",
            semantic_dispatched=False,
        )
        night = _dispatch(env, f"2026-10-17T01:0{minute}:00")
    assert seen == [(f"n{NIGHT}-a{k}", f"eia-nightly-{NIGHT}-i11-a{k}") for k in (1, 2, 3)]
    entry = night["issues"]["11"]
    assert entry["status"] == "ESCALATED" and entry["escalation"]["kind"] == "infra"
    assert "eia:escalate" in env["gh"].issues[11]["labels"]
    assert "nexus:external-intelligence" not in env["gh"].issues[11]["labels"]


def test_issue_cap_counts_as_infra(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    att = night["issues"]["11"]["attempts"][-1]
    _write_daemon_state(env, 11, att["identity_hash"], state="FANOUT_DISPATCHING")
    night = _dispatch(env, "2026-10-17T03:01:00")
    assert night["issues"]["11"]["attempts"][0]["reason"].startswith("ISSUE_CAP_EXCEEDED")
    assert (
        night["issues"]["11"]["status"] == "ARMED" and len(night["issues"]["11"]["attempts"]) == 2
    )


def test_model_result_escalates_and_disarms(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    att = night["issues"]["11"]["attempts"][-1]
    _write_daemon_state(env, 11, att["identity_hash"], state="UNIT_REPAIR_REQUIRED")
    night = _dispatch(env, "2026-10-17T01:00:00")
    issue = env["gh"].issues[11]
    assert night["issues"]["11"]["status"] == "ESCALATED"
    assert (
        "eia:escalate" in issue["labels"] and "nexus:external-intelligence" not in issue["labels"]
    )
    assert len(issue["comments"]) == 1 and "UNIT_REPAIR_REQUIRED" in issue["comments"][0]
    _dispatch(env, "2026-10-17T01:05:00")
    assert len(issue["comments"]) == 1


def test_no_arming_after_cutoff(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T06:05:00")
    assert night["issues"]["11"]["status"] == "PREPARED"


def test_stop_drains_until_hard_stop_then_finalizes(env) -> None:
    _started(env)
    env["app"].issue_cap_min = 300  # 06:00 cutoff + 150 min cap normally ends before 09:00
    _dispatch(env, "2026-10-17T05:00:00")
    env["clock"].at = dt.datetime.fromisoformat("2026-10-17T07:30:00")
    night = env["app"].stop()
    assert night["status"] == "DRAINING"
    assert not [c for c in env["sys"].calls if c[:2] == ["launchctl", "bootout"]]
    night = _dispatch(env, "2026-10-17T09:00:00")
    assert night["status"] == "FINISHED" and night["issues"]["11"]["status"] == "HARD_STOPPED"
    assert any(c[:2] == ["launchctl", "bootout"] for c in env["sys"].calls)
    assert env["kills"] and env["kills"][0][0] == 4242
    report = Path(night["finalized"]["report"]).read_text()
    assert "| #11 | HARD_STOPPED |" in report
    assert any("msg coordinator" in m for m in env["sys"].coord())
    assert any(c[0] == "osascript" and "display notification" in c[-1] for c in env["sys"].calls)
    assert "nexus:external-intelligence" not in env["gh"].issues[11]["labels"]


def test_stop_when_idle_finalizes_immediately(env) -> None:
    _started(env)
    env["clock"].at = dt.datetime.fromisoformat("2026-10-17T07:30:00")
    night = env["app"].stop()
    assert night["status"] == "FINISHED"


def test_pause_file_blocks_dispatch(env, capsys) -> None:
    (env["tmp"] / "nightly").mkdir(exist_ok=True)
    (env["tmp"] / "nightly" / "PAUSE").write_text("")
    rc = en.main([
        "dispatch",
        "--state-dir",
        str(env["tmp"] / "nightly"),
        "--eia-config",
        str(env["config"]),
        "--work-repo",
        str(env["repo"]),
    ])
    assert rc == 0 and '"PAUSED"' in capsys.readouterr().out


def test_identity_and_sha_guards() -> None:
    with pytest.raises(en.NightlyError):
        en._sha("HEAD")
    with pytest.raises(en.NightlyError):
        en._issue_number("1; rm")
    assert en._issue_number(7) == 7


def test_github_failure_while_publishing_candidate_retries_instead_of_escalating(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    sha = _complete(env, night["issues"]["11"])
    real = env["gh"].__call__
    failing = {"left": 1}

    def flaky(argv):
        if argv[1:3] == ["pr", "create"] and failing["left"]:
            failing["left"] -= 1
            return _cp(argv, 1, "", "HTTP 502")
        return real(argv)

    env["sys"].gh = flaky
    night = _dispatch(env, "2026-10-17T01:30:00")
    assert (
        night["issues"]["11"]["status"] == "ARMED"
        and night["issues"]["11"]["failures"]["_harvest"] == 1
    )
    night = _dispatch(env, "2026-10-17T01:35:00")
    assert night["issues"]["11"]["status"] == "CANDIDATE_PR"
    assert env["gh"].remote[f"eia/11-n{NIGHT}-a1"] == sha and len(env["gh"].prs) == 2


def test_arming_interrupted_after_body_edit_resumes_without_new_attempt(env) -> None:
    _started(env)
    real = env["gh"].__call__

    def no_label(argv):
        if "--add-label" in argv and "nexus:external-intelligence" in argv:
            return _cp(argv, 1, "", "HTTP 502")
        return real(argv)

    env["sys"].gh = no_label
    _dispatch(env, "2026-10-17T00:30:00")
    assert env["app"].load(NIGHT)["issues"]["11"]["status"] == "ARMING"
    env["sys"].gh = real
    night = _dispatch(env, "2026-10-17T00:35:00")
    entry = night["issues"]["11"]
    assert entry["status"] == "ARMED" and len(entry["attempts"]) == 1
    assert "nexus:external-intelligence" in env["gh"].issues[11]["labels"]


@pytest.mark.parametrize("command", ["prepare", "start", "dispatch", "stop"])
def test_launchd_templates_run_the_matching_subcommand(command: str) -> None:
    import plistlib

    path = Path(en.REPO_ROOT) / "scripts/ops" / f"com.nexus.eia-nightly-{command}.plist.template"
    plist = plistlib.loads(path.read_bytes())
    assert plist["Label"] == f"com.nexus.eia-nightly-{command}"
    assert plist["ProgramArguments"][1:] == ["__NEXUS_REPO__/scripts/ops/eia_nightly.py", command]
    assert ("StartInterval" in plist) == (command == "dispatch")
    assert plist["RunAtLoad"] is False


def test_diff_check_and_cacheprovider_forms_are_allowlisted() -> None:
    diff = 'sh -c \'git diff --check "$NEXUS_BASE_SHA" "$NEXUS_CANDIDATE_SHA"\''
    task = en.parse_task_block(
        task_body(verification=["python -m pytest -p no:cacheprovider tests/a.py::test_x", diff])
    )
    assert task["verifiers"] == [
        ["python3", "-m", "pytest", "-p", "no:cacheprovider", "tests/a.py::test_x"],
        en.DIFF_CHECK_ARGV,
    ]


def test_prepare_ignores_issue_queued_by_untrusted_actor(env) -> None:
    env["gh"].add_issue(11, task_body(), labeler="mallory")
    night = env["app"].prepare()
    assert night["status"] == "NO_TASKS" and not env["gh"].issues[11]["comments"]
    assert env["gh"].issues[11]["labels"] == {"eia:queue"}
    assert any(e["event"] == "untrusted_skipped" for e in night["events"])


def test_prepare_ignores_body_edited_by_untrusted_actor_after_queueing(env) -> None:
    env["gh"].add_issue(11, task_body())
    env["gh"].issues[11]["edits"].append({
        "editedAt": "2026-10-16T09:00:00Z",
        "editor": {"login": "mallory", "__typename": "User"},
    })
    assert env["app"].prepare()["status"] == "NO_TASKS"
    env["gh"].add_issue(12, task_body(), labeler="james3014-nexus-agent[bot]")
    env["gh"].issues[12]["edits"].append({
        "editedAt": "2026-10-16T07:00:00Z",
        "editor": {"login": "mallory", "__typename": "User"},
    })
    assert env["app"].prepare()["order"] == [12]  # edit before trusted queueing is fine


def test_trusted_actor_list_is_configurable(env) -> None:
    env["app"].trusted_actors = frozenset({"mallory"})
    env["gh"].add_issue(
        11, task_body(), labeler="mallory", author={"login": "mallory", "__typename": "User"}
    )
    assert env["app"].prepare()["order"] == [11]


def test_arm_refuses_issue_edited_by_untrusted_actor_after_cards(env) -> None:
    _started(env)
    env["gh"].issues[11]["edits"].append({
        "editedAt": "2026-10-16T22:00:00Z",
        "editor": {"login": "mallory", "__typename": "User"},
    })
    night = _dispatch(env, "2026-10-17T00:30:00")
    assert night["issues"]["11"]["status"] == "SKIPPED_UNTRUSTED"
    assert env["gh"].issues[11]["body"] == task_body()
    assert "nexus:external-intelligence" not in env["gh"].issues[11]["labels"]


def test_body_change_after_arming_disarms(env) -> None:
    _started(env)
    _dispatch(env, "2026-10-17T00:30:00")
    env["gh"].issues[11]["body"] += "\nextra prose"
    night = _dispatch(env, "2026-10-17T00:35:00")
    assert night["issues"]["11"]["status"] == "ESCALATED"
    assert "ISSUE_CHANGED_AFTER_ARMING" in night["issues"]["11"]["escalation"]["reason"]
    assert "nexus:external-intelligence" not in env["gh"].issues[11]["labels"]


def test_paths_must_be_regular_files_with_existing_parents(env) -> None:
    repo = env["repo"]
    (repo / "link").symlink_to("pkg")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "symlink")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    env["gh"].add_issue(11, task_body(allowed_files=["link/mod.py"]))
    env["gh"].add_issue(12, task_body(allowed_files=["newdir/sub/x.py"]))
    env["gh"].add_issue(13, task_body(verification=["python3 -m pytest tests/test_none.py"]))
    env["gh"].add_issue(14, task_body(allowed_files=["pkg/new.py"]))
    night = env["app"].prepare()
    assert night["order"] == [14]
    for number, code in ((11, "PARENT_INVALID"), (12, "PARENT_INVALID"), (13, "TARGET_MISSING")):
        assert code in env["gh"].issues[number]["comments"][0]


def test_missing_capability_ids_comment_lists_valid_ids(env) -> None:
    body = task_body()
    body = body.replace(', "capability_ids": ["nexus_core_domain_runtime"]', "")
    env["gh"].add_issue(11, body)
    env["app"].prepare()
    comment = env["gh"].issues[11]["comments"][0]
    assert "TASK_CAPABILITY_IDS_INVALID" in comment and "`nexus_core_domain_runtime`" in comment


def test_cross_night_cap_escalates_after_three_nights_without_candidate(env) -> None:
    ledger = env["tmp"] / "nightly" / "issues.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(json.dumps({"11": {"nights": ["20261013", "20261014", "20261015"]}}))
    env["gh"].add_issue(11, task_body())
    night = env["app"].prepare()
    assert night["status"] == "NO_TASKS"
    assert "eia:escalate" in env["gh"].issues[11]["labels"]


def test_finalize_records_attempted_nights_in_ledger(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    att = night["issues"]["11"]["attempts"][-1]
    _write_daemon_state(env, 11, att["identity_hash"], state="UNIT_REPAIR_REQUIRED")
    _dispatch(env, "2026-10-17T01:00:00")
    env["clock"].at = dt.datetime.fromisoformat("2026-10-17T07:30:00")
    env["app"].stop()
    ledger = json.loads((env["tmp"] / "nightly" / "issues.json").read_text())
    assert ledger["11"]["nights"] == [NIGHT]


def test_start_fails_closed_when_daemon_python3_cannot_import_nexus(env) -> None:
    _prepared(env)
    env["sys"].python3_rc = 1
    env["clock"].at = dt.datetime.fromisoformat("2026-10-16T23:30:00")
    night = env["app"].start()
    assert night["status"] == "START_FAILED"
    assert "DAEMON_PYTHON3_CANNOT_IMPORT_NEXUS" in night["started"]["error"]
    assert not [c for c in env["sys"].calls if c[0] == "launchctl"]


def test_watcher_disarms_terminal_result_within_the_same_invocation(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    att = night["issues"]["11"]["attempts"][-1]
    polls = []

    def sleep(seconds):
        polls.append(seconds)
        if len(polls) == 2:  # the daemon finishes while dispatch is watching
            _write_daemon_state(env, 11, att["identity_hash"], state="SCOPE_DELTA_REQUIRED")

    env["app"].sleep, env["app"].watch_seconds = sleep, 270
    night = _dispatch(env, "2026-10-17T00:35:00")
    assert polls == [20, 20] and night["issues"]["11"]["status"] == "ESCALATED"
    assert "nexus:external-intelligence" not in env["gh"].issues[11]["labels"]


# ------------------------------------------------------------------------- review round 2


def test_untrusted_author_is_refused_silently(env) -> None:
    env["gh"].add_issue(11, task_body(), author={"login": "mallory", "__typename": "User"})
    night = env["app"].prepare()
    assert night["status"] == "NO_TASKS" and not env["gh"].issues[11]["comments"]
    assert not env["gh"].writes or all("11" not in w for w in env["gh"].writes)


@pytest.mark.parametrize(
    "labeler,editor",
    [
        ("james3014-nexus-agent", None),  # REST bot actor must carry [bot]
        ("James3014", {"login": "james3014-nexus-agent", "__typename": "User"}),
        ("James3014", {"login": "james3014-nexus-agent[bot]", "__typename": "Bot"}),
        ("James3014", None),
    ],
)
def test_bot_identity_is_matched_exactly(env, labeler, editor) -> None:
    env["gh"].add_issue(11, task_body(), labeler=labeler)
    if editor:
        env["gh"].issues[11]["edits"].append({"editedAt": "2026-10-16T09:00:00Z", "editor": editor})
    trusted = labeler == "James3014" and editor is None
    assert env["app"]._queue_trusted(11)[0] is trusted


def test_incomplete_edit_history_fails_closed(env) -> None:
    env["gh"].add_issue(11, task_body())
    real = env["gh"].__call__

    def truncated(argv):
        out = real(argv)
        if argv[1:3] == ["api", "graphql"]:
            data = json.loads(out.stdout)
            data["data"]["repository"]["issue"]["userContentEdits"]["totalCount"] = 101
            return _cp(argv, out=json.dumps(data))
        return out

    env["sys"].gh = truncated
    assert env["app"]._queue_trusted(11) == (False, "EDIT_HISTORY_INCOMPLETE")


def test_title_change_between_readback_and_label_aborts_arming(env) -> None:
    _started(env)
    real = env["gh"].__call__
    seen = {"edited": False, "views": 0}

    def racing(argv):
        if argv[1:3] == ["issue", "edit"] and "--body-file" in argv:
            seen["edited"] = True
        if argv[1:3] == ["issue", "view"] and seen["edited"]:
            seen["views"] += 1
            if seen["views"] == 2:  # the re-check right before the label
                env["gh"].issues[11]["title"] = "Do something else"
        return real(argv)

    env["sys"].gh = racing
    night = _dispatch(env, "2026-10-17T00:30:00")
    assert night["issues"]["11"]["status"] == "ESCALATED"
    assert "ARM_RACE" in night["issues"]["11"]["escalation"]["reason"]
    assert "nexus:external-intelligence" not in env["gh"].issues[11]["labels"]


def test_watch_rereads_issue_and_disarms_on_edit(env) -> None:
    _started(env)
    _dispatch(env, "2026-10-17T00:30:00")
    polls = []

    def sleep(seconds):
        polls.append(seconds)
        if len(polls) == 1:
            env["gh"].issues[11]["body"] += "\nredirect the worker"

    env["app"].sleep, env["app"].watch_seconds = sleep, 270
    night = _dispatch(env, "2026-10-17T00:35:00")
    assert len(polls) == 3  # caught by the 60 s Issue re-read
    assert night["issues"]["11"]["status"] == "ESCALATED"
    assert "nexus:external-intelligence" not in env["gh"].issues[11]["labels"]


def test_withdrawn_queue_label_only_removes_our_label(env) -> None:
    _started(env)
    _dispatch(env, "2026-10-17T00:30:00")
    env["gh"].issues[11]["labels"].discard("eia:queue")
    night = _dispatch(env, "2026-10-17T00:35:00")
    assert night["issues"]["11"]["status"] == "WITHDRAWN"
    assert env["gh"].issues[11]["labels"] == set() and not env["gh"].issues[11]["comments"]


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"extra_commits": 1}, "NOT_SINGLE_COMMIT"),
        ({"symlink": True}, "CANDIDATE_SCOPE_VIOLATION"),
        ({"run_id": "run 1`"}, "PUBLICATION_FIELD_INVALID"),
        ({"verifier_ids": []}, "WHOLE_VERIFICATION_NOT_PASSED"),
    ],
)
def test_candidate_shape_and_fields_are_enforced(env, kwargs, code) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    if kwargs.get("extra_commits"):
        night["issues"]["11"]["allowed_files"].append("pkg/extra0.py")
        env["app"].save(night)
    _complete(env, night["issues"]["11"], **kwargs)
    night = _dispatch(env, "2026-10-17T01:30:00")
    assert night["issues"]["11"]["status"] == "ESCALATED"
    assert code in night["issues"]["11"]["escalation"]["reason"]
    assert len(env["gh"].prs) == 1  # only the card PR


def test_existing_closed_pr_for_candidate_branch_is_refused(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    sha = _complete(env, night["issues"]["11"])
    branch = f"eia/11-n{NIGHT}-a1"
    env["gh"].remote[branch] = sha
    env["gh"].prs[900] = {
        "number": 900,
        "head": branch,
        "headRefOid": sha,
        "state": "CLOSED",
        "baseRefName": "main",
        "isCrossRepository": False,
        "headRepositoryOwner": {"login": "James3014"},
    }
    night = _dispatch(env, "2026-10-17T01:30:00")
    assert "EXISTING_PR_INVALID" in night["issues"]["11"]["escalation"]["reason"]


def test_label_failure_after_candidate_pr_is_reconciled_next_tick(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    _complete(env, night["issues"]["11"])
    real = env["gh"].__call__

    def no_labels(argv):
        if "--add-label" in argv and "eia:candidate-pr" in argv:
            return _cp(argv, 1, "", "HTTP 502")
        return real(argv)

    env["sys"].gh = no_labels
    night = _dispatch(env, "2026-10-17T01:30:00")
    assert night["issues"]["11"]["status"] == "CANDIDATE_PR"
    assert night["issues"]["11"]["labels_pending"] is True
    env["sys"].gh = real
    night = _dispatch(env, "2026-10-17T01:35:00")
    assert night["issues"]["11"]["status"] == "CANDIDATE_PR" and len(env["gh"].prs) == 2
    assert "eia:candidate-pr" in env["gh"].issues[11]["labels"]


def test_bootout_failure_keeps_night_open_and_retries(env) -> None:
    _started(env)
    env["sys"].bootout_rc = 1
    env["clock"].at = dt.datetime.fromisoformat("2026-10-17T07:30:00")
    night = env["app"].stop()
    assert night["status"] == "BOOTOUT_FAILED" and not night.get("finalized")
    assert not env["kills"]
    env["sys"].bootout_rc = 0
    night = _dispatch(env, "2026-10-17T07:35:00")
    assert night["status"] == "FINISHED" and env["kills"]


def test_bootout_of_unloaded_daemon_finishes_the_night(env) -> None:
    _started(env)
    env["sys"].bootout_rc = 3
    env["sys"].launchctl_print = ["Could not find service"]
    env["clock"].at = dt.datetime.fromisoformat("2026-10-17T07:30:00")
    night = env["app"].stop()
    assert night["status"] == "FINISHED" and night["finalized"]["bootout_ok"]


@pytest.mark.parametrize(
    "path",
    [
        "pkg/conftest.py",
        "MAKEFILE",
        "Policy/rules.py",
        "pkg/.hidden/x.py",
        "pkg/governance_baseline_manifest_v2.json",
        "Taskfile.yml",
        "PYTEST.INI",
        "Scripts/Ops/Trusted_x.py",
    ],
)
def test_dotfiles_and_protected_names_are_refused(path: str) -> None:
    with pytest.raises(en.NightlyError, match="TASK_ALLOWED_FILES_(PROTECTED|INVALID)"):
        en.parse_task_block(task_body(allowed_files=[path]))


def test_stop_file_releases_a_watching_dispatch(env) -> None:
    _started(env)
    _dispatch(env, "2026-10-17T05:00:00")
    polls = []

    def sleep(seconds):
        polls.append(seconds)
        if len(polls) == 2:
            env["app"].request_stop(NIGHT)

    env["app"].sleep, env["app"].watch_seconds = sleep, 270
    night = _dispatch(env, "2026-10-17T07:30:00")
    assert len(polls) == 2 and night["stop_requested_at"]
    assert night["issues"]["11"]["status"] == "ARMED"  # still draining, nothing new armed


def test_stop_waits_for_lock_bounded(env) -> None:
    import fcntl

    app = env["app"]
    app.state_dir.mkdir(parents=True, exist_ok=True)
    waits = []
    app.sleep = waits.append
    with open(app.state_dir / ".lock", "a") as holder:
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with app.locked(wait_polls=3) as got:
            assert got is False
    assert waits == [5, 5, 5]
    with app.locked(wait_polls=3) as got:
        assert got is True


def test_one_failing_issue_is_escalated_after_three_errors(env) -> None:
    _started(env)
    _dispatch(env, "2026-10-17T00:30:00")
    real = env["gh"].__call__

    def broken_view(argv):
        if argv[1:4] == ["issue", "view", "11"]:
            return _cp(argv, 1, "", "HTTP 500")
        return real(argv)

    env["sys"].gh = broken_view
    for minute in (35, 40, 45):
        night = _dispatch(env, f"2026-10-17T00:{minute}:00")
    entry = night["issues"]["11"]
    assert entry["failures"]["_harvest"] == 3 and entry["status"] == "ESCALATED"
    assert "REPEATED_ERRORS" in entry["escalation"]["reason"]


def test_markers_in_untrusted_comments_do_not_suppress_ours(env) -> None:
    env["gh"].add_issue(13, "no block")
    marker = f"<!-- eia-nightly:needs-template:{NIGHT} -->"
    env["gh"].issues[13]["foreign_comments"].append(("mallory", marker))
    env["app"].prepare()
    assert len(env["gh"].issues[13]["comments"]) == 1


# ------------------------------------------------------------------------- review round 3

REAL = Path(__file__).parent / "fixtures" / "eia_nightly_real"


def test_real_complete_record_passes_field_and_verification_checks(env) -> None:
    """Minimal copies of the real #2150 COMPLETE record, packet and whole-task verification
    record: guards against drift between the test fixtures and what the daemon writes."""
    record = json.loads((REAL / "automation" / "complete-record.json").read_text())
    tokens = en.publication_tokens(record)
    assert tokens["model"] == "opencli_chatgpt/advanced"
    pub = record["publication"]
    packet_path = REAL / "closure" / "acceptance-packets" / Path(pub["acceptance_packet_ref"]).name
    raw = packet_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pub["acceptance_packet_sha256"]
    packet = json.loads(raw)
    env["app"].eia_state_root = REAL.resolve()
    verification = env["app"].load_whole_verification(
        packet_path.resolve(), packet, pub["task_id"], pub["candidate_commit"]
    )
    assert verification["status"] == "PASS"


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("status", "FAIL", "ID_MISMATCH"),  # tampering breaks the content-derived id
        ("integrity_status", "FAIL", "ID_MISMATCH"),
    ],
)
def test_tampered_verification_record_is_refused(env, tmp_path, field, value, code) -> None:
    import shutil

    root = tmp_path / "state"
    shutil.copytree(REAL, root)
    vfile = next((root / "closure" / "verifications").iterdir())
    data = json.loads(vfile.read_text())
    data[field] = value
    vfile.write_text(json.dumps(data))
    record = json.loads((root / "automation" / "complete-record.json").read_text())
    pub = record["publication"]
    packet_path = root / "closure" / "acceptance-packets" / Path(pub["acceptance_packet_ref"]).name
    env["app"].eia_state_root = root.resolve()
    with pytest.raises(en.CandidateRefused, match=code):
        env["app"].load_whole_verification(
            packet_path.resolve(),
            json.loads(packet_path.read_text()),
            pub["task_id"],
            pub["candidate_commit"],
        )


def test_failed_integrity_with_consistent_id_is_refused(env, tmp_path) -> None:
    import shutil

    root = tmp_path / "state"
    shutil.copytree(REAL, root)
    vfile = next((root / "closure" / "verifications").iterdir())
    data = json.loads(vfile.read_text())
    data["integrity_checks"][0]["passed"] = False
    data.pop("verification_id")
    vid = closure_sha256(closure_canonical_json(data))
    data["verification_id"] = vid
    task_id = json.loads((root / "automation" / "complete-record.json").read_text())["publication"][
        "task_id"
    ]
    (root / "closure" / "verifications" / f"{task_id}--task--whole_task--{vid}.json").write_text(
        json.dumps(data)
    )
    env["app"].eia_state_root = root.resolve()
    packet_path = next((root / "closure" / "acceptance-packets").iterdir()).resolve()
    with pytest.raises(en.CandidateRefused, match="INTEGRITY_FAILED"):
        env["app"].load_whole_verification(
            packet_path, {"whole_task_verification_id": vid}, task_id, data["candidate_commit"]
        )


def test_publication_tokens_reject_bad_worker_values() -> None:
    record = json.loads((REAL / "automation" / "complete-record.json").read_text())
    for bad in ("a/b/c", "x y", "`m`", None):
        record["worker_binding"]["model"] = bad
        with pytest.raises(en.CandidateRefused):
            en.publication_tokens(record)


def test_partial_label_write_after_candidate_pr_is_never_withdrawn(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    _complete(env, night["issues"]["11"])
    real = env["gh"].__call__

    def partial(argv):
        if "--add-label" in argv and "eia:candidate-pr" in argv:
            env["gh"].issues[11]["labels"].discard("eia:queue")  # half applied, then 502
            return _cp(argv, 1, "", "HTTP 502")
        return real(argv)

    env["sys"].gh = partial
    night = _dispatch(env, "2026-10-17T01:30:00")
    entry = night["issues"]["11"]
    assert entry["status"] == "CANDIDATE_PR" and entry["labels_pending"] is True
    assert entry["attempts"][-1]["pr_number"] == entry["pr"]["number"]
    env["sys"].gh = real
    night = _dispatch(env, "2026-10-17T01:35:00")
    assert night["issues"]["11"]["status"] == "CANDIDATE_PR"
    assert night["issues"]["11"]["labels_pending"] is False
    assert env["gh"].issues[11]["labels"] == {"eia:candidate-pr"}


@pytest.mark.parametrize(
    "edits", [{"nodes": []}, {"totalCount": None, "nodes": []}, {"totalCount": 0}]
)
def test_missing_edit_history_fields_fail_closed(env, edits) -> None:
    env["gh"].add_issue(11, task_body())
    real = env["gh"].__call__

    def mangled(argv):
        out = real(argv)
        if argv[1:3] == ["api", "graphql"]:
            data = json.loads(out.stdout)
            data["data"]["repository"]["issue"]["userContentEdits"] = edits
            return _cp(argv, out=json.dumps(data))
        return out

    env["sys"].gh = mangled
    assert env["app"]._queue_trusted(11) == (False, "EDIT_HISTORY_INCOMPLETE")


def test_new_candidate_pr_is_read_back_before_ready(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    _complete(env, night["issues"]["11"])
    real = env["gh"].__call__

    def wrong_base(argv):
        out = real(argv)
        if argv[1:3] == ["pr", "create"]:
            env["gh"].prs[env["gh"].next_number]["baseRefName"] = "release"
        return out

    env["sys"].gh = wrong_base
    night = _dispatch(env, "2026-10-17T01:30:00")
    assert night["issues"]["11"]["status"] == "ESCALATED"
    assert not any("ready-candidate" in k for k in night.get("outbox", {}))


def test_fork_pr_with_same_branch_name_is_ignored(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    sha = _complete(env, night["issues"]["11"])
    branch = f"eia/11-n{NIGHT}-a1"
    env["gh"].prs[901] = {
        "number": 901,
        "head": branch,
        "headRefOid": "f" * 40,
        "state": "OPEN",
        "baseRefName": "main",
        "isCrossRepository": True,
        "headRepositoryOwner": {"login": "mallory"},
    }
    night = _dispatch(env, "2026-10-17T01:30:00")
    entry = night["issues"]["11"]
    assert entry["status"] == "CANDIDATE_PR" and entry["pr"]["number"] != 901
    assert env["gh"].prs[entry["pr"]["number"]]["headRefOid"] == sha


def test_guarded_counts_consecutive_failures_and_catches_value_errors(env) -> None:
    env["gh"].add_issue(11, task_body())
    env["gh"].labels.add("eia:escalate")
    entry = {"issue": 11, "status": "ARMED", "attempts": [], "task_id": "t-11"}
    night = {"night": NIGHT, "issues": {"11": entry}, "order": [11]}

    def bad(_n, _e):
        raise ValueError("corrupt json")

    def good(_n, _e):
        return None

    env["app"]._guarded(night, entry, bad)
    env["app"]._guarded(night, entry, bad)
    assert entry["failures"]["bad"] == 2
    env["app"]._guarded(night, entry, good)  # another step succeeding must not reset "bad"
    assert entry["failures"] == {"bad": 2, "good": 0}
    env["app"]._guarded(night, entry, bad)
    assert entry["status"] == "ESCALATED" and "REPEATED_ERRORS:bad" in entry["escalation"]["reason"]


def test_guarded_success_resets_only_its_own_step(env) -> None:
    env["gh"].add_issue(11, task_body())
    env["gh"].labels.add("eia:escalate")
    entry = {"issue": 11, "status": "ARMED", "attempts": [], "task_id": "t-11"}
    night = {"night": NIGHT, "issues": {"11": entry}, "order": [11]}

    def bad(_n, _e):
        raise OSError("disk")

    env["app"]._guarded(night, entry, bad)
    env["app"]._guarded(night, entry, lambda _n, _e: None)
    env["app"]._guarded(night, entry, bad)
    entry["status"] = "ARMED"
    env["app"]._guarded(night, entry, bad)
    assert entry["failures"]["bad"] == 3


def test_bootout_failure_notifies_once_and_next_start_finishes_it(env) -> None:
    _started(env)
    env["sys"].bootout_rc = 1
    env["clock"].at = dt.datetime.fromisoformat("2026-10-17T07:30:00")
    env["app"].stop()
    _dispatch(env, "2026-10-17T07:35:00")
    _dispatch(env, "2026-10-17T07:40:00")
    notes = [c for c in env["sys"].calls if c[0] == "osascript" and "bootout failed" in c[-1]]
    assert len(notes) == 1
    env["sys"].bootout_rc = 0
    env["clock"].at = dt.datetime.fromisoformat("2026-10-17T16:00:00")
    env["app"].prepare()
    assert env["app"].load(NIGHT)["status"] == "FINISHED"


def test_integrity_checks_removed_with_recomputed_id_are_refused(env, tmp_path) -> None:
    import shutil

    root = tmp_path / "state"
    shutil.copytree(REAL, root)
    vfile = next((root / "closure" / "verifications").iterdir())
    data = json.loads(vfile.read_text())
    task_id = json.loads((root / "automation" / "complete-record.json").read_text())["publication"][
        "task_id"
    ]
    env["app"].eia_state_root = root.resolve()
    packet_path = next((root / "closure" / "acceptance-packets").iterdir()).resolve()
    variants = [
        lambda d: [d.pop(k) for k in ("integrity_checks", "integrity_status")],
        lambda d: d.__setitem__("integrity_checks", d["integrity_checks"][:2]),
        lambda d: d.pop("failed_integrity_check_ids"),
    ]
    for mutate in variants:
        changed = json.loads(json.dumps(data))
        changed.pop("verification_id")
        mutate(changed)
        vid = closure_sha256(closure_canonical_json(changed))
        changed["verification_id"] = vid
        name = f"{task_id}--task--whole_task--{vid}.json"
        (root / "closure" / "verifications" / name).write_text(json.dumps(changed))
        with pytest.raises(en.CandidateRefused, match="INTEGRITY_FAILED"):
            env["app"].load_whole_verification(
                packet_path, {"whole_task_verification_id": vid}, task_id, data["candidate_commit"]
            )


def test_candidate_pr_not_visible_yet_is_retried_then_found(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    sha = _complete(env, night["issues"]["11"])
    real = env["gh"].__call__
    hide = {"on": True}

    def lagging(argv):
        if argv[1:3] == ["pr", "list"] and hide["on"] and "eia/" in " ".join(argv):
            return _cp(argv, out="[]")
        return real(argv)

    env["sys"].gh = lagging
    night = _dispatch(env, "2026-10-17T01:30:00")
    entry = night["issues"]["11"]
    assert entry["status"] == "ARMED" and entry["failures"]["_harvest"] == 1
    hide["on"] = False
    night = _dispatch(env, "2026-10-17T01:35:00")
    entry = night["issues"]["11"]
    assert entry["status"] == "CANDIDATE_PR" and len(env["gh"].prs) == 2
    assert env["gh"].prs[entry["pr"]["number"]]["headRefOid"] == sha


def test_launchd_effects_go_through_the_eia_service_owner(env) -> None:
    """No raw launchctl argv in the scheduler (effect-owner architecture test)."""
    source = Path(en.__file__).read_text(encoding="utf-8")
    assert '"launchctl"' not in source and "'launchctl'" not in source
    assert '"update-ref"' not in source
    app = en.Nightly(
        state_dir=env["tmp"] / "other",
        eia_config=env["config"],
        work_repo=env["repo"],
    )
    assert app.launchctl is en.safe_daemon_launchd


# ------------------------------------------------------------------------- review round 5


def test_bootout_timeout_still_disarms_and_retries(env, monkeypatch) -> None:
    env["app"].issue_cap_min = 300
    _started(env)
    _dispatch(env, "2026-10-17T05:00:00")

    def hang(*args):
        raise subprocess.TimeoutExpired(["launchd", *args], 20)

    monkeypatch.setattr(en.eia_service, "_launchctl", hang)
    env["app"].launchctl = en.safe_daemon_launchd
    night = _dispatch(env, "2026-10-17T09:00:00")
    assert night["status"] == "BOOTOUT_FAILED" and not night.get("finalized")
    assert night["issues"]["11"]["status"] == "HARD_STOPPED"
    assert "nexus:external-intelligence" not in env["gh"].issues[11]["labels"]
    monkeypatch.setattr(en.eia_service, "_launchctl", lambda *a: _cp(list(a)))
    night = _dispatch(env, "2026-10-17T09:05:00")
    assert night["status"] == "FINISHED"


def test_safe_runner_maps_os_errors_to_124(monkeypatch) -> None:
    def boom(*args):
        raise FileNotFoundError("no binary")

    monkeypatch.setattr(en.eia_service, "_launchctl", boom)
    result = en.safe_daemon_launchd("print", "gui/1/x")
    assert result.returncode == 124 and "FileNotFoundError" in result.stderr


@pytest.mark.parametrize(
    "printed,step,code",
    [
        ("Could not find service", "bootstrap", "BOOTSTRAP_FAILED"),
        ("state = waiting", "kickstart", "KICKSTART_FAILED"),
    ],
)
def test_start_reports_which_launchd_step_failed(env, printed, step, code) -> None:
    _prepared(env)
    env["sys"].launchctl_print = [printed]
    env["sys"].launchctl_rc = {step: 1}
    env["clock"].at = dt.datetime.fromisoformat("2026-10-16T23:30:00")
    night = env["app"].start()
    assert night["status"] == "START_FAILED"
    assert night["started"]["error"].startswith(code)
    env["app"]._flush_outbox(night)
    assert any(code in m for m in env["sys"].coord())


def _lose_card_commit(env, *, keep_base: bool) -> dict[str, Any]:
    env["gh"].add_issue(11, task_body())
    env["sys"].fail_push = True
    with pytest.raises(en.NightlyError, match="PUSH_FAILED"):
        env["app"].prepare()
    night = env["app"].load(NIGHT)
    night["card_pr"]["commit"] = "1" * 40  # pruned: no local object, never pushed
    if not keep_base:
        night["card_pr"]["base"] = "2" * 40
    env["app"].save(night)
    env["sys"].fail_push = False
    return night


def test_missing_unpushed_card_commit_is_rebuilt_from_recorded_inputs(env) -> None:
    before = _lose_card_commit(env, keep_base=True)
    night = env["app"].prepare()
    commit = night["card_pr"]["commit"]
    assert commit != "1" * 40 and env["gh"].remote[f"eia-nightly/cards-{NIGHT}"] == commit
    blob = _git(env["repo"], "rev-parse", f"{commit}:tasks/eia-nightly/{NIGHT}/issue-11.md")
    assert blob == before["issues"]["11"]["card_blob"]
    assert any(e["event"] == "card_commit_rebuilt" for e in night["events"])
    assert night["card_pr"]["number"]


def test_missing_card_commit_without_base_redoes_prepare(env) -> None:
    _lose_card_commit(env, keep_base=False)
    night = env["app"].prepare()
    assert night["order"] == [11] and night["card_pr"]["number"]
    assert any(e["event"] == "card_commit_lost_reprepare" for e in night["events"])


def test_card_commit_is_deterministic(env) -> None:
    night = _prepared(env)
    entries = [night["issues"]["11"]]
    again = env["app"]._card_commit(NIGHT, entries, night["card_pr"]["base"])
    assert again == night["card_pr"]["commit"]


def test_missing_candidate_commit_is_infra_never_substituted(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    entry = night["issues"]["11"]
    _complete(env, entry)
    path = next((env["eia_state"] / "automation" / "James3014_Nexus-new").iterdir())
    record = json.loads(path.read_text())
    record["publication"]["candidate_commit"] = "3" * 40
    path.write_text(json.dumps(record))
    night = _dispatch(env, "2026-10-17T01:30:00")
    entry = night["issues"]["11"]
    assert entry["attempts"][0]["reason"] == "CANDIDATE_COMMIT_MISSING"
    assert entry["status"] == "ARMED" and len(entry["attempts"]) == 2
    assert not [b for b in env["gh"].remote if b.startswith("eia/")]


def test_failed_disarm_at_hard_stop_is_retried_before_finishing(env) -> None:
    env["app"].issue_cap_min = 300
    _started(env)
    _dispatch(env, "2026-10-17T05:00:00")
    real = env["gh"].__call__
    failing = {"left": 1}

    def flaky(argv):
        if "--remove-label" in argv and "nexus:external-intelligence" in argv and failing["left"]:
            failing["left"] -= 1
            return _cp(argv, 1, "", "HTTP 502")
        return real(argv)

    env["sys"].gh = flaky
    night = _dispatch(env, "2026-10-17T09:00:00")
    entry = night["issues"]["11"]
    assert night["status"] == "DISARM_PENDING" and not night.get("finalized")
    assert entry["status"] == "HARD_STOPPING" and entry["disarm_pending"] is True
    assert "nexus:external-intelligence" in env["gh"].issues[11]["labels"]
    night = _dispatch(env, "2026-10-17T09:05:00")
    entry = night["issues"]["11"]
    assert night["status"] == "FINISHED"
    assert entry["status"] == "HARD_STOPPED" and entry["disarm_pending"] is False
    assert "nexus:external-intelligence" not in env["gh"].issues[11]["labels"]


def test_pending_candidate_labels_block_finishing_until_fixed(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    _complete(env, night["issues"]["11"])
    real = env["gh"].__call__
    broken = {"on": True}

    def no_labels(argv):
        if broken["on"] and "--add-label" in argv and "eia:candidate-pr" in argv:
            return _cp(argv, 1, "", "HTTP 502")
        return real(argv)

    env["sys"].gh = no_labels
    night = _dispatch(env, "2026-10-17T01:30:00")
    assert night["issues"]["11"]["labels_pending"] is True
    night = _dispatch(env, "2026-10-17T09:00:00")  # hard stop while still pending
    assert night["status"] == "DISARM_PENDING" and not night.get("finalized")
    assert "nexus:external-intelligence" in env["gh"].issues[11]["labels"]
    broken["on"] = False
    env["clock"].at = dt.datetime.fromisoformat("2026-10-17T16:00:00")
    env["app"].finish_previous_night()  # next prepare/start retries it
    night = env["app"].load(NIGHT)
    assert night["status"] == "FINISHED" and night["issues"]["11"]["labels_pending"] is False
    assert env["gh"].issues[11]["labels"] == {"eia:candidate-pr"}


def test_multi_day_label_outage_is_repaired_on_day_three(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    _complete(env, night["issues"]["11"])
    real = env["gh"].__call__
    broken = {"on": True}

    def no_labels(argv):
        if broken["on"] and "--add-label" in argv and "eia:candidate-pr" in argv:
            return _cp(argv, 1, "", "HTTP 502")
        return real(argv)

    env["sys"].gh = no_labels
    _dispatch(env, "2026-10-17T01:30:00")
    assert _dispatch(env, "2026-10-17T09:00:00")["status"] == "DISARM_PENDING"
    # Day 2: still broken; the next night must not arm while the old label may be stale.
    env["clock"].at = dt.datetime.fromisoformat("2026-10-17T16:00:00")
    env["app"].finish_previous_night()
    assert env["app"].load(NIGHT)["status"] == "DISARM_PENDING"
    assert env["app"]._older_night_pending() is True
    tonight = {
        "schema": en.STATE_SCHEMA,
        "night": "20261017",
        "issues": {"12": {"issue": 12, "status": "PREPARED", "attempts": []}},
        "order": [12],
        "started": {"ok": True},
    }
    env["app"].save(tonight)
    armed = []
    env["app"]._arm = lambda n, e: armed.append(e["issue"])
    tonight = _dispatch(env, "2026-10-18T00:30:00")
    assert armed == [] and tonight["arm_blocked"] == f"OLDER_NIGHT_PENDING:{NIGHT}"
    assert any(e["event"] == "arm_blocked" for e in tonight["events"])
    # Day 3: GitHub is back; prepare/start finishes every older night, oldest first.
    broken["on"] = False
    env["clock"].at = dt.datetime.fromisoformat("2026-10-18T16:00:00")
    env["app"].finish_previous_night()
    old = env["app"].load(NIGHT)
    assert old["status"] == "FINISHED" and old["issues"]["11"]["labels_pending"] is False
    assert env["gh"].issues[11]["labels"] == {"eia:candidate-pr"}
    assert env["app"]._older_night_pending() is False


def test_older_night_scan_is_bounded_and_skips_bad_files(env) -> None:
    state = env["app"].state_dir
    state.mkdir(parents=True, exist_ok=True)
    (state / "20260901.json").write_text("{}")  # too old: ignored
    (state / "20261015.json").write_text("not json")  # unreadable, in window: reported
    (state / "issues.json").write_text("{}")
    env["clock"].at = dt.datetime.fromisoformat("2026-10-18T16:00:00")
    assert env["app"]._older_nights() == ([], ["20261015"])
    assert env["app"]._older_night_block() == "OLDER_NIGHT_UNREADABLE:20261015"
    env["app"].finish_previous_night()  # does not crash


def _tonight_with_prepared(env, status: str = "PREPARED") -> None:
    tonight = {
        "schema": en.STATE_SCHEMA,
        "night": "20261017",
        "issues": {"12": {"issue": 12, "status": status, "attempts": []}},
        "order": [12],
        "started": {"ok": True},
    }
    env["app"].save(tonight)


def test_resumed_arming_goes_through_the_gate(env) -> None:
    state = env["app"].state_dir
    state.mkdir(parents=True, exist_ok=True)
    old = {
        "schema": en.STATE_SCHEMA,
        "night": "20261016",
        "issues": {"11": {"issue": 11, "status": "HARD_STOPPING", "disarm_pending": True}},
        "order": [11],
        "started": {"ok": True},
    }
    env["app"].save(old)
    _tonight_with_prepared(env, status="ARMING")
    armed = []
    env["app"]._arm = lambda n, e: armed.append(e["issue"])
    tonight = _dispatch(env, "2026-10-18T00:30:00")
    assert armed == [] and tonight["arm_blocked"] == "OLDER_NIGHT_PENDING:20261016"
    old["issues"]["11"].update(status="HARD_STOPPED", disarm_pending=False)
    env["app"].save(old)
    tonight = _dispatch(env, "2026-10-18T00:35:00")
    assert armed == [12] and "arm_blocked" not in tonight


@pytest.mark.parametrize("content", ["not json", "[]", '{"schema": "x"}'])
def test_unreadable_older_night_blocks_arming_and_is_reported(env, content, capsys) -> None:
    state = env["app"].state_dir
    state.mkdir(parents=True, exist_ok=True)
    (state / "20261016.json").write_text(content)
    _tonight_with_prepared(env)
    armed = []
    env["app"]._arm = lambda n, e: armed.append(e["issue"])
    tonight = _dispatch(env, "2026-10-18T00:30:00")
    assert armed == [] and tonight["arm_blocked"] == "OLDER_NIGHT_UNREADABLE:20261016"
    assert "Arming blocked: OLDER_NIGHT_UNREADABLE" in env["app"].report(tonight)


@pytest.mark.parametrize(
    "rows,blocked",
    [
        ([], False),
        ([{"number": 12}], False),
        ([{"number": 99}], True),
        ([{"number": 1}] * 200, True),
    ],
)
def test_foreign_query_is_bounded_and_fails_closed(env, rows, blocked) -> None:
    calls = []

    def gh(argv):
        calls.append(argv)
        return _cp(argv, out=json.dumps(rows))

    env["sys"].gh = gh
    night = {"night": "20261017", "issues": {}, "order": []}
    assert env["app"]._foreign_in_flight(night, own=12) is blocked
    assert calls[0][-2:] == ["--limit", "200"]


@pytest.mark.parametrize("reason,setup", [("PAUSED", "pause"), ("AFTER_CUTOFF", "late")])
def test_gate_checks_pause_and_cutoff(env, reason, setup) -> None:
    _tonight_with_prepared(env)
    if setup == "pause":
        (env["app"].state_dir / "PAUSE").write_text("")
    env["clock"].at = dt.datetime.fromisoformat(
        "2026-10-18T06:30:00" if setup == "late" else "2026-10-18T00:30:00"
    )
    night = env["app"].load("20261017")
    assert env["app"]._arm_gate(night, night["issues"]["12"]) == reason


# --------------------------------------------------------------- ARMING reconciliation


def _crash_after_label(env) -> dict[str, Any]:
    """Arm #11 fully, then rewind the saved state to ARMING (a crash after the label)."""
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    assert "nexus:external-intelligence" in env["gh"].issues[11]["labels"]
    night["issues"]["11"]["status"] = "ARMING"
    env["app"].save(night)
    return night


@pytest.mark.parametrize("at", ["2026-10-17T00:35:00", "2026-10-17T06:30:00"])
def test_arming_with_label_on_is_promoted_and_monitored(env, at) -> None:
    env["app"].issue_cap_min = 600  # isolate recovery from the per-Issue cap
    _crash_after_label(env)  # also after the cutoff: the Issue is live, harvest it
    night = _dispatch(env, at)
    entry = night["issues"]["11"]
    assert entry["status"] == "ARMED" and len(entry["attempts"]) == 1
    assert any(e["event"] == "arming_recovered" for e in night["events"])
    att = entry["attempts"][-1]
    _write_daemon_state(env, 11, att["identity_hash"], state="UNIT_REPAIR_REQUIRED")
    night = _dispatch(env, at.replace(":35:", ":40:").replace(":30:", ":45:"))
    assert night["issues"]["11"]["status"] == "ESCALATED"  # harvested normally


def test_arming_recovery_after_label_request_counts_even_if_label_is_gone(env) -> None:
    night = _crash_after_label(env)
    assert night["issues"]["11"]["attempts"][-1].get("label_requested_at")
    env["gh"].issues[11]["labels"].discard("nexus:external-intelligence")
    night = _dispatch(env, "2026-10-17T06:30:00")  # after the cutoff: deferred
    entry = night["issues"]["11"]
    assert entry["status"] == "RETRY_PENDING"
    assert entry["attempts"][-1]["result"] == "withdrawn"
    assert len(en.counted_attempts(entry)) == 1
    env["app"]._update_ledger(night)
    ledger = json.loads((env["app"].state_dir / "issues.json").read_text())
    assert ledger["11"]["nights"] == [NIGHT]


def test_arming_recovery_with_older_night_pending_still_monitors(env) -> None:
    _crash_after_label(env)
    old = {
        "schema": en.STATE_SCHEMA,
        "night": "20261015",
        "issues": {"9": {"issue": 9, "status": "HARD_STOPPING", "disarm_pending": True}},
        "order": [9],
        "started": {"ok": True},
    }
    env["app"].save(old)
    night = _dispatch(env, "2026-10-17T00:35:00")
    assert night["issues"]["11"]["status"] == "ARMED"


def test_arming_with_label_on_but_body_changed_is_disarmed_and_escalated(env) -> None:
    _crash_after_label(env)
    env["gh"].issues[11]["body"] += "\nedited"
    night = _dispatch(env, "2026-10-17T00:35:00")
    entry = night["issues"]["11"]
    assert entry["status"] == "ESCALATED"
    assert "ARMING_RECOVERY_REFUSED" in entry["escalation"]["reason"]
    assert "nexus:external-intelligence" not in env["gh"].issues[11]["labels"]


def test_arming_with_label_on_but_untrusted_edit_is_refused(env) -> None:
    _crash_after_label(env)
    env["gh"].issues[11]["edits"].append({
        "editedAt": "2026-10-16T23:59:00Z",
        "editor": {"login": "mallory", "__typename": "User"},
    })
    night = _dispatch(env, "2026-10-17T00:35:00")
    assert night["issues"]["11"]["status"] == "ESCALATED"
    assert "nexus:external-intelligence" not in env["gh"].issues[11]["labels"]


def test_arming_with_label_on_and_queue_withdrawn(env) -> None:
    _crash_after_label(env)
    env["gh"].issues[11]["labels"].discard("eia:queue")
    night = _dispatch(env, "2026-10-17T00:35:00")
    assert night["issues"]["11"]["status"] == "WITHDRAWN"
    assert env["gh"].issues[11]["labels"] == set()


def test_arming_without_label_after_cutoff_is_deferred_not_left_arming(env) -> None:
    _started(env)
    real = env["gh"].__call__

    def no_label(argv):
        if "--add-label" in argv and "nexus:external-intelligence" in argv:
            return _cp(argv, 1, "", "HTTP 502")
        return real(argv)

    env["sys"].gh = no_label
    _dispatch(env, "2026-10-17T05:55:00")
    assert env["app"].load(NIGHT)["issues"]["11"]["status"] == "ARMING"
    env["sys"].gh = real
    night = _dispatch(env, "2026-10-17T06:05:00")
    entry = night["issues"]["11"]
    assert entry["status"] == "RETRY_PENDING"
    assert entry["attempts"][-1]["reason"] == "GATE:AFTER_CUTOFF"
    assert "nexus:external-intelligence" not in env["gh"].issues[11]["labels"]


@pytest.mark.parametrize("blocking", ["eia:escalate", "eia:needs-template", "eia:candidate-pr"])
def test_arming_recovery_refuses_blocking_labels(env, blocking) -> None:
    _crash_after_label(env)
    env["gh"].issues[11]["labels"].add(blocking)
    night = _dispatch(env, "2026-10-17T00:35:00")
    entry = night["issues"]["11"]
    assert entry["status"] == "WITHDRAWN"
    assert entry["attempts"][-1]["reason"] == f"BLOCKING_LABEL:{blocking}"
    assert "nexus:external-intelligence" not in env["gh"].issues[11]["labels"]


@pytest.mark.parametrize("blocking", ["eia:escalate", "eia:needs-template", "eia:candidate-pr"])
def test_blocking_label_added_while_armed_disarms(env, blocking) -> None:
    _started(env)
    _dispatch(env, "2026-10-17T00:30:00")
    env["gh"].issues[11]["labels"].add(blocking)
    night = _dispatch(env, "2026-10-17T00:35:00")
    assert night["issues"]["11"]["status"] == "WITHDRAWN"
    assert "nexus:external-intelligence" not in env["gh"].issues[11]["labels"]


def test_gate_deferred_attempts_do_not_count_toward_retries_or_night_cap(env) -> None:
    _started(env)
    night = env["app"].load(NIGHT)
    entry = night["issues"]["11"]
    deferred = {"attempt": 1, "result": "not_armed", "reason": "GATE:AFTER_CUTOFF"}
    running = {"attempt": 2, "armed_at": "2026-10-17T00:30:00"}
    entry.update(status="ARMED", attempts=[deferred, running])
    env["gh"].issues[11]["labels"].add("nexus:external-intelligence")
    env["clock"].at = dt.datetime.fromisoformat("2026-10-17T01:00:00")
    env["app"]._infra(night, entry, "BLOCKED:OPENCLI_TIMEOUT")
    assert entry["status"] == "RETRY_PENDING"  # one counted attempt, not two
    assert en.counted_attempts(entry) == [running]
    only_deferred = {"issue": 12, "status": "RETRY_PENDING", "attempts": [dict(deferred)]}
    night["issues"]["12"] = only_deferred
    night["order"].append(12)
    env["app"]._update_ledger(night)
    ledger = json.loads((env["app"].state_dir / "issues.json").read_text())
    assert ledger["11"]["nights"] == [NIGHT] and ledger["12"]["nights"] == []


@pytest.mark.parametrize(
    "change,reason",
    [
        ("eia:escalate", "BLOCKING_LABEL:eia:escalate"),
        ("eia:candidate-pr", "BLOCKING_LABEL:eia:candidate-pr"),
        ("unqueue", "QUEUE_LABEL_REMOVED"),
        ("close", "ISSUE_NOT_OPEN"),
    ],
)
def test_arm_readback_race_with_takeover_withdraws_not_escalates(env, change, reason) -> None:
    _started(env)
    real = env["gh"].__call__
    seen = {"edited": False, "views": 0}

    def racing(argv):
        if argv[1:3] == ["issue", "edit"] and "--body-file" in argv:
            seen["edited"] = True
        if argv[1:3] == ["issue", "view"] and seen["edited"]:
            seen["views"] += 1
            if seen["views"] == 2:  # the final re-check right before the label
                issue = env["gh"].issues[11]
                if change == "unqueue":
                    issue["labels"].discard("eia:queue")
                elif change == "close":
                    issue["state"] = "CLOSED"
                else:
                    issue["labels"].add(change)
        return real(argv)

    env["sys"].gh = racing
    night = _dispatch(env, "2026-10-17T00:30:00")
    entry = night["issues"]["11"]
    assert entry["status"] == "WITHDRAWN" and entry["attempts"][-1]["reason"] == reason
    assert "escalation" not in entry and not env["gh"].issues[11]["comments"]
    assert "nexus:external-intelligence" not in env["gh"].issues[11]["labels"]


def test_arm_readback_takeover_before_label_is_not_a_counted_attempt(env) -> None:
    _started(env)
    real = env["gh"].__call__
    seen = {"edited": False, "views": 0}

    def racing(argv):
        if argv[1:3] == ["issue", "edit"] and "--body-file" in argv:
            seen["edited"] = True
        if argv[1:3] == ["issue", "view"] and seen["edited"]:
            seen["views"] += 1
            if seen["views"] == 2:  # the final re-check right before the label
                env["gh"].issues[11]["labels"].discard("eia:queue")
        return real(argv)

    env["sys"].gh = racing
    night = _dispatch(env, "2026-10-17T00:30:00")
    entry = night["issues"]["11"]
    assert entry["status"] == "WITHDRAWN"
    assert entry["attempts"][-1]["result"] == "not_armed"
    assert en.counted_attempts(entry) == []
    env["app"]._update_ledger(night)
    ledger = json.loads((env["app"].state_dir / "issues.json").read_text())
    assert ledger["11"]["nights"] == []


def test_start_python_check_requires_pydantic(env) -> None:
    _prepared(env)
    env["clock"].at = dt.datetime.fromisoformat("2026-10-16T23:30:00")
    env["app"].start()
    checks = [c for c in env["sys"].calls if "-c" in c and c[0] == "/usr/bin/env"]
    assert checks and checks[0][-1] == "import nexus, pytest, pydantic"


# ------------------------------------------------------------------ daemon checkout freshness


def _origin_ahead(env, path: str) -> str:
    """Leave the daemon checkout on its commit while origin/main gains one touching ``path``."""
    repo = env["repo"]
    base = _git(repo, "rev-parse", "HEAD")
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("changed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", f"touch {path}")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(repo, "reset", "-q", "--hard", base)
    return base


def test_prepare_fails_closed_when_daemon_checkout_misses_verifier_change(env) -> None:
    env["gh"].add_issue(11, task_body())
    base = _origin_ahead(env, "nexus/services/external_intelligence_closure.py")
    night = env["app"].prepare()
    assert night["status"] == "START_FAILED"
    assert "DAEMON_CHECKOUT_STALE" in night["started"]["error"]
    assert "behind 1 commits" in night["started"]["error"]
    assert "nexus/services/external_intelligence_closure.py" in night["started"]["error"]
    assert night["daemon_checkout"]["head"] == base
    assert not env["gh"].prs  # no card PR for a night that cannot run
    env["app"]._flush_outbox(night)
    assert any("msg coordinator" in m and "DAEMON_CHECKOUT_STALE" in m for m in env["sys"].coord())
    assert env["app"].load(NIGHT)["status"] == "START_FAILED"


def test_start_rechecks_daemon_checkout_and_fails_closed(env) -> None:
    _prepared(env)
    _origin_ahead(env, "scripts/ops/eia_nightly.py")
    env["clock"].at = dt.datetime.fromisoformat("2026-10-16T23:30:00")
    night = env["app"].start()
    env["app"]._flush_outbox(night)
    assert night["status"] == "START_FAILED"
    assert "DAEMON_CHECKOUT_STALE" in night["started"]["error"]
    assert "scripts/ops/eia_nightly.py" in night["started"]["error"]
    assert not [c for c in env["sys"].calls if c[0] in ("launchctl", "open")]
    assert night.get("caffeinate_pid") is None
    assert any("DAEMON_CHECKOUT_STALE" in m for m in env["sys"].coord())


def test_unrelated_gap_is_recorded_and_the_night_runs(env) -> None:
    env["gh"].add_issue(11, task_body())
    base = _origin_ahead(env, "docs/unrelated.md")
    night = env["app"].prepare()
    assert night["status"] == "CARDS_PENDING"
    gap = night["daemon_checkout"]
    assert (gap["status"], gap["behind"], gap["head"]) == ("BEHIND", 1, base)
    assert gap["origin_main"] == _git(env["repo"], "rev-parse", "refs/remotes/origin/main")
    pr = env["gh"].prs[night["card_pr"]["number"]]
    pr.update(state="MERGED", mergeCommit={"oid": pr["headRefOid"]})
    _git(env["repo"], "update-ref", "refs/remotes/origin/main", pr["headRefOid"])
    env["clock"].at = dt.datetime.fromisoformat("2026-10-16T23:30:00")
    night = env["app"].start()
    assert night["started"]["ok"] and night["status"] == "RUNNING"
    assert night["daemon_checkout"]["head"] == base


def test_up_to_date_daemon_checkout_is_recorded_with_head_sha(env) -> None:
    night = _started(env)
    head = _git(env["repo"], "rev-parse", "HEAD")
    assert night["daemon_checkout"]["head"] == head
    assert night["status"] == "RUNNING"
    gap = en.Nightly._daemon_checkout_gap(env["app"])
    assert gap["status"] == "BEHIND" and gap["touched"] == []  # card PR commit only


def test_daemon_checkout_current_when_head_is_origin_main(env) -> None:
    gap = env["app"]._daemon_checkout_gap()
    assert (gap["status"], gap["behind"], gap["touched"]) == ("CURRENT", 0, [])


def test_fetch_failure_is_unknown_and_start_fails_closed(env) -> None:
    _prepared(env)
    original = env["app"].run

    def runner(argv, **kw):
        if argv[0] == "git" and "fetch" in argv and str(env["repo"]) in argv:
            return _cp(argv, 1, "", "could not resolve host")
        return original(argv, **kw)

    env["app"].run = runner
    env["clock"].at = dt.datetime.fromisoformat("2026-10-16T23:30:00")
    night = env["app"].start()
    assert night["status"] == "START_FAILED"
    assert "DAEMON_CHECKOUT_UNVERIFIED" in night["started"]["error"]
    assert night["daemon_checkout"]["status"] == "UNKNOWN"
    assert "FETCH_FAILED" in night["daemon_checkout"]["error"]
    assert not [c for c in env["sys"].calls if c[0] in ("launchctl", "open")]


def test_late_prepare_does_not_fail_a_started_night_on_stale_checkout(env) -> None:
    _started(env)
    _origin_ahead(env, "nexus/services/external_intelligence_closure.py")
    night = env["app"].prepare()
    assert night["started"]["ok"] and night["status"] == "RUNNING"
    night = _dispatch(env, "2026-10-17T00:00:00")
    assert night["status"] != "START_FAILED"


def test_open_swe_service_module_and_lock_are_daemon_critical(env) -> None:
    for path in ("nexus/services/open_swe_external_intelligence.py", "uv.lock"):
        _origin_ahead(env, path)
        gap = env["app"]._daemon_checkout_gap()
        assert gap["status"] == "STALE" and path in gap["touched"], (path, gap)


def test_a_later_different_start_failure_is_still_reported(env) -> None:
    night = {"night": NIGHT, "issues": {}, "order": []}
    env["app"]._fail_start(night, en.NightlyError("DAEMON_CHECKOUT_STALE:behind 1 commits"))
    env["app"]._fail_start(night, en.NightlyError("HEALTHCHECK_FAILED"))
    notes = [m["note"] for m in night["outbox"].values()]
    assert any("DAEMON_CHECKOUT_STALE" in n for n in notes)
    assert any("HEALTHCHECK_FAILED" in n for n in notes)


def test_local_commit_reverting_a_verifier_file_is_stale(env) -> None:
    repo = env["repo"]
    target = repo / "nexus/services/external_intelligence_closure.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("local edit\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "local daemon-only commit")
    gap = env["app"]._daemon_checkout_gap()
    assert gap["status"] == "STALE"
    assert "nexus/services/external_intelligence_closure.py" in gap["touched"]


def test_renamed_verifier_file_still_lists_its_old_path(env) -> None:
    repo = env["repo"]
    old = repo / "nexus/services/external_intelligence_closure.py"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text("".join(f"line {i}\n" for i in range(50)))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add closure")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "mv", str(old), str(repo / "nexus/verifier_moved.py"))
    _git(repo, "commit", "-qm", "move closure")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(repo, "reset", "-q", "--hard", base)
    gap = env["app"]._daemon_checkout_gap()
    assert gap["status"] == "STALE"
    assert "nexus/services/external_intelligence_closure.py" in gap["touched"]


# ------------------------------------------------------------------ bridge early warning


def test_prepare_warns_coordinator_when_bridge_is_down(env) -> None:
    env["gh"].add_issue(11, task_body())
    env["sys"].bridge = "Extension: disconnected"
    night = env["app"].prepare()
    assert night["status"] == "CARDS_PENDING"  # a warning only; the night is still prepared
    warnings = [m for m in env["sys"].coord() if "Browser Bridge not connected" in m]
    assert len(warnings) == 1 and "coordinator" in warnings[0]
    env["clock"].at = dt.datetime.fromisoformat("2026-10-16T20:00:00")
    env["app"].prepare()  # the 20:00 prepare does not repeat it
    assert len([m for m in env["sys"].coord() if "Browser Bridge not connected" in m]) == 1


def test_prepare_sends_no_bridge_warning_when_connected(env) -> None:
    env["gh"].add_issue(11, task_body())
    env["app"].prepare()
    assert not [m for m in env["sys"].coord() if "Browser Bridge" in m]
    assert any(c[0].endswith("opencli") for c in env["sys"].calls)


# ------------------------------------------------------------- #2611 night-1 follow-ups


def _own_contract_body(body: str, issue: int, night: str = "20261015", attempt: int = 1) -> str:
    contract = {"task_id": f"eia-nightly-{night}-i{issue}", "revision": f"n{night}-a{attempt}"}
    return en.body_with_contract(body, contract, attempt)


def test_strip_own_contract_only_removes_the_schedulers_trailing_block() -> None:
    original = task_body()
    assert en.strip_own_contract(_own_contract_body(original, 11), 11) == original.rstrip()
    assert en.strip_own_contract(original, 11) is None  # nothing of ours to strip
    assert en.strip_own_contract(_own_contract_body(original, 12), 11) is None  # other Issue
    trailing = _own_contract_body(original, 11) + "\n\nsomeone else's note"
    assert en.strip_own_contract(trailing, 11) is None
    nested = _own_contract_body(original, 11).replace(
        "```nexus-external-intelligence\n", "```nexus-external-intelligence\n```\n"
    )
    assert en.strip_own_contract(nested, 11) is None


def test_model_escalation_restores_the_original_body(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    assert en.CONTRACT_MARKER in env["gh"].issues[11]["body"]
    att = night["issues"]["11"]["attempts"][-1]
    _write_daemon_state(env, 11, att["identity_hash"], state="UNIT_REPAIR_REQUIRED")
    night = _dispatch(env, "2026-10-17T01:00:00")
    assert night["issues"]["11"]["status"] == "ESCALATED"
    issue = env["gh"].issues[11]
    assert issue["body"] == task_body().rstrip()
    assert "nexus:external-intelligence" not in issue["labels"]
    en.parse_task_block(issue["body"])  # re-queueable: no TASK_BODY_HAS_FOREIGN_CONTRACT
    # the body edit happens only after the daemon label is gone
    writes = env["gh"].writes
    removed = max(i for i, w in enumerate(writes) if "nexus:external-intelligence" in w)
    restored = [
        i for i, w in enumerate(writes) if w[:2] == ["issue", "edit"] and "--body-file" in w
    ]
    assert restored[-1] > removed


def test_infra_exhausted_escalation_restores_the_original_body(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    for minute in range(3):
        att = night["issues"]["11"]["attempts"][-1]
        _write_daemon_state(
            env,
            11,
            att["identity_hash"],
            state="BLOCKED",
            error="ExternalIntelligenceError",
            semantic_dispatched=False,
        )
        night = _dispatch(env, f"2026-10-17T01:0{minute}:00")
    assert night["issues"]["11"]["status"] == "ESCALATED"
    assert env["gh"].issues[11]["body"] == task_body().rstrip()


def test_escalation_keeps_a_body_someone_else_edited(env) -> None:
    _started(env)
    _dispatch(env, "2026-10-17T00:30:00")
    edited = env["gh"].issues[11]["body"].replace("Original problem", "Edited problem")
    env["gh"].issues[11]["body"] = edited
    night = _dispatch(env, "2026-10-17T00:35:00")
    assert "ISSUE_CHANGED_AFTER_ARMING" in night["issues"]["11"]["escalation"]["reason"]
    assert env["gh"].issues[11]["body"] == edited  # not bytes we wrote: left alone


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _capped_ledger(env, **rows: list[str]) -> None:
    ledger = env["tmp"] / "nightly" / "issues.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    nights = ["20261013", "20261014", "20261015"]
    ledger.write_text(
        json.dumps({k.lstrip("i"): {"nights": nights, "body_sha256": v} for k, v in rows.items()})
    )


def test_cross_night_cap_restores_the_original_body(env) -> None:
    ours = _own_contract_body(task_body(), 11)
    foreign = _own_contract_body(task_body(), 99)
    _capped_ledger(env, i11=[_sha(ours)], i12=[_sha(foreign)])
    env["gh"].add_issue(11, ours)
    env["gh"].add_issue(12, foreign)
    night = env["app"].prepare()
    assert night["status"] == "NO_TASKS"
    assert "eia:escalate" in env["gh"].issues[11]["labels"]
    assert env["gh"].issues[11]["body"] == task_body().rstrip()
    assert env["gh"].issues[12]["body"] == foreign  # not this Issue's own block
    env["gh"].writes.clear()
    env["app"].prepare()  # idempotent: nothing left to strip
    assert not [w for w in env["gh"].writes if "--body-file" in w and w[0] == "issue"]


STUCK = [
    {"error": "CANONICAL_WORKFORCE_BINDING_MISSING"},
    {"error": "CANONICAL_WORKFORCE_BINDING_REPLAY_MISMATCH"},
    {"error": "INTELLIGENCE_DISPATCH_BINDING_MISSING"},
    {"error": "INTELLIGENCE_DISPATCH_BINDING_MISMATCH"},
]


@pytest.mark.parametrize("fields", STUCK)
def test_stuck_reconciliation_is_infra_at_the_first_tick(env, fields) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    att = night["issues"]["11"]["attempts"][-1]
    _write_daemon_state(
        env,
        11,
        att["identity_hash"],
        state="RECONCILIATION_REQUIRED",
        prior_state="INTELLIGENCE_DISPATCHING",
        reconcile_only=True,
        semantic_dispatched=True,
        **fields,
    )
    night = _dispatch(env, "2026-10-17T00:35:00")  # well inside the 150-min cap
    first = night["issues"]["11"]["attempts"][0]
    code = fields["error"]
    assert first["result"] == "infra"
    assert first["reason"] == (
        f"RECONCILIATION_REQUIRED:RECONCILE_ONLY:INTELLIGENCE_DISPATCHING:{code}"
    )
    assert len(night["issues"]["11"]["attempts"]) == 2  # the retry budget applies


@pytest.mark.parametrize(
    "fields",
    [
        {"state": "INTELLIGENCE_DISPATCHING"},
        {
            "state": "RECONCILIATION_REQUIRED",
            "prior_state": "INTELLIGENCE_DISPATCHING",
            "reconcile_only": True,
            "error": "SOMETHING_ELSE",
        },
        {
            "state": "RECONCILIATION_REQUIRED",
            "prior_state": "INTELLIGENCE_DISPATCHING",
            "error": "CANONICAL_WORKFORCE_BINDING_MISSING",
        },
        # the transport's read-only reconcile can still resolve it: left to the cap
        {
            "state": "RECONCILIATION_REQUIRED",
            "prior_state": "INTELLIGENCE_DISPATCHING",
            "reconcile_only": True,
            "error": "ExternalIntelligenceError",
            "error_code": "INTELLIGENCE_RECONCILIATION_REQUIRED",
        },
    ],
)
def test_progressing_dispatch_records_still_wait(env, fields) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    att = night["issues"]["11"]["attempts"][-1]
    _write_daemon_state(env, 11, att["identity_hash"], **fields)
    night = _dispatch(env, "2026-10-17T00:35:00")
    entry = night["issues"]["11"]
    assert entry["status"] == "ARMED" and len(entry["attempts"]) == 1
    assert "result" not in entry["attempts"][0]


def test_restored_record_with_transient_error_waits_and_is_noted(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    att = night["issues"]["11"]["attempts"][-1]
    _write_daemon_state(
        env,
        11,
        att["identity_hash"],
        state="RECONCILIATION_REQUIRED",
        prior_state="INTELLIGENCE_DISPATCHING",
        reconcile_only=True,
        error="CANONICAL_WORKFORCE_BINDING_MISSING",
        last_transient_error="OPENCLI_TIMEOUT",
    )
    night = _dispatch(env, "2026-10-17T00:35:00")
    entry = night["issues"]["11"]
    assert entry["status"] == "ARMED" and len(entry["attempts"]) == 1
    assert entry["attempts"][0]["note"] == "last_transient_error=OPENCLI_TIMEOUT"


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"state": "FANOUT_DISPATCHING"}, "FANOUT_DISPATCHING:TRANSIENT:SOURCE_LINEAGE_FAILED"),
        (
            {
                "state": "RECONCILIATION_REQUIRED",
                "prior_state": "INTELLIGENCE_DISPATCHING",
                "reconcile_only": True,
                "error": "CANONICAL_WORKFORCE_BINDING_MISSING",
            },
            "RECONCILIATION_REQUIRED:INTELLIGENCE_DISPATCHING:TRANSIENT:SOURCE_LINEAGE_FAILED",
        ),
    ],
)
def test_classify_names_the_transient_error_of_a_waiting_record(fields, reason) -> None:
    """#2864: a restored record still waits, but its reason names the transient error."""
    state = {**fields, "last_transient_error": "SOURCE_LINEAGE_FAILED"}
    assert en.classify(state) == ("wait", reason)
    # a daemon string that is not a safe token is never echoed
    assert en.classify({**fields, "last_transient_error": "bad `x`"})[1].endswith(
        ":TRANSIENT:INVALID"
    )


def test_classify_without_a_transient_error_is_unchanged() -> None:
    assert en.classify({"state": "FANOUT_DISPATCHING"}) == ("wait", "FANOUT_DISPATCHING")


def _transient(env, att: dict[str, Any], at: str, error: str = "SOURCE_LINEAGE_FAILED") -> None:
    _write_daemon_state(
        env,
        11,
        att["identity_hash"],
        state="INTELLIGENCE_DISPATCHING",
        last_transient_error=error,
        last_transient_error_reason={"reason_code": "LINEAGE"},
        last_transient_error_at=at,
    )


def test_repeated_transient_error_is_counted_and_reported_as_such(env) -> None:
    """#2864: each new occurrence counts once; at the cap a repeated error is named."""
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    att = night["issues"]["11"]["attempts"][-1]
    _transient(env, att, "2026-10-17T00:31:00.000+00:00")
    night = _dispatch(env, "2026-10-17T00:35:00")
    night = _dispatch(env, "2026-10-17T00:40:00")  # same occurrence polled twice
    seen = night["issues"]["11"]["attempts"][0]["transient_error"]
    assert seen["count"] == 1 and seen["error"] == "SOURCE_LINEAGE_FAILED"
    assert seen["reason"] == '{"reason_code": "LINEAGE"}'
    for minute in ("41", "46"):
        _transient(env, att, f"2026-10-17T00:{minute}:00.000+00:00")
        night = _dispatch(env, f"2026-10-17T00:{minute}:30")
    assert night["issues"]["11"]["attempts"][0]["transient_error"]["count"] == 3
    report = env["app"].report(night)
    assert "Transient errors (last attempt; record restored after the error):" in report
    assert "- #11: SOURCE_LINEAGE_FAILED x3" in report
    night = _dispatch(env, "2026-10-17T03:01:00")
    reason = night["issues"]["11"]["attempts"][0]["reason"]
    assert reason == "TRANSIENT_ERROR_REPEATED:SOURCE_LINEAGE_FAILED:x3"


def test_a_different_transient_error_restarts_the_count(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    att = night["issues"]["11"]["attempts"][-1]
    for minute in ("31", "36"):
        _transient(env, att, f"2026-10-17T00:{minute}:00.000+00:00")
        night = _dispatch(env, f"2026-10-17T00:{minute}:30")
    _transient(env, att, "2026-10-17T00:41:00.000+00:00", error="OPENCLI_TIMEOUT")
    night = _dispatch(env, "2026-10-17T00:41:30")
    seen = night["issues"]["11"]["attempts"][0]["transient_error"]
    assert (seen["error"], seen["count"]) == ("OPENCLI_TIMEOUT", 1)


def test_a_clean_poll_between_transient_errors_restarts_the_count(env) -> None:
    """Codex r1 on #2914: only consecutive occurrences count toward REPEATED."""
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    att = night["issues"]["11"]["attempts"][-1]
    for minute in ("31", "36"):
        _transient(env, att, f"2026-10-17T00:{minute}:00.000+00:00")
        night = _dispatch(env, f"2026-10-17T00:{minute}:30")
    _write_daemon_state(env, 11, att["identity_hash"], state="INTELLIGENCE_DISPATCHING")
    night = _dispatch(env, "2026-10-17T00:40:00")
    assert "transient_error" not in night["issues"]["11"]["attempts"][0]
    _transient(env, att, "2026-10-17T00:41:00.000+00:00")
    night = _dispatch(env, "2026-10-17T00:41:30")
    assert night["issues"]["11"]["attempts"][0]["transient_error"]["count"] == 1


def test_transient_error_text_cannot_inject_markdown_into_the_report(env) -> None:
    """Codex r1 on #2914: daemon text in the report carries no link or emphasis syntax."""
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    att = night["issues"]["11"]["attempts"][-1]
    _write_daemon_state(
        env,
        11,
        att["identity_hash"],
        state="INTELLIGENCE_DISPATCHING",
        last_transient_error="[click](https://evil.example) *x* !",
        last_transient_error_reason={"r": "[a](b)"},
        last_transient_error_at="[t](u)",
    )
    night = _dispatch(env, "2026-10-17T00:35:00")
    section = env["app"].report(night).split("Transient errors", 1)[1]
    assert "- #11: clickhttps:evil.example" in section
    for bad in ("[", "]", "](", "*", "!", "`"):
        assert bad not in section


def test_a_single_transient_error_at_the_cap_keeps_the_cap_reason(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    att = night["issues"]["11"]["attempts"][-1]
    _transient(env, att, "2026-10-17T00:31:00.000+00:00")
    night = _dispatch(env, "2026-10-17T03:01:00")
    reason = night["issues"]["11"]["attempts"][0]["reason"]
    assert reason == "ISSUE_CAP_EXCEEDED:INTELLIGENCE_DISPATCHING:TRANSIENT:SOURCE_LINEAGE_FAILED"


def test_report_has_no_transient_section_without_transient_errors(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    assert "Transient errors" not in env["app"].report(night)


def test_finalized_report_shows_the_final_night_status(env) -> None:
    _started(env)
    env["clock"].at = dt.datetime.fromisoformat("2026-10-17T07:30:00")
    night = env["app"].stop()
    assert night["status"] == "FINISHED"
    report = Path(night["finalized"]["report"]).read_text()
    assert "- Night status: FINISHED" in report and "RUNNING" not in report


def test_cross_night_cap_keeps_a_matching_block_the_scheduler_did_not_write(env) -> None:
    written = _own_contract_body(task_body(), 11)
    revised = _own_contract_body(task_body(), 11, attempt=2)  # same shape, other bytes
    _capped_ledger(env, i11=[_sha(written)], i12=[])
    env["gh"].add_issue(11, revised)
    human = _own_contract_body(task_body(), 12)  # a trusted author's own matching block
    env["gh"].add_issue(12, human)
    env["app"].prepare()
    assert "eia:escalate" in env["gh"].issues[11]["labels"]
    assert env["gh"].issues[11]["body"] == revised
    assert env["gh"].issues[12]["body"] == human
    assert not [w for w in env["gh"].writes if "--body-file" in w and w[:2] == ["issue", "edit"]]


def _change_body_on_view(env, issue: int, view_number: int, new_body: str) -> None:
    """From the moment ``eia:escalate`` is added, the ``view_number``-th ``issue view`` of
    ``issue`` sees a body a human just changed."""
    real = env["sys"].gh
    seen = {"views": 0}

    def gh(argv):
        args = argv[1:]
        escalated = "eia:escalate" in real.issues[issue]["labels"]
        if escalated and args[:3] == ["issue", "view", str(issue)]:
            seen["views"] += 1
            if seen["views"] == view_number:
                real.issues[issue]["body"] = new_body
        return real(argv)

    env["sys"].gh = gh


def test_escalation_restore_skips_a_body_changed_right_before_the_edit(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    att = night["issues"]["11"]["attempts"][-1]
    human = env["gh"].issues[11]["body"].replace("Original problem", "Human problem")
    _change_body_on_view(env, 11, 2, human)  # the read-back right before the edit
    _write_daemon_state(env, 11, att["identity_hash"], state="UNIT_REPAIR_REQUIRED")
    night = _dispatch(env, "2026-10-17T01:00:00")
    entry = night["issues"]["11"]
    assert entry["status"] == "ESCALATED"
    assert entry["body_restore"] == "SKIPPED:CHANGED_BEFORE_EDIT"
    assert env["gh"].issues[11]["body"] == human


def test_cross_night_restore_skips_a_body_changed_right_before_the_edit(env) -> None:
    ours = _own_contract_body(task_body(), 11)
    _capped_ledger(env, i11=[_sha(ours)])
    env["gh"].add_issue(11, ours)
    human = ours.replace("Original problem", "Human problem")
    _change_body_on_view(env, 11, 1, human)
    env["app"].prepare()
    assert env["gh"].issues[11]["body"] == human
    assert not [w for w in env["gh"].writes if "--body-file" in w and w[:2] == ["issue", "edit"]]


def test_trust_failure_escalation_never_edits_the_body(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    armed_body = env["gh"].issues[11]["body"]
    att = night["issues"]["11"]["attempts"][-1]
    env["gh"].issues[11]["edits"].append({  # edited and put back to the same bytes
        "editedAt": "2026-10-17T00:40:00Z",
        "editor": {"login": "mallory", "__typename": "User"},
    })
    _write_daemon_state(env, 11, att["identity_hash"], state="UNIT_REPAIR_REQUIRED")
    writes = len(env["gh"].writes)
    night = _dispatch(env, "2026-10-17T01:00:00")
    entry = night["issues"]["11"]
    assert entry["escalation"]["reason"].startswith("UNTRUSTED_AFTER_ARMING:")
    assert entry["body_restore"] == "SKIPPED:TRUST_FAILURE"
    assert env["gh"].issues[11]["body"] == armed_body
    assert not [w for w in env["gh"].writes[writes:] if "--body-file" in w and w[1] == "edit"]


def test_untrusted_issue_is_not_restored_even_on_a_model_escalation(env) -> None:
    _started(env)
    _dispatch(env, "2026-10-17T00:30:00")
    armed_body = env["gh"].issues[11]["body"]
    env["gh"].issues[11]["edits"].append({
        "editedAt": "2026-10-17T00:40:00Z",
        "editor": {"login": "mallory", "__typename": "User"},
    })
    env["gh"].issues[11]["title"] = "Changed title"  # guard escalates, trust not consulted
    night = _dispatch(env, "2026-10-17T00:45:00")
    entry = night["issues"]["11"]
    assert entry["escalation"]["reason"] == "ISSUE_CHANGED_AFTER_ARMING"
    assert entry["body_restore"].startswith("SKIPPED:UNTRUSTED:")
    assert env["gh"].issues[11]["body"] == armed_body


def test_finalize_records_written_body_shas_in_the_ledger(env) -> None:
    _started(env)
    night = _dispatch(env, "2026-10-17T00:30:00")
    att = night["issues"]["11"]["attempts"][-1]
    assert att["body_sha256"] == _sha(env["gh"].issues[11]["body"])
    _write_daemon_state(env, 11, att["identity_hash"], state="UNIT_REPAIR_REQUIRED")
    _dispatch(env, "2026-10-17T01:00:00")
    env["clock"].at = dt.datetime.fromisoformat("2026-10-17T07:30:00")
    env["app"].stop()
    ledger = json.loads((env["tmp"] / "nightly" / "issues.json").read_text())
    assert att["body_sha256"] in ledger["11"]["body_sha256"]
