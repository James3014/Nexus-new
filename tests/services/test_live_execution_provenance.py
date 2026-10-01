"""Tests for transport-neutral live execution provenance (#1266).

These tests intentionally distinguish caller-supplied observations from records read
through repository-owned durable producer APIs.
"""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nexus.services.agy_operation_journal import AgyOperationJournal
from nexus.services.direct_operation_journal import DirectOperationJournal
from nexus.services.live_execution_provenance import (
    EXECUTION_LANE_DIRECT_DELEGATED,
    EXECUTION_LANE_UNKNOWN,
    EXECUTION_STATE_ACTIVE,
    EXECUTION_STATE_COMPLETED,
    EXECUTION_STATE_STALE,
    EXECUTION_STATE_UNKNOWN,
    PRODUCER_SCHEMA_AGY_OPERATION_V1,
    PRODUCER_SCHEMA_EXTERNAL_WORKER_V1,
    TRANSPORT_KIND_LOCAL_RUNNER,
    TRANSPORT_KIND_RDC,
    LiveExecutionProvenance,
    LiveExecutionProvenanceView,
    ProvenanceContractError,
    VerifiedProducerRecord,
    build_live_execution_provenance,
    make_dev_mcp_receipt,
    make_rdc_receipt,
    read_operation_journal_evidence,
)


def _iso_now(offset_seconds: float = 0.0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat()


def _verified_external_worker(
    tmp_path: Path,
    *,
    task_id: str = "task-1",
    attempt_id: str = "attempt-1",
    operation_id: str | None = None,
    status: str = "RUNNING",
    timestamp: str | None = None,
    include_task_id: bool = True,
    include_session: bool = True,
    include_pid: bool = True,
    observed_provider: str = "openai",
    observed_model: str = "gpt-test",
):
    os.environ["NEXUS_EXTERNAL_WORKER_OPERATION_ROOT"] = str(tmp_path)
    journal = DirectOperationJournal(
        tmp_path / "codex",
        schema=PRODUCER_SCHEMA_EXTERNAL_WORKER_V1,
        operation_prefix="codexop_",
    )
    op_id = operation_id or journal.new_operation_id()
    initial = {"repo_root": "James3014/Nexus-new"}
    if include_task_id:
        initial["task_id"] = task_id
    journal.create(
        operation_id=op_id,
        attempt_id=attempt_id,
        cwd=str(tmp_path),
        provider="requested-provider",
        model="requested-model",
        effort="high",
        prompt_sha256="abcd1234",
        runtime_revision="runtime-rev",
        initial_fields=initial,
    )
    changes = {
        "status": status,
        "phase": status,
        "host_id": "host-1",
        "observed_provider": observed_provider,
        "observed_model": observed_model,
        "last_heartbeat_at": timestamp if timestamp is not None else _iso_now(),
    }
    if include_session:
        changes["provider_session_id"] = "session-1"
    if include_pid:
        changes["pid"] = 1234
    journal.update(op_id, **changes)
    evidence = read_operation_journal_evidence(journal, op_id)
    context = {
        "repository": "James3014/Nexus-new",
        "work_contract_id": "1266",
        "task_id": task_id,
        "attempt_id": attempt_id,
        "operation_id": op_id,
        "execution_lane": EXECUTION_LANE_DIRECT_DELEGATED,
        "worker": "requested-worker",
        "provider": "requested-provider",
        "model": "requested-model",
    }
    return journal, evidence, context


def test_unverified_declared_rdc_receipt_never_becomes_active():
    context = {
        "repository": "James3014/Nexus-new",
        "task_id": "victim-task",
        "attempt_id": "victim-attempt",
        "operation_id": "op-x",
        "execution_lane": EXECUTION_LANE_DIRECT_DELEGATED,
    }
    receipt = make_rdc_receipt(
        operation_id="op-x",
        session_id="fake-session",
        host_id="fake-host",
        status="RUNNING",
        timestamp=_iso_now(),
    )
    result = build_live_execution_provenance(context, receipt)
    assert result.execution_state == EXECUTION_STATE_UNKNOWN
    assert result.phase == "UNVERIFIED_PRODUCER_RECORD"


def test_unverified_declared_dev_mcp_receipt_never_becomes_active():
    context = {
        "repository": "James3014/Nexus-new",
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "operation_id": "op-x",
        "execution_lane": EXECUTION_LANE_DIRECT_DELEGATED,
    }
    receipt = make_dev_mcp_receipt(
        operation_id="op-x",
        session_id="fake-session",
        host_id="fake-host",
        status="RUNNING",
        timestamp=_iso_now(),
    )
    result = build_live_execution_provenance(context, receipt)
    assert result.execution_state == EXECUTION_STATE_UNKNOWN
    assert result.phase == "UNVERIFIED_PRODUCER_RECORD"


def test_verified_external_worker_journal_can_produce_live_provenance(tmp_path: Path):
    _journal, evidence, context = _verified_external_worker(tmp_path)
    result = build_live_execution_provenance(context, evidence)
    assert result.execution_state == EXECUTION_STATE_ACTIVE
    assert result.transport_kind == TRANSPORT_KIND_LOCAL_RUNNER
    assert result.task_id == "task-1"
    assert result.attempt_id == "attempt-1"
    assert result.observed_provider == "openai"
    assert result.observed_model == "gpt-test"
    assert evidence.source_ref in result.evidence_refs


def test_verified_journal_missing_task_binding_fails_closed(tmp_path: Path):
    _journal, evidence, context = _verified_external_worker(
        tmp_path,
        include_task_id=False,
    )
    result = build_live_execution_provenance(context, evidence)
    assert result.execution_state == EXECUTION_STATE_UNKNOWN
    assert "MISSING_CROSS_BINDING_IDENTITY" in result.phase
    assert "task_id" in result.phase


def test_verified_journal_missing_physical_identity_fails_closed(tmp_path: Path):
    _journal, evidence, context = _verified_external_worker(
        tmp_path,
        include_session=False,
        include_pid=False,
    )
    result = build_live_execution_provenance(context, evidence)
    assert result.execution_state == EXECUTION_STATE_UNKNOWN
    assert result.phase == "UNVERIFIED_PHYSICAL_IDENTITY"


def test_invalid_producer_timestamp_fails_closed(tmp_path: Path):
    _journal, evidence, context = _verified_external_worker(
        tmp_path,
        timestamp="not-a-time",
    )
    result = build_live_execution_provenance(context, evidence)
    assert result.execution_state == EXECUTION_STATE_UNKNOWN
    assert result.phase == "INVALID_PRODUCER_TIMESTAMP"
    assert result.observed_at == ""


def test_stale_running_producer_becomes_stale(tmp_path: Path):
    _journal, evidence, context = _verified_external_worker(
        tmp_path,
        timestamp=_iso_now(-3600),
    )
    result = build_live_execution_provenance(
        context,
        evidence,
        max_staleness_seconds=300,
    )
    assert result.execution_state == EXECUTION_STATE_STALE
    assert "HEARTBEAT_EXPIRED" in result.phase


def test_cross_binding_mismatch_fails_closed(tmp_path: Path):
    _journal, evidence, context = _verified_external_worker(tmp_path)
    context = dict(context)
    context["task_id"] = "different-task"
    result = build_live_execution_provenance(context, evidence)
    assert result.execution_state == EXECUTION_STATE_UNKNOWN
    assert "CROSS_BINDING_MISMATCH: task_id mismatch" in result.phase


def test_missing_execution_lane_fails_closed_even_for_verified_evidence(tmp_path: Path):
    _journal, evidence, context = _verified_external_worker(tmp_path)
    context = dict(context)
    context.pop("execution_lane")
    result = build_live_execution_provenance(context, evidence)
    assert result.execution_lane == EXECUTION_LANE_UNKNOWN
    assert result.execution_state == EXECUTION_STATE_UNKNOWN
    assert result.phase == "MISSING_OR_UNRECOGNIZED_EXECUTION_LANE"


def test_requested_and_observed_identity_remain_separate(tmp_path: Path):
    _journal, evidence, context = _verified_external_worker(
        tmp_path,
        observed_provider="observed-provider",
        observed_model="observed-model",
    )
    result = build_live_execution_provenance(context, evidence)
    assert result.requested_provider == "requested-provider"
    assert result.requested_model == "requested-model"
    assert result.observed_provider == "observed-provider"
    assert result.observed_model == "observed-model"


def test_verified_transport_override_mismatch_is_rejected(tmp_path: Path):
    _journal, evidence, context = _verified_external_worker(tmp_path)
    with pytest.raises(ProvenanceContractError, match="conflicts with verified producer transport"):
        build_live_execution_provenance(
            context,
            evidence,
            observed_transport_kind=TRANSPORT_KIND_RDC,
        )


def test_cross_repository_view_collision_prevention(tmp_path: Path):
    view = LiveExecutionProvenanceView()
    for repo in ("repo-A", "repo-B"):
        rec = LiveExecutionProvenance(
            repository=repo,
            work_contract_id="1",
            task_id="task",
            attempt_id="attempt",
            execution_lane=EXECUTION_LANE_DIRECT_DELEGATED,
            transport_kind=TRANSPORT_KIND_LOCAL_RUNNER,
            operation_id=f"op-{repo}",
            host_id="h",
            requested_worker="",
            requested_provider="",
            requested_model="",
            observed_worker="",
            observed_provider="",
            observed_model="",
            execution_state=EXECUTION_STATE_UNKNOWN,
        )
        view.ingest(rec)
    assert view.get("repo-A", "task", "attempt") is not None
    assert view.get("repo-B", "task", "attempt") is not None
    with pytest.raises(ProvenanceContractError, match="ambiguous lookup"):
        view.get("task", "attempt")


def test_tampered_projection_hash_fails_closed():
    record = LiveExecutionProvenance(
        repository="repo",
        work_contract_id="1",
        task_id="task",
        attempt_id="attempt",
        execution_lane=EXECUTION_LANE_DIRECT_DELEGATED,
        transport_kind=TRANSPORT_KIND_LOCAL_RUNNER,
        operation_id="op",
        host_id="host",
        requested_worker="",
        requested_provider="",
        requested_model="",
        observed_worker="",
        observed_provider="",
        observed_model="",
        execution_state=EXECUTION_STATE_UNKNOWN,
    )
    payload = record.to_dict()
    payload["execution_state"] = EXECUTION_STATE_ACTIVE
    with pytest.raises(ProvenanceContractError, match="provenance_hash mismatch"):
        LiveExecutionProvenance.from_dict(payload)


def test_cache_rebuild_from_verified_producer_records(tmp_path: Path):
    view = LiveExecutionProvenanceView()
    sources = []
    for idx in range(2):
        journal, evidence, context = _verified_external_worker(
            tmp_path,
            task_id=f"task-{idx}",
            attempt_id=f"attempt-{idx}",
        )
        sources.append((journal, evidence, context))
        view.ingest(build_live_execution_provenance(context, evidence))
    assert len(view.list_live()) == 2
    view.clear_cache()
    assert view.list_live() == []
    for _journal, evidence, context in sources:
        view.ingest(build_live_execution_provenance(context, evidence))
    assert len(view.list_live()) == 2


def test_forbidden_authority_boundaries():
    view = LiveExecutionProvenanceView()
    for method, message in (
        (view.route, "no routing authority"),
        (view.select_model, "no model selection authority"),
        (view.acquire_claim, "no claim authority"),
        (view.authorize_mutation, "no mutation authority"),
        (view.mark_completion, "no completion authority"),
        (view.accept_candidate, "no candidate acceptance authority"),
        (view.merge, "no merge authority"),
        (view.deploy, "no deployment authority"),
    ):
        with pytest.raises(NotImplementedError, match=message):
            method()


def test_verified_record_cannot_be_minted_by_caller():
    forged = {
        "schema": PRODUCER_SCHEMA_EXTERNAL_WORKER_V1,
        "operation_id": "extop_forged",
        "attempt_id": "attempt-forged",
        "status": "RUNNING",
    }
    with pytest.raises(ProvenanceContractError, match="owning read adapter"):
        VerifiedProducerRecord(
            record=forged,
            source_ref="caller:forged",
            transport_kind=TRANSPORT_KIND_LOCAL_RUNNER,
            _verification_token=object(),
        )


def test_fake_journal_object_cannot_mint_verified_evidence():
    class FakeJournal:
        def read(self, operation_id):
            return {
                "schema": PRODUCER_SCHEMA_EXTERNAL_WORKER_V1,
                "operation_id": operation_id,
                "attempt_id": "attempt-forged",
                "status": "RUNNING",
            }

    with pytest.raises(ProvenanceContractError, match="recognized operation journal"):
        read_operation_journal_evidence(FakeJournal(), "extop_forged")


def test_direct_operation_journal_subclass_cannot_mint_trust(tmp_path: Path):
    class FakeJournal(DirectOperationJournal):
        def read(self, operation_id):
            return {
                "schema": PRODUCER_SCHEMA_EXTERNAL_WORKER_V1,
                "operation_id": operation_id,
                "attempt_id": "attempt-forged",
                "status": "RUNNING",
            }

    fake = FakeJournal(
        tmp_path / "fake",
        schema=PRODUCER_SCHEMA_EXTERNAL_WORKER_V1,
        operation_prefix="extop_",
    )
    with pytest.raises(ProvenanceContractError, match="recognized operation journal"):
        read_operation_journal_evidence(fake, "codexop_" + "a" * 32)


def test_verified_envelope_payload_is_copy_and_not_replaceable(tmp_path: Path):
    _journal, evidence, context = _verified_external_worker(tmp_path)
    original = build_live_execution_provenance(context, evidence)
    assert original.execution_state == EXECUTION_STATE_ACTIVE

    leaked = evidence.record
    leaked["status"] = "FAILED"
    leaked["observed_model"] = "forged-model"
    replay = build_live_execution_provenance(context, evidence)
    assert replay.execution_state == EXECUTION_STATE_ACTIVE
    assert replay.observed_model == "gpt-test"

    with pytest.raises(TypeError):
        replace(evidence, source_ref="caller:forged")


@pytest.mark.parametrize(
    "repository",
    ["Attacker/Nexus-new", "/unrelated/checkouts/Nexus-new"],
)
def test_repository_cross_binding_requires_exact_identity(tmp_path: Path, repository: str):
    _journal, evidence, context = _verified_external_worker(tmp_path)
    context = dict(context)
    context["repository"] = repository
    result = build_live_execution_provenance(context, evidence)
    assert result.execution_state == EXECUTION_STATE_UNKNOWN
    assert "CROSS_BINDING_MISMATCH: repository mismatch" in result.phase


def test_completed_with_malformed_timestamp_fails_closed(tmp_path: Path):
    _journal, evidence, context = _verified_external_worker(
        tmp_path,
        status="COMPLETED",
        timestamp="not-a-time",
    )
    result = build_live_execution_provenance(
        context,
        evidence,
        max_staleness_seconds=0,
    )
    assert result.execution_state == EXECUTION_STATE_UNKNOWN
    assert result.phase == "INVALID_PRODUCER_TIMESTAMP"


def test_running_with_malformed_timestamp_and_zero_staleness_limit_fails_closed(tmp_path: Path):
    _journal, evidence, context = _verified_external_worker(
        tmp_path,
        status="RUNNING",
        timestamp="not-a-time",
    )
    result = build_live_execution_provenance(
        context,
        evidence,
        max_staleness_seconds=0,
    )
    assert result.execution_state == EXECUTION_STATE_UNKNOWN
    assert result.phase == "INVALID_PRODUCER_TIMESTAMP"


def test_exact_journal_at_noncanonical_root_is_rejected(tmp_path: Path):
    os.environ["NEXUS_EXTERNAL_WORKER_OPERATION_ROOT"] = str(tmp_path / "canonical")
    journal = DirectOperationJournal(
        tmp_path / "attacker" / "codex",
        schema=PRODUCER_SCHEMA_EXTERNAL_WORKER_V1,
        operation_prefix="codexop_",
    )
    with pytest.raises(ProvenanceContractError, match="canonical producer root"):
        read_operation_journal_evidence(journal, "codexop_" + "a" * 32)


def test_private_mint_is_not_a_trust_boundary(tmp_path: Path):
    op_id = "codexop_" + "b" * 32
    context = {
        "repository": "James3014/Nexus-new",
        "task_id": "task-forged",
        "attempt_id": "attempt-forged",
        "operation_id": op_id,
        "execution_lane": EXECUTION_LANE_DIRECT_DELEGATED,
    }
    record = {
        "schema": PRODUCER_SCHEMA_EXTERNAL_WORKER_V1,
        "repository": "James3014/Nexus-new",
        "task_id": "task-forged",
        "attempt_id": "attempt-forged",
        "operation_id": op_id,
        "status": "RUNNING",
        "host_id": "host-forged",
        "provider_session_id": "session-forged",
        "last_heartbeat_at": _iso_now(),
    }
    envelope = VerifiedProducerRecord._mint(
        record=record,
        source_ref="caller:forged",
        transport_kind=TRANSPORT_KIND_LOCAL_RUNNER,
        record_path=tmp_path / "fake-operation.json",
    )
    result = build_live_execution_provenance(context, envelope)
    assert result.execution_state == EXECUTION_STATE_UNKNOWN
    assert result.phase.startswith("PRODUCER_EVIDENCE_REVALIDATION_FAILED")


def test_old_envelope_fails_closed_after_producer_record_changes(tmp_path: Path):
    journal, evidence, context = _verified_external_worker(tmp_path)
    first = build_live_execution_provenance(context, evidence)
    assert first.execution_state == EXECUTION_STATE_ACTIVE

    journal.update(
        context["operation_id"],
        status="COMPLETED",
        phase="COMPLETED",
        last_heartbeat_at=_iso_now(),
    )
    stale = build_live_execution_provenance(context, evidence)
    assert stale.execution_state == EXECUTION_STATE_UNKNOWN
    assert "fresh read required" in stale.phase

    fresh = read_operation_journal_evidence(journal, context["operation_id"])
    completed = build_live_execution_provenance(context, fresh)
    assert completed.execution_state == EXECUTION_STATE_COMPLETED


@pytest.mark.parametrize("limit", [0, -1, float("nan"), float("inf")])
def test_invalid_staleness_limit_never_keeps_running_record_active(
    tmp_path: Path,
    limit: float,
):
    _journal, evidence, context = _verified_external_worker(tmp_path)
    result = build_live_execution_provenance(
        context,
        evidence,
        max_staleness_seconds=limit,
    )
    assert result.execution_state == EXECUTION_STATE_UNKNOWN
    assert result.phase == "INVALID_STALENESS_LIMIT"


def test_canonical_agy_journal_reader_is_supported(tmp_path: Path):
    os.environ["NEXUS_AGY_OPERATION_ROOT"] = str(tmp_path)
    journal = AgyOperationJournal(tmp_path)
    operation_id = journal.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id="attempt-agy",
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort="high",
        prompt_sha256="a" * 64,
        runtime_revision="b" * 40,
    )
    evidence = read_operation_journal_evidence(journal, operation_id)
    assert evidence.record["schema"] == PRODUCER_SCHEMA_AGY_OPERATION_V1
    assert Path(evidence.record_path).resolve() == journal.record_path(operation_id).resolve()
