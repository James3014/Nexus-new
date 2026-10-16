"""Every worker named by Workforce routing must be an active channel (#2393)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "nexus/config/model_workforce.yaml"

# Providers dropped from the frontier priority (Claude -> Gemini -> Codex,
# 2026-10-15).  A worker on one of these may stay registered for benchmark
# lineage but no routing entry may point at it.
RETIRED_PROVIDERS = frozenset({"grok"})


def _manifest() -> dict[str, Any]:
    loaded = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _worker_id(value: str) -> str:
    return value.split("_when_", 1)[0]


def _routing_targets(routing: dict[str, Any]) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []

    def add(label: str, value: Any) -> None:
        if value is None or isinstance(value, bool):
            return
        if isinstance(value, str):
            targets.append((label, _worker_id(value)))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                add(f"{label}[{index}]", item)
        elif isinstance(value, dict):
            for key, item in value.items():
                add(f"{label}.{key}", item)

    for group, entries in routing.items():
        if not isinstance(entries, dict):
            continue
        for role, value in entries.items():
            if role in {
                "blocked_or_disabled_models_must_not_be_selected",
                "experiment_only_models_require_explicit_authorization",
                "mandatory_escalation_conditions",
            }:
                continue
            if role == "route_defaults":
                for route_role, entry in value.items():
                    add(
                        f"{group}.route_defaults.{route_role}.current_default",
                        entry.get("current_default"),
                    )
                    add(f"{group}.route_defaults.{route_role}.fallback", entry.get("fallback"))
                continue
            add(f"{group}.{role}", value)
    return targets


def test_every_routing_target_is_an_active_registered_worker() -> None:
    manifest = _manifest()
    workers = manifest["workers"]
    targets = _routing_targets(manifest["routing"])
    assert len(targets) >= 15  # the walk really visited the routing tree

    problems = []
    for label, worker_id in targets:
        worker = workers.get(worker_id)
        if worker is None:
            problems.append(f"{label}: unknown worker {worker_id}")
            continue
        if worker.get("availability") != "AVAILABLE":
            problems.append(f"{label}: {worker_id} availability {worker.get('availability')}")
        if worker.get("provider") in RETIRED_PROVIDERS:
            problems.append(f"{label}: {worker_id} is on retired provider {worker['provider']}")
    assert problems == []


def test_retired_provider_workers_stay_registered_but_unavailable() -> None:
    workers = _manifest()["workers"]
    retired = {wid: w for wid, w in workers.items() if w.get("provider") in RETIRED_PROVIDERS}
    assert "grok_review" in retired  # kept for benchmark lineage, not deleted
    for worker_id, worker in retired.items():
        assert worker["availability"] == "UNAVAILABLE", worker_id
        assert worker.get("reason"), worker_id


def test_independent_review_routes_to_gemini_high_via_agy_and_fails_closed() -> None:
    manifest = _manifest()
    online = manifest["routing"]["online"]
    worker = manifest["workers"][online["independent_review"]]
    assert worker["provider"] == "agy"
    assert worker["model"] == "gemini-3.8-flash-high"
    assert worker["availability"] == "AVAILABLE"
    assert "independent_review" in worker["roles"]
    for forbidden in ("approval", "merge", "route_authority"):
        assert forbidden in worker["forbidden_actions"]

    # No fallback: neither a fallback key nor a route_defaults fallback exists,
    # so a failed request is not redirected or substituted.
    assert online.get("independent_review_fallback") is None
    fallback = (online.get("route_defaults") or {}).get("independent_review", {}).get("fallback")
    assert fallback is None
    assert not [
        label
        for label, _ in _routing_targets(manifest["routing"])
        if label.startswith("online.independent_review") and label != "online.independent_review"
    ]
