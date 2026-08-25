from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.ops.fast_start_consumer import REGISTRY_ISSUE, consumer_preflight, safe_consumer_preflight
from scripts.ops.fast_start_v2 import registry_payload_hash

ROOT = Path(__file__).resolve().parents[2]


class FakeClient:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.requested_paths: list[str] = []

    def get(self, path: str) -> Any:
        self.requested_paths.append(path)
        value = self.responses[path]
        if isinstance(value, Exception):
            raise value
        return value


def _entry(issue: int, dispatch_state: str, **extra: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "issue": issue,
        "cache_state": "BASE_READY",
        "dispatch_state": dispatch_state,
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
        "repository": "James3014/Nexus-new",
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


def test_blocked_entry_returns_live_blocker_before_implementation_reads() -> None:
    blocked = _entry(
        129,
        "BLOCKED_OVERLAP",
        blocker={"pr": 479, "state": "open", "head_sha": "a" * 40},
        unlock_condition="PR #479 terminal then rebind",
    )
    client = FakeClient(
        {
            "/repos/James3014/Nexus-new/issues/549": _registry(blocked),
            "/repos/James3014/Nexus-new/pulls/479": {
                "state": "open",
                "head": {"sha": "a" * 40},
            },
        }
    )

    report = consumer_preflight(client, 129)

    assert report["outcome"] == "EARLY_STOP_BLOCKED"
    assert report["next_action"] == "RETURN_BLOCKER"
    assert report["implementation_source_or_test_body_reads"] == 0
    assert client.requested_paths == [
        "/repos/James3014/Nexus-new/issues/549",
        "/repos/James3014/Nexus-new/pulls/479",
    ]


def test_host_bound_entry_stops_after_registry_read() -> None:
    client = FakeClient(
        {
            "/repos/James3014/Nexus-new/issues/549": _registry(
                _entry(526, "HOST_REBIND_REQUIRED")
            )
        }
    )

    report = consumer_preflight(client, 526)

    assert report["outcome"] == "EARLY_STOP_HOST_BOUND"
    assert report["next_action"] == "RETURN_HOST_BLOCKER"
    assert report["implementation_source_or_test_body_reads"] == 0
    assert client.requested_paths == ["/repos/James3014/Nexus-new/issues/549"]


def test_cache_miss_falls_back_to_full_authoritative_discovery() -> None:
    client = FakeClient({"/repos/James3014/Nexus-new/issues/549": _registry()})

    report = consumer_preflight(client, 777)

    assert report["outcome"] == "CACHE_MISS"
    assert report["next_action"] == "FULL_AUTHORITATIVE_DISCOVERY"
    assert report["authority"] == "ADVISORY_CACHE_ONLY"


def test_stale_blocker_never_unlocks_from_cache() -> None:
    blocked = _entry(
        129,
        "BLOCKED_OVERLAP",
        blocker={"pr": 479, "state": "open", "head_sha": "a" * 40},
    )
    client = FakeClient(
        {
            "/repos/James3014/Nexus-new/issues/549": _registry(blocked),
            "/repos/James3014/Nexus-new/pulls/479": {
                "state": "closed",
                "head": {"sha": "b" * 40},
            },
        }
    )

    report = consumer_preflight(client, 129)

    assert report["outcome"] == "CACHE_STALE_BLOCKER"
    assert report["next_action"] == "AUTHORITATIVE_METADATA_REBIND"
    assert report["implementation_source_or_test_body_reads"] == 0


def test_invalid_registry_falls_back_without_granting_authority() -> None:
    client = FakeClient(
        {
            "/repos/James3014/Nexus-new/issues/549": _registry(
                _entry(129, "BLOCKED_OVERLAP"), corrupt_hash=True
            )
        }
    )

    report = safe_consumer_preflight(client, 129)

    assert report["outcome"] == "CACHE_UNAVAILABLE_OR_INVALID"
    assert report["next_action"] == "FULL_AUTHORITATIVE_DISCOVERY"
    assert report["authority"] == "ADVISORY_CACHE_ONLY"
    assert report["implementation_source_or_test_body_reads"] == 0


def test_root_agent_contract_makes_fast_start_preflight_mandatory() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "scripts/ops/fast_start_consumer.py --issue <number>" in agents
    assert "before any implementation source/test body read" in agents
    assert "ADVISORY_CACHE_ONLY" in agents
    assert "CACHE_MISS" in agents
    assert "CACHE_UNAVAILABLE_OR_INVALID" in agents
