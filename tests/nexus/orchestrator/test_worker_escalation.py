from nexus.executors.worker_contract import WorkerExecutionReceipt, WorkerOutcome, classify_worker_failure
from nexus.orchestrator.worker_escalation import WorkerEscalationPolicy


def _receipt(provider: str, outcome: str, *, evidence_complete: bool = False, commit_created: bool = False):
    return WorkerExecutionReceipt(
        provider=provider,
        task_id="escalation-1",
        target_worktree="/tmp/target",
        worker_status="COMPLETED",
        outcome=outcome,
        exit_code=0 if outcome == WorkerOutcome.PROVEN.value else 1,
        executable_identity="/bin/worker",
        argv=("worker",),
        stdout_sha256="a" * 64,
        stderr_sha256="b" * 64,
        wall_time_ms=1,
        process_group_id=1,
        process_group_killed=False,
        timed_out=False,
        provider_calls=1,
        evidence_complete=evidence_complete,
        commit_created=commit_created,
        merge_performed=False,
        push_performed=False,
    )


def test_failed_cheap_worker_escalates_once():
    policy = WorkerEscalationPolicy("cheap", "strong")

    decision = policy.decide([_receipt("cheap", WorkerOutcome.FAILED.value)])

    assert decision.action == "ESCALATE"
    assert decision.next_provider == "strong"


def test_strong_worker_must_prove_complete_evidence():
    policy = WorkerEscalationPolicy("cheap", "strong")

    decision = policy.decide(
        [
            _receipt("cheap", WorkerOutcome.INCOMPLETE.value),
            _receipt("strong", WorkerOutcome.EXECUTION_COMPLETED.value, evidence_complete=False),
        ]
    )

    assert decision.action == "BLOCK"
    assert decision.next_provider is None


def test_forbidden_mutation_blocks_instead_of_escalating():
    policy = WorkerEscalationPolicy("cheap", "strong")

    decision = policy.decide(
        [_receipt("cheap", WorkerOutcome.FAILED.value, commit_created=True)]
    )

    assert decision.action == "BLOCK"
    assert "forbidden" in decision.reason


def test_execution_completed_returns_action_verify():
    policy = WorkerEscalationPolicy("cheap", "strong")

    decision = policy.decide(
        [_receipt("cheap", WorkerOutcome.EXECUTION_COMPLETED.value, evidence_complete=True)]
    )

    assert decision.action == "VERIFY"
    assert decision.next_provider is None


def test_legacy_proven_outcome_fails_closed_in_policy():
    policy = WorkerEscalationPolicy("cheap", "strong")

    decision = policy.decide(
        [
            _receipt("cheap", WorkerOutcome.INCOMPLETE.value),
            _receipt("strong", WorkerOutcome.PROVEN.value, evidence_complete=True),
        ]
    )

    assert decision.action == "BLOCK"
    assert decision.next_provider is None


def test_failure_taxonomy_blocks_deterministic_and_allows_transient():
    deterministic = _receipt("cheap", WorkerOutcome.FAILED.value)
    deterministic = WorkerExecutionReceipt(**{**deterministic.__dict__, "failure_reason": "malformed verifier command"})
    assert classify_worker_failure(deterministic) == "deterministic"
    assert WorkerEscalationPolicy("cheap", "strong").decide([deterministic]).action == "BLOCK"

    transient = WorkerExecutionReceipt(**{**deterministic.__dict__, "failure_reason": "quota exceeded"})
    assert classify_worker_failure(transient) == "transient"
    assert WorkerEscalationPolicy("cheap", "strong").decide([transient]).action == "ESCALATE"
