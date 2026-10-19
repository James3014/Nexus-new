"""Shadow CLI tests (Refs #2752): local git repo, fake ghc, no network."""

from __future__ import annotations

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
    work = tmp_path / "Nexus-new"
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


def test_run_is_idempotent_and_report_joins(clone: Path, tmp_path: Path) -> None:
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
    rep = shadow.build_parser().parse_args([
        "report",
        "--log",
        str(log),
        "--clone-root",
        str(clone.parent),
        "--no-fetch",
        "--now",
        "2026-10-30T00:00:00+00:00",
    ])
    assert shadow.cmd_report(rep) == 0
    young = shadow.build_parser().parse_args([
        "report",
        "--log",
        str(log),
        "--clone-root",
        str(clone.parent),
        "--no-fetch",
        "--now",
        "2026-10-03T00:00:00+00:00",
        "--json",
    ])
    assert shadow.cmd_report(young) == 0


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
