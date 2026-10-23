#!/usr/bin/env python3
"""L2-1 shadow runner (Refs #2752): record-only static flags over real PRs.

``run``    for merged (and optionally open) PRs, compute the two static checks of
           ``nexus.review.l2_static_flags`` and append one JSON line per
           (repo, PR number, head sha) to the shadow log (default
           ``~/.local/state/nexus-l2-shadow/flags.jsonl``).  Idempotent.  A scan that
           errors (git failure, transient GitHub failure) is written to ``errors.jsonl``
           next to the log, not to the log, so the next run retries it.
``report`` join the log with a 7-day follow-up signal and print flagged vs unflagged
           rates.  ``flagged`` is the refined tier; ``iv1_flagged`` is the exact offline
           IV1 tier; both are shown.  ``--json`` prints scored / pending counts and rates.

Zero model calls.  GitHub is read only through ``~/workspace/agent-coord/bin/ghc``
(shared 60 s cache, separate quota) with a delay between calls; diffs come from a
dedicated clone ``~/.local/state/nexus-l2-shadow/clone/<owner>__<repo>`` (created on first
run with ``--reference ... --dissociate``; a clone root that overlaps ``~/workspace`` is refused,
and the shared main clone is never fetched into).  Nothing here comments on, blocks, or labels a PR, and
no gate or Gateway path reads the log.

Merged PR diff: against the merge commit's first parent (squash commit or true merge).
Merge commits are recognised by ``(#N)`` subjects and ``Merge pull request #N from ...``.

Follow-up heuristic for a merged PR P (merge commit M), over first-parent commits on
origin/main after M within 7 days (a PR is only scored once M is >= 7 days old):
  * ``ref``   a later commit SUBJECT line contains ``#P`` (this repo only, not
              ``owner/other#P``) together with a fix / revert / hotfix / regression word;
  * ``touch`` a later commit's diff removes or rewrites a line that ``git blame`` (at its
              first parent) attributes to P (M, or the branch commits of a true merge),
              in a file P touched;
  * ``any``   ref or touch.
``touch`` is noisier than ``ref`` (feature work also rewrites fresh lines), so the
report prints all three rates, plus per-check breakdowns.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.review import l2_static_flags as flags_lib  # noqa: E402

SCHEMA = "nexus.l2_flag_shadow.v2"
DEFAULT_LOG = Path.home() / ".local/state/nexus-l2-shadow/flags.jsonl"
DEFAULT_GHC = Path.home() / "workspace/agent-coord/bin/ghc"
DEFAULT_CLONE_ROOT = Path.home() / ".local/state/nexus-l2-shadow/clone"
SEED_CLONE_ROOT = (
    Path.home() / "workspace"
)  # read only: used as --reference object store, never fetched into
MAX_DIFF_BYTES = 2_000_000
CLONE_TIMEOUT_SECONDS = 1800
FOLLOWUP_DAYS = 7
FIX_WORD = re.compile(r"\b(revert\w*|fix\w*|hotfix\w*|regress\w*)\b", re.I)
MERGE_SUBJECT = re.compile(r"^Merge pull request #(\d+) from ")
SQUASH_SUBJECT = re.compile(r"\(#(\d+)\)\s*$")
REF_ISSUE = re.compile(r"(?:refs?|closes?|fix(?:es|ed)?|resolves?)\s+(?:[\w./-]+)?#(\d+)", re.I)
ANY_ISSUE = re.compile(r"(?<![\w/])#(\d+)")


# --------------------------------------------------------------------------- plumbing
def git(clone: Path, *args: str, check: bool = True) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(clone), *args],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # A timeout is a git failure like any other: callers turn it into an errored scan or an
        # unknown follow-up, never into a clean result or an aborted report.
        raise RuntimeError(f"git {' '.join(args[:3])} timed out after {exc.timeout}s") from exc
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])} failed: {r.stderr.strip()[:300]}")
    return r.stdout


class GhError(RuntimeError):
    """A failed ghc call; ``confirmed_absent`` is True only for a definite 404 / not-an-issue answer."""

    @property
    def confirmed_absent(self) -> bool:
        text = str(self).lower()
        return any(
            k in text
            for k in ("could not resolve to an issue", "http 404", "not found", "is a pull request")
        )


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
            raise GhError(
                f"ghc {' '.join(args[:3])} failed (exit {r.returncode}): {r.stderr.strip()[:300]}"
            )
        return json.loads(r.stdout or "null")

    return call


def read_log(path: Path) -> list[dict]:
    """Parsed records; torn / non-JSON lines are skipped."""
    if not path.is_file():
        return []
    rows = []
    for line in path.read_bytes().decode("utf-8", errors="replace").split("\n"):
        if line.strip():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def append_log(path: Path, row: dict) -> None:
    """Append one record with a single write; never glue it onto a torn last line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(row, sort_keys=True) + "\n").encode()
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        size = os.fstat(fd).st_size
        if size and os.pread(fd, 1, size - 1) != b"\n":
            data = b"\n" + data
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


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
        """Issue text; "" is cached only for a confirmed absent Issue / PR number.

        Any other failure (ghc exit 75, network, timeout) raises and is never cached.
        """
        key = f"{repo}#{number}"
        if key not in self.cache:
            try:
                data = self.gh_json(
                    "issue", "view", str(number), "--repo", repo, "--json", "title,body"
                )
                text = f"{data['title']}\n\n{data.get('body') or ''}"  # type: ignore[index,union-attr]
            except GhError as exc:
                if not exc.confirmed_absent:
                    raise
                text = ""
            self.cache[key] = text
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + f".tmp{os.getpid()}")
            tmp.write_text(json.dumps(self.cache, sort_keys=True))
            os.replace(tmp, self.path)
        return self.cache[key]


# --------------------------------------------------------------------------- scan
def pr_diff(clone: Path, pr: dict, state: str) -> tuple[str, str, str | None]:
    """(diff text, base sha, merge sha) from the local clone."""
    if state == "merged":
        merge = pr["mergeCommit"]["oid"]
        base = git(clone, "rev-parse", f"{merge}^1").strip()  # first parent: squash or true merge
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
    """One log record. ``row["error"]`` is set when the scan failed; such rows are retried, not logged."""
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
    try:
        refs = issue_refs(pr.get("title", ""), pr.get("body") or "", pr["number"])
        texts = [(n, issues.get(repo, n)) for n in refs]  # transient failures raise: scan retried
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
        diff, base, merge = pr_diff(clone, pr, state)
        row.update(base_sha=base, merge_sha=merge, diff_bytes=len(diff))
        if len(diff) > MAX_DIFF_BYTES:
            row["result"] = None
            row["skipped"] = "diff_too_large"
        else:
            result = flags_lib.flag_candidate(
                diff, issue_text, intake, head_tree=flags_lib.GitTree(clone, base)
            )
            if result["errors"]:  # a checker that could not read its input is not "clean"
                raise RuntimeError(
                    "checker errors: "
                    + "; ".join(f"{e['kind']} {e['path']}" for e in result["errors"][:5])
                )
            row["result"] = result
    except Exception as exc:  # never raise: a bad PR must not stop the stream
        row["result"] = None
        row["error"] = str(exc)[:300]
    return row


def _check_clone_root(root: Path, repo: str) -> Path:
    """Refuse a clone root that is, is inside, or contains a shared main clone location."""
    resolved = root.expanduser().resolve()
    home = Path.home().resolve()
    shared = {
        (home / "workspace").resolve(),
        (home / "Workspace").resolve(),
        SEED_CLONE_ROOT.resolve(),
    }
    for s_dir in shared:
        if resolved == s_dir or s_dir in resolved.parents or resolved in s_dir.parents:
            raise RuntimeError(
                f"refusing clone root {resolved}: it overlaps the shared clones in {s_dir}"
            )
    if (resolved / repo.split("/")[-1] / ".git").exists():
        raise RuntimeError(
            f"refusing clone root {resolved}: it already holds a main clone of {repo}"
        )
    return resolved


def _same_repo(remote_url: str, repo: str) -> bool:
    """True when a remote URL (https or ssh form) points at exactly ``owner/repo``."""
    text = remote_url.strip().removesuffix(".git").rstrip("/")
    for prefix in (
        "https://github.com/",
        "http://github.com/",
        "git@github.com:",
        "ssh://git@github.com/",
    ):
        if text.startswith(prefix):
            return text[len(prefix) :].lower() == repo.lower()
    return False


def repo_url(repo: str) -> str:
    """Clone URL for ``owner/repo`` (tests replace this seam with a local path)."""
    return f"https://github.com/{repo}.git"


def ensure_clone(repo: str, clone_root: Path) -> Path:
    """Dedicated clone ``<root>/<owner>__<repo>`` (created on first use, never a shared main clone).

    The shared ``~/workspace/<repo>`` main clone is only used as a read-only ``--reference`` source
    and the new clone is ``--dissociate``d from it; nothing is ever fetched into the shared one.
    """
    root = _check_clone_root(Path(clone_root), repo)
    dest = root / repo.replace("/", "__")
    if (dest / ".git").exists() or (dest / "HEAD").exists():
        return dest
    seed = SEED_CLONE_ROOT / repo.split("/")[-1]
    url = repo_url(repo)
    use_seed = False
    if (seed / ".git").exists():
        try:
            r = subprocess.run(
                ["git", "-C", str(seed), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            origin = r.stdout.strip()
        except subprocess.TimeoutExpired:
            origin = ""  # an unreadable seed is simply not used

        # The seed is only an object source, and only when it is a clone of the SAME owner/repo;
        # the clone URL is always the requested repository, never the seed's origin.
        use_seed = origin == url or _same_repo(origin, repo)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", "-q", "--no-checkout"]
    if use_seed:
        cmd += ["--reference", str(seed), "--dissociate"]
    try:
        r = subprocess.run(
            [*cmd, url, str(dest)],
            capture_output=True,
            text=True,
            timeout=CLONE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # The killed clone cannot clean up after itself; a partial dest would be reused next run.
        shutil.rmtree(dest, ignore_errors=True)
        raise RuntimeError(f"clone of {repo} timed out after {exc.timeout}s") from exc
    if r.returncode != 0:
        raise RuntimeError(f"clone of {repo} failed: {r.stderr.strip()[:300]}")
    return dest


def cmd_run(args: argparse.Namespace, gh_json: Callable[..., object] | None = None) -> int:
    log = Path(args.log).expanduser()
    state_dir = log.parent
    gh_json = gh_json or make_ghc_json(Path(args.ghc).expanduser(), args.gh_delay)
    # errored scans are never logged, so they are never "seen" and get retried next run
    seen = {
        (r.get("repo"), r.get("pr"), r.get("head_sha")) for r in read_log(log) if not r.get("error")
    }
    counts = {"new": 0, "skipped_seen": 0, "flagged": 0, "flagged_refined": 0, "errors": 0}
    for repo in args.repo:
        clone = ensure_clone(repo, Path(args.clone_root).expanduser())
        if not args.no_fetch:
            git(clone, "fetch", "-q", "origin", "main")
        issues = IssueText(gh_json, state_dir / "issue_cache.json")
        fields = "number,title,body,mergedAt,mergeCommit,headRefOid"
        batches = []
        for state in ("merged", *(("open",) if args.open else ())):
            listing = gh_json(
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                state,
                "--limit",
                str(args.limit),
                "--json",
                fields,
            )
            batches.append((state, listing))
        for state, prs in batches:
            for pr in prs:  # type: ignore[union-attr]
                if (repo, pr["number"], pr["headRefOid"]) in seen:
                    counts["skipped_seen"] += 1
                    continue
                row = scan_pr(repo, pr, state, clone, issues)
                if row.get("error"):
                    counts["errors"] += 1
                    append_log(
                        state_dir / "errors.jsonl",
                        {
                            k: row[k]
                            for k in ("repo", "pr", "head_sha", "state", "error", "checked_at")
                        },
                    )
                    continue
                append_log(log, row)
                seen.add((repo, pr["number"], pr["headRefOid"]))
                counts["new"] += 1
                res = row.get("result") or {}
                counts["flagged"] += int(bool(res.get("flags")))
                counts["flagged_refined"] += int(bool(res.get("flags_refined")))
    print(json.dumps({"log": str(log), **counts}, sort_keys=True))
    return 0


# --------------------------------------------------------------------------- follow-up
def main_commits(clone: Path) -> dict[int, dict]:
    """PR number -> {sha, date, subject, parents} for first-parent commits of origin/main that are PR merges.

    Recognises squash subjects ending ``(#N)`` and ``Merge pull request #N from ...``.
    """
    out: dict[int, dict] = {}
    for line in git(
        clone, "log", "--first-parent", "origin/main", "--format=%H%x1f%cI%x1f%P%x1f%s"
    ).splitlines():
        sha, date, parents, subject = (line.split("\x1f") + ["", "", ""])[:4]
        m = MERGE_SUBJECT.match(subject) or SQUASH_SUBJECT.search(subject)
        if m:
            out.setdefault(
                int(m.group(1)),
                {"sha": sha, "date": date, "subject": subject, "parents": parents.split()},
            )
    return out


class FollowupError(RuntimeError):
    """A git failure while computing a follow-up; the PR's follow-up is unknown, not "clean"."""


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
        f"{commit}^1",
        commit,
        "--",
        *paths,
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


def is_ref_subject(subject: str, pr_number: int) -> bool:
    """Fix/revert word and ``#P`` (same repo, not ``owner/other#P``) both on the commit subject line."""
    own = SQUASH_SUBJECT.search(subject) or MERGE_SUBJECT.match(subject)
    if own and int(own.group(1)) == pr_number:
        return False
    return bool(
        FIX_WORD.search(subject)
        and re.search(rf"(?<![\w/]){re.escape(f'#{pr_number}')}\b", subject)
    )


def followup(
    clone: Path, merge_sha: str, pr_number: int, merged_iso: str, commits: list[dict] | None = None
) -> dict:
    """Follow-up signal for one merged PR; raises FollowupError on any git failure."""
    try:
        return _followup(clone, merge_sha, pr_number, merged_iso)
    except RuntimeError as exc:
        raise FollowupError(str(exc)) from exc


def _followup(clone: Path, merge_sha: str, pr_number: int, merged_iso: str) -> dict:
    start = dt.datetime.fromisoformat(merged_iso)
    until = start + dt.timedelta(days=FOLLOWUP_DAYS)
    # files and lines of the PR: diff against the first parent (squash commit or true merge)
    files = [
        f
        for f in git(
            clone, "diff", "--name-only", "--no-renames", f"{merge_sha}^1", merge_sha
        ).splitlines()
        if f
    ]
    parents = git(clone, "rev-list", "--parents", "-n", "1", merge_sha).split()[1:]
    owned = {merge_sha}
    if len(parents) > 1:  # true merge: blame attributes the lines to the branch commits
        owned.update(git(clone, "rev-list", f"{parents[0]}..{parents[1]}").split())
    later = []
    for line in git(
        clone,
        "log",
        "--first-parent",
        "--reverse",
        f"{merge_sha}..origin/main",
        "--format=%H%x1f%cI%x1f%B%x1e",
    ).split("\x1e"):
        line = line.strip("\n")
        if not line.strip():
            continue
        sha, date, msg = (line.split("\x1f") + ["", ""])[:3]
        if dt.datetime.fromisoformat(date) <= until:
            later.append({"sha": sha.strip(), "msg": msg})
    ref: list[str] = []
    touch: list[str] = []
    for c in later:
        subject = c["msg"].split("\n", 1)[0]
        if is_ref_subject(subject, pr_number):
            ref.append(c["sha"][:12])
            continue
        if not files:
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
                    f"{c['sha']}^1",
                    "--",
                    path,
                )
                if any(ln.split(" ", 1)[0] in owned for ln in blame.splitlines() if len(ln) > 40):
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
    """Rates per group; rows carry ``flagged`` (refined tier), ``iv1_flagged`` and follow-up booleans."""

    def rate(sub: list[dict], key: str) -> dict:
        n = len(sub)
        k = sum(1 for r in sub if r["follow"][key])
        return {"n": n, "k": k, "rate": round(k / n, 3) if n else None}

    groups = {
        "flagged": [r for r in rows if r["flagged"]],
        "unflagged": [r for r in rows if not r["flagged"]],
        "iv1_flagged": [r for r in rows if r.get("iv1_flagged")],
        "iv1_unflagged": [r for r in rows if not r.get("iv1_flagged")],
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
    unknown: list[dict] = []
    by_repo: dict[str, list[dict]] = {}
    for r in latest.values():
        by_repo.setdefault(r["repo"], []).append(r)
    for repo, rs in by_repo.items():
        clone = ensure_clone(repo, Path(args.clone_root).expanduser())
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
            try:
                fu = followup(clone, info["sha"], r["pr"], info["date"])
            except FollowupError as exc:
                unknown.append({"repo": repo, "pr": r["pr"], "error": str(exc)[:200]})
                continue
            res = r["result"]
            refined = res.get("flags_refined", res["flags"])  # v1 log lines had one tier
            scored.append({
                "repo": repo,
                "pr": r["pr"],
                "flagged": bool(refined),
                "iv1_flagged": bool(res["flags"]),
                "checks": sorted({f["check"] for f in refined}),
                "tamper": bool(res.get("tamper_refined", res["tamper"])),
                "api_delta": bool(res.get("api_delta_refined", res["api_delta"])),
                "follow": fu,
            })
    out = {
        "scored": len(scored),
        "pending_under_7d": pending,
        "not_merged_or_unknown": unmerged,
        "followup_unknown": {"n": len(unknown), "prs": [u["pr"] for u in unknown]},
        **summarize(scored),
    }
    if args.json:
        print(json.dumps(out, indent=2, sort_keys=True))
    else:
        print(
            f"scored {len(scored)} merged PRs (pending <7d: {pending}, not merged/unknown: {unmerged}, "
            f"follow-up unknown after git failure: {len(unknown)})"
        )
        for name in out:
            if name in ("scored", "pending_under_7d", "not_merged_or_unknown", "followup_unknown"):
                continue
            cells = "  ".join(f"{k}: {v['k']}/{v['n']} ({v['rate']})" for k, v in out[name].items())
            print(f"{name:14s} {cells}")
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
