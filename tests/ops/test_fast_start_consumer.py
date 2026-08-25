from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.ops.fast_start_consumer import (
    REGISTRY_ISSUE,
    REPOSITORY,
    consumer_preflight,
    safe_consumer_preflight,
)
from scripts.ops.fast_start_v2 import registry_payload_hash

ROOT = Path(__file__).resolve().parents[2]


class FakeClient:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.requested_paths: list[str] = []

    def get(self, path: str) -> Any:
        self.requested_paths.append(path)
        if path not in self.responses:
            raise AssertionError(f"unexpected request: {path}")
        value = self.responses[path]
        if isinstance(value, Exception):
            raise value
        return value


def _entry(issue: int, dispatch_state: str, **extra: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "issue": issue,
        "cache_state": "BASE_READY",
        "dispatch_state": dispatch_state,
        "issue_updated_at": "2026-08-19T01:01:17Z",
        "latest_material_comment_id": 100,
        "stable_goal": f"goal-{issue}",
        "entrypoints": [f"entry-{issue}"],
        "minimum_verification": [f"verify-{issue}"],
    }
    value.update(extra)
    return value


def _registry(*entries: dict[str, Any], corrupt_hash: bool = False) -> dict[str, Any]:
    payload = {
        "schema": "nexus.fast_start_cache.v1",
        "registry_revision": 7,
        "authority": "ADVISORY_CACHE_ONLY",
        "repository": REPOSITORY,
        "entries": list(entries),
    }
    payload_hash = registry_payload_hash(payload)
    if corrupt_hash:
        payload_hash = "0" * 64
    body = (
        "## Durable cache registry\n\n"
        "**Authority:** `ADVISORY_CACHE_ONLY`  \n"
        "**Registry revision:** `7`  \n"
        f"**Canonical payload SHA-256:** `{payload_hash}`\n\n"
        "```json\n"
        f"{json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)}\n"
        "```\n"
    )
    return {"number": REGISTRY_ISSUE, "state": "open", "body": body}


def _fresh_issue(issue: int) -> dict[str, Any]:
    return {"number": issue, "state": "open", "updated_at": "2026-08-19T01:01:17Z"}


def test_blocked_entry_reads_549_first_and_stops_before_implementation() -> None:
    blocked = _entry(
        129,
        "BLOCKED_OVERLAP",
        blocker={"pr": 479, "state": "open", "head_sha": "a" * 40},
        unlock_condition="PR #479 terminal then rebind",
    )
    client = FakeClient(
        {
            f"/repos/{REPOSITORY}/issues/549": _registry(blocked),
            f"/repos/{REPOSITORY}/issues/129": _fresh_issue(129),
            f"/repos/{REPOSITORY}/pulls/479": {
                "state": "open",
                "head": {"sha": "a" * 40},
            },
        }
    )

    report = consumer_preflight(client, 129)

    assert client.requested_paths[0] == f"/repos/{REPOSITORY}/issues/549"
    assert report["outcome"] == "EARLY_STOP_BLOCKED"
    assert report["next_action"] == "RETURN_BLOCKER"
    assert report["implementation_source_or_test_body_reads"] == 0
    assert all("/contents/" not in path for path in client.requested_paths)
    assert all("/files" not in path for path in client.requested_paths)


def test_issue_contract_drift_falls_back_before_blocker_pr_read() -> None:
    blocked = _entry(
        129,
        "BLOCKED_OVERLAP",
        blocker={"pr": 479, "state": "open", "head_sha": "a" * 40},
    )
    client = FakeClient(
        {
            f"/repos/{REPOSITORY}/issues/549": _registry(blocked),
            f"/repos/{REPOSITORY}/issues/129": {
                "number": 129,
                "state": "open",
                "updated_at": "2026-08-25T01:00:00Z",
            },
            f"/repos/{REPOSITORY}/issues/129/comments?per_page=100": [
                {"id": 101, "body": "material contract change"}
            ],
        }
    )

    report = consumer_preflight(client, 129)

    assert report["outcome"] == "CACHE_STALE_CONTRACT"
    assert report["next_action"] == "FULL_AUTHORITATIVE_DISCOVERY"
    assert f"/repos/{REPOSITORY}/pulls/479" not in client.requested_paths


def test_non_authority_wakeup_comment_preserves_valid_blocker_cache() -> None:
    blocked = _entry(
        129,
        "BLOCKED_OVERLAP",
        blocker={"pr": 479, "state": "open", "head_sha": "a" * 40},
    )
    client = FakeClient(
        {
            f"/repos/{REPOSITORY}/issues/549": _registry(blocked),
            f"/repos/{REPOSITORY}/issues/129": {
                "number": 129,
                "state": "open",
                "updated_at": "2026-08-25T01:00:00Z",
            },
            f"/repos/{REPOSITORY}/issues/129/comments?per_page=100": [
                {"id": 101, "body": "WAKEUP_HINT_ONLY NO_AUTHORITY canary"}
            ],
            f"/repos/{REPOSITORY}/pulls/479": {
                "state": "open",
                "head": {"sha": "a" * 40},
            },
        }
    )

    report = consumer_preflight(client, 129)

    assert report["outcome"] == "EARLY_STOP_BLOCKED"
    assert report["implementation_source_or_test_body_reads"] == 0


def test_blocker_head_drift_requires_metadata_rebind_not_unlock() -> None:
    blocked = _entry(
        129,
        "BLOCKED_OVERLAP",
        blocker={"pr": 479, "state": "open", "head_sha": "a" * 40},
    )
    client = FakeClient(
        {
            f"/repos/{REPOSITORY}/issues/549": _registry(blocked),
            f"/repos/{REPOSITORY}/issues/129": _fresh_issue(129),
            f"/repos/{REPOSITORY}/pulls/479": {
                "state": "open",
                "head": {"sha": "b" * 40},
            },
        }
    )

    report = consumer_preflight(client, 129)

    assert report["outcome"] == "CACHE_STALE_BLOCKER"
    assert report["next_action"] == "AUTHORITATIVE_METADATA_REBIND"
    assert report["implementation_source_or_test_body_reads"] == 0


def test_host_bound_entry_early_stops_when_issue_watermark_is_fresh() -> None:
    host = _entry(526, "HOST_REBIND_REQUIRED")
    client = FakeClient(
        {
            f"/repos/{REPOSITORY}/issues/549": _registry(host),
            f"/repos/{REPOSITORY}/issues/526": _fresh_issue(526),
        }
    )

    report = consumer_preflight(client, 526)

    assert report["outcome"] == "EARLY_STOP_HOST_BOUND"
    assert report["next_action"] == "RETURN_HOST_BLOCKER"
    assert report["implementation_source_or_test_body_reads"] == 0


def test_cache_miss_falls_back_to_full_authoritative_discovery() -> None:
    client = FakeClient({f"/repos/{REPOSITORY}/issues/549": _registry()})

    report = consumer_preflight(client, 777)

    assert report["outcome"] == "CACHE_MISS"
    assert report["next_action"] == "FULL_AUTHORITATIVE_DISCOVERY"
    assert report["authority"] == "ADVISORY_CACHE_ONLY"


def test_invalid_registry_falls_back_without_granting_authority() -> None:
    client = FakeClient(
        {f"/repos/{REPOSITORY}/issues/549": _registry(_entry(129, "BLOCKED_OVERLAP"), corrupt_hash=True)}
    )

    report = safe_consumer_preflight(client, 129)

    assert report["outcome"] == "CACHE_UNAVAILABLE_OR_INVALID"
    assert report["next_action"] == "FULL_AUTHORITATIVE_DISCOVERY"
    assert report["authority"] == "ADVISORY_CACHE_ONLY"
    assert report["implementation_source_or_test_body_reads"] == 0


def test_primary_coordinator_l1_contract_makes_preflight_step_zero() -> None:
    contract = (ROOT / "docs/agents/TASK_EXECUTION_CONTRACT.md").read_text(encoding="utf-8")
    command = "python -B scripts/ops/fast_start_consumer.py --issue <number>"

    assert command in contract
    assert "0. For GitHub Issue work" in contract
    assert "before implementation source/test body reads" in contract
    assert "#549 is `ADVISORY_CACHE_ONLY`" in contract
    assert "miss/invalid/stale" in contract
    assert "fresh authoritative discovery/rebind" in contract
