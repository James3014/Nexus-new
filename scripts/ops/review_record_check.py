#!/usr/bin/env python3
"""Review record present (#2290): the PR must carry its review evidence at its head.

Advisory. Stdlib only. Reads the PR, its file list, its issue comments and its
submitted reviews through the GitHub REST API and publishes a commit status on
the PR head. PR code is never checked out or executed, and PR-controlled text
(comment bodies, paths) is only pattern-matched; every printed line goes through
``_log_safe`` so it can never be read as a workflow command.

A *record* is an issue comment that names the current head (the full 40-hex sha,
or a hex prefix of at least ``MIN_PREFIX`` characters) and carries an uppercase
verdict token (``ACCEPT``/``ACCEPTED``/``APPROVE``/``APPROVED``). A submitted
``APPROVED`` review whose ``commit_id`` is the head also counts. Records are
classified by reviewer family from the words they use: ``claude``/``opus``/
``sonnet`` and the cross-model family ``codex``/``gemini``/``gpt``.

Verdict:
- ``OK``: an independent record at head exists and, for a high-risk PR, a
  cross-model record at head (a verdict, or a rebuttal at the round cap).
- ``MISSING_RECORD`` / ``MISSING_CROSS_MODEL``: what is absent.
- ``ERROR``: the API could not be read (fails closed).

Making this check required is a ruleset change and an Owner decision.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any, Callable

API_ROOT = "https://api.github.com"
PER_PAGE = 100
STATUS_CONTEXT = "Review record present (advisory)"
MIN_PREFIX = 9
MAX_DESCRIPTION = 140

# Paths whose change makes the PR high-risk (nexus-codex-review skill list, 2026-10-15).
HIGH_RISK_PREFIXES = (
    ".github/workflows/",
    ".nexus-core/",
    "scripts/ops/",
    "scripts/ci/",
    "nexus/orchestrator/governed_integration.py",
    "nexus/orchestrator/self_hosted_task_service.py",
    "nexus/orchestrator/target_integration_lifecycle.py",
    "nexus/governance/",
)
HIGH_RISK_FILES = frozenset({"pyproject.toml", "uv.lock"})

_HEX_TOKEN = re.compile(r"(?<![0-9a-fA-F])([0-9a-f]{9,40})(?![0-9a-fA-F])")
_VERDICT = re.compile(r"\b(?:ACCEPT|ACCEPTED|APPROVE|APPROVED)\b")
_REBUTTAL = re.compile(r"\brebut", re.IGNORECASE)
_CAP = re.compile(r"\b(?:cap|round\s*3|r3|three rounds|3 rounds)\b", re.IGNORECASE)
_CLAUDE = re.compile(r"\b(?:claude|opus|sonnet)\b", re.IGNORECASE)
_CROSS = re.compile(r"\b(?:codex|gemini|gpt)\b", re.IGNORECASE)


class CheckError(Exception):
    """Raised for any condition that must fail closed."""


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "nexus-review-record-check",
    }


def _get_json(url: str, token: str) -> Any:
    request = urllib.request.Request(url, headers=_headers(token))
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, token: str, payload: dict[str, Any]) -> Any:
    data = json.dumps(payload).encode("utf-8")
    headers = _headers(token)
    headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _paginate(fetch: Callable[[str, str], Any], url: str, token: str) -> list[Any]:
    items: list[Any] = []
    page = 1
    while True:
        batch = fetch(f"{url}?per_page={PER_PAGE}&page={page}", token)
        if not isinstance(batch, list):
            raise CheckError("unexpected API response shape")
        items.extend(batch)
        if len(batch) < PER_PAGE:
            return items
        page += 1


def _log_safe(line: str) -> str:
    """One physical log line that can never be read as a GitHub workflow command."""
    text = str(line)
    indent = len(text) - len(text.lstrip(" "))
    body = " ".join("".join(ch if ch.isprintable() else " " for ch in text).split())
    while "##[" in body:
        body = body.replace("##[", "# #[")
    if body.startswith("::"):
        body = "> " + body
    return " " * indent + body


def names_head(body: str, head: str) -> bool:
    """True when the body contains the head sha or a hex prefix of it (>= MIN_PREFIX)."""
    head = head.lower()
    for match in _HEX_TOKEN.finditer(body):
        token = match.group(1)
        if len(token) >= MIN_PREFIX and head.startswith(token):
            return True
    return False


def classify_record(body: str, head: str) -> dict[str, Any] | None:
    """Classify one comment body; None when it does not name the head."""
    if not isinstance(body, str) or not names_head(body, head):
        return None
    return {
        "verdict": bool(_VERDICT.search(body)),
        "rebuttal_at_cap": bool(_REBUTTAL.search(body) and _CAP.search(body)),
        "claude": bool(_CLAUDE.search(body)),
        "cross_model": bool(_CROSS.search(body)),
    }


def high_risk_paths(files: list[Any]) -> list[str]:
    paths: list[str] = []
    for entry in files:
        name = entry.get("filename") if isinstance(entry, dict) else None
        if not isinstance(name, str):
            continue
        if name in HIGH_RISK_FILES or name.startswith(HIGH_RISK_PREFIXES):
            paths.append(name)
    return sorted(paths)


def evaluate(
    head: str, files: list[Any], comments: list[Any], reviews: list[Any]
) -> dict[str, Any]:
    """Pure classification of the PR's review evidence at ``head``."""
    risky = high_risk_paths(files)
    records = []
    for comment in comments:
        body = comment.get("body") if isinstance(comment, dict) else None
        record = classify_record(body or "", head)
        if record is not None:
            records.append(record)
    approved_reviews = sum(
        1
        for review in reviews
        if isinstance(review, dict)
        and review.get("state") == "APPROVED"
        and str(review.get("commit_id", "")).lower() == head.lower()
    )
    independent = approved_reviews > 0 or any(r["verdict"] for r in records)
    cross_model = any(r["cross_model"] and (r["verdict"] or r["rebuttal_at_cap"]) for r in records)
    if not independent:
        status, reason = (
            "MISSING_RECORD",
            f"no review record names head {head[:12]} with an ACCEPT/APPROVE verdict",
        )
    elif risky and not cross_model:
        status, reason = (
            "MISSING_CROSS_MODEL",
            f"high-risk paths changed but no Codex/Gemini record at head {head[:12]}",
        )
    else:
        status, reason = "OK", f"review record present at head {head[:12]}"
    return {
        "schema": "nexus.review_record_check.v1",
        "head": head,
        "high_risk": bool(risky),
        "high_risk_paths": risky,
        "records_at_head": len(records),
        "approved_reviews_at_head": approved_reviews,
        "independent": independent,
        "cross_model": cross_model,
        "status": status,
        "reason": reason,
    }


def _description(report: dict[str, Any]) -> str:
    text = _log_safe(f"{report['status']}: {report['reason']}").strip()
    return text[:MAX_DESCRIPTION]


def run(
    repo: str,
    pr: int,
    token: str,
    fetch: Callable[[str, str], Any] = _get_json,
    post: Callable[[str, str, dict[str, Any]], Any] = _post_json,
    *,
    publish: bool = True,
    fail_on_missing: bool = True,
    target_url: str = "",
    output: str | None = None,
) -> int:
    base = f"{API_ROOT}/repos/{repo}"
    report: dict[str, Any]
    try:
        pull = fetch(f"{base}/pulls/{pr}", token)
        head = str((pull.get("head") or {}).get("sha", "")) if isinstance(pull, dict) else ""
        if not re.fullmatch(r"[0-9a-f]{40}", head):
            raise CheckError("PR head sha unavailable")
        files = _paginate(fetch, f"{base}/pulls/{pr}/files", token)
        comments = _paginate(fetch, f"{base}/issues/{pr}/comments", token)
        reviews = _paginate(fetch, f"{base}/pulls/{pr}/reviews", token)
        report = evaluate(head, files, comments, reviews)
    except (CheckError, urllib.error.URLError, OSError, ValueError) as exc:
        head = ""
        report = {
            "schema": "nexus.review_record_check.v1",
            "head": "",
            "status": "ERROR",
            "reason": f"could not read the PR: {type(exc).__name__}: {exc}",
        }
    if output:
        with open(output, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
    for line in (
        f"review-record-check: {report['status']}",
        f"  {report['reason']}",
        f"  high-risk paths: {', '.join(report.get('high_risk_paths') or []) or '-'}",
    ):
        print(_log_safe(line))
    state = "success" if report["status"] == "OK" else "failure"
    if publish and head:
        payload = {
            "state": state,
            "context": STATUS_CONTEXT,
            "description": _description(report),
        }
        if target_url:
            payload["target_url"] = target_url
        try:
            post(f"{base}/statuses/{head}", token, payload)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(_log_safe(f"review-record-check: could not publish the status: {exc}"))
            return 1
    if report["status"] == "ERROR":
        return 1
    return 1 if (fail_on_missing and state == "failure") else 0


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review record present (#2290): advisory check")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--output")
    parser.add_argument("--target-url", default="")
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument(
        "--no-fail", action="store_true", help="exit 0 even when a record is missing"
    )
    args = parser.parse_args(argv)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        print("review-record-check: ERROR: GH_TOKEN is not set")
        return 1
    return run(
        args.repo,
        args.pr,
        token,
        publish=not args.no_publish,
        fail_on_missing=not args.no_fail,
        target_url=args.target_url,
        output=args.output,
    )


if __name__ == "__main__":
    sys.exit(_cli())
