#!/usr/bin/env python3
"""Read-only Fast Start v2 consumer preflight for GitHub Issue work."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Mapping

from scripts.ops.fast_start_v2 import parse_registry_body, registry_payload_hash

REPOSITORY = "James3014/Nexus-new"
REGISTRY_ISSUE = 549
REPORT_SCHEMA = "nexus.fast_start_consumer_preflight.v1"


class GitHubMetadataClient:
    """Small GET-only client for advisory preflight metadata."""

    def __init__(self, token: str = "", opener: Any | None = None) -> None:
        self._token = token
        self._opener = opener or urllib.request.urlopen
        self.requested_paths: list[str] = []

    def get(self, path: str) -> Any:
        if not path.startswith("/"):
            raise ValueError("GitHub path must start with /")
        self.requested_paths.append(path)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "nexus-fast-start-consumer",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = urllib.request.Request(
            f"https://api.github.com{path}",
            headers=headers,
            method="GET",
        )
        try:
            with self._opener(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - live boundary
            raise RuntimeError(f"GitHub GET failed: HTTP {exc.code} {path}") from exc


def _header_hash(body: str) -> str:
    match = re.search(r"\*\*Canonical payload SHA-256:\*\* `([0-9a-f]{64})`", body)
    if not match:
        raise ValueError("registry hash header missing or malformed")
    return match.group(1)


def _base_report(*, outcome: str, next_action: str) -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "authority": "ADVISORY_CACHE_ONLY",
        "registry_issue": REGISTRY_ISSUE,
        "outcome": outcome,
        "next_action": next_action,
        "implementation_source_or_test_body_reads": 0,
    }


def _compact_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: entry[key]
        for key in (
            "issue",
            "cache_state",
            "dispatch_state",
            "stable_goal",
            "blocker",
            "unlock_condition",
            "entrypoints",
            "minimum_verification",
        )
        if key in entry
    }


def consumer_preflight(client: Any, issue_number: int) -> dict[str, Any]:
    """Read #549 first and return the smallest safe next action for one Issue.

    The cache may stop or narrow discovery, but it can never grant readiness or
    mutation authority. No implementation source/test body is read here.
    """

    registry = client.get(f"/repos/{REPOSITORY}/issues/{REGISTRY_ISSUE}")
    if not isinstance(registry, Mapping):
        raise ValueError("registry response malformed")
    body = str(registry.get("body") or "")
    payload = parse_registry_body(body)
    payload_hash = registry_payload_hash(payload)
    if _header_hash(body) != payload_hash:
        raise ValueError("REGISTRY_HASH_MISMATCH")
    if payload.get("authority") != "ADVISORY_CACHE_ONLY":
        raise ValueError("REGISTRY_AUTHORITY_MISMATCH")

    entries = {
        int(entry["issue"]): entry
        for entry in payload.get("entries", [])
        if isinstance(entry, Mapping) and "issue" in entry
    }
    entry = entries.get(issue_number)
    if entry is None:
        report = _base_report(
            outcome="CACHE_MISS",
            next_action="FULL_AUTHORITATIVE_DISCOVERY",
        )
        report["registry_revision"] = payload.get("registry_revision")
        report["registry_hash"] = payload_hash
        return report

    dispatch_state = str(entry.get("dispatch_state") or "")
    report = _base_report(
        outcome="ADVISORY_ENTRY_FOUND",
        next_action="AUTHORITATIVE_REBIND_BEFORE_IMPLEMENTATION",
    )
    report["registry_revision"] = payload.get("registry_revision")
    report["registry_hash"] = payload_hash
    report["entry"] = _compact_entry(entry)

    if dispatch_state.startswith("HOST_"):
        report["outcome"] = "EARLY_STOP_HOST_BOUND"
        report["next_action"] = "RETURN_HOST_BLOCKER"
        return report

    if dispatch_state.startswith("BLOCKED_"):
        blocker = entry.get("blocker") if isinstance(entry.get("blocker"), Mapping) else {}
        pr_number = blocker.get("pr")
        if isinstance(pr_number, int):
            pull = client.get(f"/repos/{REPOSITORY}/pulls/{pr_number}")
            if not isinstance(pull, Mapping):
                raise ValueError("blocker PR response malformed")
            state = str(pull.get("state") or "")
            head = pull.get("head") if isinstance(pull.get("head"), Mapping) else {}
            head_sha = str(head.get("sha") or "")
            cached_head = str(blocker.get("head_sha") or "")
            if state == "open" and re.fullmatch(r"[0-9a-f]{40}", head_sha):
                if not cached_head or head_sha == cached_head:
                    report["outcome"] = "EARLY_STOP_BLOCKED"
                    report["next_action"] = "RETURN_BLOCKER"
                    report["live_blocker"] = {
                        "pr": pr_number,
                        "state": state,
                        "head_sha": head_sha,
                    }
                    return report
            report["outcome"] = "CACHE_STALE_BLOCKER"
            report["next_action"] = "AUTHORITATIVE_METADATA_REBIND"
            report["live_blocker"] = {
                "pr": pr_number,
                "state": state,
                "head_sha": head_sha or None,
            }
            return report

        report["outcome"] = "EARLY_STOP_BLOCKED"
        report["next_action"] = "RETURN_BLOCKER"
        return report

    return report


def safe_consumer_preflight(client: Any, issue_number: int) -> dict[str, Any]:
    """Fail open to normal discovery while failing closed on cache authority."""

    try:
        return consumer_preflight(client, issue_number)
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        report = _base_report(
            outcome="CACHE_UNAVAILABLE_OR_INVALID",
            next_action="FULL_AUTHORITATIVE_DISCOVERY",
        )
        report["reason"] = str(exc)
        return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", type=int, required=True)
    args = parser.parse_args()
    if args.issue <= 0:
        parser.error("--issue must be a positive integer")

    report = safe_consumer_preflight(
        GitHubMetadataClient(os.environ.get("GITHUB_TOKEN", "")),
        args.issue,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
