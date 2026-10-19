#!/usr/bin/env python3
"""L2-1 shadow runner (Refs #2752): record-only static flags over real PRs.

``run``    for merged (and optionally open) PRs, compute the two static checks of
           ``nexus.review.l2_static_flags`` and append one JSON line per
           (repo, PR number, head sha) to the shadow log (default
           ``~/.local/state/nexus-l2-shadow/flags.jsonl``).  Idempotent.
``report`` join the log with a 7-day follow-up signal (see ``followup``) and print
           flagged vs unflagged fix/revert rates.

Zero model calls.  GitHub is read only through ``~/workspace/agent-coord/bin/ghc``
(shared 60 s cache, separate quota) with a delay between calls; diffs come from a
local clone with ``git`` (read-only: fetch + diff/show/blame/log).  Nothing here
comments on, blocks, or labels a PR, and no gate or Gateway path reads the log.

Follow-up heuristic for a merged PR P (merge commit M), over commits on origin
main after M within 7 days (a PR is only scored once M is >= 7 days old):
  * ``ref``   a later commit message mentions ``#P`` (or M's sha) together with a
              fix / revert / hotfix / regression word, or says ``This reverts commit M``;
  * ``touch`` a later commit's diff removes or rewrites a line that ``git blame``
              (at the commit's parent) attributes to M, in a file P touched;
  * ``any``   ref or touch.
``touch`` is noisier than ``ref`` (feature work also rewrites fresh lines), so the
report prints all three rates.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.review import l2_static_flags as flags_lib  # noqa: E402

SCHEMA = "nexus.l2_flag_shadow.v1"
DEFAULT_LOG = Path.home() / ".local/state/nexus-l2-shadow/flags.jsonl"
DEFAULT_GHC = Path.home() / "workspace/agent-coord/bin/ghc"
DEFAULT_CLONE_ROOT = Path.home() / "workspace"
MAX_DIFF_BYTES = 2_000_000
FOLLOWUP_DAYS = 7
FIX_WORD = re.compile(r"\b(revert\w*|fix\w*|hotfix\w*|regress\w*)\b", re.I)
REF_ISSUE = re.compile(r"(?:refs?|closes?|fix(?:es|ed)?|resolves?)\s+(?:[\w./-]+)?#(\d+)", re.I)
ANY_ISSUE = re.compile(r"(?<![\w/])#(\d+)")


# --------------------------------------------------------------------------- plumbing
def git(clone: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(
        ["git", "-C", str(clone), *args],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=300,
        check=False,
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])} failed: {r.stderr.strip()[:300]}")
    return r.stdout


def make_ghc_json(ghc: Path, delay: float) -> Callable[..., object]:
    last = [0.0]

    def call(*args: str) -> object:
        wait = delay - (time.monotonic() - last[0])
        if wait > 0:
            time.sleep(wait)
        r = subprocess.run(
            [str(ghc), *args], capture_output=True, text=True, timeout=120, check=False
        )
        last[0] = time.monotonic()
        if r.returncode != 0:
            raise RuntimeError(f"ghc {' '.join(args[:3])} failed: {r.stderr.strip()[:300]}")
        return json.loads(r.stdout or "null")

    return call


def read_log(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def append_log(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- issue text
def issue_refs(title: str, body: str, own: int) -> list[int]:
    text = f"{title}\n{body or ''}"
    out: list[int] = []
    for rx in (REF_ISSUE, ANY_ISSUE):
        for m in rx.finditer(text):
            n = int(m.group(1))
            if n != own and n not in out:
                out.append(n)
    return out[:3]


def intake_from_issue(text: str) -> list[str] | None:
    """``allowed_files`` of a fenced ``eia-task`` JSON block, if the Issue has one."""
    m = re.search(r"```eia-task\s*\n(.*?)```", text or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    files = data.get("allowed_files") if isinstance(data, dict) else None
    return [str(f) for f in files] if isinstance(files, list) and files else None


class IssueText:
    """Read-only Issue fetch with an on-disk cache (one ghc call per Issue, ever)."""

    def __init__(self, gh_json: Callable[..., object], cache_path: Path):
        self.gh_json = gh_json
        self.path = cache_path
        self.cache: dict[str, str] = {}
        if cache_path.is_file():
            try:
                self.cache = json.loads(cache_path.read_text())
            except json.JSONDecodeError:
                self.cache = {}

    def get(self, repo: str, number: int) -> str:
        key = f"{repo}#{number}"
        if key not in self.cache:
            try:
                data = self.gh_json(
                    "issue", "view", str(number), "--repo", repo, "--json", "title,body"
                )
                text = f"{data['title']}\n\n{data.get('body') or ''}"  # type: ignore[index,union-attr]
            except Exception:  # a PR number or a transient error: remember emptiness only for PRs
                text = ""
            self.cache[key] = text
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.cache, sort_keys=True))
        return self.cache[key]


# --------------------------------------------------------------------------- scan
def pr_diff(clone: Path, pr: dict, state: str) -> tuple[str, str, str | None]:
    """(diff text, base sha, merge sha) from the local clone."""
    if state == "merged":
        merge = pr["mergeCommit"]["oid"]
        base = git(clone, "rev-parse", f"{merge}^").strip()
        return (
            git(clone, "diff", "--no-color", "--no-ext-diff", "--no-renames", base, merge),
            base,
            merge,
        )
    git(clone, "fetch", "-q", "origin", f"refs/pull/{pr['number']}/head")
    head = git(clone, "rev-parse", "FETCH_HEAD").strip()
    base = git(clone, "merge-base", "origin/main", head).strip()
    return git(clone, "diff", "--no-color", "--no-ext-diff", "--no-renames", base, head), base, None


def scan_pr(repo: str, pr: dict, state: str, clone: Path, issues: IssueText) -> dict:
    row: dict = {
        "schema": SCHEMA,
        "repo": repo,
        "pr": pr["number"],
        "head_sha": pr["headRefOid"],
        "state": state,
        "title": pr.get("title", "")[:200],
        "merged_at": pr.get("mergedAt"),
        "checked_at": now_iso(),
    }
    refs = issue_refs(pr.get("title", ""), pr.get("body") or "", pr["number"])
    texts = [(n, issues.get(repo, n)) for n in refs]
    texts = [(n, t) for n, t in texts if t]
    issue_text = (
        "\n\n".join(t for _n, t in texts) or f"{pr.get('title', '')}\n\n{pr.get('body') or ''}"
    )
    intake = next((i for _n, t in texts if (i := intake_from_issue(t))), None)
    row.update(
        issue_refs=[n for n, _t in texts],
        issue_source="issue" if texts else "pr_body",
        intake_source="eia-task" if intake else "none",
    )
    try:
        diff, base, merge = pr_diff(clone, pr, state)
        row.update(base_sha=base, merge_sha=merge, diff_bytes=len(diff))
        if len(diff) > MAX_DIFF_BYTES:
            row["result"] = None
            row["skipped"] = "diff_too_large"
        else:
            row["result"] = flags_lib.flag_candidate(
                diff, issue_text, intake, head_tree=flags_lib.GitTree(clone, base)
            )
    except Exception as exc:  # record, never raise: a bad PR must not stop the stream
        row["result"] = None
        row["error"] = str(exc)[:300]
    return row


def cmd_run(args: argparse.Namespace, gh_json: Callable[..., object] | None = None) -> int:
    log = Path(args.log).expanduser()
    state_dir = log.parent
    gh_json = gh_json or make_ghc_json(Path(args.ghc).expanduser(), args.gh_delay)
    seen = {(r.get("repo"), r.get("pr"), r.get("head_sha")) for r in read_log(log)}
    counts = {"new": 0, "skipped_seen": 0, "flagged": 0, "errors": 0}
    for repo in args.repo:
        clone = Path(args.clone_root).expanduser() / repo.split("/")[-1]
        if not args.no_fetch:
            git(clone, "fetch", "-q", "origin", "main")
        issues = IssueText(gh_json, state_dir / "issue_cache.json")
        fields = "number,title,body,mergedAt,mergeCommit,headRefOid"
        batches = [
            (
                "merged",
                gh_json(
                    "pr",
                    "list",
                    "--repo",
                    repo,
                    "--state",
                    "merged",
                    "--limit",
                    str(args.limit),
                    "--json",
                    fields,
                ),
            )
        ]
        if args.open:
            batches.append((
                "open",
                gh_json(
                    "pr",
                    "list",
                    "--repo",
                    repo,
                    "--state",
                    "open",
                    "--limit",
                    str(args.limit),
                    "--json",
                    fields,
                ),
            ))
        for state, prs in batches:
            for pr in prs:  # type: ignore[union-attr]
                if (repo, pr["number"], pr["headRefOid"]) in seen:
                    counts["skipped_seen"] += 1
                    continue
                row = scan_pr(repo, pr, state, clone, issues)
                append_log(log, row)
                seen.add((repo, pr["number"], pr["headRefOid"]))
                counts["new"] += 1
                counts["errors"] += int(bool(row.get("error")))
                counts["flagged"] += int(bool((row.get("result") or {}).get("flags")))
    print(json.dumps({"log": str(log), **counts}, sort_keys=True))
    return 0


# --------------------------------------------------------------------------- follow-up
def main_commits(clone: Path) -> dict[int, dict]:
    """PR number -> {sha, date, subject} for commits on origin/main whose subject ends with (#N)."""
    out: dict[int, dict] = {}
    for line in git(clone, "log", "origin/main", "--format=%H%x1f%cI%x1f%s").splitlines():
        sha, date, subject = (line.split("\x1f") + ["", ""])[:3]
        m = re.search(r"\(#(\d+)\)\s*$", subject)
        if m:
            out.setdefault(int(m.group(1)), {"sha": sha, "date": date, "subject": subject})
    return out


def _changed_old_ranges(
    clone: Path, commit: str, paths: list[str]
) -> dict[str, list[tuple[int, int]]]:
    out: dict[str, list[tuple[int, int]]] = {}
    text = git(
        clone,
        "diff",
        "--no-color",
        "--no-renames",
        "-U0",
        f"{commit}^",
        commit,
        "--",
        *paths,
        check=False,
    )
    path = None
    for line in text.splitlines():
        if line.startswith("--- "):
            path = line[6:] if line.startswith("--- a/") else None
        elif line.startswith("@@") and path:
            m = re.match(r"@@ -(\d+)(?:,(\d+))? ", line)
            if m and int(m.group(2) if m.group(2) is not None else 1) > 0:
                start, n = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
                out.setdefault(path, []).append((start, start + n - 1))
    return out


def followup(
    clone: Path, merge_sha: str, pr_number: int, merged_iso: str, commits: list[dict] | None = None
) -> dict:
    """Follow-up signal for one merged PR; see the module docstring."""
    start = dt.datetime.fromisoformat(merged_iso)
    until = start + dt.timedelta(days=FOLLOWUP_DAYS)
    files = [
        f
        for f in git(
            clone, "diff-tree", "--no-commit-id", "--name-only", "-r", merge_sha
        ).splitlines()
        if f
    ]
    later = []
    for line in git(
        clone, "log", "--reverse", f"{merge_sha}..origin/main", "--format=%H%x1f%cI%x1f%B%x1e"
    ).split("\x1e"):
        line = line.strip("\n")
        if not line.strip():
            continue
        sha, date, msg = (line.split("\x1f") + ["", ""])[:3]
        if dt.datetime.fromisoformat(date) <= until:
            later.append({"sha": sha.strip(), "msg": msg})
    ref: list[str] = []
    touch: list[str] = []
    short = merge_sha[:9]
    for c in later:
        msg = c["msg"]
        mentions = re.search(rf"#{pr_number}\b", msg) or short in msg
        own = re.search(r"\(#(\d+)\)\s*$", msg.split("\n", 1)[0])
        if own and int(own.group(1)) == pr_number:
            continue
        if (mentions and FIX_WORD.search(msg)) or f"reverts commit {merge_sha[:7]}" in msg.lower():
            ref.append(c["sha"][:12])
            continue
        if not files or c["sha"] in touch:
            continue
        ranges = _changed_old_ranges(clone, c["sha"], files)
        hit = False
        for path, spans in ranges.items():
            for s, e in spans:
                blame = git(
                    clone,
                    "blame",
                    "--porcelain",
                    "-L",
                    f"{s},{e}",
                    f"{c['sha']}^",
                    "--",
                    path,
                    check=False,
                )
                if any(re.match(rf"^{merge_sha}\b", ln) for ln in blame.splitlines()):
                    hit = True
                    break
            if hit:
                break
        if hit:
            touch.append(c["sha"][:12])
    return {
        "ref": bool(ref),
        "touch": bool(touch),
        "any": bool(ref or touch),
        "ref_commits": ref[:5],
        "touch_commits": touch[:5],
        "later_commits_in_window": len(later),
    }


# --------------------------------------------------------------------------- report
def summarize(rows: list[dict]) -> dict:
    """Rates per group; rows carry ``flagged`` plus follow-up booleans."""

    def rate(sub: list[dict], key: str) -> dict:
        n = len(sub)
        k = sum(1 for r in sub if r["follow"][key])
        return {"n": n, "k": k, "rate": round(k / n, 3) if n else None}

    groups = {
        "flagged": [r for r in rows if r["flagged"]],
        "unflagged": [r for r in rows if not r["flagged"]],
        "tamper": [r for r in rows if r["tamper"]],
        "api_delta": [r for r in rows if r["api_delta"]],
    }
    for check in sorted({c for r in rows for c in r.get("checks", [])}):
        groups[check] = [r for r in rows if check in r.get("checks", [])]
    return {
        name: {key: rate(sub, key) for key in ("ref", "touch", "any")}
        for name, sub in groups.items()
    }


def cmd_report(args: argparse.Namespace) -> int:
    log = Path(args.log).expanduser()
    now = dt.datetime.fromisoformat(args.now) if args.now else dt.datetime.now(dt.timezone.utc)
    entries = [r for r in read_log(log) if r.get("result") is not None]
    # a PR may appear as open first and merged later with the same head: keep one entry per (repo, pr)
    latest: dict[tuple[str, int], dict] = {}
    for r in entries:
        latest[(r["repo"], r["pr"])] = r
    scored: list[dict] = []
    pending = unmerged = 0
    by_repo: dict[str, list[dict]] = {}
    for r in latest.values():
        by_repo.setdefault(r["repo"], []).append(r)
    for repo, rs in by_repo.items():
        clone = Path(args.clone_root).expanduser() / repo.split("/")[-1]
        if not args.no_fetch:
            git(clone, "fetch", "-q", "origin", "main")
        merged = main_commits(clone)
        for r in rs:
            info = merged.get(r["pr"])
            if not info:
                unmerged += 1
                continue
            if dt.datetime.fromisoformat(info["date"]) + dt.timedelta(days=FOLLOWUP_DAYS) > now:
                pending += 1
                continue
            fu = followup(clone, info["sha"], r["pr"], info["date"])
            res = r["result"]
            scored.append({
                "repo": repo,
                "pr": r["pr"],
                "flagged": bool(res["flags"]),
                "checks": sorted({f["check"] for f in res["flags"]}),
                "tamper": bool(res["tamper"]),
                "api_delta": bool(res["api_delta"]),
                "follow": fu,
            })
    out = {
        "scored": len(scored),
        "pending_under_7d": pending,
        "not_merged_or_unknown": unmerged,
        **summarize(scored),
    }
    if args.json:
        print(json.dumps(out, indent=2, sort_keys=True))
    else:
        print(
            f"scored {len(scored)} merged PRs (pending <7d: {pending}, not merged/unknown: {unmerged})"
        )
        for name in out:
            if name in ("scored", "pending_under_7d", "not_merged_or_unknown"):
                continue
            cells = "  ".join(f"{k}: {v['k']}/{v['n']} ({v['rate']})" for k, v in out[name].items())
            print(f"{name:10s} {cells}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("run", "report"):
        s = sub.add_parser(name)
        s.add_argument("--log", default=str(DEFAULT_LOG))
        s.add_argument(
            "--repo",
            action="append",
            default=None,
            help="owner/name; repeatable (default James3014/Nexus-new)",
        )
        s.add_argument("--clone-root", default=str(DEFAULT_CLONE_ROOT))
        s.add_argument("--no-fetch", action="store_true", help="skip git fetch origin main")
        if name == "run":
            s.add_argument("--limit", type=int, default=50)
            s.add_argument("--open", action="store_true", help="also scan open PRs")
            s.add_argument("--ghc", default=str(DEFAULT_GHC))
            s.add_argument("--gh-delay", type=float, default=1.0, help="seconds between ghc calls")
        else:
            s.add_argument("--now", help="ISO time to treat as now (tests)")
            s.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.repo = args.repo or ["James3014/Nexus-new"]
    return cmd_run(args) if args.cmd == "run" else cmd_report(args)


if __name__ == "__main__":
    sys.exit(main())
