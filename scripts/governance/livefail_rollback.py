#!/usr/bin/env python3
"""Open a draft revert PR (and hold the Gateway deployer) after LIVE_FAILED (#2532, #2453).

Owner decision (James, 2026-10-18, main session, 「第三點同意」): when an independent
confirmer judges a merged change LIVE_FAILED, stop the bleeding fast instead of only
labelling it.  This tool:

1. reads the Issue's comments and the origin PRs and asks
   ``nexus.services.livefail_rollback.evaluate_trigger`` whether an independent
   LIVE_FAILED verdict exists (``NEXUS_LIVE_FAILED_V1`` block or a promise report);
2. plans the revert on a throwaway detached worktree at ``origin/main``: a clean
   ``git revert`` becomes a **draft** PR (it still needs an independent review and
   green required checks; nothing is pushed to main); a conflicting revert, a
   commit that is not on main or one already reverted only produces manual advice;
   later main commits touching the same files are listed as dependents;
3. for a Gateway-class change, plans the deployer action under workspace-86's
   conditions: HOLD only while the failed merge is not yet live, only with
   ``--apply-hold``, only when no HOLD file or HOLD env exists (O_CREAT|O_EXCL);
   ``--release-hold`` removes only the exact HOLD text this tool wrote, only after
   the revert merged and within 6 h;
   ``status.json`` can lag the deployer by one cycle, so "not yet live" is a
   snapshot: a deploy finishing in the same minute wins and the plan falls back
   to the fast-revert advice on the next run;
4. appends a timing event to ``~/.local/state/nexus-livefail-rollback/events.jsonl``.

Without ``--apply`` nothing is written anywhere except the local throwaway worktree
(removed again); ``--apply-hold`` has no effect without ``--apply``.
Independence is text-level, as in #2595: every bot comment shares one login, so a
``confirmer`` name is trusted as written by a trusted, unedited comment.  ``--sweep`` lists open ``nexus:live-failed`` Issues and reports
which still lack a revert PR (read-only unless ``--apply``).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus.services.livefail_rollback import (  # noqa: E402
    LIVE_FAILED_LABEL,
    comment_trust_reason,
    evaluate_trigger,
    gateway_hold_plan,
    hold_text,
    is_gateway_class,
    minutes_between,
    pr_number_of,
    release_allowed,
    witness_declaration,
)

REPO = "James3014/Nexus-new"
DEFAULT_TRUSTED = ("James3014", "james3014-nexus-agent[bot]")
DEFAULT_SHARED = ("james3014-nexus-agent[bot]",)
BOT_GH = str(Path.home() / ".config/nexus-agent-bot/bin/nexus-agent-gh")
STATE = Path.home() / ".local/state/nexus-livefail-rollback"
DEPLOY_STATE = Path.home() / ".local/state/nexus-gateway-auto-deploy"
HOLD_ENV = "NEXUS_GATEWAY_AUTO_DEPLOY_HOLD"
_MARKER_RE = re.compile(r"^<!-- NEXUS_AUTHOR_SESSION_V1: ([A-Za-z0-9._-]{1,64}) -->$")
_CONFIRM_RE = re.compile(r"<!-- NEXUS_PROMISE_CONFIRMATION_V1\s*\n")
_BLOCK_PR_RE = re.compile(r'"origin_pr"\s*:\s*(\d{1,9})')


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sessions_in(*bodies: str) -> list[str]:
    out = []
    for body in bodies:
        for line in (body or "").splitlines():
            m = _MARKER_RE.match(line.strip())
            if m:
                out.append(m.group(1))
    return out


def run(cmd: list[str], cwd: str | Path | None = None, check: bool = True) -> str:
    out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and out.returncode != 0:
        raise subprocess.CalledProcessError(out.returncode, cmd, out.stdout, out.stderr)
    return out.stdout


# --- GitHub ----------------------------------------------------------------------


class Gh:
    def __init__(self, repo: str, read_bin: str, write_bin: str) -> None:
        self.repo, self.read, self.write = repo, read_bin, write_bin

    def api(self, *args: str) -> Any:
        return json.loads(run([self.read, "api", *args]) or "null")

    def issue(self, n: int) -> dict:
        return self.api(f"repos/{self.repo}/issues/{n}")

    def comments(self, n: int) -> list[dict]:
        data = self.api(
            "--paginate", "--slurp", f"repos/{self.repo}/issues/{n}/comments?per_page=100"
        )
        flat = [c for part in data for c in (part if isinstance(part, list) else [part])]
        return [
            {
                "body": c.get("body") or "",
                "created_at": c.get("created_at"),
                "updated_at": c.get("updated_at"),
                "author_association": c.get("author_association"),
                "author": (c.get("user") or {}).get("login", ""),
                "url": c.get("html_url"),
            }
            for c in flat
        ]

    def pr(self, m: int) -> dict:
        p = self.api(f"repos/{self.repo}/pulls/{m}")
        body = p.get("body") or ""
        return {
            "number": p["number"],
            "title": p.get("title") or "",
            "merge_sha": p.get("merge_commit_sha") if p.get("merged_at") else None,
            "merged_at": p.get("merged_at"),
            "author": (p.get("user") or {}).get("login", ""),
            "author_sessions": sessions_in(body),
            "witness": witness_declaration(body),
            "url": p.get("html_url"),
        }

    def open_revert_pr(self, branch: str) -> dict | None:
        owner = self.repo.split("/")[0]
        items = self.api(f"repos/{self.repo}/pulls?state=all&head={owner}:{branch}&per_page=5")
        return items[0] if items else None

    def live_failed_issues(self) -> list[int]:
        q = f"repo:{self.repo} is:issue is:open label:{LIVE_FAILED_LABEL}"
        data = self.api("-X", "GET", "search/issues", "-f", f"q={q}", "-f", "per_page=100")
        return [i["number"] for i in data.get("items", [])]

    def comment(self, issue: int, body: str) -> None:
        run([self.write, "issue", "comment", str(issue), "--repo", self.repo, "--body", body])

    def create_draft_pr(self, branch: str, title: str, body_file: Path) -> str:
        return run([
            self.write,
            "pr",
            "create",
            "--repo",
            self.repo,
            "--base",
            "main",
            "--head",
            branch,
            "--draft",
            "--title",
            title,
            "--body-file",
            str(body_file),
        ]).strip()


# --- git -------------------------------------------------------------------------


class Git:
    def __init__(self, repo_dir: Path, main_ref: str) -> None:
        self.dir, self.main_ref = repo_dir, main_ref

    def __call__(self, *args: str, cwd: Path | None = None, check: bool = True) -> str:
        return run(["git", "-C", str(cwd or self.dir), *args], check=check)

    def main_sha(self) -> str:
        return self("rev-parse", "--verify", f"{self.main_ref}^{{commit}}").strip()

    def has(self, sha: str) -> bool:
        probe = subprocess.run(
            ["git", "-C", str(self.dir), "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True
        )
        return probe.returncode == 0

    def contains(self, ancestor: str, commit: str) -> bool | None:
        if not (self.has(ancestor) and self.has(commit)):
            return None
        rc = subprocess.run(
            ["git", "-C", str(self.dir), "merge-base", "--is-ancestor", ancestor, commit],
            capture_output=True,
        ).returncode
        return True if rc == 0 else False if rc == 1 else None

    def parents(self, sha: str) -> int:
        return len(self("rev-list", "--parents", "-n", "1", sha).split()) - 1

    def files(self, sha: str) -> list[str]:
        extra = ["-m", "--first-parent"] if self.parents(sha) > 1 else []
        out = self("diff-tree", "--no-commit-id", "--name-only", "-r", *extra, sha)
        return sorted({line for line in out.splitlines() if line})


def plan_revert(git: Git, merge_shas: list[str]) -> dict[str, Any]:
    """Try the revert on a throwaway worktree; never touches the caller's checkout."""
    base = git.main_sha()
    plan: dict[str, Any] = {"base": base, "merge_shas": merge_shas, "dependents": [], "files": []}
    for m in merge_shas:
        if git.contains(m, base) is not True:
            return {**plan, "status": "MANUAL", "reason": f"NOT_ON_MAIN:{m[:12]}"}
        if git("log", "--format=%H", f"--grep=This reverts commit {m}", f"{m}..{base}").strip():
            return {**plan, "status": "MANUAL", "reason": f"ALREADY_REVERTED:{m[:12]}"}
    files = sorted({f for m in merge_shas for f in git.files(m)})
    plan["files"] = files
    oldest = min(merge_shas, key=lambda m: int(git("rev-list", "--count", m).strip()))
    later = git("log", "--format=%H%x09%s", f"{oldest}..{base}", "--", *files) if files else ""
    for line in later.splitlines():
        sha, _, subject = line.partition("\t")
        if sha in merge_shas:
            continue
        overlap = sorted(set(git.files(sha)) & set(files))
        plan["dependents"].append({
            "sha": sha,
            "pr": pr_number_of(subject),
            "subject": subject[:120],
            "files": overlap,
        })
    tmp = Path(tempfile.mkdtemp(prefix="livefail-revert-"))
    wt = tmp / "wt"
    try:
        git("worktree", "add", "--detach", "-q", str(wt), base)
        ordered = sorted(merge_shas, key=lambda m: -int(git("rev-list", "--count", m).strip()))
        for m in ordered:
            args = ["revert", "--no-commit", *(["-m", "1"] if git.parents(m) > 1 else []), m]
            proc = subprocess.run(["git", "-C", str(wt), *args], capture_output=True, text=True)
            if proc.returncode != 0:
                conflicts = git("diff", "--name-only", "--diff-filter=U", cwd=wt, check=False)
                return {
                    **plan,
                    "status": "MANUAL",
                    "reason": "REVERT_CONFLICT",
                    "conflicts": [c for c in conflicts.splitlines() if c],
                    "git_error": (proc.stderr or proc.stdout).strip()[-400:],
                }
        if not git("diff", "--cached", "--name-only", cwd=wt).strip():
            return {**plan, "status": "MANUAL", "reason": "REVERT_IS_EMPTY"}
        plan["diffstat"] = git("diff", "--cached", "--stat", cwd=wt).strip().splitlines()[-1:]
        plan["status"] = "CLEAN"
        plan["_worktree"] = str(wt)
        plan["_tmp"] = str(tmp)
        return plan
    finally:
        if plan.get("status") != "CLEAN":
            cleanup(git, wt, tmp)


def cleanup(git: Git, wt: Path, tmp: Path) -> None:
    if wt.is_dir():
        with contextlib.suppress(subprocess.CalledProcessError, OSError):
            git("revert", "--abort", cwd=wt, check=False)
    with contextlib.suppress(subprocess.CalledProcessError, OSError):
        git("worktree", "remove", "--force", str(wt), check=False)
    shutil.rmtree(tmp, ignore_errors=True)


# --- bodies ----------------------------------------------------------------------


def _advice_lines(plan: dict, gw: dict | None) -> list[str]:
    lines = []
    if plan.get("dependents"):
        lines.append(
            "**Later main commits touching the same files** (review before merging the revert):"
        )
        lines += [
            f"- {d['sha'][:12]} {('#' + str(d['pr'])) if d['pr'] else ''} {d['subject']} — {', '.join(d['files'][:6])}"
            for d in plan["dependents"]
        ]
    if gw:
        lines.append("")
        lines.append(
            f"**Gateway:** `{gw['action']}` ({gw['reason']}). previous_commit `{gw.get('previous_commit')}`, previous_root `{gw.get('previous_root')}`."
        )
        if gw.get("advice"):
            lines.append(gw["advice"])
    return lines


_CLOSING = re.compile(
    r"\b(close[sd]?|fix(?:e[sd])?|resolve[sd]?)(\s*:?\s*)((?:[\w.-]+/[\w.-]+)?#)(\d+)", re.I
)


def defuse_closing_keywords(text: str) -> str:
    """'fix #12' in copied subjects/witness text must not close Issue 12 on merge."""
    return _CLOSING.sub(lambda m: f"{m.group(1)}{m.group(2)}PR/issue {m.group(4)}", text)


def revert_pr_body(issue: int, trig: dict, prs: dict, plan: dict, gw: dict | None) -> str:
    return defuse_closing_keywords(_prose(issue, trig, prs, plan, gw)) + _blocks(
        issue, prs, trig, gw
    )


def _prose(issue: int, trig: dict, prs: dict, plan: dict, gw: dict | None) -> str:
    origin = ", ".join(f"#{n} ({prs[n]['merge_sha'][:12]})" for n in trig["origin_prs"])
    lines = [
        f"Draft revert after an independent LIVE_FAILED verdict on #{issue} (Refs #{issue}, Refs #2532).",
        "",
        f"- Origin PR(s): {origin}",
        f"- Verdict: {trig['source']} by `{trig['confirmer']}` at {trig['judged_at']}; witness: {trig['witness']}",
        f"- Reason: {trig['reason']}",
        f"- Reverted on main at `{plan['base']}`; files: {', '.join(plan['files'][:20])}{' …' if len(plan['files']) > 20 else ''}",
        "",
        "This PR was opened by `scripts/governance/livefail_rollback.py`. It is a **draft**: it merges only "
        "under the normal rule (independent Claude review, cross-model review if high risk, every required "
        "check green). If a forward fix is better, close this PR and name it on the Issue.",
        "",
        "If the tool held the Gateway deployer for this Issue, release it right after this PR merges: "
        f"`python scripts/governance/livefail_rollback.py --issue {issue} --release-hold`.",
        "",
        *_advice_lines(plan, gw),
        "",
    ]
    return "\n".join(lines)


def _blocks(issue: int, prs: dict, trig: dict, gw: dict | None) -> str:
    origin = ", ".join(f"PR {n} ({prs[n]['merge_sha'][:12]})" for n in trig["origin_prs"])
    lines = [
        "",
        f"<!-- NEXUS_CORE_ISSUE: {issue} -->",
        "<!-- NEXUS_ISSUE_INTENT_V1",
        json.dumps([{"issue": issue, "on_merge": "KEEP_OPEN"}]),
        "NEXUS_ISSUE_INTENT_V1 -->",
        "<!-- NEXUS_LIVE_WITNESS_V1",
        json.dumps({
            "surface": (gw and "gateway") or "library",
            "promise": f"behaviour returns to before {origin}",
            "witness": "the origin PR's own witness entry, rerun on the deployed revert",
            "window_hours": 48,
            "sensitive": False,
        }),
        "NEXUS_LIVE_WITNESS_V1 -->",
        "<!-- NEXUS_AUTHOR_SESSION_V1: livefail-rollback -->",
        "",
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
    ]
    return "\n".join(lines)


def manual_comment(issue: int, trig: dict, plan: dict, gw: dict | None) -> str:
    lines = [
        f"## LIVE_FAILED fast rollback — manual handling needed (#{issue})",
        "",
        f"Verdict {trig['source']} by `{trig['confirmer']}` at {trig['judged_at']} for "
        + ", ".join(f"#{n}" for n in trig["origin_prs"])
        + ".",
        f"No revert PR was opened: **{plan.get('reason')}**"
        + (f" (conflicts: {', '.join(plan.get('conflicts', []))})" if plan.get("conflicts") else "")
        + ".",
        "Suggested handling: write a forward fix naming the origin PR, or revert the dependent PRs "
        "below first (newest first) and rerun this tool. Split/refactor series (S1–S9) depend on each "
        "other in order; do not force a partial revert.",
        "",
        *_advice_lines(plan, gw),
    ]
    return "\n".join(lines)


# --- deployer HOLD (workspace-86 conditions) ----------------------------------------


def read_deployer(state_dir: Path) -> tuple[dict | None, dict | None, bool]:
    status = receipt = None
    with contextlib.suppress(OSError, ValueError):
        status = json.loads((state_dir / "status.json").read_text())
    with contextlib.suppress(OSError, ValueError, IndexError):
        receipt = json.loads((state_dir / "receipts.jsonl").read_text().splitlines()[-1])
    return status, receipt, (state_dir / "HOLD").exists()


def write_hold(state_dir: Path, text: str) -> bool:
    """O_CREAT|O_EXCL: never overwrite anyone's HOLD."""
    try:
        fd = os.open(state_dir / "HOLD", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    return True


def record_path(issue: int) -> Path:
    return STATE / "holds" / f"issue-{issue}.json"


def release_hold(
    state_dir: Path, issue: int, revert_merged: bool, now: str, apply: bool = True
) -> tuple[bool, str]:
    rec = record_path(issue)
    if not rec.is_file():
        return False, "NO_HOLD_WRITTEN_BY_THIS_TOOL"
    written = json.loads(rec.read_text(encoding="utf-8"))["text"]
    try:
        current = (state_dir / "HOLD").read_text(encoding="utf-8")
    except FileNotFoundError:
        current = None
    ok, why = release_allowed(
        current_text=current, written_text=written, revert_merged=revert_merged, now=now
    )
    if ok and not apply:
        return False, "RELEASE_DUE_DRY_RUN"
    if ok:
        # Move it aside atomically, re-check the moved bytes, and only then delete;
        # a HOLD rewritten in between is put back (never over a newer one).
        aside = state_dir / f"HOLD.livefail-release-{os.getpid()}"
        try:
            os.rename(state_dir / "HOLD", aside)
        except FileNotFoundError:
            return False, "HOLD_ABSENT"
        if aside.read_text(encoding="utf-8") != written:
            try:
                os.link(aside, state_dir / "HOLD")
                aside.unlink()
            except FileExistsError:
                pass  # a newer HOLD exists; keep both, the aside copy is evidence
            return False, "HOLD_TEXT_CHANGED"
        aside.unlink()
        rec.rename(rec.with_suffix(".released"))
    return ok, why


def notify_86(issue: int, text: str) -> None:
    coord = Path.home() / "workspace/agent-coord/bin/coord"
    note = (
        f"livefail-rollback: deployer HOLD for #{issue} is older than 6 h and was NOT released "
        f"automatically (your condition 4). Please decide. HOLD text: {text.strip()}"
    )
    with contextlib.suppress(OSError):
        subprocess.run(
            [str(coord), "msg", "workspace-86", "--as", "livefail-rollback", "--note", note],
            capture_output=True,
            timeout=60,
        )


# --- events ----------------------------------------------------------------------


def append_event(event: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")


def make_event(
    repo: str, issue: int, trig: dict, revert_at: str | None, gw_at: str | None, outcome: str
) -> dict:
    return {
        "event_id": f"{repo}#{issue}:{'+'.join(map(str, trig['origin_prs']))}:{trig['judged_at']}",
        "repo": repo.split("/")[-1],
        "issue": issue,
        "origin_pr": trig["origin_prs"],
        "judged_at": trig["judged_at"],
        "revert_pr_opened_at": revert_at,
        "gateway_action_at": gw_at,
        "minutes_to_revert_pr": minutes_between(trig["judged_at"], revert_at),
        "minutes_to_gateway_action": minutes_between(trig["judged_at"], gw_at),
        "outcome": outcome,
    }


# --- main ------------------------------------------------------------------------


def trusted(comments: list[dict], logins: list[str], now: str) -> list[dict]:
    return [c for c in comments if comment_trust_reason(c, logins, now) is None]


def latest_confirmation_at(comments: list[dict]) -> str | None:
    """Callers pass trusted, unedited comments only."""
    stamps = [c["created_at"] for c in comments if _CONFIRM_RE.search(c.get("body") or "")]
    return max(stamps) if stamps else None


def promise_report(issue: int, prs: list[int], repo: str, sessions: list[str]) -> dict | None:
    script = Path(__file__).with_name("promise_confirmation.py")
    cmd = [sys.executable, str(script), "--repo", repo, "--issue", str(issue), "--json"]
    for n in prs:
        cmd += ["--pr", str(n)]
    for name in sessions:
        cmd += ["--author-session", name]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        return None
    with contextlib.suppress(ValueError):
        return json.loads(out.stdout)
    return None


def handle_issue(args: argparse.Namespace, gh: Gh | None, git: Git, offline: dict | None) -> dict:
    now = args.now or (offline or {}).get("now") or utcnow()
    if offline is not None:
        comments, labels = offline["comments"], offline.get("labels", [])
        prs = {int(k): v for k, v in offline["origin_prs"].items()}
        for p in prs.values():
            p["author_sessions"] = [*(p.get("author_sessions") or []), *args.author_session]
        report = offline.get("promise_report")
        judged = offline.get("promise_judged_at")
        promise_prs = offline.get("promise_prs", [])
        table = {(a, c): v for a, c, v in offline.get("contains", [])}
        contains = (lambda a, c: table[(a, c)]) if table else git.contains
    else:
        assert gh is not None
        issue = gh.issue(args.issue)
        labels = [lb["name"] for lb in issue.get("labels", [])]
        comments = gh.comments(args.issue)
        good = trusted(comments, args.trusted_login, now)
        numbers = set(args.pr) | {
            int(n)
            for c in good
            for n in _BLOCK_PR_RE.findall(c["body"])
            if "NEXUS_LIVE_FAILED_V1" in c["body"]
        }
        prs = {}
        for n in sorted(numbers)[:20]:
            try:
                prs[n] = gh.pr(n)
            except (subprocess.CalledProcessError, KeyError, ValueError, TypeError):
                continue  # unknown PR: the block is then ignored as ORIGIN_PR_NOT_MERGED_OR_UNKNOWN
        issue_sessions = sessions_in(issue.get("body") or "")
        for p in prs.values():
            p["author_sessions"] = [*p["author_sessions"], *issue_sessions, *args.author_session]
        report = (
            promise_report(args.issue, args.pr, args.repo, [*issue_sessions, *args.author_session])
            if args.pr
            else None
        )
        judged = latest_confirmation_at(good)
        promise_prs = list(args.pr)
        contains = git.contains
    verdict = evaluate_trigger(
        comments=comments,
        origin_prs=prs,
        now=now,
        contains=contains,
        trusted_logins=args.trusted_login,
        shared_logins=args.shared_login,
        labels=labels,
        promise_report=report,
        promise_judged_at=judged,
        promise_prs=promise_prs,
    )
    result: dict[str, Any] = {"issue": args.issue, "verdict": verdict}
    trig = verdict["trigger"]
    if trig is None:
        result["outcome"] = "NOT_TRIGGERED"
        return result
    branch = f"livefail/revert-issue-{args.issue}-pr-{'-'.join(map(str, trig['origin_prs']))}"
    result["branch"] = branch
    if gh is not None:
        existing = gh.open_revert_pr(branch)
        if existing:
            result.update(outcome="REVERT_PR_EXISTS", revert_pr=existing.get("html_url"))
            return result
    # Gateway class?
    files_by_pr = sorted({f for m in trig["merge_shas"] if git.has(m) for f in git.files(m)})
    surfaces = [(prs[n].get("witness") or {}).get("surface") for n in trig["origin_prs"]]
    gw = None
    if is_gateway_class(surfaces, files_by_pr):
        status, receipt, hold_present = read_deployer(args.deploy_state)
        gw = gateway_hold_plan(
            merge_shas=trig["merge_shas"],
            status=status,
            hold_present=hold_present,
            hold_env=os.environ.get(HOLD_ENV, "") not in ("", "0"),
            contains=git.contains,
            last_receipt=receipt,
        )
    result["gateway"] = gw
    plan = plan_revert(git, trig["merge_shas"])
    result["plan"] = {k: v for k, v in plan.items() if not k.startswith("_")}
    gw_at = revert_at = None
    try:
        # A HOLD needs a revert PR that can merge and release it: --apply, a clean
        # plan, and --apply-hold (workspace-86: off by default).
        if (
            gw
            and gw["action"] == "HOLD"
            and args.apply_hold
            and args.apply
            and plan["status"] == "CLEAN"
        ):
            text = hold_text(
                args.issue, trig["origin_prs"], trig["merge_shas"], args.now or utcnow()
            )
            # Re-read the deployer right before writing: planning took seconds and a
            # switch in between would make the HOLD block the revert's own deploy.
            status, receipt, present = read_deployer(args.deploy_state)
            again = gateway_hold_plan(
                merge_shas=trig["merge_shas"],
                status=status,
                hold_present=present,
                hold_env=os.environ.get(HOLD_ENV, "") not in ("", "0"),
                contains=git.contains,
                last_receipt=receipt,
            )
            rec = record_path(args.issue)
            rec.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "text": text,
                "branch": branch,
                "event": make_event(args.repo, args.issue, trig, None, None, "HOLD"),
            }
            # Record first, so a HOLD can never exist without the record that releases it.
            rec.write_text(json.dumps(record), encoding="utf-8")
            if again["action"] == "HOLD" and write_hold(args.deploy_state, text):
                gw_at = utcnow()
                gw["applied"] = True
                if gh is not None:
                    gh.comment(
                        args.issue,
                        f"livefail-rollback: Gateway auto-deployer HOLD written at {gw_at} so the failed merge does not go live.\n\n```\n{text}```\nRelease: `python scripts/governance/livefail_rollback.py --issue {args.issue} --release-hold` after the revert merges (only this exact text is removed; after 6 h workspace-86 decides).",
                    )
            else:
                rec.unlink()
                gw["applied"] = False
                gw["reason"] = (
                    "HOLD_APPEARED_CONCURRENTLY" if again["action"] == "HOLD" else again["reason"]
                )
        if not args.apply or gh is None:
            result["outcome"] = "DRY_RUN_" + plan["status"]
            if gw_at:
                append_event(make_event(args.repo, args.issue, trig, None, gw_at, "HOLD_ONLY"))
            return result
        if plan["status"] == "CLEAN":
            wt = Path(plan["_worktree"])
            msg = (
                f"revert: #{', #'.join(map(str, trig['origin_prs']))} after LIVE_FAILED on #{args.issue} (Refs #{args.issue})\n\n"
                + "\n".join(f"This reverts commit {m}." for m in trig["merge_shas"])
                + f"\n\nRefs #{args.issue}. Refs #2532.\n"
            )
            git(
                "-c",
                "user.name=james3014-nexus-agent[bot]",
                "-c",
                "user.email=341779647+james3014-nexus-agent[bot]@users.noreply.github.com",
                "commit",
                "-q",
                "-m",
                msg,
                cwd=wt,
            )
            git(
                "-c",
                "credential.helper=",
                "-c",
                f"credential.helper=!{args.gh_write} auth git-credential",
                "push",
                "-q",
                "--force",  # tool-owned livefail/ branch; a run that died before `pr create`
                "origin",
                f"HEAD:refs/heads/{branch}",
                cwd=wt,
            )
            body = Path(plan["_tmp"]) / "body.md"
            body.write_text(revert_pr_body(args.issue, trig, prs, plan, gw), encoding="utf-8")
            title = f"revert: #{', #'.join(map(str, trig['origin_prs']))} (LIVE_FAILED on #{args.issue})"
            url = gh.create_draft_pr(branch, title, body)
            revert_at = utcnow()
            gh.comment(
                args.issue,
                f"livefail-rollback: draft revert PR opened {url} (normal review and required checks apply before merge).",
            )
            result.update(outcome="REVERT_PR_OPENED", revert_pr=url)
        else:
            gh.comment(args.issue, manual_comment(args.issue, trig, plan, gw))
            result["outcome"] = "MANUAL_ADVICE_POSTED"
        append_event(make_event(args.repo, args.issue, trig, revert_at, gw_at, result["outcome"]))
        return result
    finally:
        if plan.get("status") == "CLEAN":
            cleanup(git, Path(plan["_worktree"]), Path(plan["_tmp"]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--issue", type=int)
    ap.add_argument("--pr", type=int, action="append", default=[], help="origin PR (promise path)")
    ap.add_argument("--apply", action="store_true", help="open the draft PR / post advice")
    ap.add_argument(
        "--apply-hold", action="store_true", help="write the deployer HOLD (off by default)"
    )
    ap.add_argument("--release-hold", action="store_true")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--repo-dir", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--main-ref", default="origin/main")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--deploy-state", type=Path, default=DEPLOY_STATE)
    ap.add_argument("--gh-read", default=os.environ.get("NEXUS_GH_BIN", "gh"))
    ap.add_argument("--gh-write", default=BOT_GH)
    ap.add_argument("--trusted-login", action="append", default=list(DEFAULT_TRUSTED))
    ap.add_argument("--shared-login", action="append", default=list(DEFAULT_SHARED))
    ap.add_argument(
        "--author-session",
        action="append",
        default=[],
        help="author session of the origin PR(s) when the PR body has no marker",
    )
    ap.add_argument("--offline-input", type=Path)
    ap.add_argument("--now")
    args = ap.parse_args(argv)
    git = Git(args.repo_dir, args.main_ref)
    try:
        offline = json.loads(args.offline_input.read_text()) if args.offline_input else None
        gh = None if offline is not None else Gh(args.repo, args.gh_read, args.gh_write)
        if not args.no_fetch and offline is None:
            git("fetch", "-q", "origin", "main")
        if args.release_hold:
            if args.issue is None:
                ap.error("--release-hold needs --issue")
            merged = False
            rec = record_path(args.issue)
            if gh is not None and rec.is_file():
                pr = gh.open_revert_pr(json.loads(rec.read_text(encoding="utf-8"))["branch"])
                merged = bool(pr and pr.get("merged_at"))
            ok, why = release_hold(args.deploy_state, args.issue, merged, args.now or utcnow())
            if ok and gh is not None:
                gh.comment(
                    args.issue,
                    f"livefail-rollback: Gateway auto-deployer HOLD released at {utcnow()} (revert merged).",
                )
            print(json.dumps({"released": ok, "reason": why}))
            return 0 if ok else 1
        if args.sweep:
            if gh is None:
                ap.error("--sweep needs GitHub")
            rows = []
            for n in gh.live_failed_issues():
                sub = argparse.Namespace(**{**vars(args), "issue": n, "pr": []})
                try:
                    res = handle_issue(sub, gh, git, None)
                except (
                    subprocess.CalledProcessError,
                    OSError,
                    ValueError,
                    KeyError,
                    TypeError,
                ) as exc:
                    rows.append({"issue": n, "outcome": "ERROR", "error": type(exc).__name__})
                    continue
                rows.append({
                    "issue": n,
                    "outcome": res.get("outcome"),
                    "reasons": res["verdict"]["reason_codes"],
                })
            holds = STATE / "holds"
            for rec in sorted(holds.glob("issue-*.json")) if holds.is_dir() else []:
                data = json.loads(rec.read_text(encoding="utf-8"))
                n = int(rec.stem.split("-")[1])
                pr = gh.open_revert_pr(data["branch"])
                merged = bool(pr and pr.get("merged_at"))
                ok, why = release_hold(args.deploy_state, n, merged, utcnow(), apply=args.apply)
                if ok:
                    append_event({
                        **data["event"],
                        "outcome": "HOLD_RELEASED",
                        "released_at": utcnow(),
                    })
                if why == "HOLD_OLDER_THAN_6H_ASK_WORKSPACE_86":
                    notify_86(n, data["text"])
                rows.append({
                    "hold_issue": n,
                    "revert_merged": merged,
                    "released": ok,
                    "reason": why,
                })
            print(json.dumps({"sweep": rows, "at": utcnow()}, indent=2))
            return 0
        if args.issue is None:
            ap.error("--issue is required")
        res = handle_issue(args, gh, git, offline)
        print(json.dumps(res, indent=2, sort_keys=True, default=str))
        return 0
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError) as exc:
        detail = (getattr(exc, "stderr", "") or str(exc)).strip().splitlines()
        print(
            f"livefail_rollback: {type(exc).__name__}: {detail[0] if detail else ''}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
