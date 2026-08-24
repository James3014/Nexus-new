#!/usr/bin/env python3
"""Deterministic Fast Start v2 invalidation/reconcile simulator.

This module is deliberately advisory and read-only.  It never mutates GitHub,
selects a worker/route, or upgrades an Issue to execution authority.  Production
writers and event delivery are separate gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

REPOSITORY = "James3014/Nexus-new"
REGISTRY_ISSUE = 549
SCHEMA = "nexus.fast_start_invalidation_hint.v2"

ENTRY_RULES: dict[int, dict[str, Any]] = {
    129: {
        "direct_prs": {479},
        "issues": {129},
        "paths": {
            "nexus/orchestrator/self_hosted_task_service.py",
            "tests/nexus/orchestrator/test_self_hosted_task_service.py",
            "tasks/github-issue-129-atomic-work-claim-20260813/00-atomic-work-claim.md",
            "tasks/github-issue-129-atomic-work-claim-20260813/INDEX.md",
        },
    },
    92: {
        "direct_prs": {403},
        "issues": {92, 29},
        "paths": {"nexus/services/unified_runtime.py"},
    },
    419: {
        "direct_prs": {402},
        "issues": {419},
        "paths": {
            "AGENTS.md",
            "tests/ops/test_bootstrap_context_budget.py",
            "tests/ops/test_bootstrap_authority_files.py",
        },
    },
    526: {
        "direct_prs": set(),
        "issues": {526},
        "paths": {
            "tasks/github-issue-526-host-authority-and-canary-20260823/02-host-effect-authority-receipt.json"
        },
    },
    398: {
        "direct_prs": set(),
        "issues": {398},
        "paths": set(),
    },
}

VALID_FRONTIERS = {
    "READY_CANDIDATE",
    "BLOCKED",
    "HOST_REBIND_REQUIRED",
    "NEEDS_DECISION",
    "EVIDENCE_BLOCKED",
}
EARLY_STOP_FRONTIERS = VALID_FRONTIERS - {"READY_CANDIDATE"}


@dataclass(frozen=True)
class Hint:
    schema: str
    repository: str
    event_type: str
    action: str
    subject_type: str
    subject_number: int | None
    head_sha: str | None
    changed_paths_digest: str | None
    seed_keys: tuple[str, ...]
    affected_entries: tuple[int, ...]
    reason_codes: tuple[str, ...]
    authority: str = "WAKEUP_HINT_ONLY"

    def canonical_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["seed_keys"] = list(self.seed_keys)
        payload["affected_entries"] = list(self.affected_entries)
        payload["reason_codes"] = list(self.reason_codes)
        return payload

    def sha256(self) -> str:
        return sha256_json(self.canonical_payload())


@dataclass(frozen=True)
class ReconcileDecision:
    reconcile_action: str
    frontier_state: str
    implementation_context: str
    source_body_reads_allowed: bool
    test_body_reads_allowed: bool


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _digest_paths(paths: Sequence[str]) -> str | None:
    normalized = sorted({path.strip() for path in paths if path.strip()})
    if not normalized:
        return None
    return hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()


def _entry_matches_path(entry: int, path: str) -> bool:
    return path in ENTRY_RULES[entry]["paths"]


def affected_entries_for_event(
    event_type: str,
    payload: Mapping[str, Any],
    *,
    changed_paths: Sequence[str] = (),
) -> Hint:
    """Return the minimal deterministic impact set for a GitHub wakeup.

    Raw Issue/PR prose is intentionally ignored.  Event data may wake an entry,
    but current authoritative state must be re-read by the reconciler.
    """

    action = str(payload.get("action") or "unknown")
    event_type = event_type.strip()
    affected: set[int] = set()
    reasons: set[str] = set()
    seed_keys: set[str] = set()
    subject_type = "repository"
    subject_number: int | None = None
    head_sha: str | None = None

    issue = payload.get("issue") if isinstance(payload.get("issue"), Mapping) else None
    pr = payload.get("pull_request") if isinstance(payload.get("pull_request"), Mapping) else None

    if event_type == "issue_comment" and issue:
        subject_type = "issue"
        subject_number = _optional_int(issue.get("number"))
        if subject_number == REGISTRY_ISSUE:
            return _make_hint(
                event_type,
                action,
                subject_type,
                subject_number,
                None,
                changed_paths,
                (),
                (f"issue:{REGISTRY_ISSUE}",),
                ("REGISTRY_SELF_EVENT_SUPPRESSED",),
            )
        if subject_number is not None:
            seed_keys.add(f"issue:{subject_number}")
            for entry, rule in ENTRY_RULES.items():
                if subject_number in rule["issues"]:
                    affected.add(entry)
            if affected:
                reasons.add("ISSUE_COMMENT_WAKEUP")

    elif event_type == "issues" and issue:
        subject_type = "issue"
        subject_number = _optional_int(issue.get("number"))
        if subject_number == REGISTRY_ISSUE:
            return _make_hint(
                event_type,
                action,
                subject_type,
                subject_number,
                None,
                changed_paths,
                (),
                (f"issue:{REGISTRY_ISSUE}",),
                ("REGISTRY_SELF_EVENT_SUPPRESSED",),
            )
        if subject_number is not None:
            seed_keys.add(f"issue:{subject_number}")
            for entry, rule in ENTRY_RULES.items():
                if subject_number in rule["issues"]:
                    affected.add(entry)
            if affected:
                reasons.add("ISSUE_STATE_WAKEUP")

    elif event_type in {"pull_request", "pull_request_target"} and pr:
        subject_type = "pull_request"
        subject_number = _optional_int(payload.get("number") or pr.get("number"))
        head = pr.get("head") if isinstance(pr.get("head"), Mapping) else {}
        head_sha = _optional_str(head.get("sha"))
        if subject_number is not None:
            seed_keys.add(f"pr:{subject_number}")
            for entry, rule in ENTRY_RULES.items():
                if subject_number in rule["direct_prs"]:
                    affected.add(entry)
                    reasons.add("DIRECT_PR_INPUT")
        _add_path_impacts(changed_paths, affected, seed_keys, reasons)

    elif event_type == "push":
        subject_type = "ref"
        ref = _optional_str(payload.get("ref"))
        if ref:
            seed_keys.add(ref)
        head_sha = _optional_str(payload.get("after"))
        _add_path_impacts(changed_paths, affected, seed_keys, reasons)
        if not changed_paths:
            reasons.add("PATH_IMPACT_DISCOVERY_REQUIRED")

    elif event_type in {"workflow_dispatch", "schedule", "anti_entropy"}:
        subject_type = "repository"
        seed_keys.add("anti-entropy")
        affected.update(ENTRY_RULES)
        reasons.add("FULL_ANTI_ENTROPY")

    return _make_hint(
        event_type,
        action,
        subject_type,
        subject_number,
        head_sha,
        changed_paths,
        affected,
        seed_keys,
        reasons or {"NO_RELEVANT_IMPACT"},
    )


def _add_path_impacts(
    changed_paths: Sequence[str],
    affected: set[int],
    seed_keys: set[str],
    reasons: set[str],
) -> None:
    for path in sorted(set(changed_paths)):
        seed_keys.add(f"path:{path}")
        for entry in ENTRY_RULES:
            if _entry_matches_path(entry, path):
                affected.add(entry)
                reasons.add("PATH_OVERLAP")


def _make_hint(
    event_type: str,
    action: str,
    subject_type: str,
    subject_number: int | None,
    head_sha: str | None,
    changed_paths: Sequence[str],
    affected: Iterable[int],
    seed_keys: Iterable[str],
    reason_codes: Iterable[str],
) -> Hint:
    return Hint(
        schema=SCHEMA,
        repository=REPOSITORY,
        event_type=event_type,
        action=action,
        subject_type=subject_type,
        subject_number=subject_number,
        head_sha=head_sha,
        changed_paths_digest=_digest_paths(changed_paths),
        seed_keys=tuple(sorted(set(seed_keys))),
        affected_entries=tuple(sorted(set(affected))),
        reason_codes=tuple(sorted(set(reason_codes))),
    )


def decide_reconcile(
    *,
    frontier_state: str,
    contract_changed: bool = False,
    dispatch_changed: bool = False,
    wakeup_changed: bool = False,
    implementation_dirty: bool = False,
    evidence_complete: bool = True,
) -> ReconcileDecision:
    """Apply the G4/G5 two-axis state machine without reading implementation bodies."""

    if frontier_state not in VALID_FRONTIERS:
        raise ValueError(f"unknown frontier_state: {frontier_state}")

    effective_frontier = frontier_state if evidence_complete else "EVIDENCE_BLOCKED"
    if contract_changed:
        action = "FULL_REBUILD"
    elif dispatch_changed:
        action = "TARGETED_REBIND"
    elif wakeup_changed:
        action = "LIGHT_REBIND"
    else:
        action = "CACHE_HIT"

    allow_implementation_reads = effective_frontier == "READY_CANDIDATE"
    if implementation_dirty and not allow_implementation_reads:
        context_state = "DIRTY_DEFERRED"
    elif implementation_dirty:
        context_state = "DIRTY_REBIND_REQUIRED"
    else:
        context_state = "UNCHANGED"

    return ReconcileDecision(
        reconcile_action=action,
        frontier_state=effective_frontier,
        implementation_context=context_state,
        source_body_reads_allowed=allow_implementation_reads,
        test_body_reads_allowed=allow_implementation_reads,
    )


def parse_registry_body(body: str) -> dict[str, Any]:
    marker = "```json"
    start = body.find(marker)
    if start < 0:
        raise ValueError("registry JSON block missing")
    start += len(marker)
    end = body.find("```", start)
    if end < 0:
        raise ValueError("registry JSON block unterminated")
    value = json.loads(body[start:end].strip())
    if not isinstance(value, dict):
        raise ValueError("registry payload must be an object")
    return value


def registry_payload_hash(payload: Mapping[str, Any]) -> str:
    return sha256_json(payload)


class GitHubReadClient:
    """Small read-only GitHub REST client used only by shadow-live."""

    def __init__(self, token: str, opener: Callable[..., Any] | None = None) -> None:
        self._token = token
        self._opener = opener or urllib.request.urlopen
        self.requested_urls: list[str] = []

    def get(self, path: str) -> Any:
        if not path.startswith("/"):
            raise ValueError("GitHub path must start with /")
        url = f"https://api.github.com{path}"
        self.requested_urls.append(url)
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "nexus-fast-start-v2-shadow",
            },
        )
        try:
            with self._opener(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - live boundary
            raise RuntimeError(f"GitHub read failed: HTTP {exc.code} {path}") from exc


def live_shadow_report(client: GitHubReadClient) -> dict[str, Any]:
    """Read the current v1 frontier only; never fetch implementation file bodies."""

    registry_issue = client.get(f"/repos/{REPOSITORY}/issues/{REGISTRY_ISSUE}")
    payload = parse_registry_body(str(registry_issue.get("body") or ""))
    expected_hash = _extract_header_hash(str(registry_issue.get("body") or ""))
    actual_hash = registry_payload_hash(payload)
    if expected_hash != actual_hash:
        raise ValueError("REGISTRY_HASH_MISMATCH")

    branch = client.get(f"/repos/{REPOSITORY}/branches/main")
    current_main = str(branch["commit"]["sha"])
    current_tree = str(branch["commit"]["commit"]["tree"]["sha"])

    cached = {int(entry["issue"]): entry for entry in payload.get("entries", [])}
    prs = {
        479: client.get(f"/repos/{REPOSITORY}/pulls/479"),
        403: client.get(f"/repos/{REPOSITORY}/pulls/403"),
        402: client.get(f"/repos/{REPOSITORY}/pulls/402"),
    }
    issue29 = client.get(f"/repos/{REPOSITORY}/issues/29")
    comments398 = client.get(f"/repos/{REPOSITORY}/issues/398/comments?per_page=100")

    decisions: dict[str, Any] = {}
    decisions["129"] = asdict(
        decide_reconcile(
            frontier_state="BLOCKED" if prs[479].get("state") == "open" else "EVIDENCE_BLOCKED",
            dispatch_changed=_pr_changed(cached[129], prs[479]),
        )
    )
    decisions["92"] = asdict(
        decide_reconcile(
            frontier_state=(
                "BLOCKED"
                if prs[403].get("state") == "open" or issue29.get("state") == "open"
                else "EVIDENCE_BLOCKED"
            ),
            dispatch_changed=_pr_changed(cached[92], prs[403]),
        )
    )
    decisions["419"] = asdict(
        decide_reconcile(
            frontier_state="BLOCKED" if prs[402].get("state") == "open" else "EVIDENCE_BLOCKED",
            dispatch_changed=_pr_changed(cached[419], prs[402]),
        )
    )
    decisions["526"] = asdict(decide_reconcile(frontier_state="HOST_REBIND_REQUIRED"))
    host398 = any(
        "HOST_OAUTH_SESSION_OR_CONNECTOR_REQUIRED" in str(item.get("body") or "")
        for item in comments398
        if isinstance(item, Mapping)
    )
    decisions["398"] = asdict(
        decide_reconcile(frontier_state="HOST_REBIND_REQUIRED" if host398 else "EVIDENCE_BLOCKED")
    )

    forbidden_reads = [
        url
        for url in client.requested_urls
        if "/contents/" in url or "/git/blobs/" in url or "/pulls/" in url and "/files" in url
    ]
    return {
        "schema": "nexus.fast_start_shadow_report.v2",
        "registry_revision": payload.get("registry_revision"),
        "registry_hash": actual_hash,
        "cached_main": payload.get("snapshot", {}).get("main_sha"),
        "cached_tree": payload.get("snapshot", {}).get("main_tree"),
        "current_main": current_main,
        "current_tree": current_tree,
        "decisions": decisions,
        "implementation_source_or_test_body_reads": len(forbidden_reads),
        "requested_url_count": len(client.requested_urls),
        "authority": "SHADOW_READ_ONLY",
    }


def _pr_changed(entry: Mapping[str, Any], pr: Mapping[str, Any]) -> bool:
    blocker = entry.get("blocker") if isinstance(entry.get("blocker"), Mapping) else {}
    return blocker.get("state") != pr.get("state") or blocker.get("head_sha") != pr.get(
        "head", {}
    ).get("sha")


def _extract_header_hash(body: str) -> str:
    prefix = "**Canonical payload SHA-256:** `"
    start = body.find(prefix)
    if start < 0:
        raise ValueError("registry hash header missing")
    start += len(prefix)
    end = body.find("`", start)
    value = body[start:end]
    if len(value) != 64:
        raise ValueError("registry hash header malformed")
    return value


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _load_event(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("event payload must be a JSON object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    hint_parser = sub.add_parser("hint", help="derive a read-only invalidation hint")
    hint_parser.add_argument("--event-name", required=True)
    hint_parser.add_argument("--event-json", required=True)
    hint_parser.add_argument("--changed-path", action="append", default=[])

    sub.add_parser("shadow-live", help="run the current GitHub frontier shadow canary")

    args = parser.parse_args(argv)
    if args.command == "hint":
        hint = affected_entries_for_event(
            args.event_name,
            _load_event(args.event_json),
            changed_paths=args.changed_path,
        )
        output = hint.canonical_payload()
        output["hint_sha256"] = hint.sha256()
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
        return 0

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("GITHUB_TOKEN is required for shadow-live", file=sys.stderr)
        return 2
    report = live_shadow_report(GitHubReadClient(token))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
