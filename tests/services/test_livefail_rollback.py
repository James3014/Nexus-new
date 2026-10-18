"""RED contract for the LIVE_FAILED fast rollback (#2532; #2453 pilot, James 2026-10-18)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.services.livefail_rollback import (
    HOLD_PREFIX,
    evaluate_trigger,
    gateway_hold_plan,
    hold_text,
    is_gateway_class,
    release_allowed,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts" / "governance" / "livefail_rollback.py"
MERGE = "b" * 40
LIVE = "c" * 40
NOW = "2026-10-18T12:00:00Z"
T = "2026-10-18T10:00:00Z"
BOT = "james3014-nexus-agent[bot]"


def block(**over) -> str:
    data = {
        "origin_pr": 77,
        "merge_sha": MERGE,
        "live_commit": LIVE,
        "confirmer": "workspace-4e/independent-agent",
        "witness": "https://github.com/x/y/issues/1#issuecomment-1",
        "reason": "entry ran and errored",
        **over,
    }
    return f"Independent confirmation: FAILED\n<!-- NEXUS_LIVE_FAILED_V1\n{json.dumps(data)}\nNEXUS_LIVE_FAILED_V1 -->"


def comment(body: str, author: str = BOT, assoc: str = "CONTRIBUTOR", updated: str = T) -> dict:
    return {
        "body": body,
        "author": author,
        "author_association": assoc,
        "created_at": T,
        "updated_at": updated,
    }


def prs(author: str = "someone", sessions=("author-session",), merge: str | None = MERGE) -> dict:
    return {
        77: {
            "merge_sha": merge,
            "merged_at": T,
            "author": author,
            "author_sessions": list(sessions),
        }
    }


def contains_yes(a: str, c: str) -> bool:
    return True


def ev(comments, origin=None, contains=contains_yes, **kw) -> dict:
    return evaluate_trigger(
        comments=comments,
        origin_prs=prs() if origin is None else origin,
        now=NOW,
        contains=contains,
        trusted_logins=["James3014", BOT],
        shared_logins=[BOT],
        **kw,
    )


# --- who can trigger ---------------------------------------------------------------


def test_independent_confirmer_block_triggers():
    out = ev([comment(block())])
    assert out["triggered"] is True
    trig = out["trigger"]
    assert trig["origin_prs"] == [77] and trig["merge_shas"] == [MERGE]
    assert trig["judged_at"] == T and trig["live_commit"] == LIVE


def test_untrusted_commenter_cannot_trigger():
    out = ev([comment(block(), author="random-user", assoc="NONE")])
    assert out["triggered"] is False
    assert out["ignored"][0]["reason"] == "UNTRUSTED_COMMENT_AUTHOR"


def test_label_alone_does_not_trigger():
    out = ev([], labels=["nexus:live-failed"])
    assert out["triggered"] is False
    assert out["reason_codes"] == ["LABEL_WITHOUT_VALID_CONFIRMATION"]


@pytest.mark.parametrize(
    "confirmer", ["author-session", "AUTHOR-SESSION", "someone", "author-session/independent-agent"]
)
def test_author_cannot_be_the_confirmer(confirmer):
    out = ev([comment(block(confirmer=confirmer))])
    assert out["triggered"] is False
    assert out["ignored"][0]["reason"] == "CONFIRMER_NOT_INDEPENDENT"


def test_pilot_owner_pr_needs_another_confirmer():
    out = ev([comment(block())], origin=prs(sessions=("workspace-4e",)))
    assert out["ignored"][0]["reason"] == "CONFIRMER_NOT_INDEPENDENT"


def test_pr_author_login_posting_is_not_independent_unless_shared():
    out = ev([comment(block(), author="someone", assoc="COLLABORATOR")])
    assert out["ignored"][0]["reason"] == "CONFIRMER_NOT_INDEPENDENT"
    shared = ev([comment(block())], origin=prs(author=BOT))
    assert shared["triggered"] is True


def test_unknown_author_session_fails_closed():
    out = ev([comment(block())], origin=prs(sessions=()))
    assert out["ignored"][0]["reason"] == "AUTHOR_SESSION_UNKNOWN"


def test_edited_comment_is_ignored():
    out = ev([comment(block(), updated="2026-10-18T11:00:00Z")])
    assert out["ignored"][0]["reason"] == "COMMENT_EDITED_AFTER_POSTING"


def test_merge_sha_must_match_github_and_be_in_live_commit():
    assert ev([comment(block(merge_sha="e" * 40))])["ignored"][0]["reason"] == "MERGE_SHA_MISMATCH"
    out = ev([comment(block())], contains=lambda a, c: False)
    assert out["ignored"][0]["reason"] == "MERGE_NOT_IN_LIVE_COMMIT"
    assert ev([comment(block())], origin=prs(merge=None))["ignored"][0]["reason"] == (
        "ORIGIN_PR_NOT_MERGED_OR_UNKNOWN"
    )


@pytest.mark.parametrize(
    "bad",
    [
        '{"origin_pr": 77}',
        "not json",
        json.dumps({
            "origin_pr": "77",
            "merge_sha": MERGE,
            "live_commit": LIVE,
            "confirmer": "x",
            "witness": "w",
            "reason": "r",
        }),
    ],
)
def test_malformed_block_is_ignored(bad):
    body = f"<!-- NEXUS_LIVE_FAILED_V1\n{bad}\nNEXUS_LIVE_FAILED_V1 -->"
    out = ev([comment(body)])
    assert out["triggered"] is False and out["ignored"][0]["reason"] == "BLOCK_MALFORMED"


def _report(verdict, status="FAILED", ignored=False):
    row = {"promise_id": "P1", "status": status, "confirmer_verdict": None}
    if verdict:
        row["confirmer_verdict"] = {"verdict": verdict, "ignored": ignored, "confirmer": "judge"}
    return {"recommendation": "LIVE_FAILED", "promises": [row]}


def test_promise_live_failed_from_author_witness_only_does_not_trigger():
    out = ev([], promise_report=_report(None), promise_judged_at=T, promise_prs=[77])
    assert out["triggered"] is False
    assert out["ignored"][0]["reason"] == "NO_INDEPENDENT_CONFIRMER"


def test_promise_live_failed_with_ignored_confirmer_does_not_trigger():
    out = ev(
        [], promise_report=_report("REJECT", ignored=True), promise_judged_at=T, promise_prs=[77]
    )
    assert out["triggered"] is False


@pytest.mark.parametrize("verdict,status", [("REJECT", "UNCOVERED"), ("ACCEPT", "FAILED")])
def test_promise_live_failed_with_independent_confirmer_triggers(verdict, status):
    out = ev([], promise_report=_report(verdict, status), promise_judged_at=T, promise_prs=[77])
    assert out["triggered"] is True
    assert out["trigger"]["source"] == "PROMISE_CONFIRMATION"


def test_promise_provisional_never_triggers():
    rep = {**_report("REJECT"), "recommendation": "PROVISIONAL"}
    assert ev([], promise_report=rep, promise_judged_at=T, promise_prs=[77])["triggered"] is False


# --- Gateway (workspace-86 conditions) ---------------------------------------------


def _plan(live: bool, status="IN_SYNC", hold=False, env=False):
    return gateway_hold_plan(
        merge_shas=[MERGE],
        status={"status": status, "live_commit": LIVE},
        hold_present=hold,
        hold_env=env,
        contains=lambda a, c: live,
        last_receipt={"previous_commit": "f" * 40, "previous_root": "/x/a1-fff"},
    )


def test_gateway_not_live_yet_plans_hold():
    assert _plan(False)["action"] == "HOLD"


def test_gateway_already_live_never_holds_and_names_previous_deploy():
    plan = _plan(True)
    assert plan["action"] == "RECOMMEND_FAST_REVERT"
    assert plan["previous_commit"] == "f" * 40 and plan["previous_root"] == "/x/a1-fff"


@pytest.mark.parametrize(
    "kw,reason",
    [
        ({"hold": True}, "HOLD_ALREADY_PRESENT"),
        ({"env": True}, "HOLD_ENV_SET"),
        ({"status": "ERROR"}, "DEPLOYER_STATUS_ERROR"),
        ({"status": "BACKOFF"}, "DEPLOYER_STATUS_BACKOFF"),
    ],
)
def test_gateway_no_hold_when_unsafe(kw, reason):
    plan = _plan(False, **kw)
    assert plan["action"] == "NONE" and plan["reason"] == reason


def test_gateway_unreadable_status_or_ancestry_means_no_hold():
    assert (
        gateway_hold_plan(
            merge_shas=[MERGE],
            status=None,
            hold_present=False,
            hold_env=False,
            contains=contains_yes,
        )["reason"]
        == "DEPLOYER_STATUS_UNREADABLE"
    )
    assert (
        gateway_hold_plan(
            merge_shas=[MERGE],
            status={"status": "IN_SYNC", "live_commit": LIVE},
            hold_present=False,
            hold_env=False,
            contains=lambda a, c: None,
        )["reason"]
        == "LIVE_ANCESTRY_UNKNOWN"
    )


def test_gateway_class():
    assert is_gateway_class(["gateway"], ["docs/x.md"]) is True
    assert is_gateway_class(["cli"], ["nexus/x.py"]) is False
    assert is_gateway_class([None], ["nexus/x.py"]) is True
    assert is_gateway_class([None], ["docs/a.md", "tests/t.py", "README.md"]) is False


def test_release_only_own_unchanged_recent_hold_after_merge():
    text = hold_text(5, [77], [MERGE], "2026-10-18T10:00:00Z")
    assert text.startswith(HOLD_PREFIX) and text.endswith("\n")
    ok = lambda **kw: release_allowed(  # noqa: E731
        **{"current_text": text, "written_text": text, "revert_merged": True, "now": NOW, **kw}
    )
    assert ok() == (True, "RELEASE")
    assert ok(current_text=None)[1] == "HOLD_ABSENT"
    assert ok(current_text=text.rstrip("\n"))[1] == "HOLD_TEXT_CHANGED"
    assert ok(current_text="auto-hold: RECONCILE_FAILED x")[1] == "HOLD_TEXT_CHANGED"
    assert ok(current_text="manual hold")[1] == "HOLD_TEXT_CHANGED"
    assert ok(revert_merged=False)[1] == "REVERT_NOT_MERGED"
    assert ok(now="2026-10-18T16:00:01Z")[1] == "HOLD_OLDER_THAN_6H_ASK_WORKSPACE_86"
    assert ok(now="2026-10-18T09:59:59Z")[1] == "HOLD_CREATED_IN_FUTURE"


# --- CLI on a real temporary git repository -----------------------------------------


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _commit(repo: Path, path: str, text: str, msg: str) -> str:
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text)
    _git(repo, "add", path)
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _commit(r, "nexus/a.py", "a = 1\n", "base")
    _commit(r, "nexus/b.py", "b = 1\n", "other")
    return r


def _cli(tmp_path: Path, repo: Path, merge: str, *extra: str, origin_extra=None) -> dict:
    data = {
        "now": NOW,
        "labels": ["nexus:live-failed"],
        "comments": [comment(block(merge_sha=merge, live_commit=_git(repo, "rev-parse", "HEAD")))],
        "origin_prs": {"77": {**prs(merge=merge)[77], **(origin_extra or {})}},
    }
    inp = tmp_path / "in.json"
    inp.write_text(json.dumps(data))
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "PYTHONPATH": os.pathsep.join([
            str(REPO_ROOT),
            *([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else []),
        ]),
    }
    (tmp_path / "home").mkdir(exist_ok=True)
    state = tmp_path / "deploy"
    state.mkdir(exist_ok=True)
    out = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--issue",
            "5",
            "--offline-input",
            str(inp),
            "--repo-dir",
            str(repo),
            "--main-ref",
            "main",
            "--no-fetch",
            "--deploy-state",
            str(state),
            *extra,
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_cli_clean_revert_is_planned_with_dependents_and_leaves_no_worktree(tmp_path, repo):
    lines = [f"x{i} = {i}" for i in range(12)]
    _commit(repo, "nexus/a.py", "\n".join(lines) + "\n", "widen a")
    bad = _commit(repo, "nexus/a.py", "\n".join(["x0 = 99", *lines[1:]]) + "\n", "feat: a (#77)")
    _commit(repo, "nexus/c.py", "c = 1\n", "feat: c (#78)")
    later = ["x0 = 99", *lines[1:-1], "x11 = 100"]
    _commit(repo, "nexus/a.py", "\n".join(later) + "\n", "fix: touch a again (#79)")
    res = _cli(tmp_path, repo, bad)
    assert res["outcome"] == "DRY_RUN_CLEAN"
    assert res["plan"]["status"] == "CLEAN"
    assert [d["pr"] for d in res["plan"]["dependents"]] == [79]
    assert _git(repo, "worktree", "list").count("\n") == 0
    assert _git(repo, "status", "--porcelain") == ""


def test_cli_conflicting_revert_only_gives_manual_advice(tmp_path, repo):
    bad = _commit(repo, "nexus/a.py", "a = 2\n", "feat: change a (#77)")
    _commit(repo, "nexus/a.py", "a = 3\n", "fix: later change a (#80)")
    res = _cli(tmp_path, repo, bad)
    assert res["outcome"] == "DRY_RUN_MANUAL"
    assert res["plan"]["reason"] == "REVERT_CONFLICT"
    assert res["plan"]["conflicts"] == ["nexus/a.py"]
    assert [d["pr"] for d in res["plan"]["dependents"]] == [80]
    assert _git(repo, "worktree", "list").count("\n") == 0


def test_cli_already_reverted_is_manual(tmp_path, repo):
    bad = _commit(repo, "nexus/a.py", "a = 2\n", "feat: change a (#77)")
    _git(repo, "revert", "--no-edit", bad)
    res = _cli(tmp_path, repo, bad)
    assert res["plan"]["reason"].startswith("ALREADY_REVERTED")


def test_cli_untrusted_block_does_nothing(tmp_path, repo):
    bad = _commit(repo, "nexus/a.py", "a = 2\n", "feat: change a (#77)")
    res = _cli(tmp_path, repo, bad, origin_extra={"author_sessions": ["workspace-4e"]})
    assert res["outcome"] == "NOT_TRIGGERED"
    assert "plan" not in res


def _deploy_state(tmp_path: Path, live: str, hold: str | None = None) -> Path:
    state = tmp_path / "deploy"
    state.mkdir(exist_ok=True)
    (state / "status.json").write_text(json.dumps({"status": "IN_SYNC", "live_commit": live}))
    (state / "receipts.jsonl").write_text(
        json.dumps({"previous_commit": live, "previous_root": "/x"}) + "\n"
    )
    if hold is not None:
        (state / "HOLD").write_text(hold)
    return state


def test_cli_gateway_hold_written_only_with_flag_and_not_live(tmp_path, repo):
    live = _git(repo, "rev-parse", "HEAD")
    bad = _commit(repo, "nexus/a.py", "a = 2\n", "feat: change a (#77)")
    state = _deploy_state(tmp_path, live)
    dry = _cli(tmp_path, repo, bad)
    assert dry["gateway"]["action"] == "HOLD" and not (state / "HOLD").exists()
    alone = _cli(tmp_path, repo, bad, "--apply-hold")
    assert not (state / "HOLD").exists() and "applied" not in alone["gateway"]
    res = _cli(tmp_path, repo, bad, "--apply-hold", "--apply")
    assert res["gateway"]["applied"] is True
    text = (state / "HOLD").read_text()
    assert text.startswith(HOLD_PREFIX) and "#77" in text
    events = (tmp_path / "home/.local/state/nexus-livefail-rollback/events.jsonl").read_text()
    assert json.loads(events.splitlines()[-1])["gateway_action_at"]


def test_cli_never_overwrites_someone_elses_hold(tmp_path, repo):
    live = _git(repo, "rev-parse", "HEAD")
    bad = _commit(repo, "nexus/a.py", "a = 2\n", "feat: change a (#77)")
    state = _deploy_state(tmp_path, live, hold="manual hold by 86\n")
    res = _cli(tmp_path, repo, bad, "--apply-hold")
    assert res["gateway"]["action"] == "NONE"
    assert res["gateway"]["reason"] == "HOLD_ALREADY_PRESENT"
    assert (state / "HOLD").read_text() == "manual hold by 86\n"


def test_cli_merge_already_live_does_not_hold(tmp_path, repo):
    bad = _commit(repo, "nexus/a.py", "a = 2\n", "feat: change a (#77)")
    state = _deploy_state(tmp_path, bad)
    res = _cli(tmp_path, repo, bad, "--apply-hold")
    assert res["gateway"]["action"] == "RECOMMEND_FAST_REVERT"
    assert not (state / "HOLD").exists()


def test_cli_non_gateway_surface_has_no_gateway_plan(tmp_path, repo):
    live = _git(repo, "rev-parse", "HEAD")
    bad = _commit(repo, "nexus/a.py", "a = 2\n", "feat: change a (#77)")
    _deploy_state(tmp_path, live)
    res = _cli(tmp_path, repo, bad, origin_extra={"witness": {"surface": "cli"}})
    assert res["gateway"] is None


# --- --apply path with a fake gh and a local origin ----------------------------------

FAKE_GH = r"""#!/usr/bin/env python3
import json, os, sys
data = json.load(open(os.environ["FAKE_GH_DATA"]))
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write(json.dumps(args) + "\n")
if args[:2] == ["pr", "create"]:
    body = open(args[args.index("--body-file") + 1]).read()
    with open(os.environ["FAKE_GH_LOG"] + ".body", "w") as fh:
        fh.write(body)
    print("https://github.com/James3014/Nexus-new/pull/900")
    sys.exit(0)
if args[:2] == ["issue", "comment"]:
    sys.exit(0)
path = [a for a in args if a.startswith("repos/")][0]
if path.endswith("/comments?per_page=100"):
    print(json.dumps([data["comments"]]))
elif "/pulls?" in path:
    print(json.dumps(data.get("head_prs", [])))
elif "/pulls/" in path:
    print(json.dumps(data["pulls"][path.rsplit("/", 1)[1]]))
else:
    print(json.dumps(data["issue"]))
"""


def _online(tmp_path: Path, repo: Path, bad: str, *extra: str, head_prs=None, extra_comments=()):
    bare = tmp_path / "origin.git"
    if not bare.exists():
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        _git(repo, "remote", "add", "origin", str(bare))
    gh = tmp_path / "fake-gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    data = {
        "issue": {"labels": [{"name": "nexus:live-failed"}], "body": ""},
        "comments": [
            {
                **comment(block(merge_sha=bad, live_commit=bad)),
                "user": {"login": BOT},
                "html_url": "u",
            },
            *[{**c, "user": {"login": c["author"]}} for c in extra_comments],
        ],
        "pulls": {
            "77": {
                "number": 77,
                "title": "feat",
                "merge_commit_sha": bad,
                "merged_at": T,
                "user": {"login": BOT},
                "body": "<!-- NEXUS_AUTHOR_SESSION_V1: author-session -->",
                "html_url": "p",
            }
        },
        "head_prs": head_prs or [],
    }
    (tmp_path / "gh.json").write_text(json.dumps(data))
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {
        **os.environ,
        "HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "FAKE_GH_DATA": str(tmp_path / "gh.json"),
        "FAKE_GH_LOG": str(tmp_path / "gh.log"),
        "PYTHONPATH": os.pathsep.join([
            str(REPO_ROOT),
            *([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else []),
        ]),
    }
    out = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--issue",
            "5",
            "--repo-dir",
            str(repo),
            "--main-ref",
            "main",
            "--no-fetch",
            "--deploy-state",
            str(tmp_path / "deploy"),
            "--gh-read",
            str(gh),
            "--gh-write",
            str(gh),
            "--now",
            NOW,
            *extra,
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    return out, bare, home


def test_cli_apply_opens_draft_revert_pr_with_keep_open_body(tmp_path, repo):
    bad = _commit(repo, "nexus/a.py", "a = 2\n", "feat: change a (#77)")
    (tmp_path / "deploy").mkdir()
    out, bare, home = _online(tmp_path, repo, bad, "--apply")
    assert out.returncode == 0, out.stderr
    res = json.loads(out.stdout)
    assert res["outcome"] == "REVERT_PR_OPENED"
    branch = "livefail/revert-issue-5-pr-77"
    msg = _git(bare, "log", "-1", "--format=%B", branch)
    assert f"This reverts commit {bad}." in msg and "Refs #5" in msg
    assert "close" not in msg.lower() and "fix #" not in msg.lower()
    assert _git(bare, "show", f"{branch}:nexus/a.py") == "a = 1"
    calls = [json.loads(x) for x in (tmp_path / "gh.log").read_text().splitlines()]
    create = next(c for c in calls if c[:2] == ["pr", "create"])
    assert "--draft" in create
    body = (tmp_path / "gh.log.body").read_text()
    assert '"on_merge": "KEEP_OPEN"' in body and "<!-- NEXUS_CORE_ISSUE: 5 -->" in body
    assert "Closes" not in body
    event = json.loads(
        (home / ".local/state/nexus-livefail-rollback/events.jsonl").read_text().splitlines()[-1]
    )
    assert event["origin_pr"] == [77] and event["judged_at"] == T
    assert event["revert_pr_opened_at"] and event["minutes_to_revert_pr"] is not None
    assert _git(repo, "branch", "--list", branch) == ""


def test_cli_apply_is_idempotent_when_revert_pr_exists(tmp_path, repo):
    bad = _commit(repo, "nexus/a.py", "a = 2\n", "feat: change a (#77)")
    (tmp_path / "deploy").mkdir()
    out, _, _ = _online(tmp_path, repo, bad, "--apply", head_prs=[{"html_url": "x"}])
    assert json.loads(out.stdout)["outcome"] == "REVERT_PR_EXISTS"


def test_cli_apply_conflict_posts_manual_advice_only(tmp_path, repo):
    bad = _commit(repo, "nexus/a.py", "a = 2\n", "feat: change a (#77)")
    _commit(repo, "nexus/a.py", "a = 3\n", "S5 split follows (#81)")
    (tmp_path / "deploy").mkdir()
    out, bare, _ = _online(tmp_path, repo, bad, "--apply")
    assert json.loads(out.stdout)["outcome"] == "MANUAL_ADVICE_POSTED"
    calls = [json.loads(x) for x in (tmp_path / "gh.log").read_text().splitlines()]
    assert not any(c[:2] == ["pr", "create"] for c in calls)
    advice = next(c for c in calls if c[:2] == ["issue", "comment"])
    assert "REVERT_CONFLICT" in advice[advice.index("--body") + 1]
    assert "#81" in advice[advice.index("--body") + 1]
    assert _git(bare, "branch", "--list") == ""


def test_cli_release_hold_only_own_text_after_merge(tmp_path, repo):
    live = _git(repo, "rev-parse", "HEAD")
    bad = _commit(repo, "nexus/a.py", "a = 2\n", "feat: change a (#77)")
    state = _deploy_state(tmp_path, live)
    out, _, _ = _online(tmp_path, repo, bad, "--apply-hold", "--apply")
    assert json.loads(out.stdout)["gateway"]["applied"] is True, out.stderr
    written = (state / "HOLD").read_text()
    # revert not merged yet -> kept
    out, _, _ = _online(tmp_path, repo, bad, "--release-hold")
    assert json.loads(out.stdout) == {"released": False, "reason": "REVERT_NOT_MERGED"}
    # someone edited the HOLD -> kept
    (state / "HOLD").write_text(written + "86 says keep\n")
    merged = [{"merged_at": T, "html_url": "x"}]
    out, _, _ = _online(tmp_path, repo, bad, "--release-hold", head_prs=merged)
    assert json.loads(out.stdout)["reason"] == "HOLD_TEXT_CHANGED"
    assert (state / "HOLD").exists()
    # own text, merged -> released
    (state / "HOLD").write_text(written)
    out, _, _ = _online(tmp_path, repo, bad, "--release-hold", head_prs=merged)
    assert json.loads(out.stdout) == {"released": True, "reason": "RELEASE"}
    assert not (state / "HOLD").exists()


def test_cli_author_session_flag_supplies_missing_marker(tmp_path, repo):
    bad = _commit(repo, "nexus/a.py", "a = 2\n", "feat: change a (#77)")
    res = _cli(tmp_path, repo, bad, origin_extra={"author_sessions": []})
    assert res["outcome"] == "NOT_TRIGGERED"
    res = _cli(
        tmp_path, repo, bad, "--author-session", "rie-live", origin_extra={"author_sessions": []}
    )
    assert res["verdict"]["triggered"] is True
    res = _cli(
        tmp_path,
        repo,
        bad,
        "--author-session",
        "workspace-4e",
        origin_extra={"author_sessions": []},
    )
    assert res["verdict"]["ignored"][0]["reason"] == "CONFIRMER_NOT_INDEPENDENT"


def test_defuse_closing_keywords_in_copied_text():
    sys.path.insert(0, str(CLI.parent))
    try:
        import livefail_rollback as cli  # type: ignore[import-not-found]
    finally:
        sys.path.remove(str(CLI.parent))
    text = "fix #12, Closes: #13, resolved owner/repo#14, fixes  #15, see #16, prefix #17"
    out = cli.defuse_closing_keywords(text)
    for n in ("#12", "#13", "repo#14", "#15"):
        assert n not in out
    assert "see #16" in out and "prefix #17" in out


def test_cli_apply_body_never_closes_issues_named_in_dependent_subjects(tmp_path, repo):
    lines = [f"x{i} = {i}" for i in range(12)]
    _commit(repo, "nexus/a.py", "\n".join(lines) + "\n", "widen a")
    bad = _commit(repo, "nexus/a.py", "\n".join(["x0 = 9", *lines[1:]]) + "\n", "feat (#77)")
    later = ["x0 = 9", *lines[1:-1], "x11 = 0"]
    _commit(repo, "nexus/a.py", "\n".join(later) + "\n", "fix #4242 crash (#79)")
    (tmp_path / "deploy").mkdir()
    out, _, _ = _online(tmp_path, repo, bad, "--apply")
    assert json.loads(out.stdout)["outcome"] == "REVERT_PR_OPENED", out.stderr
    body = (tmp_path / "gh.log.body").read_text()
    assert "4242" in body and "fix #4242" not in body.lower()


def test_cli_hold_file_is_owner_only(tmp_path, repo):
    live = _git(repo, "rev-parse", "HEAD")
    bad = _commit(repo, "nexus/a.py", "a = 2\n", "feat: change a (#77)")
    state = _deploy_state(tmp_path, live)
    _cli(tmp_path, repo, bad, "--apply-hold", "--apply")
    assert (state / "HOLD").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "confirmer",
    [
        "someone/worker",
        "x/author-session",
        "/author-session",
        "author-session\\sub",
        "a b",
        "a/b/c",
    ],
)
def test_confirmer_segment_and_format_tricks_do_not_trigger(confirmer):
    out = ev([comment(block(confirmer=confirmer))])
    assert out["triggered"] is False


def test_future_promise_judged_at_does_not_trigger():
    out = ev(
        [],
        promise_report=_report("REJECT"),
        promise_judged_at="2026-10-19T00:00:00Z",
        promise_prs=[77],
    )
    assert out["triggered"] is False


def test_cli_hold_without_clean_revert_is_not_written(tmp_path, repo):
    live = _git(repo, "rev-parse", "HEAD")
    bad = _commit(repo, "nexus/a.py", "a = 2\n", "feat: change a (#77)")
    _commit(repo, "nexus/a.py", "a = 3\n", "later (#80)")
    state = _deploy_state(tmp_path, live)
    res = _cli(tmp_path, repo, bad, "--apply-hold", "--apply")
    assert res["plan"]["status"] == "MANUAL" and not (state / "HOLD").exists()


def test_cli_untrusted_block_pr_is_never_fetched(tmp_path, repo):
    bad = _commit(repo, "nexus/a.py", "a = 2\n", "feat: change a (#77)")
    (tmp_path / "deploy").mkdir()
    data_hook = {"comments_extra": [comment(block(origin_pr=999999), author="x", assoc="NONE")]}
    out, _, _ = _online(tmp_path, repo, bad, extra_comments=data_hook["comments_extra"])
    assert out.returncode == 0, out.stderr
    calls = (tmp_path / "gh.log").read_text()
    assert "pulls/999999" not in calls
