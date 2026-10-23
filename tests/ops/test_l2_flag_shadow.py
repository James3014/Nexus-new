"""Shadow CLI tests (Refs #2752): local git repo, fake ghc, no network."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.ops import l2_flag_shadow as shadow

ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def _git(repo: Path, *args: str, date: str | None = None) -> str:
    env = dict(ENV)
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=env
    ).stdout.strip()


@pytest.fixture()
def clone(tmp_path: Path) -> Path:
    """origin (bare) + clone `work`; main history: base, PR #10 (changes API + line), later fix, unrelated."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    work = tmp_path / "root" / "James3014__Nexus-new"
    work.parent.mkdir(exist_ok=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
    (work / "pkg").mkdir()
    (work / "pkg/mod.py").write_text(
        "def alpha(a):\n    return a\n\n\ndef beta(b):\n    return b\n"
    )
    (work / "other.py").write_text("X = 1\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "base", date="2026-10-01T00:00:00+00:00")
    (work / "pkg/mod.py").write_text(
        "def alpha(a, extra):\n    return a\n\n\ndef beta(b):\n    return b + 1\n"
    )
    _git(work, "commit", "-qam", "feat: tweak (#10)", date="2026-10-02T00:00:00+00:00")
    (work / "pkg/mod.py").write_text(
        "def alpha(a, extra):\n    return a\n\n\ndef beta(b):\n    return b + 2\n"
    )
    _git(work, "commit", "-qam", "unrelated rewrite (#11)", date="2026-10-04T00:00:00+00:00")
    (work / "other.py").write_text("X = 2\n")
    _git(
        work, "commit", "-qam", "fix: revert thing from #10 (#12)", date="2026-10-05T00:00:00+00:00"
    )
    (work / "other.py").write_text("X = 3\n")
    _git(work, "commit", "-qam", "late change (#13)", date="2026-10-20T00:00:00+00:00")
    _git(work, "push", "-q", "origin", "main")
    return work


def test_followup_ref_and_touch_signals(clone: Path) -> None:
    merged = shadow.main_commits(clone)
    assert set(merged) == {10, 11, 12, 13}
    fu = shadow.followup(clone, merged[10]["sha"], 10, merged[10]["date"])
    assert fu["ref"] and fu["ref_commits"] == [merged[12]["sha"][:12]]
    assert fu["touch"] and fu["touch_commits"] == [
        merged[11]["sha"][:12]
    ]  # rewrote the line #10 introduced
    assert fu["later_commits_in_window"] == 2  # #13 is outside the 7-day window
    quiet = shadow.followup(clone, merged[12]["sha"], 12, merged[12]["date"])
    assert not quiet["any"]


def test_summarize_rates() -> None:
    rows = [
        {
            "flagged": True,
            "checks": ["C5.x"],
            "tamper": True,
            "api_delta": False,
            "follow": {"ref": True, "touch": False, "any": True},
        },
        {
            "flagged": True,
            "tamper": False,
            "api_delta": True,
            "follow": {"ref": False, "touch": False, "any": False},
        },
        {
            "flagged": False,
            "tamper": False,
            "api_delta": False,
            "follow": {"ref": False, "touch": False, "any": False},
        },
    ]
    out = shadow.summarize(rows)
    assert out["flagged"]["any"] == {"n": 2, "k": 1, "rate": 0.5}
    assert out["unflagged"]["any"] == {"n": 1, "k": 0, "rate": 0.0}
    assert out["tamper"]["ref"]["k"] == 1
    assert out["C5.x"]["ref"] == {"n": 1, "k": 1, "rate": 1.0}


def test_issue_refs_and_intake_block() -> None:
    assert shadow.issue_refs(
        "t (#5)", "Refs #2752 and see #9\nCloses James3014/Nexus-new#44", 5
    ) == [2752, 44, 9]
    text = 'x\n```eia-task\n{"allowed_files": ["a.py", "tests/test_a.py"]}\n```\n'
    assert shadow.intake_from_issue(text) == ["a.py", "tests/test_a.py"]
    assert shadow.intake_from_issue("no block") is None


def test_run_is_idempotent_and_report_joins(
    clone: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    merged = shadow.main_commits(clone)
    calls: list[tuple[str, ...]] = []

    def fake_gh(*args: str) -> object:
        calls.append(args)
        if args[:2] == ("pr", "list"):
            return [
                {
                    "number": 10,
                    "title": "feat: tweak",
                    "body": "Refs #99",
                    "mergedAt": merged[10]["date"],
                    "mergeCommit": {"oid": merged[10]["sha"]},
                    "headRefOid": "headsha10",
                }
            ]
        if args[:2] == ("issue", "view"):
            return {"title": "tweak", "body": "Please improve `beta`."}
        raise AssertionError(args)

    log = tmp_path / "state/flags.jsonl"
    argv = ["run", "--log", str(log), "--clone-root", str(clone.parent), "--no-fetch"]
    ns = shadow.build_parser().parse_args(argv)
    ns.repo = ["James3014/Nexus-new"]
    assert shadow.cmd_run(ns, gh_json=fake_gh) == 0
    rows = shadow.read_log(log)
    assert len(rows) == 1 and rows[0]["pr"] == 10 and rows[0]["issue_refs"] == [99]
    flags = rows[0]["result"]["flags"]
    assert [f["detail"] for f in flags] == ["SIGNATURE_CHANGED alpha"]  # beta is named in the Issue
    assert rows[0]["result"]["api_delta"] and not rows[0]["result"]["tamper"]
    n_calls = len(calls)
    assert shadow.cmd_run(ns, gh_json=fake_gh) == 0
    assert len(shadow.read_log(log)) == 1  # same (repo, pr, head sha): not appended again
    assert len(calls) == n_calls + 1  # only the list call; the Issue text is cached

    def report(now: str, capsys: pytest.CaptureFixture[str]) -> dict:
        argv = ["report", "--log", str(log), "--clone-root", str(clone.parent), "--no-fetch"]
        ns = shadow.build_parser().parse_args([*argv, "--now", now, "--json"])
        capsys.readouterr()
        assert shadow.cmd_report(ns) == 0
        return json.loads(capsys.readouterr().out)

    old = report("2026-10-30T00:00:00+00:00", capsys)
    assert old["scored"] == 1 and old["pending_under_7d"] == 0 and old["not_merged_or_unknown"] == 0
    assert old["flagged"]["any"]["n"] == 1 and old["iv1_flagged"]["any"]["n"] == 1
    assert old["flagged"]["ref"] == {"n": 1, "k": 1, "rate": 1.0}  # #12's subject: fix + #10
    young = report("2026-10-03T00:00:00+00:00", capsys)
    assert young["scored"] == 0 and young["pending_under_7d"] == 1
    assert young["flagged"]["any"] == {"n": 0, "k": 0, "rate": None}


def test_bad_pr_is_recorded_not_raised(clone: Path, tmp_path: Path) -> None:
    pr = {
        "number": 77,
        "title": "x",
        "body": "",
        "mergedAt": None,
        "mergeCommit": {"oid": "0" * 40},
        "headRefOid": "h",
    }
    issues = shadow.IssueText(lambda *a: {}, tmp_path / "c.json")
    row = shadow.scan_pr("James3014/Nexus-new", pr, "merged", clone, issues)
    assert row["result"] is None and "error" in row


def test_log_lines_are_json(clone: Path, tmp_path: Path) -> None:
    log = tmp_path / "l.jsonl"
    shadow.append_log(log, {"a": 1})
    assert json.loads(log.read_text()) == {"a": 1}


def _run_args(log: Path, clone: Path) -> argparse.Namespace:
    ns = shadow.build_parser().parse_args([
        "run",
        "--log",
        str(log),
        "--clone-root",
        str(clone.parent),
        "--no-fetch",
    ])
    ns.repo = ["James3014/Nexus-new"]
    return ns


def _pr_list(merged: dict) -> list[dict]:
    return [
        {
            "number": 10,
            "title": "feat: tweak",
            "body": "Refs #99",
            "mergedAt": merged[10]["date"],
            "mergeCommit": {"oid": merged[10]["sha"]},
            "headRefOid": "headsha10",
        }
    ]


def test_errored_scan_is_retried_not_marked_seen(clone: Path, tmp_path: Path) -> None:
    merged = shadow.main_commits(clone)
    state = {"fail": True}

    def gh(*args: str) -> object:
        if args[:2] == ("pr", "list"):
            return _pr_list(merged)
        if state["fail"]:
            raise shadow.GhError("ghc issue view failed (exit 75): temporary")
        return {"title": "t", "body": "b"}

    log = tmp_path / "state/flags.jsonl"
    ns = _run_args(log, clone)
    assert shadow.cmd_run(ns, gh_json=gh) == 0
    assert shadow.read_log(log) == []  # nothing marked seen
    assert [r["pr"] for r in shadow.read_log(log.parent / "errors.jsonl")] == [10]
    state["fail"] = False
    assert shadow.cmd_run(ns, gh_json=gh) == 0
    assert [r["pr"] for r in shadow.read_log(log)] == [10]  # retried and recorded


def test_issue_cache_only_remembers_confirmed_absence(tmp_path: Path) -> None:
    answers: list[Exception | dict] = [
        shadow.GhError("ghc issue view failed (exit 75): rate limited"),
        shadow.GhError(
            "ghc issue view failed (exit 1): GraphQL: Could not resolve to an Issue with the number of 5."
        ),
        {"title": "T", "body": "B"},
    ]

    def gh(*args: str) -> object:
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    issues = shadow.IssueText(gh, tmp_path / "c.json")
    with pytest.raises(shadow.GhError):
        issues.get("o/r", 5)
    assert not (tmp_path / "c.json").exists()  # transient failure not cached
    assert issues.get("o/r", 5) == ""  # confirmed absent: cached
    assert json.loads((tmp_path / "c.json").read_text()) == {"o/r#5": ""}
    assert issues.get("o/r", 5) == ""  # no further ghc call
    assert issues.get("o/r", 6) == "T\n\nB"
    assert answers == []


def test_append_log_never_glues_onto_a_torn_line(tmp_path: Path) -> None:
    log = tmp_path / "flags.jsonl"
    log.write_bytes(b'{"pr": 1}\n{"pr": 2, "tor')
    shadow.append_log(log, {"pr": 3})
    shadow.append_log(log, {"pr": 4})
    assert log.read_bytes().endswith(b'\n{"pr": 3}\n{"pr": 4}\n')
    assert [r["pr"] for r in shadow.read_log(log)] == [1, 3, 4]
    log.write_bytes(b'{"pr": 1}\n\xff\xfe not json\n{"pr": 5}\n')
    assert [r["pr"] for r in shadow.read_log(log)] == [1, 5]


def test_ref_signal_needs_subject_and_same_repo() -> None:
    assert shadow.is_ref_subject("fix: bad thing from #10 (#12)", 10)
    assert shadow.is_ref_subject('Revert "feat: tweak (#10)"', 10)
    assert not shadow.is_ref_subject("feat: unrelated (#10)", 11)
    assert not shadow.is_ref_subject("fix: other repo piece of other/repo#10 (#12)", 10)
    assert not shadow.is_ref_subject("fix: itself (#10)", 10)
    assert not shadow.is_ref_subject("feat: add thing (#12)", 10)  # no fix word
    assert not shadow.is_ref_subject("feat: extends #10 with more (#12)", 10)  # #P but no fix word


def test_body_mention_is_not_a_ref_signal(tmp_path: Path) -> None:
    origin = tmp_path / "o.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    work = tmp_path / "root" / "James3014__Nexus-new"
    work.parent.mkdir(exist_ok=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
    (work / "z.py").write_text("z = 0\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "base", date="2026-09-30T00:00:00+00:00")
    (work / "a.py").write_text("x = 1\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "feat: a (#10)", date="2026-10-01T00:00:00+00:00")
    (work / "b.py").write_text("y = 1\n")
    _git(work, "add", "-A")
    _git(
        work,
        "commit",
        "-qm",
        "feat: b (#11)\n\nfixes the thing, relates to #10",
        date="2026-10-02T00:00:00+00:00",
    )
    _git(work, "push", "-q", "origin", "main")
    merged = shadow.main_commits(work)
    fu = shadow.followup(work, merged[10]["sha"], 10, merged[10]["date"])
    assert not fu["ref"]


@pytest.fixture()
def merge_repo(tmp_path: Path) -> Path:
    """True merge commit `Merge pull request #20 from x/feature` followed by a rewrite of its line."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    work = tmp_path / "root" / "James3014__Nexus-new"
    work.parent.mkdir(exist_ok=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
    (work / "f.py").write_text("a = 1\nb = 2\nc = 3\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "base", date="2026-10-01T00:00:00+00:00")
    _git(work, "checkout", "-qb", "feature")
    (work / "f.py").write_text("a = 1\nb = 22\nc = 3\n")
    _git(work, "commit", "-qam", "branch only commit (#30)", date="2026-10-02T00:00:00+00:00")
    _git(work, "checkout", "-q", "main")
    (work / "other.py").write_text("z = 1\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "main moves on (#19)", date="2026-10-02T01:00:00+00:00")
    _git(
        work,
        "merge",
        "--no-ff",
        "-q",
        "feature",
        "-m",
        "Merge pull request #20 from x/feature",
        date="2026-10-03T00:00:00+00:00",
    )
    (work / "f.py").write_text("a = 1\nb = 222\nc = 3\n")
    _git(work, "commit", "-qam", "tune later (#21)", date="2026-10-04T00:00:00+00:00")
    _git(work, "push", "-q", "origin", "main")
    return work


def test_true_merge_commits_use_first_parent(merge_repo: Path, tmp_path: Path) -> None:
    merged = shadow.main_commits(merge_repo)
    assert {19, 20, 21} <= set(merged)
    assert 30 not in merged  # --first-parent: a commit that only lives on the merged branch
    assert len(merged[20]["parents"]) == 2
    merge = merged[20]["sha"]
    pr = {
        "number": 20,
        "title": "feature",
        "body": "",
        "mergedAt": merged[20]["date"],
        "mergeCommit": {"oid": merge},
        "headRefOid": "h20",
    }
    diff, base, _m = shadow.pr_diff(merge_repo, pr, "merged")
    assert base == merged[20]["parents"][0]
    assert "b = 22" in diff and "z = 1" not in diff  # main's own commit is not part of the PR
    fu = shadow.followup(merge_repo, merge, 20, merged[20]["date"])
    assert fu["touch"] and fu["touch_commits"] == [merged[21]["sha"][:12]]
    assert not fu["ref"]


def test_log_row_carries_both_tiers_and_errors_field(clone: Path, tmp_path: Path) -> None:
    merged = shadow.main_commits(clone)
    issues = shadow.IssueText(lambda *a: {"title": "t", "body": "b"}, tmp_path / "c.json")
    pr = _pr_list(merged)[0]
    row = shadow.scan_pr("James3014/Nexus-new", pr, "merged", clone, issues)
    assert row["result"]["errors"] == []
    assert isinstance(row["result"]["flags_refined"], list) and row["schema"] == shadow.SCHEMA


def test_default_clone_root_is_dedicated_and_created_on_first_use(
    clone: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert shadow.DEFAULT_CLONE_ROOT == Path.home() / ".local/state/nexus-l2-shadow/clone"
    seed_root = tmp_path / "seed"
    seed_root.mkdir()
    subprocess.run(
        ["git", "clone", "-q", str(clone), str(seed_root / "Nexus-new")],
        check=True,
        capture_output=True,
    )
    # the seed's origin is `clone` (a path), standing in for the GitHub URL
    monkeypatch.setattr(shadow, "SEED_CLONE_ROOT", seed_root)
    monkeypatch.setattr(shadow, "repo_url", lambda repo: str(clone))
    root = tmp_path / "state/clone"
    dest = shadow.ensure_clone("James3014/Nexus-new", root)
    assert dest == root.resolve() / "James3014__Nexus-new"  # keyed by owner__repo
    assert shadow.main_commits(dest).keys() == {10, 11, 12, 13}
    assert not (
        dest / ".git/objects/info/alternates"
    ).exists()  # --dissociate: independent of the shared clone
    assert shadow.ensure_clone("James3014/Nexus-new", root) == dest  # second call reuses it
    assert shadow.ensure_clone("Other/Nexus-new", root) != dest  # same repo name, other owner


def test_clone_root_overlapping_shared_clones_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    (home / "workspace/Nexus-new/.git").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(shadow, "SEED_CLONE_ROOT", home / "workspace")
    for bad in (home / "workspace", home / "workspace/sub", home, home / "Workspace/x"):
        with pytest.raises(RuntimeError, match="refusing clone root"):
            shadow.ensure_clone("James3014/Nexus-new", bad)
    holder = tmp_path / "elsewhere"
    (holder / "Nexus-new/.git").mkdir(parents=True)  # a root that already holds a main clone
    with pytest.raises(RuntimeError, match="main clone"):
        shadow.ensure_clone("James3014/Nexus-new", holder)


def test_checker_errors_make_the_scan_errored(
    clone: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    merged = shadow.main_commits(clone)
    monkeypatch.setattr(
        shadow.flags_lib,
        "flag_candidate",
        lambda *a, **k: {
            "flags": [],
            "errors": [{"kind": "PATCH_NOT_APPLIED", "path": "pkg/mod.py"}],
        },
    )

    def gh(*args: str) -> object:
        return _pr_list(merged) if args[:2] == ("pr", "list") else {"title": "t", "body": "b"}

    log = tmp_path / "state/flags.jsonl"
    assert shadow.cmd_run(_run_args(log, clone), gh_json=gh) == 0
    assert shadow.read_log(log) == []  # not logged as a clean record, not seen
    errs = shadow.read_log(log.parent / "errors.jsonl")
    assert len(errs) == 1 and "PATCH_NOT_APPLIED pkg/mod.py" in errs[0]["error"]


def test_git_failure_in_followup_is_unknown_not_clean(clone: Path, tmp_path: Path) -> None:
    merged = shadow.main_commits(clone)
    with pytest.raises(shadow.FollowupError):
        shadow.followup(clone, "0" * 40, 10, merged[10]["date"])
    with pytest.raises(RuntimeError):
        shadow._changed_old_ranges(clone, "0" * 40, ["pkg/mod.py"])


def test_report_excludes_unknown_followups_and_uses_refined_for_flagged(
    clone: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    flag = {"check": "C2.public_signature", "path": "p.py", "line": 1, "detail": "d", "tier": "iv1"}

    def row(pr: int, iv1: list, refined: list) -> dict:
        return {
            "repo": "James3014/Nexus-new",
            "pr": pr,
            "head_sha": f"h{pr}",
            "state": "merged",
            "result": {
                "flags": iv1,
                "flags_refined": refined,
                "tamper": False,
                "api_delta": bool(iv1),
                "tamper_refined": False,
                "api_delta_refined": bool(refined),
                "errors": [],
            },
        }

    log = tmp_path / "state/flags.jsonl"
    shadow.append_log(log, row(10, [flag], []))  # iv1 flags it, refined does not
    shadow.append_log(log, row(11, [flag], [dict(flag, tier="refined")]))  # both flag it
    shadow.append_log(log, row(12, [], []))
    real = shadow.followup

    def fake(clone_: Path, sha: str, pr: int, date: str, commits=None) -> dict:
        if pr == 11:
            raise shadow.FollowupError("git blame failed")
        return real(clone_, sha, pr, date)

    monkeypatch.setattr(shadow, "followup", fake)
    argv = [
        "report",
        "--log",
        str(log),
        "--clone-root",
        str(clone.parent),
        "--no-fetch",
        "--now",
        "2026-10-30T00:00:00+00:00",
        "--json",
    ]
    capsys.readouterr()
    assert shadow.cmd_report(shadow.build_parser().parse_args(argv)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["scored"] == 2 and out["followup_unknown"] == {"n": 1, "prs": [11]}
    assert out["flagged"]["any"]["n"] == 0  # refined tier: PR 10 is unflagged, PR 11 is unknown
    assert out["iv1_flagged"]["any"]["n"] == 1  # iv1 tier flags PR 10
    assert out["unflagged"]["any"]["n"] == 2 and out["iv1_unflagged"]["any"]["n"] == 1
    assert out["flagged"] != out["iv1_flagged"]


def test_git_timeout_in_followup_is_unknown_not_an_abort(clone: Path, monkeypatch) -> None:
    merged = shadow.main_commits(clone)

    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 300)

    monkeypatch.setattr(shadow.subprocess, "run", slow)
    with pytest.raises(shadow.FollowupError):
        shadow.followup(clone, merged[10]["sha"], 10, merged[10]["date"])


def test_blame_failure_in_followup_is_unknown(clone: Path, monkeypatch) -> None:
    merged = shadow.main_commits(clone)
    real_git = shadow.git

    def failing_blame(c, *args, **kwargs):
        if args and args[0] == "blame":
            raise RuntimeError("git blame failed")
        return real_git(c, *args, **kwargs)

    monkeypatch.setattr(shadow, "git", failing_blame)
    # PR 10's lines are touched by PR 11 (see test_followup_ref_and_touch_signals), so blame runs
    with pytest.raises(shadow.FollowupError):
        shadow.followup(clone, merged[10]["sha"], 10, merged[10]["date"])


def test_same_repo_matches_only_exact_owner_and_name() -> None:
    assert shadow._same_repo("https://github.com/James3014/Nexus-new.git", "James3014/Nexus-new")
    assert shadow._same_repo("git@github.com:James3014/Nexus-new.git", "james3014/nexus-new")
    assert not shadow._same_repo("https://github.com/Other/Nexus-new.git", "James3014/Nexus-new")
    assert not shadow._same_repo(
        "https://example.com/James3014/Nexus-new.git", "James3014/Nexus-new"
    )
    assert not shadow._same_repo("", "James3014/Nexus-new")


def test_seed_of_another_owner_is_never_used(clone: Path, tmp_path: Path, monkeypatch) -> None:
    """Codex r3: a same-named seed of a different owner must not redirect the clone URL."""
    seed_root = tmp_path / "seed2"
    seed_root.mkdir()
    subprocess.run(
        ["git", "clone", "-q", str(clone), str(seed_root / "Nexus-new")],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(seed_root / "Nexus-new"),
            "remote",
            "set-url",
            "origin",
            "https://github.com/James3014/Nexus-new.git",
        ],
        check=True,
    )
    monkeypatch.setattr(shadow, "SEED_CLONE_ROOT", seed_root)
    calls: list[list[str]] = []
    real_run = shadow.subprocess.run

    def record(cmd, *args, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            calls.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(shadow.subprocess, "run", record)
    shadow.ensure_clone("Other/Nexus-new", tmp_path / "state3/clone")
    assert calls and calls[0][-2] == "https://github.com/Other/Nexus-new.git"
    assert "--reference" not in calls[0]


def test_clone_and_seed_probe_are_time_bounded(tmp_path: Path, monkeypatch) -> None:
    # #2752 follow-up: a hung network clone or seed probe must not stall the daily run forever.
    seed_root = tmp_path / "seeds"
    (seed_root / "Nexus-new/.git").mkdir(parents=True)
    monkeypatch.setattr(shadow, "SEED_CLONE_ROOT", seed_root)
    timeouts: list[tuple[str, object]] = []

    def hang(cmd, *args, **kwargs):
        timeouts.append((cmd[1] if cmd[1] != "-C" else cmd[3], kwargs.get("timeout")))
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout") or 0)

    monkeypatch.setattr(shadow.subprocess, "run", hang)
    with pytest.raises(RuntimeError, match="timed out"):
        shadow.ensure_clone("James3014/Nexus-new", tmp_path / "state/clone")
    assert [name for name, _ in timeouts] == ["remote", "clone"]
    assert all(isinstance(t, (int, float)) and t > 0 for _, t in timeouts)


def test_timed_out_clone_leaves_no_partial_clone(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(shadow, "SEED_CLONE_ROOT", tmp_path / "no-seeds")
    root = tmp_path / "state/clone"

    def partial_then_hang(cmd, *args, **kwargs):
        (Path(cmd[-1]) / ".git").mkdir(parents=True)  # git had started writing dest
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout") or 0)

    monkeypatch.setattr(shadow.subprocess, "run", partial_then_hang)
    with pytest.raises(RuntimeError, match="timed out"):
        shadow.ensure_clone("James3014/Nexus-new", root)
    assert not (root / "James3014__Nexus-new").exists()
