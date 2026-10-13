#!/usr/bin/env python3
"""Render and upsert the one Repository Intelligence sticky PR comment.

Owner decision 2026-10-13 (reverses the "no PR comments" non-goal of #969):
surface Repository Intelligence as ONE concise, actionable comment per PR.

Security model (runs under ``pull_request_target`` with a write token):

* This file, and everything it executes, comes from the default branch. The PR
  head is never checked out, imported, or executed.
* PR data (paths, check names) is read only through the GitHub REST API and is
  treated as untrusted text: control and bidi characters are stripped, the
  value is length-limited, and it is rendered only inside code spans.
* The pinned Repository Intelligence engine decides overlap, impact, and
  systemic failures. This script only acquires inputs, runs the engine with
  ``python -I``, and renders its results.
* The impact graph is built by parsing default-branch Python with ``ast``
  (never importing it).

Stdlib only, so ``python3 -I`` works on a bare runner.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import warnings
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

MARKER = "<!-- nexus-rie-sticky-comment:v1 -->"
BOT_LOGIN = "github-actions[bot]"
NOTHING_TO_FLAG = "RIE: nothing to flag"

API_URL = "https://api.github.com"
MAX_OPEN_PRS = 60
MAX_PAGES = 10
MAX_ITEM_CHARS = 100
MAX_FILES_PER_OVERLAP = 4
MAX_OVERLAP_LINES = 8
MAX_IMPACT_AREAS = 5
MAX_SYSTEMIC_LINES = 5
MAX_PRS_PER_SYSTEMIC = 6
MAX_COMMENT_CHARS = 4000
ENGINE_TIMEOUT_SECONDS = 120
MAX_GRAPH_ERRORS = 20

_BIDI_AND_INVISIBLE = {
    "​",
    "‌",
    "‍",
    "⁠",
    "﻿",
    *(chr(code) for code in range(0x202A, 0x202F)),
    *(chr(code) for code in range(0x2066, 0x206A)),
}


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
        category = unicodedata.category(char)
        if category.startswith("C"):  # control, format, surrogate, private, unassigned
            cleaned.append(" ")
            continue
        cleaned.append("'" if char == "`" else char)
    collapsed = " ".join("".join(cleaned).split())
    if not collapsed:
        return "?"
    if len(collapsed) > limit:
        return collapsed[: max(1, limit - 1)] + "…"
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
class Findings:
    overlaps: Mapping[int, Sequence[str]] = field(default_factory=dict)
    direct_impacted: Sequence[str] = ()
    all_impacted: Sequence[str] = ()
    systemic: Sequence[tuple[str, Sequence[int]]] = ()


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

    for name, numbers in list(findings.systemic)[:MAX_SYSTEMIC_LINES]:
        refs = ", ".join(f"#{int(n)}" for n in list(numbers)[:MAX_PRS_PER_SYSTEMIC])
        more = ", …" if len(numbers) > MAX_PRS_PER_SYSTEMIC else ""
        lines.append(
            f"- Check {code(name)} is failing on {len(numbers)} open PRs ({refs}{more}), likely systemic"
        )

    body_lines = lines or [NOTHING_TO_FLAG]
    body = "\n".join([MARKER, *body_lines])
    if len(body) > MAX_COMMENT_CHARS:
        kept: list[str] = []
        for line in body_lines:
            if len("\n".join([MARKER, *kept, line])) > MAX_COMMENT_CHARS - 40:
                break
            kept.append(line)
        body = "\n".join([MARKER, *kept, f"- …{len(body_lines) - len(kept)} more lines omitted"])
    return body


# ------------------------------------------------------------- GitHub REST


class GitHubClient:
    def __init__(self, token: str, api_url: str = API_URL, timeout: float = 30.0) -> None:
        if not token:
            raise CommentError("GITHUB_TOKEN is required")
        if not api_url.startswith("https://"):
            raise CommentError("GitHub API URL must be https")
        self.token = token
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout

    def request(
        self, method: str, path: str, params: Mapping[str, Any] | None = None, body: Any = None
    ) -> Any:
        if not path.startswith("/") or path.startswith("//"):
            raise CommentError("API path must be host-relative")
        query = urllib.parse.urlencode(params or {})
        url = f"{self.api_url}{path}{'?' + query if query else ''}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            url,
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
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - fixed https host
                raw = response.read(8 * 1024 * 1024 + 1)
        except urllib.error.HTTPError as exc:
            raise CommentError(f"GitHub HTTP {exc.code} for {method} {path}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise CommentError(f"GitHub request failed for {method} {path}: {exc}") from exc
        if len(raw) > 8 * 1024 * 1024:
            raise CommentError("GitHub response exceeded 8 MiB")
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CommentError(f"GitHub returned invalid JSON for {path}") from exc

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        return self.request("GET", path, params)

    def paginate(
        self, path: str, *, key: str | None = None, params: Mapping[str, Any] | None = None
    ) -> list[Any]:
        rows: list[Any] = []
        for page in range(1, MAX_PAGES + 1):
            value = self.get(path, {**(params or {}), "per_page": 100, "page": page})
            batch = value.get(key) if key and isinstance(value, Mapping) else value
            if not isinstance(batch, list):
                raise CommentError(f"unexpected pagination shape for {path}")
            rows.extend(batch)
            if len(batch) < 100:
                break
        return rows


# --------------------------------------------------------- data acquisition


@dataclass(frozen=True)
class PullRequestData:
    number: int
    head_sha: str
    base_sha: str
    changed_files: tuple[str, ...]
    checks: tuple[dict[str, Any], ...]


def _check_summary(row: Mapping[str, Any]) -> dict[str, Any] | None:
    name, status = row.get("name"), row.get("conclusion") or row.get("status")
    if not isinstance(name, str) or not isinstance(status, str):
        return None
    summary: dict[str, Any] = {"name": name, "status": status}
    for key, source in (
        ("check_run_id", "id"),
        ("completed_at", "completed_at"),
        ("started_at", "started_at"),
    ):
        value = row.get(source)
        if value is not None:
            summary[key] = value
    return summary


def collect_pull_requests(
    client: GitHubClient, repository: str, pr_number: int
) -> tuple[PullRequestData, list[PullRequestData], str]:
    """Return (this PR, all open PRs including this one, current main SHA)."""
    prefix = f"/repos/{repository}"
    repo = client.get(prefix)
    default_branch = repo.get("default_branch") if isinstance(repo, Mapping) else None
    if not isinstance(default_branch, str) or not default_branch:
        raise CommentError("default branch unavailable")
    ref = client.get(f"{prefix}/git/ref/heads/{urllib.parse.quote(default_branch, safe='')}")
    main_sha = ref.get("object", {}).get("sha") if isinstance(ref, Mapping) else None
    if not isinstance(main_sha, str) or len(main_sha) != 40:
        raise CommentError("default branch SHA unavailable")

    listed = client.paginate(
        f"{prefix}/pulls", params={"state": "open", "sort": "updated", "direction": "desc"}
    )
    by_number: dict[int, Mapping[str, Any]] = {}
    for row in listed:
        number = row.get("number") if isinstance(row, Mapping) else None
        if isinstance(number, int) and len(by_number) < MAX_OPEN_PRS:
            by_number[number] = row
    if pr_number not in by_number:
        this = client.get(f"{prefix}/pulls/{pr_number}")
        if not isinstance(this, Mapping):
            raise CommentError("pull request unavailable")
        by_number[pr_number] = this

    pulls: list[PullRequestData] = []
    for number, row in sorted(by_number.items()):
        head_sha = row.get("head", {}).get("sha") if isinstance(row.get("head"), Mapping) else None
        base_sha = row.get("base", {}).get("sha") if isinstance(row.get("base"), Mapping) else None
        if not isinstance(head_sha, str) or not isinstance(base_sha, str):
            continue
        files = client.paginate(f"{prefix}/pulls/{number}/files")
        changed = tuple(
            sorted({
                f["filename"]
                for f in files
                if isinstance(f, Mapping) and isinstance(f.get("filename"), str)
            })
        )
        check_rows = client.paginate(
            f"{prefix}/commits/{urllib.parse.quote(head_sha, safe='')}/check-runs", key="check_runs"
        )
        checks = tuple(
            c for c in (_check_summary(r) for r in check_rows if isinstance(r, Mapping)) if c
        )
        pulls.append(PullRequestData(number, head_sha, base_sha, changed, checks))
    this_pr = next((pr for pr in pulls if pr.number == pr_number), None)
    if this_pr is None:
        raise CommentError("pull request identity incomplete")
    return this_pr, pulls, main_sha


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
    this_pr: PullRequestData,
    pulls: Sequence[PullRequestData],
    main_sha: str,
    graph: tuple[Sequence[str], Sequence[Mapping[str, str]], Sequence[str]],
    run_engine: EngineRunner,
    observed_at: str,
) -> Findings:
    overlap = run_engine(
        "overlap", {"snapshots": [_snapshot(repository, pr, main_sha) for pr in pulls]}
    )
    overlaps: dict[int, list[str]] = {}
    for pair in overlap.get("overlap_pairs", []):
        left, right, paths = pair.get("pr_a"), pair.get("pr_b"), pair.get("shared_paths", [])
        if this_pr.number in (left, right):
            other = right if left == this_pr.number else left
            if isinstance(other, int):
                overlaps[other] = sorted(str(p) for p in paths)

    covered, edges, errors = graph
    covered_set = set(covered)
    impact = run_engine(
        "impact",
        {
            "snapshot": _snapshot(repository, this_pr, main_sha),
            "covered_files": sorted(covered_set | set(this_pr.changed_files)),
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
            "pull_requests": [{"pr_number": pr.number, "checks": list(pr.checks)} for pr in pulls],
        },
    )
    systemic = [
        (
            str(item.get("check_name")),
            [int(n) for n in item.get("pr_numbers", []) if isinstance(n, int)],
        )
        for item in systemic_report.get("systemic_failures", [])
        if isinstance(item, Mapping)
    ]
    return Findings(
        overlaps=overlaps, direct_impacted=direct, all_impacted=every, systemic=systemic
    )


# ----------------------------------------------------------- sticky upsert


def upsert_sticky_comment(client: GitHubClient, repository: str, pr_number: int, body: str) -> str:
    """Create or update the single bot-authored comment carrying MARKER."""
    comments = client.paginate(f"/repos/{repository}/issues/{pr_number}/comments")
    ours = [
        c
        for c in comments
        if isinstance(c, Mapping)
        and isinstance(c.get("body"), str)
        and c["body"].startswith(MARKER)
        and isinstance(c.get("user"), Mapping)
        and c["user"].get("login") == BOT_LOGIN
        and c["user"].get("type") == "Bot"
    ]
    if ours:
        existing = ours[0]
        if existing.get("body") == body:
            return "UNCHANGED"
        client.request(
            "PATCH",
            f"/repos/{repository}/issues/comments/{int(existing['id'])}",
            body={"body": body},
        )
        return "UPDATED"
    client.request("POST", f"/repos/{repository}/issues/{pr_number}/comments", body={"body": body})
    return "CREATED"


# ---------------------------------------------------------------------- CLI


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
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
    args = parser.parse_args(argv)

    owner, _, name = args.repository.partition("/")
    if not owner or not name or "/" in name or args.pr_number <= 0:
        print("invalid repository or PR number", file=sys.stderr)
        return 2
    try:
        client = GitHubClient(
            os.environ.get("GITHUB_TOKEN", ""), os.environ.get("GITHUB_API_URL", API_URL)
        )
        this_pr, pulls, main_sha = collect_pull_requests(client, args.repository, args.pr_number)
        graph = build_import_graph(args.repo_root)
        findings = analyze(
            args.repository,
            this_pr,
            pulls,
            main_sha,
            graph,
            engine_runner(args.engine_root, args.engine_pin),
            _utc_now(),
        )
        body = render_comment(findings)
        outcome = (
            upsert_sticky_comment(client, args.repository, args.pr_number, body)
            if args.post
            else "DRY_RUN"
        )
    except CommentError as exc:
        # Advisory surface: report and leave any existing comment untouched.
        message = f"RIE comment skipped: {sanitize_text(exc, 300)}"
        print(message, file=sys.stderr)
        if args.step_summary:
            with open(args.step_summary, "a", encoding="utf-8") as handle:
                handle.write(message + "\n")
        return 0
    print(body)
    print(f"sticky comment: {outcome}", file=sys.stderr)
    if args.step_summary:
        with open(args.step_summary, "a", encoding="utf-8") as handle:
            handle.write(f"sticky comment: {outcome}\n\n{body.replace(MARKER, '').strip()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
