"""Contract/simulation tests for transport-neutral operation continuity.

These tests exercise source-level contracts with synthetic identities. They are not
physical Local->Online canary evidence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus.services.direct_operation_journal import (
    DirectOperationJournal,
    DirectOperationJournalError,
    public_operation_view,
)
from nexus.services.live_execution_provenance import PRODUCER_SCHEMA_DEV_MCP_V1
from nexus.services.operation_continuity import (
    DISPOSITION_BLOCKED,
    DISPOSITION_CONTINUE,
    DISPOSITION_RECONCILE,
    DISPOSITION_STOP,
    ContinuityExpectation,
    evaluate_journal_operation,
    evaluate_operation_continuity,
)

BASE_HEAD = "a" * 40
HANDOFF_HASH = "b" * 64
FIRST_PASS_HASH = "c" * 64
PREDECESSOR_OPERATION = "codexop_" + "d" * 32
PREDECESSOR_ATTEMPT = "attempt_local_terminal"
OPERATION_ID = "devmcpop_" + "1" * 32
ATTEMPT_ID = "attempt_online_takeover"
REPOSITORY = "James3014/Nexus-new"


def _journal(tmp_path: Path, *, lineage: bool = True) -> DirectOperationJournal:
    journal = DirectOperationJournal(
        tmp_path / "journal",
        schema=PRODUCER_SCHEMA_DEV_MCP_V1,
        operation_prefix="devmcpop_",
    )
    initial_fields = {
        "repo_root": REPOSITORY,
        "base_head": BASE_HEAD,
    }
    if lineage:
        initial_fields.update({
            "predecessor_operation_id": PREDECESSOR_OPERATION,
            "predecessor_attempt_id": PREDECESSOR_ATTEMPT,
            "transition_role": "LOCAL_TO_ONLINE",
            "continuation_role": "ONLINE_TAKEOVER",
            "evidence_refs": ["local-final-receipt", "online-input-packet"],
            "handoff_hash": HANDOFF_HASH,
            "first_pass_receipt_linkage": FIRST_PASS_HASH,
        })
    journal.create(
        operation_id=OPERATION_ID,
        attempt_id=ATTEMPT_ID,
        cwd=str(tmp_path),
        provider="openai",
        model="test-model",
        effort="high",
        prompt_sha256="prompt",
        runtime_revision="test-runtime",
        initial_fields=initial_fields,
    )
    return journal


def _expectation(**overrides: object) -> ContinuityExpectation:
    values = {
        "operation_id": OPERATION_ID,
        "attempt_id": ATTEMPT_ID,
        "repository": REPOSITORY,
        "expected_base_head": BASE_HEAD,
        "predecessor_operation_id": PREDECESSOR_OPERATION,
        "predecessor_attempt_id": PREDECESSOR_ATTEMPT,
        "transition_role": "LOCAL_TO_ONLINE",
        "continuation_role": "ONLINE_TAKEOVER",
        "handoff_hash": HANDOFF_HASH,
        "first_pass_receipt_linkage": FIRST_PASS_HASH,
        "required_evidence_refs": ("local-final-receipt",),
        "expected_paths": ("nexus/services/", "tests/services/"),
    }
    values.update(overrides)
    return ContinuityExpectation(**values)


def test_journal_preserves_predecessor_first_pass_and_handoff_lineage(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    projected = public_operation_view(journal.read(OPERATION_ID))

    assert projected["predecessor_operation_id"] == PREDECESSOR_OPERATION
    assert projected["predecessor_attempt_id"] == PREDECESSOR_ATTEMPT
    assert projected["transition_role"] == "LOCAL_TO_ONLINE"
    assert projected["continuation_role"] == "ONLINE_TAKEOVER"
    assert projected["handoff_hash"] == HANDOFF_HASH
    assert projected["first_pass_receipt_linkage"] == FIRST_PASS_HASH
    assert projected["evidence_refs"] == ["local-final-receipt", "online-input-packet"]


def test_journal_rejects_incomplete_or_malformed_continuity_lineage(tmp_path: Path) -> None:
    journal = DirectOperationJournal(
        tmp_path / "journal",
        schema=PRODUCER_SCHEMA_DEV_MCP_V1,
        operation_prefix="devmcpop_",
    )
    with pytest.raises(DirectOperationJournalError, match="CONTINUITY_PREDECESSOR_INCOMPLETE"):
        journal.create(
            operation_id=OPERATION_ID,
            attempt_id=ATTEMPT_ID,
            cwd=str(tmp_path),
            provider="openai",
            model="test-model",
            effort=None,
            prompt_sha256="prompt",
            runtime_revision=None,
            initial_fields={"predecessor_operation_id": PREDECESSOR_OPERATION},
        )
    assert not journal.operation_dir(OPERATION_ID).exists()

    good = _journal(tmp_path / "second")
    with pytest.raises(DirectOperationJournalError, match="CONTINUITY_HANDOFF_HASH_INVALID"):
        good.update(OPERATION_ID, handoff_hash="not-a-sha256")


def test_transport_session_replacement_does_not_change_logical_operation_identity(
    tmp_path: Path,
) -> None:
    journal = _journal(tmp_path)
    journal.update(
        OPERATION_ID,
        status="COMPLETED",
        phase="TERMINAL",
        exit_code=0,
        provider_session_id="chat-session-alpha",
        observed_changed_paths=["nexus/services/direct_operation_journal.py"],
        scope_validation_state="VERIFIED_IN_SCOPE",
    )
    first = evaluate_journal_operation(journal, _expectation())

    journal.update(OPERATION_ID, provider_session_id="chat-session-beta")
    second = evaluate_journal_operation(journal, _expectation())

    assert first.disposition == DISPOSITION_STOP
    assert second.disposition == DISPOSITION_STOP
    assert first.reason == second.reason == "TERMINAL_PHYSICAL_EFFECT_COMPLETED"
    assert first.operation_id == second.operation_id == OPERATION_ID
    assert first.retry_permitted is second.retry_permitted is False
    assert first.details["transport_evidence"]["provider_session_id"] == "chat-session-alpha"
    assert second.details["transport_evidence"]["provider_session_id"] == "chat-session-beta"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("predecessor_operation_id", "codexop_" + "e" * 32, "PREDECESSOR_OPERATION_ID_MISMATCH"),
        ("predecessor_attempt_id", "attempt_tampered", "PREDECESSOR_ATTEMPT_ID_MISMATCH"),
        ("handoff_hash", "e" * 64, "HANDOFF_HASH_MISMATCH"),
        ("first_pass_receipt_linkage", "f" * 64, "FIRST_PASS_RECEIPT_LINKAGE_MISMATCH"),
    ],
)
def test_tampered_predecessor_or_receipt_lineage_fails_closed(
    tmp_path: Path,
    field: str,
    value: str,
    reason: str,
) -> None:
    journal = _journal(tmp_path)
    record = journal.read(OPERATION_ID)
    record[field] = value

    decision = evaluate_operation_continuity(_expectation(), record)

    assert decision.disposition == DISPOSITION_BLOCKED
    assert decision.retry_permitted is False
    assert decision.reason == reason


def test_predecessor_without_explicit_transition_provenance_fails_closed(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    record = journal.read(OPERATION_ID)
    record["transition_role"] = None

    decision = evaluate_operation_continuity(
        _expectation(transition_role=None),
        record,
    )

    assert decision.disposition == DISPOSITION_BLOCKED
    assert decision.reason == "PREDECESSOR_PROVENANCE_INCOMPLETE"


def test_missing_required_evidence_ref_fails_closed(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    decision = evaluate_journal_operation(
        journal,
        _expectation(required_evidence_refs=("missing-receipt",)),
    )

    assert decision.disposition == DISPOSITION_BLOCKED
    assert decision.reason == "REQUIRED_EVIDENCE_MISSING"
    assert decision.details["missing_evidence_refs"] == ["missing-receipt"]


@pytest.mark.parametrize("status", ["QUEUED", "RUNNING", "WAITING_INPUT"])
def test_active_physical_effect_continues_without_granting_retry(
    tmp_path: Path,
    status: str,
) -> None:
    journal = _journal(tmp_path)
    journal.update(OPERATION_ID, status=status, phase=status)

    decision = evaluate_journal_operation(journal, _expectation())

    assert decision.disposition == DISPOSITION_CONTINUE
    assert decision.terminal is False
    assert decision.retry_permitted is False


def test_outcome_unknown_requires_reconciliation_and_never_grants_retry(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.update(OPERATION_ID, status="OUTCOME_UNKNOWN", phase="TERMINAL")

    decision = evaluate_journal_operation(journal, _expectation())

    assert decision.disposition == DISPOSITION_RECONCILE
    assert decision.terminal is False
    assert decision.retry_permitted is False
    assert decision.reason == "EFFECT_REQUIRES_RECONCILIATION"


def test_unresolved_external_effect_requires_reconciliation(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.update(
        OPERATION_ID,
        status="RUNNING",
        phase="RUNNING",
        has_unresolved_external_effect=True,
    )

    decision = evaluate_journal_operation(journal, _expectation())

    assert decision.disposition == DISPOSITION_RECONCILE
    assert decision.retry_permitted is False
    assert decision.reason == "UNRESOLVED_EXTERNAL_EFFECT_REQUIRES_RECONCILIATION"


@pytest.mark.parametrize(
    ("expectation", "reason"),
    [
        (_expectation(repository="Attacker/OtherRepo"), "REPOSITORY_MISMATCH"),
        (_expectation(expected_base_head="9" * 40), "BASE_HEAD_MISMATCH"),
        (_expectation(attempt_id="attempt_wrong"), "ATTEMPT_ID_MISMATCH"),
    ],
)
def test_repository_base_and_attempt_mismatch_fail_closed(
    tmp_path: Path,
    expectation: ContinuityExpectation,
    reason: str,
) -> None:
    journal = _journal(tmp_path)

    decision = evaluate_journal_operation(journal, expectation)

    assert decision.disposition == DISPOSITION_BLOCKED
    assert decision.retry_permitted is False
    assert decision.reason == reason


def test_scope_violation_and_unexpected_path_fail_closed(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.update(
        OPERATION_ID,
        status="COMPLETED",
        phase="TERMINAL",
        observed_changed_paths=["secret/outside.txt"],
        scope_validation_state="VIOLATION_OUT_OF_SCOPE",
        scope_violations=["secret/outside.txt"],
    )
    decision = evaluate_journal_operation(journal, _expectation())

    assert decision.disposition == DISPOSITION_BLOCKED
    assert decision.reason == "MUTATION_OUTSIDE_ALLOWED_PATHS"

    journal.update(
        OPERATION_ID,
        scope_validation_state="VERIFIED_IN_SCOPE",
        scope_violations=[],
        observed_changed_paths=["other/unexpected.py"],
    )
    decision = evaluate_journal_operation(journal, _expectation())

    assert decision.disposition == DISPOSITION_BLOCKED
    assert decision.reason == "MUTATION_OUTSIDE_EXPECTED_PATHS"


def test_terminal_failure_is_fact_not_completion_or_retry_authority(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.update(OPERATION_ID, status="FAILED", phase="TERMINAL", exit_code=1)

    decision = evaluate_journal_operation(journal, _expectation())

    assert decision.disposition == DISPOSITION_STOP
    assert decision.terminal is True
    assert decision.retry_permitted is False
    assert decision.claim_ceiling == "NEXUS_TRANSPORT_NEUTRAL_OPERATION_CONTINUITY_SOURCE_VERIFIED"
