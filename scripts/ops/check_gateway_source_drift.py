#!/usr/bin/env python3
"""Read-only drift check between the live MCP Gateway source and published main (#1900).

Owner decision (Issue #1900, 2026-10-12T23:47:51Z): the live Gateway may run
only commits published on GitHub ``main``, or an exact published PR head
(open or merged PR) during a bounded rebind.  The check reads the Gateway
``/health`` identity and classifies:

* a loaded ``git_head`` that is neither reachable from published main nor an
  exact published PR head: alert ``GATEWAY_SOURCE_UNPUBLISHED(n)``, where n is
  the number of commits not on main (the JSON lists the paths they touch);
  Owner refinement (#1900, 2026-10-13T02:09:54Z): when EVERY unpublished commit
  touches only ``tasks/`` paths (a merge is judged by its diff against its
  first parent) the finding is INFO ``GATEWAY_BIND_ONLY_LOCAL_COMMITS(n)``
  instead; root cause is tracked in #1939.  Any path outside ``tasks/`` keeps
  the alert;
* lag of the published base (newest ancestor of ``git_head`` on main) behind
  main: warning ``GATEWAY_BEHIND_MAIN(n)`` when n > 50 commits or main's tip is
  more than 7 days newer than the base; below that, OK.

Auto-deploy (#2153): when the deployer's receipt log exists, the report also
carries ``auto_deploy`` (the last receipt from
``scripts/ops/nexus_gateway_auto_deploy.py``) and the summary names it.

It never starts, stops, reloads or rebinds anything.  The only write paths are
``git fetch`` into the analysis clone (objects and remote-tracking refs) and,
only when ``--report-issue`` is passed explicitly, one deduplicated Issue
comment.  Routine deploys are the #2153 auto-deployer's job and need no Owner
activation (Owner decision 2026-10-14, #2155); a manual #526 rebind is only
the emergency fallback (hold -> manual rebind -> adopt -> release).

Exit codes: 0 = OK/INFO, 1 = WARN/ALERT, 2 = probe failure.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ops.nexus_gateway_auto_deploy import last_receipt  # noqa: E402
from scripts.ops.run_golden_behavior_eval import (  # noqa: E402
    GATEWAY_HEALTH_URL,
    _fetch_gateway_health,
    _is_object_id,
)

SCHEMA = "nexus.gateway_source_drift.v1"
REPORT_MARKER = "<!-- GATEWAY_DRIFT_REPORT -->"
DEFAULT_REPORT_REPO = "James3014/Nexus-new"
DEFAULT_MAIN_REF = "origin/main"
TASK_BINDING_PREFIX = "tasks/"
BEHIND_MAX_COMMITS = 50
BEHIND_MAX_SECONDS = 7 * 24 * 60 * 60
REMEDY = (
    "let the #2153 auto-deployer catch up (no Owner activation needed, #2155); emergency only:"
    " hold, manual #526 rebind, adopt, release"
)
DEFAULT_AUTO_DEPLOY_STATE = Path.home() / ".local/state/nexus-gateway-auto-deploy"
BIND_ONLY_NOTE = "bind-only local task commits; root cause tracked in #1939"

OK, INFO, WARN, ALERT, PROBE_FAILURE = "OK", "INFO", "WARN", "ALERT", "PROBE_FAILURE"
EXIT_CODES = {OK: 0, INFO: 0, WARN: 1, ALERT: 1, PROBE_FAILURE: 2}
_RANK = {OK: 0, INFO: 1, WARN: 2, ALERT: 3}

# Returns the numbers of open or merged PRs whose head SHA equals the given SHA.
PrHeadLookup = Callable[[str], list[int]]


class ProbeError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _git_out(repo: Path, *args: str, code: str = "GIT_FAILED") -> str:
    result = _git(repo, *args)
    if result.returncode != 0:
        raise ProbeError(code, f"git {' '.join(args)}: {result.stderr.strip()[:300]}")
    return result.stdout


def _has_commit(repo: Path, sha: str) -> bool:
    return _git(repo, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def read_health(fetch: Callable[[], Any]) -> dict[str, Any]:
    try:
        health = fetch()
    except (OSError, ValueError) as exc:
        # URLError/timeouts are OSError; JSON decode errors are ValueError.
        if isinstance(exc, ValueError):
            raise ProbeError("GATEWAY_HEALTH_MALFORMED", f"invalid JSON: {exc}") from exc
        raise ProbeError("GATEWAY_HEALTH_UNREACHABLE", str(exc)) from exc
    if not isinstance(health, dict):
        raise ProbeError("GATEWAY_HEALTH_MALFORMED", "health payload is not an object")
    if not _is_object_id(health.get("git_head")):
        raise ProbeError("GATEWAY_HEALTH_MALFORMED", "git_head missing or not a 40-hex SHA")
    return health


def _resolve_head(repo: Path, head: str, source_repo: str | None) -> None:
    if _has_commit(repo, head):
        return
    if source_repo:
        # Read-only on the source: copies the objects into the analysis clone.
        _git(repo, "fetch", "--quiet", "--no-tags", source_repo, head)
    if not _has_commit(repo, head):
        raise ProbeError(
            "GATEWAY_HEAD_UNRESOLVABLE",
            f"{head} not present in {repo} (source repo: {source_repo or 'none'})",
        )


def _changed_paths(repo: Path, commit: str) -> list[str]:
    # A merge is judged by its diff against its first parent; plain commits by
    # their own diff.
    if _git(repo, "rev-parse", "--verify", "--quiet", f"{commit}^2^{{commit}}").returncode == 0:
        out = _git_out(repo, "diff", "--name-only", f"{commit}^1", commit)
    else:
        out = _git_out(repo, "diff-tree", "-r", "--no-commit-id", "--name-only", "--root", commit)
    return [line for line in out.splitlines() if line]


def analyze(
    repo: Path,
    health: dict[str, Any],
    *,
    main_ref: str = DEFAULT_MAIN_REF,
    source_repo: str | None = None,
    pr_head_lookup: PrHeadLookup | None = None,
) -> dict[str, Any]:
    head = health["git_head"]
    _resolve_head(repo, head, source_repo)
    main = _git_out(
        repo, "rev-parse", "--verify", f"{main_ref}^{{commit}}", code="MAIN_REF_UNRESOLVABLE"
    ).strip()
    base_result = _git(repo, "merge-base", head, main)
    if base_result.returncode != 0 or not base_result.stdout.strip():
        raise ProbeError("NO_PUBLISHED_BASE", f"{head} shares no history with {main_ref}")
    base = base_result.stdout.strip()

    findings: list[dict[str, Any]] = []
    unpublished = _git_out(repo, "rev-list", "--reverse", f"{base}..{head}").split()
    pr_lookup = "NOT_NEEDED"
    if unpublished:
        published_prs: list[int] = []
        if pr_head_lookup is None:
            pr_lookup = "SKIPPED_OFFLINE"
        else:
            published_prs = sorted(pr_head_lookup(head))
            pr_lookup = "MATCHED" if published_prs else "NO_MATCH"
        if published_prs:
            findings.append({
                "code": f"GATEWAY_PUBLISHED_PR_HEAD(#{published_prs[0]})",
                "severity": INFO,
                "pull_requests": published_prs,
            })
        else:
            touched = sorted({p for commit in unpublished for p in _changed_paths(repo, commit)})
            outside = [p for p in touched if not p.startswith(TASK_BINDING_PREFIX)]
            bind_only = not outside
            findings.append({
                "code": (
                    f"GATEWAY_BIND_ONLY_LOCAL_COMMITS({len(unpublished)})"
                    if bind_only
                    else f"GATEWAY_SOURCE_UNPUBLISHED({len(unpublished)})"
                ),
                "severity": INFO if bind_only else ALERT,
                "touched_paths": touched[:100],
                "touched_paths_outside_tasks": outside[:100],
                **({"note": BIND_ONLY_NOTE} if bind_only else {}),
            })

    behind = int(_git_out(repo, "rev-list", "--count", f"{base}..{main}").strip())
    base_time = int(_git_out(repo, "show", "-s", "--format=%ct", base).strip())
    main_time = int(_git_out(repo, "show", "-s", "--format=%ct", main).strip())
    lag_seconds = main_time - base_time
    if behind:
        reasons = []
        if behind > BEHIND_MAX_COMMITS:
            reasons.append(f"MORE_THAN_{BEHIND_MAX_COMMITS}_COMMITS")
        if lag_seconds > BEHIND_MAX_SECONDS:
            reasons.append("MORE_THAN_7_DAYS")
        if reasons:
            findings.append({
                "code": f"GATEWAY_BEHIND_MAIN({behind})",
                "severity": WARN,
                "reasons": reasons,
                "lag_seconds": lag_seconds,
            })

    verdict = max((f["severity"] for f in findings), key=_RANK.__getitem__, default=OK)
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "findings": findings,
        "git_head": head,
        "published_base": base,
        "main_ref": main_ref,
        "main_head": main,
        "unpublished_commits": unpublished,
        "pr_head_lookup": pr_lookup,
        "behind_main": behind,
        "lag_seconds": lag_seconds,
        "observed": {
            k: health.get(k)
            for k in (
                "repo_root_hmac_sha256",
                "repo_head_at_start",
                "repo_head_current",
                "reload_required",
                "server_instance_id",
            )
        },
    }


def _auto_deploy_source(state_dir: Path, head: str) -> str | None:
    """Deployment tree of the #2153 auto-deployer that holds ``head``, if any."""
    try:
        receipt = last_receipt(state_dir)
    except OSError:
        return None
    for key in ("deployment_root", "previous_root"):
        root = (receipt or {}).get(key)
        if isinstance(root, str) and root.endswith(head) and Path(root).is_dir():
            return root
    return None


def failure_report(error: ProbeError) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "verdict": PROBE_FAILURE,
        "findings": [{"code": error.code, "severity": PROBE_FAILURE, "detail": error.detail}],
    }


def summarize(report: dict[str, Any]) -> str:
    codes = ", ".join(f["code"] for f in report["findings"]) or "in sync with main"
    line = f"gateway-source-drift {report['verdict']}: {codes}"
    if report["verdict"] in (WARN, ALERT):
        line += f" -- remedy: {REMEDY}"
    elif report["verdict"] == PROBE_FAILURE:
        line += " -- drift unknown (fail closed)"
    if any(f["code"].startswith("GATEWAY_BIND_ONLY_LOCAL_COMMITS") for f in report["findings"]):
        line += f" -- {BIND_ONLY_NOTE}"
    receipt = report.get("auto_deploy")
    if isinstance(receipt, dict):
        line += (
            f" -- last auto-deploy {receipt.get('outcome')} "
            f"{str(receipt.get('candidate_commit'))[:12]} at {receipt.get('finished_at')}"
        )
    return line


def comment_body(report: dict[str, Any]) -> str:
    return (
        f"{REPORT_MARKER}\n**Gateway source drift report** (read-only, `scripts/ops/check_gateway_source_drift.py`)\n\n"
        f"`{summarize(report)}`\n\n```json\n{json.dumps(report, indent=2, sort_keys=True)}\n```\n"
    )


GhRunner = Callable[[Sequence[str], str | None], str]


def _run_gh(args: Sequence[str], stdin: str | None) -> str:
    result = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ProbeError("REPORT_FAILED", f"gh {' '.join(args[:3])}: {result.stderr.strip()[:300]}")
    return result.stdout


def gh_pr_head_lookup(repo_slug: str, gh: GhRunner = _run_gh) -> PrHeadLookup:
    def lookup(sha: str) -> list[int]:
        try:
            out = gh(
                [
                    "pr",
                    "list",
                    "-R",
                    repo_slug,
                    "--state",
                    "all",
                    "--search",
                    sha,
                    "--json",
                    "number,headRefOid,state",
                    "--limit",
                    "20",
                ],
                None,
            )
        except ProbeError as exc:
            raise ProbeError("PR_LOOKUP_FAILED", exc.detail) from exc
        try:
            prs = json.loads(out or "[]")
        except ValueError as exc:
            raise ProbeError("PR_LOOKUP_FAILED", f"invalid gh output: {exc}") from exc
        return [
            p["number"]
            for p in prs
            if p.get("headRefOid") == sha and p.get("state") in ("OPEN", "MERGED")
        ]

    return lookup


def report_to_issue(
    report: dict[str, Any], issue: int, repo_slug: str, gh: GhRunner = _run_gh
) -> str:
    """Create or edit the single marker-tagged comment; returns 'created' or 'updated'."""
    listing = gh(
        [
            "api",
            "--paginate",
            f"repos/{repo_slug}/issues/{issue}/comments",
            "--jq",
            ".[] | {id, body}",
        ],
        None,
    )
    existing = None
    for line in listing.splitlines():
        if line.strip():
            item = json.loads(line)
            if REPORT_MARKER in (item.get("body") or ""):
                existing = item["id"]
    payload = json.dumps({"body": comment_body(report)})
    if existing is not None:
        gh(
            ["api", "-X", "PATCH", f"repos/{repo_slug}/issues/comments/{existing}", "--input", "-"],
            payload,
        )
        return "updated"
    gh(["api", "-X", "POST", f"repos/{repo_slug}/issues/{issue}/comments", "--input", "-"], payload)
    return "created"


def main(
    argv: Sequence[str] | None = None,
    *,
    fetch_health: Callable[[str], Any] | None = None,
    gh: GhRunner | None = None,
    pr_head_lookup: PrHeadLookup | None = None,
) -> int:
    gh = gh or _run_gh
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--health-url", default=GATEWAY_HEALTH_URL)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        "--main-ref",
        default=None,
        help=f"use this ref as published main without fetching (default: fetch origin, use {DEFAULT_MAIN_REF})",
    )
    parser.add_argument(
        "--source-repo",
        default=None,
        help="where to fetch the deployed git_head from when absent (default: legacy health repo_root, else the auto-deploy receipt)",
    )
    parser.add_argument(
        "--json", action="store_true", help="print the JSON report instead of the summary line"
    )
    parser.add_argument(
        "--auto-deploy-state",
        type=Path,
        default=DEFAULT_AUTO_DEPLOY_STATE,
        help="state dir of the #2153 auto-deployer whose last receipt is reported",
    )
    parser.add_argument("--report-issue", type=int, default=None)
    parser.add_argument(
        "--report-repo", default=DEFAULT_REPORT_REPO, help="GitHub repo for PR lookup and reports"
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="skip the published-PR-head lookup (an unpublished head then alerts)",
    )
    args = parser.parse_args(argv)

    fetch = fetch_health or (lambda url: _fetch_gateway_health(url))
    try:
        health = read_health(lambda: fetch(args.health_url))
        main_ref = args.main_ref
        if main_ref is None:
            fetched = _git(args.repo, "fetch", "--quiet", "--no-tags", "origin", "main")
            if fetched.returncode != 0:
                raise ProbeError("MAIN_FETCH_FAILED", fetched.stderr.strip()[:300])
            main_ref = DEFAULT_MAIN_REF
        source_repo = args.source_repo
        if (
            source_repo is None
            and isinstance(health.get("repo_root"), str)
            and Path(health["repo_root"]).is_dir()
        ):
            source_repo = health["repo_root"]
        if source_repo is None:
            # #2153 layout: deployments/a1-<sha> worktrees named by the receipt.
            source_repo = _auto_deploy_source(args.auto_deploy_state, health["git_head"])
        lookup = (
            None if args.offline else (pr_head_lookup or gh_pr_head_lookup(args.report_repo, gh))
        )
        report = analyze(
            args.repo, health, main_ref=main_ref, source_repo=source_repo, pr_head_lookup=lookup
        )
    except ProbeError as error:
        report = failure_report(error)
    try:
        report["auto_deploy"] = last_receipt(args.auto_deploy_state)
    except OSError:
        report["auto_deploy"] = None
    report["summary"] = summarize(report)

    print(json.dumps(report, sort_keys=True) if args.json else report["summary"])
    exit_code = EXIT_CODES[report["verdict"]]
    if args.report_issue is not None:
        try:
            action = report_to_issue(report, args.report_issue, args.report_repo, gh)
            print(f"report {action} on {args.report_repo}#{args.report_issue}", file=sys.stderr)
        except (ProbeError, ValueError, KeyError) as exc:
            print(f"REPORT_FAILED: {exc}", file=sys.stderr)
            return EXIT_CODES[PROBE_FAILURE]
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
