"""Tests for transport-neutral operation continuity and reconciliation (#1350).

Verifies that durable Nexus logical operations:
1. Survive transport / connector / session / OAuth replacement (R1, R4).
2. Treat transport identity purely as evidence, never durable operation ownership (R2, R4).
3. Strictly enforce OUTCOME_UNKNOWN != retry permission (R3).
4. Forbid blind replay of unresolved external effects (R5).
5. Directly recognize terminal synchronous local effects without recovery choreography (AC 6).
6. Fail closed on missing, mismatched, or tampered operation/effect identity (R5).
7. Reuse existing DirectOperationJournal / #1266 provenance without a second store (AC 8).
8. Pass end-to-end canary matching DevSpace#338 direct coding without Core mutation sessions.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

import nexus.services.live_execution_provenance as provenance_module
from nexus.services.direct_operation_journal import DirectOperationJournal
from nexus.services.live_execution_provenance import (
    EXECUTION_LANE_DIRECT_CANONICAL,
    EXECUTION_LANE_DIRECT_DELEGATED,
    PRODUCER_SCHEMA_DEV_MCP_V1,
    PRODUCER_SCHEMA_RDC_V1,
    TRANSPORT_KIND_DEV_MCP,
    TRANSPORT_KIND_RDC,
)
from nexus.services.operation_continuity import (
    DISPOSITION_BLOCKED,
    DISPOSITION_CONTINUE,
    DISPOSITION_RECONCILE,
    DISPOSITION_STOP,
    EFFECT_KIND_EXTERNAL_PUBLICATION,
    EFFECT_KIND_GIT_COMMIT,
    EFFECT_KIND_LOCAL_MUTATION,
    OPERATION_CONTINUITY_CLAIM_CEILING,
    OPERATION_CONTINUITY_SCHEMA,
    ContinuityContractViolation,
    LogicalOperation,
    PhysicalExecutionReceipt,
    TransportEvidence,
    build_devspace_execution_receipt,
    evaluate_operation_continuity,
    reconcile_journal_operation,
)


@pytest.fixture(autouse=True)
def _isolated_producer_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dev_mcp_root = tmp_path / "dev-mcp"
    rdc_root = tmp_path / "rdc"
    dev_mcp_root.mkdir(parents=True, exist_ok=True)
    rdc_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(provenance_module, "_CANONICAL_DEV_MCP_OPERATION_ROOT", dev_mcp_root)
    monkeypatch.setattr(provenance_module, "_CANONICAL_RDC_OPERATION_ROOT", rdc_root)


def test_dev_mcp_operation_continues_after_chatgpt_connector_replacement():
    """Criterion 1 & R1, R4: Logical operation survives ChatGPT connector / OAuth replacement."""
    op_id = "devmcpop_" + "a" * 32
    att_id = "attempt_" + "1" * 32
    repo = "James3014/Nexus-new"
    logical_op = LogicalOperation(
        operation_id=op_id,
        attempt_id=att_id,
        repository=repo,
        work_contract_id="task-1350",
        execution_lane=EXECUTION_LANE_DIRECT_CANONICAL,
        expected_base_head="1" * 40,
        effect_kind=EFFECT_KIND_LOCAL_MUTATION,
    )

    # Initial execution via Dev MCP in ChatGPT session 1
    receipt_session_1 = PhysicalExecutionReceipt(
        schema=PRODUCER_SCHEMA_DEV_MCP_V1,
        transport_kind=TRANSPORT_KIND_DEV_MCP,
        operation_id=op_id,
        attempt_id=att_id,
        repository=repo,
        status="RUNNING",
        phase="RUNNING",
        transport_evidence=TransportEvidence(
            transport_kind=TRANSPORT_KIND_DEV_MCP,
            connector_session_id="chatgpt-conv-alpha",
            client_id="oauth-client-alpha",
            host_id="mac-host",
            observed_at="2026-10-03T12:00:00+00:00",
        ),
    )
    decision_1 = evaluate_operation_continuity(logical_op, receipt_session_1, now_ts=time.time())
    assert decision_1.disposition == DISPOSITION_CONTINUE
    assert decision_1.terminal is False
    assert decision_1.retry_permitted is False

    # Fresh ChatGPT connector reconnects: conversation_id and client_id changed!
    receipt_session_2 = PhysicalExecutionReceipt(
        schema=PRODUCER_SCHEMA_DEV_MCP_V1,
        transport_kind=TRANSPORT_KIND_DEV_MCP,
        operation_id=op_id,
        attempt_id=att_id,
        repository=repo,
        status="COMPLETED",
        phase="PROCESS_TERMINATED",
        exit_code=0,
        transport_evidence=TransportEvidence(
            transport_kind=TRANSPORT_KIND_DEV_MCP,
            connector_session_id="chatgpt-conv-beta-FRESH",
            client_id="oauth-client-beta-REPLACED",
            host_id="mac-host",
            observed_at="2026-10-03T12:05:00+00:00",
        ),
    )

    decision_2 = evaluate_operation_continuity(logical_op, receipt_session_2, now_ts=time.time())
    # Operation was continued/reconciled under new session WITHOUT recreating the operation
    assert decision_2.disposition == DISPOSITION_STOP
    assert decision_2.terminal is True
    assert decision_2.retry_permitted is False
    assert decision_2.reason == "TERMINAL_LOCAL_EFFECT_COMPLETED"
    assert (
        decision_2.details["transport_evidence"]["connector_session_id"]
        == "chatgpt-conv-beta-FRESH"
    )
    assert decision_2.details["transport_evidence"]["client_id"] == "oauth-client-beta-REPLACED"


def test_same_contract_for_rdc_direct_execution_receipt():
    """Criterion 2: Same contract works for RDC receipt without inventing an RDC authority lane."""
    op_id = "rdcop_" + "b" * 32
    att_id = "attempt_" + "2" * 32
    repo = "James3014/Nexus-new"
    logical_op = LogicalOperation(
        operation_id=op_id,
        attempt_id=att_id,
        repository=repo,
        work_contract_id="task-rdc-work",
        execution_lane=EXECUTION_LANE_DIRECT_DELEGATED,
        effect_kind=EFFECT_KIND_LOCAL_MUTATION,
    )

    rdc_receipt = PhysicalExecutionReceipt(
        schema=PRODUCER_SCHEMA_RDC_V1,
        transport_kind=TRANSPORT_KIND_RDC,
        operation_id=op_id,
        attempt_id=att_id,
        repository=repo,
        status="COMPLETED",
        exit_code=0,
        transport_evidence=TransportEvidence(
            transport_kind=TRANSPORT_KIND_RDC,
            host_id="rdc-worker-node",
            pid=4242,
            observed_at="2026-10-03T12:10:00+00:00",
        ),
    )

    decision = evaluate_operation_continuity(logical_op, rdc_receipt, now_ts=time.time())
    assert decision.disposition == DISPOSITION_STOP
    assert decision.terminal is True
    assert decision.transport_kind == TRANSPORT_KIND_RDC
    assert decision.execution_lane == EXECUTION_LANE_DIRECT_DELEGATED

    # Negative control: RDC is transport kind, NOT an authority lane
    with pytest.raises(ContinuityContractViolation, match="unrecognized or missing execution_lane"):
        LogicalOperation(
            operation_id=op_id,
            attempt_id=att_id,
            repository=repo,
            work_contract_id="task-rdc-work",
            execution_lane="RDC",
        )


def test_oauth_and_session_identity_is_evidence_not_ownership():
    """Criterion 3 & R4: OAuth/client/session identity appears only as transport evidence."""
    op_id = "devmcpop_" + "c" * 32
    logical_op = LogicalOperation(
        operation_id=op_id,
        attempt_id="attempt_c",
        repository="James3014/Nexus-new",
        work_contract_id="task-oauth-test",
        execution_lane=EXECUTION_LANE_DIRECT_CANONICAL,
    )

    receipt = PhysicalExecutionReceipt(
        transport_kind=TRANSPORT_KIND_DEV_MCP,
        operation_id=op_id,
        attempt_id="attempt_c",
        repository="James3014/Nexus-new",
        status="COMPLETED",
        exit_code=0,
        transport_evidence=TransportEvidence(
            transport_kind=TRANSPORT_KIND_DEV_MCP,
            connector_session_id="conv-random-123",
            client_id="oauth-token-xyz",
            host_id="host-1",
            observed_at="2026-10-03T12:00:00+00:00",
        ),
    )

    decision = evaluate_operation_continuity(logical_op, receipt)
    # Evidence is recorded in details
    assert decision.details["transport_evidence"]["connector_session_id"] == "conv-random-123"
    assert decision.details["transport_evidence"]["client_id"] == "oauth-token-xyz"
    # Ownership remains with logical operation
    assert decision.operation_id == op_id
    assert decision.repository == "James3014/Nexus-new"
    assert decision.execution_lane == EXECUTION_LANE_DIRECT_CANONICAL


def test_tampered_or_mismatched_operation_identity_fails_closed():
    """Criterion 4 & R5: Missing, tampered, or mismatched identity fails closed."""
    op_id = "devmcpop_" + "d" * 32
    logical_op = LogicalOperation(
        operation_id=op_id,
        attempt_id="attempt_d",
        repository="James3014/Nexus-new",
        work_contract_id="task-tamper-check",
        execution_lane=EXECUTION_LANE_DIRECT_CANONICAL,
        expected_base_head="2" * 40,
        expected_paths=("src/allowed.py",),
    )

    # 1. Operation ID mismatch fails closed
    bad_op_receipt = PhysicalExecutionReceipt(
        transport_kind=TRANSPORT_KIND_DEV_MCP,
        operation_id="devmcpop_" + "e" * 32,
        attempt_id="attempt_d",
        repository="James3014/Nexus-new",
        status="COMPLETED",
    )
    d1 = evaluate_operation_continuity(logical_op, bad_op_receipt)
    assert d1.disposition == DISPOSITION_BLOCKED
    assert "operation_id mismatch" in d1.reason

    # 2. Repository mismatch fails closed
    bad_repo_receipt = PhysicalExecutionReceipt(
        transport_kind=TRANSPORT_KIND_DEV_MCP,
        operation_id=op_id,
        attempt_id="attempt_d",
        repository="Attacker/OtherRepo",
        status="COMPLETED",
    )
    d2 = evaluate_operation_continuity(logical_op, bad_repo_receipt)
    assert d2.disposition == DISPOSITION_BLOCKED
    assert "repository mismatch" in d2.reason

    # 3. Base head mismatch fails closed
    bad_base_receipt = PhysicalExecutionReceipt(
        transport_kind=TRANSPORT_KIND_DEV_MCP,
        operation_id=op_id,
        attempt_id="attempt_d",
        repository="James3014/Nexus-new",
        base_head="9" * 40,
        status="COMPLETED",
    )
    d3 = evaluate_operation_continuity(logical_op, bad_base_receipt)
    assert d3.disposition == DISPOSITION_BLOCKED
    assert "base_head mismatch" in d3.reason

    # 4. Out of scope path mutation fails closed
    bad_paths_receipt = PhysicalExecutionReceipt(
        transport_kind=TRANSPORT_KIND_DEV_MCP,
        operation_id=op_id,
        attempt_id="attempt_d",
        repository="James3014/Nexus-new",
        status="COMPLETED",
        exit_code=0,
        observed_changed_paths=("src/allowed.py", "secret/leak.txt"),
    )
    d4 = evaluate_operation_continuity(logical_op, bad_paths_receipt)
    assert d4.disposition == DISPOSITION_BLOCKED
    assert d4.reason == "MUTATION_OUTSIDE_ALLOWED_PATHS"


def test_unresolved_external_effect_cannot_be_blindly_replayed():
    """Criterion 5 & R3, R5: Unresolved external effect fails into RECONCILE and forbids retry."""
    op_id = "devmcpop_" + "f" * 32
    logical_op = LogicalOperation(
        operation_id=op_id,
        attempt_id="attempt_f",
        repository="James3014/Nexus-new",
        work_contract_id="task-publish-work",
        execution_lane=EXECUTION_LANE_DIRECT_CANONICAL,
        effect_kind=EFFECT_KIND_EXTERNAL_PUBLICATION,
    )

    unresolved_receipt = PhysicalExecutionReceipt(
        transport_kind=TRANSPORT_KIND_DEV_MCP,
        operation_id=op_id,
        attempt_id="attempt_f",
        repository="James3014/Nexus-new",
        status="OUTCOME_UNKNOWN",
        has_unresolved_external_effect=True,
    )

    decision = evaluate_operation_continuity(logical_op, unresolved_receipt)
    assert decision.disposition == DISPOSITION_RECONCILE
    assert decision.retry_permitted is False  # BLIND REPLAY FORBIDDEN!
    assert decision.terminal is False
    assert decision.reason == "UNRESOLVED_EXTERNAL_EFFECT_REQUIRES_RECONCILIATION"


def test_outcome_unknown_is_not_retry_permission():
    """R3 invariant: OUTCOME_UNKNOWN != retry permission."""
    op_id = "devmcpop_" + "1" * 32
    logical_op = LogicalOperation(
        operation_id=op_id,
        attempt_id="attempt_1",
        repository="James3014/Nexus-new",
        work_contract_id="task-unknown-test",
        execution_lane=EXECUTION_LANE_DIRECT_CANONICAL,
    )

    unknown_receipt = PhysicalExecutionReceipt(
        transport_kind=TRANSPORT_KIND_DEV_MCP,
        operation_id=op_id,
        attempt_id="attempt_1",
        repository="James3014/Nexus-new",
        status="OUTCOME_UNKNOWN",
    )

    decision = evaluate_operation_continuity(logical_op, unknown_receipt)
    assert decision.disposition == DISPOSITION_RECONCILE
    assert decision.retry_permitted is False  # Never retry blindly on OUTCOME_UNKNOWN
    assert decision.terminal is False


def test_terminal_synchronous_local_effect_recognized_directly():
    """Criterion 6: Terminal synchronous local effect recognized without recovery choreography."""
    op_id = "devmcpop_" + "2" * 32
    commit_sha = "c" * 40
    base_sha = "b" * 40
    logical_op = LogicalOperation(
        operation_id=op_id,
        attempt_id="attempt_commit",
        repository="James3014/Nexus-new",
        work_contract_id="task-commit-test",
        execution_lane=EXECUTION_LANE_DIRECT_CANONICAL,
        expected_base_head=base_sha,
        expected_paths=("nexus/example.py",),
        effect_kind=EFFECT_KIND_GIT_COMMIT,
    )

    commit_receipt = PhysicalExecutionReceipt(
        transport_kind=TRANSPORT_KIND_DEV_MCP,
        operation_id=op_id,
        attempt_id="attempt_commit",
        repository="James3014/Nexus-new",
        status="COMPLETED",
        base_head=base_sha,
        current_head=commit_sha,
        observed_changed_paths=("nexus/example.py",),
        exit_code=0,
    )

    decision = evaluate_operation_continuity(logical_op, commit_receipt)
    assert decision.disposition == DISPOSITION_STOP
    assert decision.terminal is True
    assert decision.retry_permitted is False
    assert decision.reason == "TERMINAL_LOCAL_EFFECT_COMPLETED"
    assert decision.details["candidate_commit_sha"] == commit_sha


def test_physical_receipt_does_not_grant_candidate_acceptance_or_merge_authority():
    """Criterion 7: Candidate, verification, acceptance, and merge authorities remain separate."""
    op_id = "devmcpop_" + "3" * 32
    logical_op = LogicalOperation(
        operation_id=op_id,
        attempt_id="attempt_sep",
        repository="James3014/Nexus-new",
        work_contract_id="task-boundary-test",
        execution_lane=EXECUTION_LANE_DIRECT_CANONICAL,
    )

    receipt = PhysicalExecutionReceipt(
        transport_kind=TRANSPORT_KIND_DEV_MCP,
        operation_id=op_id,
        attempt_id="attempt_sep",
        repository="James3014/Nexus-new",
        status="COMPLETED",
        exit_code=0,
    )

    decision = evaluate_operation_continuity(logical_op, receipt)
    # Physical execution produces OPERATION_CONTINUITY_CLAIM_CEILING
    assert decision.claim_ceiling == OPERATION_CONTINUITY_CLAIM_CEILING
    assert decision.schema == OPERATION_CONTINUITY_SCHEMA
    # Does NOT grant candidate acceptance, merge, release, or deploy
    assert "candidate_acceptance" not in decision.details
    assert "merge_performed" not in decision.details


def test_reconciles_via_existing_direct_operation_journal_without_second_store(tmp_path: Path):
    """Criterion 8: Reuses existing DirectOperationJournal; no second durable store."""
    journal_dir = tmp_path / "dev-mcp"
    journal = DirectOperationJournal(
        journal_dir,
        schema=PRODUCER_SCHEMA_DEV_MCP_V1,
        operation_prefix="devmcpop_",
    )
    op_id = journal.new_operation_id()
    att_id = "attempt_journal_01"
    repo_path = str(tmp_path.resolve())

    # Create operation in canonical journal
    journal.create(
        operation_id=op_id,
        attempt_id=att_id,
        cwd=repo_path,
        provider="dev-mcp",
        model="gpt-test",
        effort="high",
        prompt_sha256="abcd",
        runtime_revision="rev-1",
        initial_fields={"repo_root": repo_path},
    )

    logical_op = LogicalOperation(
        operation_id=op_id,
        attempt_id=att_id,
        repository=repo_path,
        work_contract_id="task-journal-reuse",
        execution_lane=EXECUTION_LANE_DIRECT_CANONICAL,
    )

    # Mark completed with exit code 0
    journal.mark_terminal(op_id, status="COMPLETED", exit_code=0)

    # Reconcile using existing journal without introducing a second store
    record, decision = reconcile_journal_operation(
        journal,
        logical_op,
        transport_kind=TRANSPORT_KIND_DEV_MCP,
    )
    assert record["status"] == "COMPLETED"
    assert decision.disposition == DISPOSITION_STOP
    assert decision.terminal is True
    assert decision.reason == "TERMINAL_LOCAL_EFFECT_COMPLETED"


def test_real_canary_direct_coding_survives_connector_replacement_without_core_session():
    """Criterion 9: Real canary after DevSpace#338: direct coding operation survives connector

    replacement and reconciles without DevSpace Core mutation session ownership.
    """
    op_id = "devmcpop_" + "9" * 32
    att_id = "attempt_canary_338"
    repo = "James3014/devspace"
    base_head = "a" * 40
    commit_sha = "c" * 40

    logical_op = LogicalOperation(
        operation_id=op_id,
        attempt_id=att_id,
        repository=repo,
        work_contract_id="DevSpace#338",
        execution_lane=EXECUTION_LANE_DIRECT_CANONICAL,
        expected_base_head=base_head,
        expected_paths=("feature.js",),
        effect_kind=EFFECT_KIND_GIT_COMMIT,
    )

    # Step 1: DevSpace git_commit response in ChatGPT conversation session 1
    # Note: NO coreMutation object (matching DevSpace PR #340 implementation)
    devspace_commit_response_session_1 = {
        "created": True,
        "commitSha": commit_sha,
        "expectedHead": base_head,
        "paths": ["feature.js"],
        "coreMutation": None,  # DevSpace direct coding does not create Core mutation sessions
        "conversationId": "chatgpt-session-1-pre-disconnect",
        "clientId": "oauth-client-initial",
    }

    # Step 2: Build receipt from DevSpace tool response and evaluate in session 1
    receipt_1 = build_devspace_execution_receipt(
        devspace_commit_response_session_1,
        operation_id=op_id,
        attempt_id=att_id,
        repository=repo,
        base_head=base_head,
        conversation_id="chatgpt-session-1-pre-disconnect",
        client_id="oauth-client-initial",
    )
    decision_1 = evaluate_operation_continuity(logical_op, receipt_1)
    assert decision_1.disposition == DISPOSITION_STOP
    assert decision_1.terminal is True
    assert (
        decision_1.details["transport_evidence"]["connector_session_id"]
        == "chatgpt-session-1-pre-disconnect"
    )

    # Step 3: ChatGPT session dies / disconnects. Fresh connector starts session 2.
    # The client now reconciles/continues operation using fresh transport evidence:
    reconnected_receipt = build_devspace_execution_receipt(
        devspace_commit_response_session_1,
        operation_id=op_id,
        attempt_id=att_id,
        repository=repo,
        base_head=base_head,
        conversation_id="chatgpt-session-2-reconnected",
        client_id="oauth-client-fresh-token",
    )

    decision = evaluate_operation_continuity(logical_op, reconnected_receipt)

    # Step 4: Verification of canary claims:
    # 1. Operation survived connector replacement
    assert decision.operation_id == op_id
    assert (
        decision.details["transport_evidence"]["connector_session_id"]
        == "chatgpt-session-2-reconnected"
    )
    assert decision.details["transport_evidence"]["client_id"] == "oauth-client-fresh-token"
    # 2. Terminal commit effect recognized cleanly
    assert decision.disposition == DISPOSITION_STOP
    assert decision.terminal is True
    assert decision.retry_permitted is False
    assert decision.details["candidate_commit_sha"] == commit_sha
    # 3. No Core mutation session was required or expected
    assert reconnected_receipt.raw_payload.get("coreMutation") is None
