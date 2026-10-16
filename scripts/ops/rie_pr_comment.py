#!/usr/bin/env python3
"""Render and upsert the one Repository Intelligence sticky PR comment.

Owner decision 2026-10-13 (reverses the "no PR comments" non-goal of #969):
surface Repository Intelligence as ONE concise, actionable comment per PR.

Security model (runs under ``pull_request_target`` with a write token):

* This file, and everything it executes, comes from the default branch. The PR
  head is never checked out, imported, or executed. Fork PRs are skipped.
* PR data (paths, check names) is read only through the GitHub API and is
  treated as untrusted text: control and bidi characters are stripped, the
  value is length-limited, and it is rendered only inside code spans.
* The pinned Repository Intelligence engine decides overlap, impact, and
  systemic failures. This script only acquires inputs, runs the engine with
  ``python -I``, and renders its results.
* The impact graph is built by parsing default-branch Python with ``ast``
  (never importing it).

API budget: one GraphQL query reads every open PR (files and check rollup), the
recent main commits' check rollup, and the existing comments; a second small
GraphQL query (only when some check is failing) reads when each failing
workflow file last changed on main; at most one REST write updates the comment.

Stdlib only, so ``python3 -I`` works on a bare runner.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.request
import warnings
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

MARKER = "<!-- nexus-rie-sticky-comment:v1 -->"
# GraphQL reports the Actions bot as login "github-actions" with type "Bot".
BOT_LOGIN = "github-actions"
BOT_TYPENAME = "Bot"
NOTHING_TO_FLAG = "RIE: nothing to flag"
ELLIPSIS = "..."

API_URL = "https://api.github.com"
MAX_OPEN_PRS = 60
MAX_FILES = 100
MAX_CONTEXTS = 100
MAX_MAIN_COMMITS = 20
MAX_COMMENTS = 100
MAX_WORKFLOW_PATHS = 20
MAX_ITEM_CHARS = 100
MAX_FILES_PER_OVERLAP = 4
MAX_OVERLAP_LINES = 8
MAX_IMPACT_AREAS = 5
MAX_SYSTEMIC_LINES = 5
MAX_PRS_PER_SYSTEMIC = 6
MAX_NOTE_PRS = 8
MAX_COMMENT_CHARS = 4000
ENGINE_TIMEOUT_SECONDS = 120
MAX_GRAPH_ERRORS = 20

# Zero-width and bidi controls, written as code points so the source itself
# never contains invisible characters.
_BIDI_AND_INVISIBLE = frozenset(
    chr(code)
    for code in (
        0x200B,
        0x200C,
        0x200D,
        0x2060,
        0xFEFF,
        *range(0x202A, 0x202F),
        *range(0x2066, 0x206A),
    )
)


class CommentError(RuntimeError):
    """Expected, reportable failure (API, engine, or input shape)."""


# --------------------------------------------------------------- sanitizing


def sanitize_text(value: Any, limit: int = MAX_ITEM_CHARS) -> str:
    """Make untrusted PR text safe to place inside a Markdown code span."""
    text = value if isinstance(value, str) else str(value)
    cleaned = []
    for char in text:
        if char in _BIDI_AND_INVISIBLE:
            continue
        if unicodedata.category(char).startswith("C"):  # control/format/private/unassigned
            cleaned.append(" ")
            continue
        cleaned.append("'" if char == "`" else char)
    collapsed = " ".join("".join(cleaned).split())
    if not collapsed:
        return "?"
    if len(collapsed) > limit:
        return collapsed[: max(1, limit - len(ELLIPSIS))] + ELLIPSIS
    return collapsed


def code(value: Any, limit: int = MAX_ITEM_CHARS) -> str:
    return f"`{sanitize_text(value, limit)}`"


# --------------------------------------------------------------- rendering


def is_test_path(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return bool(parts) and (parts[0] in {"tests", "test"} or parts[-1].startswith("test_"))


def impact_areas(paths: Iterable[str], depth: int = 2) -> list[tuple[str, int]]:
    """Group file paths into directory areas (top ``depth`` components)."""
    counts: Counter[str] = Counter()
    for path in paths:
        parts = PurePosixPath(path).parts
        area = "/".join(parts[:depth]) if len(parts) > depth else "/".join(parts[:-1]) or "."
        counts[area] += 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


@dataclass(frozen=True)
class SystemicLine:
    check_name: str
    workflow_path: str
    pr_numbers: Sequence[int]


@dataclass(frozen=True)
class Findings:
    overlaps: Mapping[int, Sequence[str]] = field(default_factory=dict)
    direct_impacted: Sequence[str] = ()
    all_impacted: Sequence[str] = ()
    systemic: Sequence[SystemicLine] = ()
    notes: Sequence[str] = ()
    guard_delta: GuardDelta | None = None


# ------------------------------------------------- guard semantic delta (#1580)

GUARD_DELTA_SCHEMA = "nexus.rie_guard_semantic_delta_advisory.v1"
GUARD_DELTA_CLAIM_CEILING = "RIE_GUARD_SEMANTIC_DELTA_PR_REVIEW_ADVISORY_ONLY"
GUARD_DELTA_FLAGGED = frozenset({"TIGHTENS", "LOOSENS", "MIXED", "UNKNOWN"})
MAX_GUARD_WITNESSES = 3
MAX_GUARD_FILE_BYTES = 1_000_000


@dataclass(frozen=True)
class GuardDelta:
    """Verified (or explicitly not observed) guard semantic delta for this PR."""

    observed: bool
    reason: str = ""
    family: str = "canonical_owner_table"
    classification: str = "NOT_OBSERVED"
    attention: str = ""
    report_sha: str = ""
    tightening: Sequence[str] = ()
    tightening_total: int = 0
    loosening: Sequence[str] = ()
    loosening_total: int = 0
    reason_codes: Sequence[str] = ()
    reason_codes_total: int = 0


def _not_observed(reason: str) -> GuardDelta:
    return GuardDelta(observed=False, reason=reason)


def _guard_canonical_hash(value: Mapping[str, Any]) -> str:
    # Must stay byte-identical to rie_guard_delta_evidence.canonical_hash (parity-tested).
    return hashlib.sha256(
        json.dumps(
            dict(value), ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def _guard_refs(block: Any) -> tuple[list[str], int]:
    mapping = _map(block)
    items = [str(v) for v in _list(mapping.get("items")) if isinstance(v, str)]
    total = mapping.get("total")
    return items, total if isinstance(total, int) and total >= len(items) else len(items)


def load_guard_delta(path: Path | str, pr_number: int, head_sha: str | None = None) -> GuardDelta:
    """Read and verify the guard-delta projection. Any failure is NOT_OBSERVED, never UNCHANGED."""
    try:
        file_path = Path(path)
        if file_path.stat().st_size > MAX_GUARD_FILE_BYTES:
            return _not_observed("FILE_TOO_LARGE")
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _not_observed("FILE_MISSING")
    except (OSError, ValueError):
        return _not_observed("FILE_UNREADABLE")
    if not isinstance(raw, dict):
        return _not_observed("BAD_SHAPE")
    if raw.get("schema") != GUARD_DELTA_SCHEMA:
        return _not_observed("BAD_SCHEMA")
    if raw.get("claim_ceiling") != GUARD_DELTA_CLAIM_CEILING:
        return _not_observed("BAD_CLAIM_CEILING")
    seal = raw.get("content_sha256")
    try:
        body_hash = _guard_canonical_hash({k: v for k, v in raw.items() if k != "content_sha256"})
    except (TypeError, ValueError):
        return _not_observed("BAD_SHAPE")
    if not isinstance(seal, str) or seal != body_hash:
        return _not_observed("BAD_SEAL")
    identity = _map(raw.get("new_identity"))
    if identity.get("pr_number") != pr_number or isinstance(identity.get("pr_number"), bool):
        return _not_observed("IDENTITY_MISMATCH")
    if head_sha is not None and identity.get("head_sha") != head_sha:
        return _not_observed("IDENTITY_MISMATCH")
    classification = raw.get("classification")
    if raw.get("disposition") != "OBSERVED" or classification == "NOT_OBSERVED":
        reason = raw.get("reason")
        return _not_observed(str(reason) if isinstance(reason, str) and reason else "INCOMPLETE")
    if classification != "UNCHANGED" and classification not in GUARD_DELTA_FLAGGED:
        return _not_observed("BAD_CLASSIFICATION")
    tightening, tightening_total = _guard_refs(raw.get("tightening_witnesses"))
    loosening, loosening_total = _guard_refs(raw.get("loosening_witnesses"))
    codes, codes_total = _guard_refs(raw.get("reason_codes"))
    return GuardDelta(
        observed=True,
        family=str(raw.get("guard_family") or "?"),
        classification=str(classification),
        attention=str(raw.get("reviewer_attention") or ""),
        report_sha=str(raw.get("report_content_sha256") or "")[:12],
        tightening=tightening[:MAX_GUARD_WITNESSES],
        tightening_total=tightening_total,
        loosening=loosening[:MAX_GUARD_WITNESSES],
        loosening_total=loosening_total,
        reason_codes=codes[:MAX_GUARD_WITNESSES],
        reason_codes_total=codes_total,
    )


def _guard_witnesses(label: str, items: Sequence[str], total: int) -> str:
    if not items:
        return ""
    shown = ", ".join(code(item) for item in items)
    extra = total - len(items)
    return f"; {label} {shown}" + (f" (+{extra} more)" if extra > 0 else "")


def render_guard_delta(guard: GuardDelta) -> tuple[str | None, str | None]:
    """Return (flagged line, note); exactly one is set."""
    if not guard.observed:
        return None, (
            f"guard semantic delta not observed ({code(guard.reason)}); "
            "this is not an unchanged result"
        )
    sha = code(guard.report_sha or "?", 12)
    if guard.classification == "UNCHANGED":
        return None, (
            f"guard semantic delta ({code(guard.family)}) {code(guard.classification)}, "
            f"report {sha}, static evidence only (behavioral probes not run), advisory only"
        )
    attention = f", reviewer attention {code(guard.attention)}" if guard.attention else ""
    detail = _guard_witnesses("tightening", guard.tightening, guard.tightening_total)
    detail += _guard_witnesses("loosening", guard.loosening, guard.loosening_total)
    if guard.classification == "UNKNOWN":
        detail += _guard_witnesses("reasons", guard.reason_codes, guard.reason_codes_total)
    return (
        f"- Guard semantic delta ({code(guard.family)}): {code(guard.classification)}"
        f"{attention}{detail}; report {sha}"
    ), None


def _pr_refs(numbers: Sequence[int], limit: int) -> str:
    refs = ", ".join(f"#{int(n)}" for n in list(numbers)[:limit])
    return refs + (f", {ELLIPSIS}" if len(numbers) > limit else "")


def render_comment(findings: Findings) -> str:
    lines: list[str] = []
    overlap_items = sorted(findings.overlaps.items())
    for number, paths in overlap_items[:MAX_OVERLAP_LINES]:
        shown = ", ".join(code(path) for path in list(paths)[:MAX_FILES_PER_OVERLAP])
        extra = len(paths) - MAX_FILES_PER_OVERLAP
        suffix = f" (+{extra} more)" if extra > 0 else ""
        lines.append(f"- Overlaps with open PR #{int(number)} on {shown}{suffix}")
    if len(overlap_items) > MAX_OVERLAP_LINES:
        lines.append(f"- Overlaps with {len(overlap_items) - MAX_OVERLAP_LINES} more open PRs")

    if findings.all_impacted:
        tests = [path for path in findings.all_impacted if is_test_path(path)]
        source = [path for path in findings.all_impacted if not is_test_path(path)]
        areas = impact_areas(source or tests)
        shown = ", ".join(f"{code(area)} ({count})" for area, count in areas[:MAX_IMPACT_AREAS])
        extra = len(areas) - MAX_IMPACT_AREAS
        suffix = f", +{extra} more areas" if extra > 0 else ""
        test_note = f", {len(tests)} of them tests" if source and tests else ""
        lines.append(
            f"- Impact: {len(findings.all_impacted)} files depend on the changed code "
            f"({len(findings.direct_impacted)} directly{test_note}): {shown}{suffix}"
        )

    for item in list(findings.systemic)[:MAX_SYSTEMIC_LINES]:
        where = f" in {code(item.workflow_path)}" if item.workflow_path else ""
        lines.append(
            f"- Check {code(item.check_name)}{where} is failing on {len(item.pr_numbers)} open PRs "
            f"({_pr_refs(item.pr_numbers, MAX_PRS_PER_SYSTEMIC)}), likely systemic"
        )

    notes = list(findings.notes)
    if findings.guard_delta is not None:
        guard_line, guard_note = render_guard_delta(findings.guard_delta)
        if guard_line:
            lines.append(guard_line)
        if guard_note:
            notes.append(guard_note)
    body_lines = [*(lines or [NOTHING_TO_FLAG]), *(f"- Note: {note}" for note in notes)]
    body = "\n".join([MARKER, *body_lines])
    if len(body) > MAX_COMMENT_CHARS:
        kept: list[str] = []
        for line in body_lines:
            if len("\n".join([MARKER, *kept, line])) > MAX_COMMENT_CHARS - 40:
                break
            kept.append(line)
        omitted = len(body_lines) - len(kept)
        body = "\n".join([MARKER, *kept, f"- {ELLIPSIS}{omitted} more lines omitted"])
    return body


# ---------------------------------------------------------------- GitHub API


class GitHubClient:
    def __init__(self, token: str, api_url: str = API_URL, timeout: float = 30.0) -> None:
        if not token:
            raise CommentError("GITHUB_TOKEN is required")
        if not api_url.startswith("https://"):
            raise CommentError("GitHub API URL must be https")
        self.token = token
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self.calls: Counter[str] = Counter()

    def request(self, method: str, path: str, body: Any = None) -> Any:
        if not path.startswith("/") or path.startswith("//"):
            raise CommentError("API path must be host-relative")
        self.calls["graphql" if path == "/graphql" else "rest"] += 1
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"{self.api_url}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "nexus-rie-pr-comment",
                **({"Content-Type": "application/json"} if data is not None else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310  # nosec B310 - https-only API host
                raw = response.read(16 * 1024 * 1024 + 1)
        except urllib.error.HTTPError as exc:
            raise CommentError(f"GitHub HTTP {exc.code} for {method} {path}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise CommentError(f"GitHub request failed for {method} {path}: {exc}") from exc
        if len(raw) > 16 * 1024 * 1024:
            raise CommentError("GitHub response exceeded 16 MiB")
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CommentError(f"GitHub returned invalid JSON for {path}") from exc

    def graphql(self, query: str, variables: Mapping[str, Any]) -> dict[str, Any]:
        payload = self.request("POST", "/graphql", {"query": query, "variables": dict(variables)})
        if (
            not isinstance(payload, Mapping)
            or payload.get("errors")
            or not isinstance(payload.get("data"), Mapping)
        ):
            raise CommentError("GitHub GraphQL query failed")
        return dict(payload["data"])


_CONTEXTS = """
  totalCount
  nodes {
    __typename
    ... on CheckRun {
      databaseId name conclusion status startedAt completedAt
      checkSuite { databaseId app { slug } workflowRun { file { path } workflow { databaseId } } }
    }
    ... on StatusContext { context state createdAt }
  }
"""

OVERVIEW_QUERY = f"""
fragment Pr on PullRequest {{
  number headRefOid baseRefOid isCrossRepository
  files(first: {MAX_FILES}) {{ totalCount nodes {{ path }} }}
  commits(last: 1) {{ nodes {{ commit {{ statusCheckRollup {{
    contexts(first: {MAX_CONTEXTS}) {{ {_CONTEXTS} }} }} }} }} }}
}}
query($owner: String!, $name: String!, $number: Int!) {{
  repository(owner: $owner, name: $name) {{
    defaultBranchRef {{ target {{ ... on Commit {{
      oid
      history(first: {MAX_MAIN_COMMITS}) {{ nodes {{ statusCheckRollup {{
        contexts(first: {MAX_CONTEXTS}) {{ {_CONTEXTS} }} }} }} }}
    }} }} }}
    pullRequests(states: OPEN, first: {MAX_OPEN_PRS}, orderBy: {{field: UPDATED_AT, direction: DESC}}) {{
      totalCount nodes {{ ...Pr }}
    }}
    pullRequest(number: $number) {{
      ...Pr
      comments(last: {MAX_COMMENTS}) {{ totalCount nodes {{ databaseId body author {{ login __typename }} }} }}
    }}
  }}
}}
"""


def workflow_changes_query(count: int) -> str:
    """Aliased ``history(path:)`` lookups; paths travel only as variables."""
    params = "".join(f", $p{i}: String!" for i in range(count))
    fields = " ".join(
        f"w{i}: history(first: 1, path: $p{i}) {{ nodes {{ committedDate }} }}"
        for i in range(count)
    )
    return (
        f"query($owner: String!, $name: String!{params}) {{ repository(owner: $owner, name: $name) {{ "
        f"defaultBranchRef {{ target {{ ... on Commit {{ {fields} }} }} }} }} }}"
    )


# --------------------------------------------------------- data acquisition


@dataclass(frozen=True)
class PullRequestData:
    number: int
    head_sha: str
    base_sha: str
    changed_files: tuple[str, ...]
    checks: tuple[dict[str, Any], ...] = ()
    files_truncated: bool = False
    checks_truncated: bool = False
    is_cross_repository: bool = False


@dataclass(frozen=True)
class Acquisition:
    this_pr: PullRequestData
    pulls: tuple[PullRequestData, ...]
    open_total: int
    main_sha: str
    main_checks: tuple[dict[str, Any], ...]
    comments: tuple[dict[str, Any], ...]
    main_checks_truncated: bool = False
    comments_truncated: bool = False


def _map(value: Any) -> Mapping[str, Any]:
    """Untrusted JSON object, or an empty mapping."""
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    """Untrusted JSON array, or an empty list."""
    return value if isinstance(value, list) else []


def check_summary(node: Mapping[str, Any]) -> dict[str, Any] | None:
    """Normalize a GraphQL rollup context into the engine's check shape.

    Check runs carry the identity the engine needs to tell runs of the same
    check apart: check-run id, app, check suite, workflow id and path.
    """
    if node.get("__typename") == "CheckRun":
        name = node.get("name")
        status = node.get("conclusion") or node.get("status")
        if not isinstance(name, str) or not isinstance(status, str):
            return None
        suite = _map(node.get("checkSuite"))
        run = _map(suite.get("workflowRun"))
        optional = {
            "check_run_id": node.get("databaseId"),
            "completed_at": node.get("completedAt"),
            "started_at": node.get("startedAt"),
            "check_suite_id": suite.get("databaseId"),
            "app_slug": _map(suite.get("app")).get("slug"),
            "workflow_id": _map(run.get("workflow")).get("databaseId"),
            "workflow_path": _map(run.get("file")).get("path"),
        }
        summary: dict[str, Any] = {"name": name, "status": status.lower()}
        summary.update({key: value for key, value in optional.items() if value is not None})
        return summary
    if node.get("__typename") == "StatusContext":
        name, state = node.get("context"), node.get("state")
        if not isinstance(name, str) or not isinstance(state, str):
            return None
        summary = {"name": name, "status": state.lower()}
        if isinstance(node.get("createdAt"), str):
            summary["completed_at"] = node["createdAt"]
        return summary
    return None


def _contexts(rollup_owner: Any) -> tuple[list[dict[str, Any]], bool]:
    contexts = _map(_map(_map(rollup_owner).get("statusCheckRollup")).get("contexts"))
    nodes = _list(contexts.get("nodes"))
    checks = [c for c in (check_summary(n) for n in nodes if isinstance(n, Mapping)) if c]
    total = contexts.get("totalCount")
    return checks, isinstance(total, int) and total > len(nodes)


def _pull_request(node: Mapping[str, Any]) -> PullRequestData | None:
    number, head, base = node.get("number"), node.get("headRefOid"), node.get("baseRefOid")
    if not isinstance(number, int) or not isinstance(head, str) or not isinstance(base, str):
        return None
    files = _map(node.get("files"))
    paths = tuple(
        sorted({
            path for f in _list(files.get("nodes")) if isinstance(path := _map(f).get("path"), str)
        })
    )
    total = files.get("totalCount")
    commit_nodes = _list(_map(node.get("commits")).get("nodes"))
    commit = _map(commit_nodes[-1]).get("commit") if commit_nodes else None
    checks, checks_truncated = _contexts(commit)
    return PullRequestData(
        number=number,
        head_sha=head,
        base_sha=base,
        changed_files=paths,
        checks=tuple(checks),
        files_truncated=isinstance(total, int) and total > len(paths),
        checks_truncated=checks_truncated,
        is_cross_repository=node.get("isCrossRepository") is True,
    )


def collect(client: GitHubClient, repository: str, pr_number: int) -> Acquisition:
    owner, _, name = repository.partition("/")
    data = client.graphql(OVERVIEW_QUERY, {"owner": owner, "name": name, "number": pr_number})
    repo = _map(data.get("repository"))
    target = _map(_map(repo.get("defaultBranchRef")).get("target"))
    main_sha = target.get("oid")
    if not isinstance(main_sha, str) or len(main_sha) != 40:
        raise CommentError("default branch SHA unavailable")
    main_checks: list[dict[str, Any]] = []
    main_truncated = False
    for commit in _list(_map(target.get("history")).get("nodes")):
        commit_checks, commit_truncated = _contexts(commit)
        main_checks.extend(commit_checks)
        main_truncated = main_truncated or commit_truncated

    listing = _map(repo.get("pullRequests"))
    by_number: dict[int, PullRequestData] = {}
    for node in _list(listing.get("nodes")):
        pr = _pull_request(_map(node))
        if pr is not None:
            by_number[pr.number] = pr
    this_node = _map(repo.get("pullRequest"))
    this_pr = _pull_request(this_node)
    if this_pr is None:
        raise CommentError("pull request unavailable")
    by_number[this_pr.number] = this_pr
    comment_listing = _map(this_node.get("comments"))
    comments = tuple(dict(c) for c in _list(comment_listing.get("nodes")) if isinstance(c, Mapping))
    comment_total = comment_listing.get("totalCount")
    open_total = listing.get("totalCount")
    return Acquisition(
        this_pr=this_pr,
        pulls=tuple(by_number[n] for n in sorted(by_number)),
        open_total=open_total if isinstance(open_total, int) else len(by_number),
        main_sha=main_sha,
        main_checks=tuple(main_checks),
        comments=comments,
        main_checks_truncated=main_truncated,
        comments_truncated=isinstance(comment_total, int) and comment_total > len(comments),
    )


_FAILING = {"failure", "failed", "error", "timed_out"}


def failing_workflow_paths(pulls: Sequence[PullRequestData]) -> list[str]:
    """Every workflow file with a failing check on some open PR (uncapped)."""
    return sorted({
        check["workflow_path"]
        for pr in pulls
        for check in pr.checks
        if isinstance(check.get("workflow_path"), str) and check.get("status") in _FAILING
    })


def collect_workflow_changes(
    client: GitHubClient, repository: str, pulls: Sequence[PullRequestData]
) -> dict[str, str]:
    """When each failing check's workflow file last changed on main."""
    paths = failing_workflow_paths(pulls)[:MAX_WORKFLOW_PATHS]
    if not paths:
        return {}
    owner, _, name = repository.partition("/")
    variables: dict[str, Any] = {"owner": owner, "name": name}
    variables.update({f"p{i}": path for i, path in enumerate(paths)})
    data = client.graphql(workflow_changes_query(len(paths)), variables)
    target = _map(_map(_map(data.get("repository")).get("defaultBranchRef")).get("target"))
    changed: dict[str, str] = {}
    for i, path in enumerate(paths):
        nodes = _list(_map(target.get(f"w{i}")).get("nodes"))
        committed = _map(nodes[0]).get("committedDate") if nodes else None
        if isinstance(committed, str):
            changed[path] = committed
    return changed


def truncation_notes(acq: Acquisition) -> list[str]:
    """Say what was not compared instead of silently truncating."""
    notes: list[str] = []
    if acq.open_total > len(acq.pulls):
        notes.append(
            f"compared only the {len(acq.pulls)} most recently updated of {acq.open_total} open PRs"
        )
    if acq.this_pr.files_truncated:
        notes.append(
            f"this PR changes more than {MAX_FILES} files; overlap and impact use the first {MAX_FILES}"
        )
    others = [
        pr.number for pr in acq.pulls if pr.files_truncated and pr.number != acq.this_pr.number
    ]
    if others:
        notes.append(
            f"file lists of open PRs {_pr_refs(others, MAX_NOTE_PRS)} were cut at {MAX_FILES}; overlaps with them may be incomplete"
        )
    checks = [pr.number for pr in acq.pulls if pr.checks_truncated]
    if checks:
        notes.append(
            f"check lists of open PRs {_pr_refs(checks, MAX_NOTE_PRS)} were cut at {MAX_CONTEXTS}; systemic detection may be incomplete"
        )
    if acq.main_checks_truncated:
        notes.append(
            f"main check history was cut at {MAX_CONTEXTS} checks per commit; systemic cutoffs may be incomplete"
        )
    workflows = len(failing_workflow_paths(acq.pulls))
    if workflows > MAX_WORKFLOW_PATHS:
        notes.append(
            f"only {MAX_WORKFLOW_PATHS} of {workflows} failing workflows were checked for recent changes on main"
        )
    if acq.comments_truncated:
        notes.append(
            f"this PR has more than {MAX_COMMENTS} comments; an earlier RIE comment outside that window may be duplicated"
        )
    return notes


# --------------------------------------------------- default-branch import graph


def _tracked_python_files(repo_root: Path) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z", "--", "*.py"],
            capture_output=True,
            check=True,
            timeout=60,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise CommentError("unable to list default-branch Python files") from exc
    return sorted(p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p)


def _module_name(path: str) -> str:
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve(module: str, modules: Mapping[str, str]) -> str | None:
    parts = module.split(".")
    while parts:
        hit = modules.get(".".join(parts))
        if hit is not None:
            return hit
        parts.pop()
    return None


def build_import_graph(
    repo_root: Path, files: Sequence[str] | None = None
) -> tuple[list[str], list[dict[str, str]], list[str]]:
    """Parse (never import) Python files and return (covered, edges, errors)."""
    paths = list(files) if files is not None else _tracked_python_files(repo_root)
    modules = {_module_name(path): path for path in paths if _module_name(path)}
    edges: set[tuple[str, str]] = set()
    errors: list[str] = []
    for path in paths:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                tree = ast.parse((repo_root / path).read_bytes(), filename=path)
        except (SyntaxError, ValueError, OSError) as exc:
            errors.append(f"{path}: {type(exc).__name__}")
            continue
        package = _module_name(path)
        if not path.endswith("__init__.py"):
            package = package.rpartition(".")[0]
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    anchor = package.split(".") if package else []
                    anchor = anchor[: len(anchor) - (node.level - 1)] if node.level > 1 else anchor
                    base = ".".join([*anchor, base] if base else anchor)
                targets = [f"{base}.{alias.name}" if base else alias.name for alias in node.names]
                if base:
                    targets.append(base)
            for target in targets:
                dependency = _resolve(target, modules)
                if dependency and dependency != path:
                    edges.add((path, dependency))
    edge_rows = [{"consumer": c, "dependency": d} for c, d in sorted(edges)]
    return paths, edge_rows, errors


# -------------------------------------------------------------- engine calls

EngineRunner = Callable[[str, Mapping[str, Any]], dict[str, Any]]


def engine_runner(
    engine_root: Path, engine_pin: str, python_bin: str = sys.executable
) -> EngineRunner:
    """Run the pinned engine CLI in isolated mode; verify the checkout pin first."""
    try:
        head = subprocess.run(
            ["git", "-C", str(engine_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError) as exc:
        raise CommentError("engine checkout unverifiable") from exc
    if head != engine_pin:
        raise CommentError("engine checkout does not match the pin")
    bootstrap = (
        "import sys;sys.path.insert(0, sys.argv.pop(1));"
        "from repository_intelligence.cli import main;sys.exit(main(sys.argv[1:]))"
    )

    def run(operation: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            proc = subprocess.run(
                [
                    python_bin,
                    "-I",
                    "-c",
                    bootstrap,
                    str(engine_root),
                    "--operation",
                    operation,
                    "--input",
                    "-",
                ],
                input=json.dumps(payload, sort_keys=True),
                capture_output=True,
                text=True,
                timeout=ENGINE_TIMEOUT_SECONDS,
                check=False,
                cwd=str(engine_root),
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise CommentError(f"engine {operation} could not run") from exc
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise CommentError(f"engine {operation} returned malformed output") from exc
        if (
            proc.returncode != 0
            or envelope.get("operation") != operation
            or not isinstance(envelope.get("result"), dict)
        ):
            raise CommentError(
                f"engine {operation} failed: {sanitize_text(envelope.get('error', ''), 200)}"
            )
        return envelope["result"]

    return run


def _snapshot(repository: str, pr: PullRequestData, main_sha: str) -> dict[str, Any]:
    return {
        "repository": repository,
        "pr_number": pr.number,
        "head_sha": pr.head_sha,
        "base_sha": pr.base_sha,
        "current_main_sha": main_sha,
        "changed_files": list(pr.changed_files),
        "mergeable": None,
    }


def analyze(
    repository: str,
    acq: Acquisition,
    graph: tuple[Sequence[str], Sequence[Mapping[str, str]], Sequence[str]],
    workflow_changed_at: Mapping[str, str],
    run_engine: EngineRunner,
    observed_at: str,
) -> Findings:
    this_pr = acq.this_pr
    overlap = run_engine(
        "overlap", {"snapshots": [_snapshot(repository, pr, acq.main_sha) for pr in acq.pulls]}
    )
    overlaps: dict[int, list[str]] = {}
    for pair in overlap.get("overlap_pairs", []):
        left, right, paths = pair.get("pr_a"), pair.get("pr_b"), pair.get("shared_paths", [])
        if this_pr.number in (left, right):
            other = right if left == this_pr.number else left
            if isinstance(other, int):
                overlaps[other] = sorted(str(p) for p in paths)

    covered, edges, errors = graph
    impact = run_engine(
        "impact",
        {
            "snapshot": _snapshot(repository, this_pr, acq.main_sha),
            "covered_files": sorted(set(covered) | set(this_pr.changed_files)),
            "dependency_edges": list(edges),
            "graph_complete": not errors,
            "graph_errors": list(errors[:MAX_GRAPH_ERRORS]),
        },
    )
    changed = set(this_pr.changed_files)
    direct = [p for p in impact.get("direct_impacted_files", []) if p not in changed]
    every = [p for p in impact.get("all_impacted_files", []) if p not in changed]

    systemic_report = run_engine(
        "systemic",
        {
            "repository": repository,
            "observed_at": observed_at,
            "pull_requests": [
                {"pr_number": pr.number, "checks": list(pr.checks)} for pr in acq.pulls
            ],
            "main_checks": list(acq.main_checks),
            "workflow_changed_at": dict(workflow_changed_at),
        },
    )
    systemic = [
        SystemicLine(
            check_name=str(item.get("check_name")),
            workflow_path=str(item.get("workflow_path") or ""),
            pr_numbers=[int(n) for n in item.get("pr_numbers", []) if isinstance(n, int)],
        )
        for item in systemic_report.get("systemic_failures", [])
        if isinstance(item, Mapping)
    ]
    return Findings(
        overlaps=overlaps,
        direct_impacted=direct,
        all_impacted=every,
        systemic=systemic,
        notes=truncation_notes(acq),
    )


# ----------------------------------------------------------- sticky upsert


def find_sticky_comment(comments: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """The bot-authored comment carrying MARKER; user comments are ignored."""
    for comment in comments:
        author = _map(comment.get("author"))
        if (
            isinstance(comment.get("body"), str)
            and comment["body"].startswith(MARKER)
            and author.get("login") == BOT_LOGIN
            and author.get("__typename") == BOT_TYPENAME
            and isinstance(comment.get("databaseId"), int)
        ):
            return comment
    return None


def upsert_sticky_comment(
    client: GitHubClient,
    repository: str,
    pr_number: int,
    comments: Iterable[Mapping[str, Any]],
    body: str,
) -> str:
    """Create or update the single bot-authored comment carrying MARKER."""
    existing = find_sticky_comment(comments)
    if existing is not None:
        if existing.get("body") == body:
            return "UNCHANGED"
        client.request(
            "PATCH",
            f"/repos/{repository}/issues/comments/{int(existing['databaseId'])}",
            {"body": body},
        )
        return "UPDATED"
    client.request("POST", f"/repos/{repository}/issues/{pr_number}/comments", {"body": body})
    return "CREATED"


# ---------------------------------------------------------------------- CLI


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _summary(path: str, text: str) -> None:
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render and upsert the Repository Intelligence sticky PR comment."
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument(
        "--repo-root", type=Path, required=True, help="default-branch checkout (never the PR head)"
    )
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--engine-pin", required=True)
    parser.add_argument(
        "--post", action="store_true", help="upsert the sticky comment (otherwise dry run)"
    )
    parser.add_argument("--step-summary", default="")
    parser.add_argument(
        "--guard-delta-json",
        default=None,
        help="sealed guard semantic delta projection (advisory); omitted = not rendered",
    )
    args = parser.parse_args(argv)

    owner, _, name = args.repository.partition("/")
    if not owner or not name or "/" in name or args.pr_number <= 0:
        print("invalid repository or PR number", file=sys.stderr)
        return 2
    client: GitHubClient | None = None
    try:
        client = GitHubClient(
            os.environ.get("GITHUB_TOKEN", ""), os.environ.get("GITHUB_API_URL", API_URL)
        )
        acq = collect(client, args.repository, args.pr_number)
        if acq.this_pr.is_cross_repository:
            raise CommentError("fork pull request; not commented")
        run_engine = engine_runner(args.engine_root, args.engine_pin)
        workflow_changed = collect_workflow_changes(client, args.repository, acq.pulls)
        findings = analyze(
            args.repository,
            acq,
            build_import_graph(args.repo_root),
            workflow_changed,
            run_engine,
            _utc_now(),
        )
        if args.guard_delta_json is not None:
            guard = load_guard_delta(args.guard_delta_json, args.pr_number, acq.this_pr.head_sha)
            findings = replace(findings, guard_delta=guard)
        body = render_comment(findings)
        if args.post:
            outcome = upsert_sticky_comment(
                client, args.repository, args.pr_number, acq.comments, body
            )
        else:
            outcome = "DRY_RUN"
    except CommentError as exc:
        # Advisory surface: report and leave any existing comment untouched.
        message = f"RIE comment skipped: {sanitize_text(exc, 300)}"
        print(message, file=sys.stderr)
        _summary(args.step_summary, message)
        return 0
    assert client is not None
    calls = f"api calls: graphql={client.calls['graphql']} rest={client.calls['rest']}"
    print(body)
    print(f"sticky comment: {outcome}; {calls}", file=sys.stderr)
    _summary(
        args.step_summary,
        f"sticky comment: {outcome}; {calls}\n\n{body.replace(MARKER, '').strip()}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
