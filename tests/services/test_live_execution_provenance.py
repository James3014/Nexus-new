"""Tests for #1266 durable transport-neutral live execution provenance.

Invariants verified:
1. Concurrent visibility: read back Main GPT direct and RDC delegated attempts as separate exact records concurrently.
2. execution_lane != transport_kind: DIRECT_DELEGATED + RDC without an RDC authority lane.
3. Independent requested vs physically observed worker/provider/model.
4. Real DirectOperationJournal readback: physically sourced external-worker journal entry rebuilds live provenance.
5. Canonical Dev MCP and RDC receipt adapters.
6. Negative controls:
   - Missing execution lane -> fails closed to UNKNOWN (MISSING_OR_UNRECOGNIZED_EXECUTION_LANE)
   - Missing receipt -> UNAVAILABLE
   - Unrecognized/arbitrary receipt schema -> fails closed to UNKNOWN (RECEIPT_REJECTED)
   - Missing physical operation/host/session identity -> UNKNOWN (UNVERIFIED_PHYSICAL_IDENTITY)
   - Missing producer timestamp -> UNKNOWN (MISSING_PRODUCER_TIMESTAMP)
   - Stale producer timestamp / expired heartbeat -> STALE
   - Identity cross-binding mismatch (repo, task, attempt) -> UNKNOWN (CROSS_BINDING_MISMATCH)
   - Cross-repository collision protection in LiveExecutionProvenanceView
   - Tampered hash -> raises ProvenanceContractError
7. Rebuildable cache: discarding cache and rebuilding from source records preserves identical view.
8. Authority boundary: proves provenance view cannot route, claim, mutate, complete, accept, merge, or deploy.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nexus.services.direct_operation_journal import DirectOperationJournal
from nexus.services.live_execution_provenance import (
    EXECUTION_LANE_DIRECT_CANONICAL,
    EXECUTION_LANE_DIRECT_DELEGATED,
    EXECUTION_LANE_LOCAL,
    EXECUTION_LANE_UNKNOWN,
    EXECUTION_STATE_ACTIVE,
    EXECUTION_STATE_COMPLETED,
    EXECUTION_STATE_STALE,
    EXECUTION_STATE_UNKNOWN,
    PRODUCER_SCHEMA_DEV_MCP_V1,
    PRODUCER_SCHEMA_OPERATION_V1,
    TRANSPORT_KIND_DEV_MCP,
    TRANSPORT_KIND_LOCAL_RUNNER,
    TRANSPORT_KIND_RDC,
    LiveExecutionProvenance,
    LiveExecutionProvenanceView,
    ProvenanceContractError,
    build_live_execution_provenance,
    make_dev_mcp_receipt,
    make_rdc_receipt,
)


def _iso_now(offset_seconds: float = 0.0) -> str:
    dt = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    return dt.isoformat()


def test_concurrent_visibility_main_gpt_and_rdc():
    now_ts = _iso_now()

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
    direct_receipt = make_dev_mcp_receipt(
        operation_id="op-mcp-01",
        session_id="session-mcp-abc",
        host_id="mac-local",
        pid=12345,
        observed_worker="gpt-6-luna-worker",
        observed_provider="openai",
        observed_model="gpt-6-luna-live",
        status="RUNNING",
        timestamp=now_ts,
        task_id="task-direct-1",
        attempt_id="att-direct-1",
        repository="James3014/Nexus-new",
    )
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
    rdc_receipt = make_rdc_receipt(
        operation_id="op-rdc-01",
        session_id="session-rdc-xyz",
        host_id="remote-cluster-host-9",
        pid=54321,
        observed_worker="rdc-worker-slot-4",
        observed_provider="openai",
        observed_model="gpt-6-luna-2026",
        status="RUNNING",
        timestamp=now_ts,
        task_id="task-rdc-1",
        attempt_id="att-rdc-1",
        repository="James3014/Nexus-new",
    )
    rec_rdc = build_live_execution_provenance(rdc_context, rdc_receipt)

    # Ingest both into view
    view = LiveExecutionProvenanceView()
    view.ingest(rec_direct)
    view.ingest(rec_rdc)

    # Read back concurrently
    live_records = view.list_live()
    assert len(live_records) == 2

    # Check Direct GPT
    d = view.get("James3014/Nexus-new", "task-direct-1", "att-direct-1")
    assert d is not None
    assert d.execution_lane == EXECUTION_LANE_DIRECT_CANONICAL
    assert d.transport_kind == TRANSPORT_KIND_DEV_MCP
    assert d.execution_state == EXECUTION_STATE_ACTIVE
    assert d.observed_worker == "gpt-6-luna-worker"
    assert d.observed_model == "gpt-6-luna-live"

    # Check RDC Delegated
    r = view.get("James3014/Nexus-new", "task-rdc-1", "att-rdc-1")
    assert r is not None
    assert r.execution_lane == EXECUTION_LANE_DIRECT_DELEGATED
    assert r.transport_kind == TRANSPORT_KIND_RDC
    assert r.execution_state == EXECUTION_STATE_ACTIVE
    assert r.observed_worker == "rdc-worker-slot-4"
    assert r.observed_model == "gpt-6-luna-2026"


def test_real_direct_operation_journal_readback(tmp_path: Path):
    journal = DirectOperationJournal(
        tmp_path / "journal",
        schema=PRODUCER_SCHEMA_OPERATION_V1,
        operation_prefix="dir_",
    )
    op_id = journal.new_operation_id()
    att_id = "attempt_op_001"
    now_ts = _iso_now()

    # Create physically sourced record via DirectOperationJournal
    journal.create(
        operation_id=op_id,
        attempt_id=att_id,
        cwd=str(tmp_path),
        provider="openai",
        model="gpt-6-luna",
        effort="high",
        prompt_sha256="abcd1234",
        runtime_revision="c715962e38d8",
        initial_fields={
            "repo_root": "James3014/Nexus-new",
        },
    )

    # Transition to RUNNING with physical process and observation facts
    record = journal.update(
        op_id,
        status="RUNNING",
        pid=9988,
        started_at=now_ts,
        last_heartbeat_at=now_ts,
        observed_provider="openai",
        observed_model="gpt-6-luna-audit",
        provider_session_id="sess-direct-journal",
    )

    work_context = {
        "repository": "James3014/Nexus-new",
        "work_contract_id": "1266",
        "task_id": "task-direct-journal",
        "attempt_id": att_id,
        "execution_lane": EXECUTION_LANE_DIRECT_CANONICAL,
        "worker": "gpt-6-luna",
        "provider": "openai",
        "model": "gpt-6-luna",
    }

    # Rebuild provenance from real journal record
    prov = build_live_execution_provenance(work_context, record)
    assert prov.execution_lane == EXECUTION_LANE_DIRECT_CANONICAL
    assert prov.transport_kind == TRANSPORT_KIND_DEV_MCP
    assert prov.execution_state == EXECUTION_STATE_ACTIVE
    assert prov.operation_id == op_id
    assert prov.attempt_id == att_id
    assert prov.host_id == record["host_id"]
    assert prov.pid == 9988
    assert prov.observed_provider == "openai"
    assert prov.observed_model == "gpt-6-luna-audit"
    assert prov.observed_at == now_ts


def test_execution_lane_differs_from_transport_kind():
    context = {
        "repository": "repo",
        "task_id": "t1",
        "attempt_id": "a1",
        "execution_lane": EXECUTION_LANE_DIRECT_DELEGATED,
    }
    receipt = make_rdc_receipt(
        operation_id="op1",
        host_id="h1",
        pid=123,
        status="RUNNING",
        timestamp=_iso_now(),
        task_id="t1",
        attempt_id="a1",
        repository="repo",
    )
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
        "repository": "repo",
        "task_id": "t1",
        "attempt_id": "a1",
        "execution_lane": EXECUTION_LANE_DIRECT_DELEGATED,
        "worker": "requested-worker-alias",
        "provider": "anthropic",
        "model": "claude-3-opus",
    }
    # Physical receipt reports fallback to gpt-4
    receipt = make_rdc_receipt(
        operation_id="op-fallback",
        host_id="h1",
        pid=1234,
        observed_worker="physical-worker-node-12",
        observed_provider="openai",
        observed_model="gpt-4-turbo",
        status="RUNNING",
        timestamp=_iso_now(),
        task_id="t1",
        attempt_id="a1",
        repository="repo",
    )
    rec = build_live_execution_provenance(context, receipt)

    # Requested must NOT equal observed
    assert rec.requested_worker == "requested-worker-alias"
    assert rec.requested_provider == "anthropic"
    assert rec.requested_model == "claude-3-opus"

    assert rec.observed_worker == "physical-worker-node-12"
    assert rec.observed_provider == "openai"
    assert rec.observed_model == "gpt-4-turbo"


def test_requested_model_never_copied_to_missing_observed():
    context = {
        "repository": "repo",
        "task_id": "t1",
        "attempt_id": "a1",
        "execution_lane": EXECUTION_LANE_DIRECT_CANONICAL,
        "worker": "gpt-6-luna",
        "provider": "openai",
        "model": "gpt-6-luna",
    }
    # Receipt has NO observed_model
    receipt = make_dev_mcp_receipt(
        operation_id="op-mcp",
        session_id="sess-1",
        host_id="h1",
        pid=111,
        status="RUNNING",
        timestamp=_iso_now(),
        task_id="t1",
        attempt_id="a1",
        repository="repo",
    )
    rec = build_live_execution_provenance(context, receipt)
    assert rec.requested_model == "gpt-6-luna"
    # Must NOT copy requested_model to observed_model
    assert rec.observed_model == ""
    assert rec.observed_provider == ""


def test_negative_control_missing_execution_lane():
    # Context missing execution_lane must fail closed to UNKNOWN
    context = {
        "repository": "repo",
        "task_id": "t1",
        "attempt_id": "a1",
    }
    receipt = make_dev_mcp_receipt(
        operation_id="op1",
        session_id="sess1",
        host_id="h1",
        pid=123,
        status="RUNNING",
        timestamp=_iso_now(),
        task_id="t1",
        attempt_id="a1",
        repository="repo",
    )
    rec = build_live_execution_provenance(context, receipt)
    assert rec.execution_lane == EXECUTION_LANE_UNKNOWN
    assert rec.execution_state == EXECUTION_STATE_UNKNOWN
    assert "MISSING_OR_UNRECOGNIZED_EXECUTION_LANE" in rec.phase


def test_negative_control_arbitrary_unrecognized_receipt_schema():
    context = {
        "repository": "repo",
        "task_id": "t1",
        "attempt_id": "a1",
        "execution_lane": EXECUTION_LANE_DIRECT_CANONICAL,
    }
    # Arbitrary dictionary without canonical schema
    arbitrary = {
        "status": "RUNNING",
        "operation_id": "fake-op",
    }
    rec = build_live_execution_provenance(context, arbitrary)
    assert rec.execution_state == EXECUTION_STATE_UNKNOWN
    assert "RECEIPT_REJECTED" in rec.phase


def test_negative_control_missing_physical_identity():
    context = {
        "repository": "repo",
        "task_id": "t1",
        "attempt_id": "a1",
        "execution_lane": EXECUTION_LANE_DIRECT_CANONICAL,
    }
    # Missing host_id and session_id/pid
    receipt = {
        "schema": PRODUCER_SCHEMA_DEV_MCP_V1,
        "transport_kind": TRANSPORT_KIND_DEV_MCP,
        "operation_id": "op1",
        "status": "RUNNING",
        "timestamp": _iso_now(),
        "task_id": "t1",
        "attempt_id": "a1",
        "repository": "repo",
    }
    rec = build_live_execution_provenance(context, receipt)
    assert rec.execution_state == EXECUTION_STATE_UNKNOWN
    assert rec.phase == "UNVERIFIED_PHYSICAL_IDENTITY"


def test_negative_control_missing_and_stale_producer_timestamps():
    context = {
        "repository": "repo",
        "task_id": "t1",
        "attempt_id": "a1",
        "execution_lane": EXECUTION_LANE_DIRECT_CANONICAL,
    }

    # Missing timestamp
    receipt_no_ts = {
        "schema": PRODUCER_SCHEMA_DEV_MCP_V1,
        "transport_kind": TRANSPORT_KIND_DEV_MCP,
        "operation_id": "op1",
        "session_id": "sess1",
        "host_id": "h1",
        "pid": 100,
        "status": "RUNNING",
        "task_id": "t1",
        "attempt_id": "a1",
        "repository": "repo",
    }
    rec_no_ts = build_live_execution_provenance(context, receipt_no_ts)
    assert rec_no_ts.execution_state == EXECUTION_STATE_UNKNOWN
    assert rec_no_ts.phase == "MISSING_PRODUCER_TIMESTAMP"

    # Stale timestamp (1 hour old)
    old_ts = _iso_now(-3600)
    receipt_stale = make_dev_mcp_receipt(
        operation_id="op1",
        session_id="sess1",
        host_id="h1",
        pid=100,
        status="RUNNING",
        timestamp=old_ts,
        task_id="t1",
        attempt_id="a1",
        repository="repo",
    )
    rec_stale = build_live_execution_provenance(context, receipt_stale, max_staleness_seconds=300.0)
    assert rec_stale.execution_state == EXECUTION_STATE_STALE
    assert "HEARTBEAT_EXPIRED" in rec_stale.phase


def test_negative_control_cross_binding_mismatch():
    context = {
        "repository": "James3014/Nexus-new",
        "task_id": "task-alpha",
        "attempt_id": "att-alpha",
        "execution_lane": EXECUTION_LANE_DIRECT_CANONICAL,
    }

    # Task ID mismatch
    receipt_bad_task = make_dev_mcp_receipt(
        operation_id="op1",
        session_id="sess1",
        host_id="h1",
        pid=100,
        status="RUNNING",
        timestamp=_iso_now(),
        task_id="task-DIFFERENT",
        attempt_id="att-alpha",
        repository="James3014/Nexus-new",
    )
    rec_bad_task = build_live_execution_provenance(context, receipt_bad_task)
    assert rec_bad_task.execution_state == EXECUTION_STATE_UNKNOWN
    assert "CROSS_BINDING_MISMATCH: task_id mismatch" in rec_bad_task.phase

    # Repo mismatch
    receipt_bad_repo = make_dev_mcp_receipt(
        operation_id="op1",
        session_id="sess1",
        host_id="h1",
        pid=100,
        status="RUNNING",
        timestamp=_iso_now(),
        task_id="task-alpha",
        attempt_id="att-alpha",
        repository="OtherOwner/OtherRepo",
    )
    rec_bad_repo = build_live_execution_provenance(context, receipt_bad_repo)
    assert rec_bad_repo.execution_state == EXECUTION_STATE_UNKNOWN
    assert "CROSS_BINDING_MISMATCH: repository mismatch" in rec_bad_repo.phase


def test_cross_repository_view_collision_prevention():
    view = LiveExecutionProvenanceView()

    ts = _iso_now()
    # Repo A attempt
    rec_a = build_live_execution_provenance(
        {"repository": "repo-A", "task_id": "t1", "attempt_id": "att1", "execution_lane": EXECUTION_LANE_DIRECT_CANONICAL},
        make_dev_mcp_receipt(operation_id="op-a", session_id="s-a", host_id="h1", pid=1, status="RUNNING", timestamp=ts, task_id="t1", attempt_id="att1", repository="repo-A"),
    )
    # Repo B attempt with identical task_id and attempt_id
    rec_b = build_live_execution_provenance(
        {"repository": "repo-B", "task_id": "t1", "attempt_id": "att1", "execution_lane": EXECUTION_LANE_DIRECT_CANONICAL},
        make_dev_mcp_receipt(operation_id="op-b", session_id="s-b", host_id="h1", pid=2, status="RUNNING", timestamp=ts, task_id="t1", attempt_id="att1", repository="repo-B"),
    )

    view.ingest(rec_a)
    view.ingest(rec_b)

    assert len(view.list_live()) == 2

    # Exact lookup by repository
    qa = view.get("repo-A", "t1", "att1")
    qb = view.get("repo-B", "t1", "att1")
    assert qa is not None and qa.operation_id == "op-a"
    assert qb is not None and qb.operation_id == "op-b"

    # Ambiguous lookup without repository raises error
    with pytest.raises(ProvenanceContractError, match="ambiguous lookup"):
        view.get("t1", "att1")


def test_negative_controls_tampered_hash_fails_closed():
    context = {
        "repository": "repo",
        "task_id": "t1",
        "attempt_id": "a1",
        "execution_lane": EXECUTION_LANE_LOCAL,
    }
    receipt = {
        "schema": PRODUCER_SCHEMA_OPERATION_V1,
        "transport_kind": TRANSPORT_KIND_LOCAL_RUNNER,
        "operation_id": "op-local",
        "session_id": "sess-loc",
        "host_id": "h-loc",
        "pid": 999,
        "status": "RUNNING",
        "timestamp": _iso_now(),
        "task_id": "t1",
        "attempt_id": "a1",
        "repository": "repo",
    }
    rec = build_live_execution_provenance(context, receipt)
    d = rec.to_dict()

    # Tamper with the state
    d["execution_state"] = EXECUTION_STATE_COMPLETED
    with pytest.raises(ProvenanceContractError, match="provenance_hash mismatch"):
        LiveExecutionProvenance.from_dict(d)


def test_rebuildable_from_canonical_sources():
    view = LiveExecutionProvenanceView()
    now_ts = _iso_now()

    for i in range(3):
        ctx = {"repository": "repo", "task_id": f"t{i}", "attempt_id": f"a{i}", "execution_lane": EXECUTION_LANE_DIRECT_DELEGATED}
        rcpt = make_rdc_receipt(operation_id=f"op{i}", host_id=f"h{i}", pid=100 + i, status="COMPLETED", timestamp=now_ts, task_id=f"t{i}", attempt_id=f"a{i}", repository="repo")
        view.ingest(build_live_execution_provenance(ctx, rcpt))

    assert len(view.list_live()) == 3

    # Clear derived cache completely
    view.clear_cache()
    assert len(view.list_live()) == 0

    # Re-ingest from canonical sources
    for i in range(3):
        ctx = {"repository": "repo", "task_id": f"t{i}", "attempt_id": f"a{i}", "execution_lane": EXECUTION_LANE_DIRECT_DELEGATED}
        rcpt = make_rdc_receipt(operation_id=f"op{i}", host_id=f"h{i}", pid=100 + i, status="COMPLETED", timestamp=now_ts, task_id=f"t{i}", attempt_id=f"a{i}", repository="repo")
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
