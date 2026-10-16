"""Unit tests for scripts/ops/eia_nightly.py.

gh, launchctl, ssh, osascript and network git (push / ls-remote / fetch) are faked; local git
runs for real in a temporary repository so the daemon's own validators see real blobs.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from nexus.services.external_intelligence_automation import IssueWorkItem, parse_issue_contract
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

    def add_issue(self, number: int, body: str, labels=("eia:queue",), title: str = "Fix it"):
        self.issues[number] = {
            "number": number,
            "title": title,
            "body": body,
            "labels": set(labels),
            "state": "OPEN",
            "comments": [],
        }

    def _issue_json(self, issue: dict[str, Any]) -> dict[str, Any]:
        return {**issue, "labels": [{"name": n} for n in sorted(issue["labels"])], "comments": None}

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
        if args[0] == "api":
            number = int(args[2].split("/")[-2])
            return _cp(argv, out="\n".join(self.issues[number]["comments"]))
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

    def __call__(self, argv: list[str], **kw: Any) -> subprocess.CompletedProcess:
        self.calls.append(list(argv))
        if argv[0] == GH:
            return self.gh(argv)
        if argv[0] == "git" and ("push" in argv or "ls-remote" in argv or "fetch" in argv):
            if "push" in argv:
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
            return _cp(argv)
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
        "verification": ["python -m pytest -q tests/test_mod.py"],
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
    assert task["verifier_tails"] == [["-m", "pytest", "-q", "tests/test_mod.py"]]
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
        (task_body(allowed_files=["tasks/x.md"]), "TASK_ALLOWED_FILES_INVALID"),
        (task_body(verification=["pytest -q"]), "TASK_VERIFICATION_MUST_USE_PYTHON"),
        (task_body(verification=["python -c '`x`'"]), "TASK_VERIFICATION_INVALID"),
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
    assert str(env["repo"] / ".venv/bin/python") + " -m pytest -q tests/test_mod.py" in card
    (msg,) = env["sys"].coord()
    assert "msg merge-queue" in msg and f"Nexus-new#{pr['number']}" in msg and commit in msg
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


def _complete(env, entry: dict[str, Any], *, path: str = "pkg/mod.py") -> str:
    repo, att = env["repo"], entry["attempts"][-1]
    wt = env["tmp"] / "cand"
    _git(repo, "worktree", "add", "-q", "--detach", str(wt), att["main_sha"])
    (wt / path).parent.mkdir(parents=True, exist_ok=True)
    (wt / path).write_text("X = 2\n")
    _git(wt, "add", "-A")
    _git(wt, "-c", "user.name=t", "-c", "user.email=t@e.invalid", "commit", "-qm", "candidate")
    sha = _git(wt, "rev-parse", "HEAD")
    packet = env["eia_state"] / "closure" / "packet.json"
    packet.parent.mkdir(parents=True, exist_ok=True)
    packet.write_text(
        json.dumps({
            "task_candidate": {"candidate_commit": sha},
            "task_card_hash": entry["card_hash"],
        })
    )
    _write_daemon_state(
        env,
        11,
        att["identity_hash"],
        state="COMPLETE",
        closure_run_id="run-1",
        publication={
            "candidate_commit": sha,
            "candidate_tree": "t",
            "task_id": entry["task_id"],
            "verification_state": "WHOLE_TASK_PASS",
            "acceptance_packet_ref": str(packet),
            "acceptance_packet_sha256": hashlib.sha256(packet.read_bytes()).hexdigest(),
        },
        publication_record={"state": "COMPLETED"},
        worker_binding={"provider": "opencli_chatgpt", "model": "advanced"},
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
        "msg merge-queue" in m and f"Nexus-new#{pr['number']} head {sha}" in m
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
    with pytest.raises(en.NightlyError, match="GH_WRITE_FAILED"):
        _dispatch(env, "2026-10-17T01:30:00")
    night = env["app"].load(NIGHT)
    assert night["issues"]["11"]["status"] == "ARMED"
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
    with pytest.raises(en.NightlyError):
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
