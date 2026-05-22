from __future__ import annotations

import pytest

from nexus.contracts.local_event_pipeline import LocalEventPipeline
from nexus.contracts.local_gateway import build_local_gateway_receipt
from nexus.contracts.local_memory_hub import build_local_memory_hub_snapshot


def test_local_gateway_blocks_private_network_targets() -> None:
    receipt = build_local_gateway_receipt(
        target="https://metadata.local/latest",
        target_class="network_fetch",
        resolved_ips=["169.254.169.254"],
        backoff_reason="private_target",
    )

    assert receipt["status"] == "RETURN"
    assert receipt["allowed"] is False
    assert receipt["blockers"] == ["resolved_ip_not_public"]
    assert receipt["runtime_update_allowed"] is False


def test_local_gateway_allows_non_network_provider_gate_without_sidecar() -> None:
    receipt = build_local_gateway_receipt(
        target="provider:gemini",
        target_class="provider_call",
        retry_after_sec=0.25,
        backoff_reason="rate_limit_budget",
    )

    assert receipt["status"] == "PASS"
    assert receipt["allowed"] is True
    assert receipt["retry_policy"]["retry_after_sec"] == 0.25
    assert receipt["public_benchmark_allowed"] is False


def test_local_memory_hub_snapshot_is_read_only_and_health_checked() -> None:
    snapshot = build_local_memory_hub_snapshot(
        capabilities=["codeintel", "memory", "codeintel"],
        evidence_root="docs/reports",
        budget={"max_tokens": 1000},
        recent_receipts=[{"status": "PASS"}],
    )

    assert snapshot["status"] == "PASS"
    assert snapshot["capabilities"] == ["codeintel", "memory"]
    assert snapshot["health"] == "HEALTHY"
    assert snapshot["mutable_global_singleton"] is False
    assert snapshot["distributed_heartbeat_required"] is False


def test_local_memory_hub_degrades_on_dirty_receipts() -> None:
    snapshot = build_local_memory_hub_snapshot(
        capabilities=["codeintel"],
        evidence_root="docs/reports",
        recent_receipts=[{"status": "RETURN"}],
    )

    assert snapshot["status"] == "RETURN"
    assert snapshot["health"] == "DEGRADED"
    assert snapshot["blockers"] == ["recent_receipt_not_clean"]


@pytest.mark.asyncio
async def test_local_event_pipeline_preserves_order_and_blocks_unsealed_evidence() -> None:
    pipeline = LocalEventPipeline(max_events_per_run=2)

    first = await pipeline.publish(run_id="run-1", event_type="progress", payload={"step": "start"})
    second = await pipeline.publish(run_id="run-1", event_type="retry", payload={"attempt": 2})
    overflow = await pipeline.publish(run_id="run-1", event_type="progress", payload={"step": "overflow"})
    blocked = await pipeline.publish(run_id="run-2", event_type="sealed_evidence", evidence_seal_status="RETURN")

    assert first["status"] == "PASS"
    assert second["event"]["sequence"] == 2
    assert [event["event_type"] for event in pipeline.events_for("run-1")] == ["progress", "retry"]
    assert overflow["status"] == "RETURN"
    assert overflow["blockers"] == ["event_backpressure_overflow"]
    assert blocked["blockers"] == ["unsealed_evidence_event_blocked"]
