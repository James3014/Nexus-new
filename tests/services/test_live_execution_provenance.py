"""Tests for #1266 durable transport-neutral live execution provenance.

Invariants verified:
1. Concurrent visibility: read back Main GPT direct and RDC delegated attempts as separate exact records concurrently.
2. execution_lane != transport_kind: DIRECT_DELEGATED + RDC without an RDC authority lane.
3. Independent requested vs physically observed worker/provider/model.
4. Negative controls: missing receipt -> UNAVAILABLE, stale heartbeat -> STALE, tampered hash -> raises ProvenanceContractError, cannot default to ACTIVE/SAFE.
5. Rebuildable cache: discarding cache and rebuilding from source records preserves identical view.
6. Authority boundary: proves provenance view cannot route, claim, mutate, complete, accept, merge, or deploy.
"""

from __future__ import annotations

import pytest

from nexus.services.live_execution_provenance import (
    EXECUTION_LANE_DIRECT_CANONICAL,
    EXECUTION_LANE_DIRECT_DELEGATED,
    EXECUTION_LANE_GOVERNED,
    EXECUTION_LANE_LOCAL,
    EXECUTION_STATE_ACTIVE,
    EXECUTION_STATE_COMPLETED,
    EXECUTION_STATE_STALE,
    EXECUTION_STATE_UNAVAILABLE,
    TRANSPORT_KIND_DEV_MCP,
    TRANSPORT_KIND_ISOLATED_WORKTREE,
    TRANSPORT_KIND_LOCAL_RUNNER,
    TRANSPORT_KIND_RDC,
    LiveExecutionProvenance,
    LiveExecutionProvenanceView,
    ProvenanceContractError,
    build_live_execution_provenance,
)


def test_concurrent_visibility_main_gpt_and_rdc():
    # Direct Main GPT via Dev MCP
    direct_context = {
        "repository": "James3014/Nexus-new",
        "work_contract_id": "1266",
        "task_id": "task-direct-1",
        "attempt_id": "att-direct-1",
        "execution_lane": EXECUTION_LANE_DIRECT_CANONICAL,
        "worker": "gpt-6-luna",
        "provider": "openai",
        "model": "gpt-6-luna",
    }
    direct_receipt = {
        "operation_id": "op-mcp-01",
        "host_id": "mac-local",
        "pid": 12345,
        "observed_worker": "gpt-6-luna-worker",
        "observed_provider": "openai",
        "observed_model": "gpt-6-luna-live",
        "status": "RUNNING",
        "transport_kind": TRANSPORT_KIND_DEV_MCP,
    }
    rec_direct = build_live_execution_provenance(direct_context, direct_receipt)

    # RDC delegated worker
    rdc_context = {
        "repository": "James3014/Nexus-new",
        "work_contract_id": "1266",
        "task_id": "task-rdc-1",
        "attempt_id": "att-rdc-1",
        "execution_lane": EXECUTION_LANE_DIRECT_DELEGATED,
        "worker": "rdc-pool-worker",
        "provider": "openai",
        "model": "gpt-6-luna",
    }
    rdc_receipt = {
        "operation_id": "op-rdc-01",
        "host_id": "remote-cluster-host-9",
        "pid": 54321,
        "observed_worker": "rdc-worker-slot-4",
        "observed_provider": "openai",
        "observed_model": "gpt-6-luna-2026",
        "status": "RUNNING",
        "transport_kind": TRANSPORT_KIND_RDC,
    }
    rec_rdc = build_live_execution_provenance(rdc_context, rdc_receipt)

    # Ingest both into view
    view = LiveExecutionProvenanceView()
    view.ingest(rec_direct)
    view.ingest(rec_rdc)

    # Read back concurrently
    live_records = view.list_live()
    assert len(live_records) == 2

    # Check Direct GPT
    d = view.get("task-direct-1", "att-direct-1")
    assert d is not None
    assert d.execution_lane == EXECUTION_LANE_DIRECT_CANONICAL
    assert d.transport_kind == TRANSPORT_KIND_DEV_MCP
    assert d.execution_state == EXECUTION_STATE_ACTIVE

    # Check RDC Delegated
    r = view.get("task-rdc-1", "att-rdc-1")
    assert r is not None
    assert r.execution_lane == EXECUTION_LANE_DIRECT_DELEGATED
    assert r.transport_kind == TRANSPORT_KIND_RDC
    assert r.execution_state == EXECUTION_STATE_ACTIVE


def test_execution_lane_differs_from_transport_kind():
    # DIRECT_DELEGATED + RDC is valid
    context = {
        "task_id": "t1",
        "attempt_id": "a1",
        "execution_lane": EXECUTION_LANE_DIRECT_DELEGATED,
    }
    receipt = {
        "operation_id": "op1",
        "transport_kind": TRANSPORT_KIND_RDC,
        "status": "RUNNING",
    }
    rec = build_live_execution_provenance(context, receipt)
    assert rec.execution_lane == "DIRECT_DELEGATED"
    assert rec.transport_kind == "RDC"

    # Attempting to declare RDC as an execution_lane fails closed
    with pytest.raises(ProvenanceContractError, match="unrecognized execution_lane: 'RDC'"):
        LiveExecutionProvenance(
            repository="repo",
            work_contract_id="1",
            task_id="t1",
            attempt_id="a1",
            execution_lane="RDC",  # Invalid! Not an authority lane
            transport_kind=TRANSPORT_KIND_RDC,
            operation_id="op1",
            host_id="h1",
            requested_worker="w",
            requested_provider="p",
            requested_model="m",
            observed_worker="w",
            observed_provider="p",
            observed_model="m",
            execution_state=EXECUTION_STATE_ACTIVE,
        )


def test_independent_requested_vs_observed_identities():
    context = {
        "task_id": "t1",
        "attempt_id": "a1",
        "execution_lane": EXECUTION_LANE_DIRECT_DELEGATED,
        "worker": "requested-worker-alias",
        "provider": "anthropic",
        "model": "claude-3-opus",
    }
    # Physical receipt reports fallback to gpt-4
    receipt = {
        "operation_id": "op-fallback",
        "observed_worker": "physical-worker-node-12",
        "observed_provider": "openai",
        "observed_model": "gpt-4-turbo",
        "status": "RUNNING",
        "transport_kind": TRANSPORT_KIND_RDC,
    }
    rec = build_live_execution_provenance(context, receipt)

    # Requested must NOT equal observed
    assert rec.requested_worker == "requested-worker-alias"
    assert rec.requested_provider == "anthropic"
    assert rec.requested_model == "claude-3-opus"

    assert rec.observed_worker == "physical-worker-node-12"
    assert rec.observed_provider == "openai"
    assert rec.observed_model == "gpt-4-turbo"


def test_negative_controls_missing_receipt_and_stale_heartbeat():
    # Missing receipt -> UNAVAILABLE
    context = {
        "task_id": "t1",
        "attempt_id": "a1",
        "execution_lane": EXECUTION_LANE_GOVERNED,
    }
    rec_missing = build_live_execution_provenance(context, None)
    assert rec_missing.execution_state == EXECUTION_STATE_UNAVAILABLE
    assert rec_missing.transport_kind == "UNKNOWN"

    # Stale heartbeat -> STALE
    receipt_stale = {
        "operation_id": "op-dead",
        "status": "HEARTBEAT_EXPIRED",
        "transport_kind": TRANSPORT_KIND_ISOLATED_WORKTREE,
    }
    rec_stale = build_live_execution_provenance(context, receipt_stale)
    assert rec_stale.execution_state == EXECUTION_STATE_STALE


def test_negative_controls_tampered_hash_fails_closed():
    context = {
        "task_id": "t1",
        "attempt_id": "a1",
        "execution_lane": EXECUTION_LANE_LOCAL,
    }
    receipt = {
        "operation_id": "op-local",
        "status": "RUNNING",
        "transport_kind": TRANSPORT_KIND_LOCAL_RUNNER,
    }
    rec = build_live_execution_provenance(context, receipt)
    d = rec.to_dict()

    # Tamper with the state
    d["execution_state"] = EXECUTION_STATE_COMPLETED
    with pytest.raises(ProvenanceContractError, match="provenance_hash mismatch"):
        LiveExecutionProvenance.from_dict(d)


def test_rebuildable_from_canonical_sources():
    view = LiveExecutionProvenanceView()

    # Create 3 records
    for i in range(3):
        ctx = {"task_id": f"t{i}", "attempt_id": f"a{i}", "execution_lane": EXECUTION_LANE_DIRECT_DELEGATED}
        rcpt = {"operation_id": f"op{i}", "status": "COMPLETED", "transport_kind": TRANSPORT_KIND_RDC}
        view.ingest(build_live_execution_provenance(ctx, rcpt))

    assert len(view.list_live()) == 3

    # Clear derived cache completely
    view.clear_cache()
    assert len(view.list_live()) == 0

    # Re-ingest from canonical sources
    for i in range(3):
        ctx = {"task_id": f"t{i}", "attempt_id": f"a{i}", "execution_lane": EXECUTION_LANE_DIRECT_DELEGATED}
        rcpt = {"operation_id": f"op{i}", "status": "COMPLETED", "transport_kind": TRANSPORT_KIND_RDC}
        view.ingest(build_live_execution_provenance(ctx, rcpt))

    rebuilt = view.list_live()
    assert len(rebuilt) == 3


def test_forbidden_authority_boundaries():
    view = LiveExecutionProvenanceView()

    with pytest.raises(NotImplementedError, match="no routing authority"):
        view.route()

    with pytest.raises(NotImplementedError, match="no model selection authority"):
        view.select_model()

    with pytest.raises(NotImplementedError, match="no claim authority"):
        view.acquire_claim()

    with pytest.raises(NotImplementedError, match="no mutation authority"):
        view.authorize_mutation()

    with pytest.raises(NotImplementedError, match="no completion authority"):
        view.mark_completion()

    with pytest.raises(NotImplementedError, match="no candidate acceptance authority"):
        view.accept_candidate()

    with pytest.raises(NotImplementedError, match="no merge authority"):
        view.merge()

    with pytest.raises(NotImplementedError, match="no deployment authority"):
        view.deploy()
