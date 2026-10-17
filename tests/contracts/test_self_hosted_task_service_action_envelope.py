"""Characterization of the task-action envelope / approval projection of SHTS (split S6a).

Big-file split step S6a moves the pure task-action and approval projections of
``SelfHostedTaskService`` out of ``nexus/orchestrator/self_hosted_task_service.py`` into a
mixin.  These tests pin the behaviour before the move and must pass unchanged after it:

* ``_task_action_envelope``: the ``action_state`` / ``attention_required`` /
  ``next_action`` / ``recommended_tool`` row of every known status, every special case
  (reconcile, verified-but-uncommitted, salvage, retry, settled candidate-less
  FINAL_BLOCK, promotion-status driven approval rows, branch order), and the full
  envelope shape with its promotion-packet fallbacks and cleanup defaults;
* ``_candidate_commit``, ``_terminal_failure_blocker``, ``_projected_blocker`` and
  ``_settled_candidate_less_final_block`` (every guard);
* ``_with_task_action`` (copy, never mutates its input);
* ``_approval_requirements`` (every input reason, missing / mismatch / stale rule and
  the resulting status);
* that these projections take no state lock and do no file I/O, and that the state
  write path still computes the persisted ``task_action`` under the lock, before the
  atomic replace (lock / I/O order pinned for write, create, mutate and read);
* that every facade-module name the moved code reads (the six status sets and
  ``_bounded_failure_text``) is resolved through the facade at call time, and that
  class patches of one projection are reached from the others and from the facade's
  own callers.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import os
from contextlib import contextmanager
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterator

import pytest
from nexus_runtime import task_lifecycle

import nexus.orchestrator.self_hosted_task_service as service_module
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

COMMIT = "a" * 40
COMMIT_2 = "1" * 40
TREE = "b" * 40
TREE_2 = "2" * 40
FINDINGS = "c" * 64
FINDINGS_2 = "3" * 64

MEMBERS = {
    "_candidate_commit": ("staticmethod", "(state: 'Mapping[str, Any]') -> 'Optional[str]'"),
    "_terminal_failure_blocker": (
        "classmethod",
        "(state: 'Mapping[str, Any]') -> 'Optional[dict[str, Any]]'",
    ),
    "_projected_blocker": (
        "classmethod",
        "(state: 'Mapping[str, Any]') -> 'Optional[dict[str, Any]]'",
    ),
    "_settled_candidate_less_final_block": (
        "classmethod",
        "(state: 'Mapping[str, Any]') -> 'bool'",
    ),
    "_task_action_envelope": ("classmethod", "(state: 'Mapping[str, Any]') -> 'dict[str, Any]'"),
    "_with_task_action": ("classmethod", "(state: 'dict[str, Any]') -> 'dict[str, Any]'"),
    "_approval_requirements": ("staticmethod", "(state: 'Mapping[str, Any]') -> 'dict[str, Any]'"),
}

# status -> (action_state, attention_required, next_action, recommended_tool) for a bare
# ``{"task_id": "t", "status": <status>}`` state (recorded at the pre-move base).
STATUS_ROWS: dict[str, tuple[str, bool, str, str | None]] = {
    "ADOPTING": ("IN_PROGRESS", False, "wait_for_task", "nexus_self_hosted_wait_task"),
    "APPROVAL_INVALIDATED": (
        "ACTION_REQUIRED",
        True,
        "resubmit_exact_approval_binding",
        "nexus_candidate_approve",
    ),
    "APPROVED": (
        "ACTION_REQUIRED",
        True,
        "integrate_approved_candidate",
        "nexus_self_hosted_integrate_approved",
    ),
    "BLOCKED_INVALID_STATE": ("FINAL_BLOCK", True, "inspect_lifecycle_state", None),
    "CANCELLED": ("TERMINAL", False, "none", None),
    "CANDIDATE_CAPTURED": ("IN_PROGRESS", False, "wait_for_task", "nexus_self_hosted_wait_task"),
    "CANDIDATE_COMMITTED": ("IN_PROGRESS", False, "wait_for_task", "nexus_self_hosted_wait_task"),
    "CANDIDATE_REF_PROTECTED": (
        "IN_PROGRESS",
        False,
        "wait_for_task",
        "nexus_self_hosted_wait_task",
    ),
    "DIRECT_APPLIED": ("IN_PROGRESS", False, "nexus_task_finish", "nexus_task_finish"),
    "DIRECT_COMMITTED": ("IN_PROGRESS", False, "nexus_task_finish", "nexus_task_finish"),
    "DIRECT_COMPLETED": ("TERMINAL", False, "none", None),
    "DIRECT_INTENT_RECORDED": ("IN_PROGRESS", False, "nexus_task_finish", "nexus_task_finish"),
    "DIRECT_RECONCILE_REQUIRED": (
        "FINAL_BLOCK",
        True,
        "nexus_task_reconcile",
        "nexus_task_reconcile",
    ),
    "DIRECT_STARTED": ("IN_PROGRESS", False, "nexus_task_finish", "nexus_task_finish"),
    "DIRECT_VERIFIED": ("IN_PROGRESS", False, "nexus_task_finish", "nexus_task_finish"),
    "FINAL_BLOCK": (
        "FINAL_BLOCK",
        True,
        "inspect_receipt_and_candidate",
        "nexus_self_hosted_get_receipt",
    ),
    "INTEGRATED": ("TERMINAL", False, "none", None),
    "INTEGRATED_AND_CLEANED": ("TERMINAL", False, "none", None),
    "INTEGRATED_TARGET_RETAINED": (
        "ACTION_REQUIRED",
        True,
        "retry_cleanup",
        "nexus_self_hosted_cleanup",
    ),
    "INTEGRATING": ("IN_PROGRESS", False, "wait_for_task", "nexus_self_hosted_wait_task"),
    "INTEGRATION_FAILED": (
        "FINAL_BLOCK",
        True,
        "retry_integration_same_task",
        "nexus_self_hosted_retry_integration",
    ),
    "INTEGRATION_FAILED_PRE_APPLY": (
        "FINAL_BLOCK",
        True,
        "retry_integration_same_task",
        "nexus_self_hosted_retry_integration",
    ),
    "INTEGRATION_VERIFY_FAILED_AFTER_APPLY": (
        "FINAL_BLOCK",
        True,
        "owner_review_post_apply_failure",
        "nexus_self_hosted_get_receipt",
    ),
    "PENDING_HUMAN_APPROVAL": (
        "ACTION_REQUIRED",
        True,
        "approve_candidate",
        "nexus_candidate_approve",
    ),
    "REHEARSAL_VERIFIED": ("TERMINAL", False, "none", None),
    "REJECTED": ("TERMINAL", False, "none", None),
    "RETAINED_FOR_REVIEW": (
        "FINAL_BLOCK",
        True,
        "inspect_receipt_and_candidate",
        "nexus_self_hosted_get_receipt",
    ),
    "SUBMITTED": ("IN_PROGRESS", False, "wait_for_task", "nexus_self_hosted_wait_task"),
    "SUPERSEDED": ("TERMINAL", False, "none", None),
    "TARGET_CLEANED": ("IN_PROGRESS", False, "wait_for_task", "nexus_self_hosted_wait_task"),
    "TARGET_LEASED": ("IN_PROGRESS", False, "wait_for_task", "nexus_self_hosted_wait_task"),
    "VERIFIED": ("IN_PROGRESS", False, "wait_for_task", "nexus_self_hosted_wait_task"),
    "WORKER_COMPLETED": ("IN_PROGRESS", False, "wait_for_task", "nexus_self_hosted_wait_task"),
    "WORKER_ESCALATING": ("IN_PROGRESS", False, "wait_for_task", "nexus_self_hosted_wait_task"),
    "WORKER_RUNNING": ("IN_PROGRESS", False, "wait_for_task", "nexus_self_hosted_wait_task"),
}

INSPECT_LIFECYCLE = ("FINAL_BLOCK", True, "inspect_lifecycle_state", None)
SETTLED_FINAL_BLOCK = {
    "task_id": "t",
    "status": "FINAL_BLOCK",
    "promotion_status": "NOT_CREATED",
    "cleanup_decision": "REMOVED",
}


def _row(action: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    return (
        action["action_state"],
        action["attention_required"],
        action["next_action"],
        action["recommended_tool"],
    )


def _envelope(**state: Any) -> dict[str, Any]:
    return SelfHostedTaskService._task_action_envelope({"task_id": "t", **state})


@pytest.fixture
def service(tmp_path: Path) -> SelfHostedTaskService:
    return SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)


# ---------------------------------------------------------------------------
# member table


def test_members_keep_descriptor_kinds_and_signatures() -> None:
    for name, (kind, signature) in MEMBERS.items():
        static = inspect.getattr_static(SelfHostedTaskService, name)
        assert type(static).__name__ == kind, name
        func = static.__func__
        assert str(inspect.signature(func)).replace("cls, ", "") == signature, name


def test_members_keep_their_docstrings() -> None:
    assert (
        SelfHostedTaskService._settled_candidate_less_final_block.__doc__
        == "Identify a terminal failure whose retry is historical, not required."
    )
    assert (
        SelfHostedTaskService._approval_requirements.__doc__
        == "Project durable Architecture Approval inputs without granting approval."
    )
    for name in ("_candidate_commit", "_task_action_envelope", "_with_task_action"):
        assert getattr(SelfHostedTaskService, name).__doc__ is None, name


def test_members_are_reachable_on_the_class_and_on_an_instance(
    service: SelfHostedTaskService,
) -> None:
    state = {"task_id": "t", "status": "SUBMITTED"}
    # scripts/ops/nexus_gateway_auto_deploy.py calls the envelope on the class itself
    assert SelfHostedTaskService._task_action_envelope(state) == service._task_action_envelope(
        state
    )
    assert SelfHostedTaskService._approval_requirements(state) == service._approval_requirements(
        state
    )
    assert service._with_task_action(state)["task_action"] == _envelope(status="SUBMITTED")


# ---------------------------------------------------------------------------
# _task_action_envelope: one row per status


def test_status_rows_cover_every_known_status() -> None:
    assert set(STATUS_ROWS) == set(task_lifecycle.KNOWN_SELF_HOSTED_STATUSES)


@pytest.mark.parametrize("status", sorted(STATUS_ROWS))
def test_envelope_row_for_every_known_status(status: str) -> None:
    assert _row(_envelope(status=status)) == STATUS_ROWS[status]


@pytest.mark.parametrize("status", ["NOT_A_STATUS", "", None, 7, "submitted"])
def test_envelope_unknown_status_is_inspect_lifecycle_state(status: Any) -> None:
    assert _row(_envelope(status=status)) == INSPECT_LIFECYCLE


def test_envelope_missing_status_reads_unknown() -> None:
    action = SelfHostedTaskService._task_action_envelope({})
    assert action["task_status"] == "UNKNOWN"
    assert action["task_id"] is None
    assert _row(action) == INSPECT_LIFECYCLE


def test_envelope_invalid_state_wins_over_promotion_status() -> None:
    action = _envelope(status="BLOCKED_INVALID_STATE", promotion_status="APPROVED")
    assert _row(action) == INSPECT_LIFECYCLE


def test_envelope_direct_reconcile_retained_for_review() -> None:
    action = _envelope(
        status="DIRECT_RECONCILE_REQUIRED", reconciliation_decision="RETAINED_FOR_REVIEW"
    )
    assert _row(action) == (
        "FINAL_BLOCK",
        True,
        "inspect_receipt_and_candidate",
        "nexus_task_status",
    )
    other = _envelope(status="DIRECT_RECONCILE_REQUIRED", reconciliation_decision="OTHER")
    assert _row(other) == STATUS_ROWS["DIRECT_RECONCILE_REQUIRED"]


def test_envelope_integrating_is_checked_before_approval_rows() -> None:
    action = _envelope(status="INTEGRATING", promotion_status="APPROVED")
    assert _row(action) == STATUS_ROWS["INTEGRATING"]


@pytest.mark.parametrize(
    ("status", "promotion_status", "expected"),
    [
        (
            "SUBMITTED",
            "APPROVED",
            ("integrate_approved_candidate", "nexus_self_hosted_integrate_approved"),
        ),
        (
            "SUBMITTED",
            "APPROVAL_INVALIDATED",
            ("resubmit_exact_approval_binding", "nexus_candidate_approve"),
        ),
        ("SUBMITTED", "PENDING_HUMAN_APPROVAL", ("approve_candidate", "nexus_candidate_approve")),
        ("INTEGRATED", "PENDING_HUMAN_APPROVAL", ("approve_candidate", "nexus_candidate_approve")),
        (
            "CANCELLED",
            "APPROVED",
            ("integrate_approved_candidate", "nexus_self_hosted_integrate_approved"),
        ),
        (
            "VERIFIED",
            "APPROVAL_INVALIDATED",
            ("resubmit_exact_approval_binding", "nexus_candidate_approve"),
        ),
        # APPROVED status wins over an invalidated promotion status, invalidated over pending
        (
            "APPROVED",
            "APPROVAL_INVALIDATED",
            ("integrate_approved_candidate", "nexus_self_hosted_integrate_approved"),
        ),
        (
            "APPROVAL_INVALIDATED",
            "PENDING_HUMAN_APPROVAL",
            ("resubmit_exact_approval_binding", "nexus_candidate_approve"),
        ),
        (
            "PENDING_HUMAN_APPROVAL",
            "APPROVED",
            ("integrate_approved_candidate", "nexus_self_hosted_integrate_approved"),
        ),
    ],
)
def test_envelope_promotion_status_drives_the_approval_rows(
    status: str, promotion_status: str, expected: tuple[str, str]
) -> None:
    action = _envelope(status=status, promotion_status=promotion_status)
    assert _row(action) == ("ACTION_REQUIRED", True, *expected)


@pytest.mark.parametrize(
    "status", ["DIRECT_COMPLETED", "DIRECT_STARTED", "INTEGRATION_FAILED_PRE_APPLY", "FINAL_BLOCK"]
)
def test_envelope_status_rows_before_the_approval_rows_ignore_promotion_status(status: str) -> None:
    action = _envelope(status=status, promotion_status="APPROVED")
    assert _row(action) == STATUS_ROWS[status]


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (
            {"status": "INTEGRATION_FAILED", "merge_performed": True},
            ("inspect_receipt_and_candidate", "nexus_self_hosted_get_receipt"),
        ),
        (
            {"status": "INTEGRATION_FAILED", "merge_performed": False},
            ("retry_integration_same_task", "nexus_self_hosted_retry_integration"),
        ),
        (
            {
                "status": "FINAL_BLOCK",
                "verified_receipt": {"verified": True},
                "attempt_resolution": {"verdict": "PROVEN"},
            },
            (
                "recover_verified_candidate",
                "nexus_self_hosted_recover_verified_uncommitted_candidate",
            ),
        ),
        (
            {
                "status": "RETAINED_FOR_REVIEW",
                "verified_receipt": {"verified": True},
                "attempt_resolution": {"verdict": "PROVEN"},
            },
            (
                "recover_verified_candidate",
                "nexus_self_hosted_recover_verified_uncommitted_candidate",
            ),
        ),
        (
            {
                "status": "INTEGRATION_FAILED",
                "merge_performed": True,
                "verified_receipt": {"verified": True},
                "attempt_resolution": {"verdict": "PROVEN"},
            },
            (
                "recover_verified_candidate",
                "nexus_self_hosted_recover_verified_uncommitted_candidate",
            ),
        ),
        (
            # integration retry is checked before the verified-uncommitted recovery
            {
                "status": "INTEGRATION_FAILED",
                "verified_receipt": {"verified": True},
                "attempt_resolution": {"verdict": "PROVEN"},
            },
            ("retry_integration_same_task", "nexus_self_hosted_retry_integration"),
        ),
        (
            {
                "status": "FINAL_BLOCK",
                "verified_receipt": {"verified": True},
                "attempt_resolution": {"verdict": "PROVEN"},
                "candidate_commit_sha": COMMIT,
            },
            ("inspect_receipt_and_candidate", "nexus_self_hosted_get_receipt"),
        ),
        (
            {
                "status": "FINAL_BLOCK",
                "verified_receipt": {"verified": True},
                "attempt_resolution": {"verdict": "PROVEN"},
                "promotion_packet": {"candidate_commit_sha": COMMIT},
            },
            ("inspect_receipt_and_candidate", "nexus_self_hosted_get_receipt"),
        ),
        (
            {
                "status": "FINAL_BLOCK",
                "verified_receipt": {"verified": True},
                "attempt_resolution": {"verdict": "PROVEN"},
                "cleanup_decision": "TARGET_CLEANED",
            },
            ("inspect_receipt_and_candidate", "nexus_self_hosted_get_receipt"),
        ),
        (
            {
                "status": "FINAL_BLOCK",
                "verified_receipt": {"verified": False},
                "attempt_resolution": {"verdict": "PROVEN"},
            },
            ("inspect_receipt_and_candidate", "nexus_self_hosted_get_receipt"),
        ),
        (
            {
                "status": "FINAL_BLOCK",
                "verified_receipt": {"verified": True},
                "attempt_resolution": {"verdict": "REFUTED"},
            },
            ("inspect_receipt_and_candidate", "nexus_self_hosted_get_receipt"),
        ),
        (
            {"status": "RETAINED_FOR_REVIEW", "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES"},
            ("salvage_or_dispose_retained_target", "nexus_self_hosted_cleanup"),
        ),
        (
            {"status": "FINAL_BLOCK", "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES"},
            ("inspect_receipt_and_candidate", "nexus_self_hosted_get_receipt"),
        ),
        (
            {
                "status": "RETAINED_FOR_REVIEW",
                "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES",
                "verified_receipt": {"verified": True},
                "attempt_resolution": {"verdict": "PROVEN"},
            },
            (
                "recover_verified_candidate",
                "nexus_self_hosted_recover_verified_uncommitted_candidate",
            ),
        ),
        (
            {
                "status": "RETAINED_FOR_REVIEW",
                "promotion_status": "NOT_CREATED",
                "cleanup_decision": "REMOVED",
            },
            ("inspect_receipt_and_candidate", "nexus_self_hosted_get_receipt"),
        ),
        (
            {
                "status": "FINAL_BLOCK",
                "promotion_status": "NOT_CREATED",
                "cleanup_decision": "ALREADY_REMOVED",
                "uncertain_mutation": True,
            },
            ("retry_same_task", "nexus_self_hosted_retry"),
        ),
        (
            {"status": "FINAL_BLOCK", "promotion_status": "", "cleanup_decision": "REMOVED"},
            ("inspect_receipt_and_candidate", "nexus_self_hosted_get_receipt"),
        ),
        (
            {
                "status": "FINAL_BLOCK",
                "promotion_status": "NOT_CREATED",
                "cleanup_decision": "RETAINED",
            },
            ("inspect_receipt_and_candidate", "nexus_self_hosted_get_receipt"),
        ),
        (
            {
                "status": "FINAL_BLOCK",
                "promotion_status": "NOT_CREATED",
                "cleanup_decision": "REMOVED",
                "promotion_packet": {"candidate_commit_sha": COMMIT},
            },
            ("inspect_receipt_and_candidate", "nexus_self_hosted_get_receipt"),
        ),
    ],
)
def test_envelope_terminal_failure_next_action(
    state: dict[str, Any], expected: tuple[str, str]
) -> None:
    action = _envelope(**state)
    assert _row(action) == ("FINAL_BLOCK", True, *expected)


def test_envelope_settled_candidate_less_final_block_is_terminal() -> None:
    action = SelfHostedTaskService._task_action_envelope(SETTLED_FINAL_BLOCK)
    assert _row(action) == ("TERMINAL", False, "retry_same_task", "nexus_self_hosted_retry")


def test_envelope_unsettled_retryable_final_block_still_needs_attention() -> None:
    state = {**SETTLED_FINAL_BLOCK, "reconciliation_required": True}
    action = SelfHostedTaskService._task_action_envelope(state)
    assert _row(action) == ("FINAL_BLOCK", True, "retry_same_task", "nexus_self_hosted_retry")


def test_envelope_settled_rule_applies_to_every_terminal_failure_next_action() -> None:
    # a settled FINAL_BLOCK can still carry a verified-uncommitted next action; the
    # settled rule only flips action_state / attention_required
    state = {
        **SETTLED_FINAL_BLOCK,
        "cleanup_decision": "BLOCKED",
        "verified_receipt": {"verified": True},
        "attempt_resolution": {"verdict": "PROVEN"},
    }
    assert _row(SelfHostedTaskService._task_action_envelope(state))[0] == "FINAL_BLOCK"


def test_envelope_non_mapping_verified_receipt_raises() -> None:
    with pytest.raises(AttributeError):
        _envelope(status="FINAL_BLOCK", verified_receipt="yes")
    with pytest.raises(AttributeError):
        _envelope(
            status="FINAL_BLOCK", verified_receipt={"verified": True}, attempt_resolution=["x"]
        )


def test_envelope_falsy_verified_receipt_and_resolution_are_tolerated() -> None:
    action = _envelope(status="FINAL_BLOCK", verified_receipt=None, attempt_resolution="")
    assert _row(action) == STATUS_ROWS["FINAL_BLOCK"]


def test_envelope_full_shape_with_packet_fallbacks() -> None:
    state = {
        "task_id": "task-9",
        "status": "PENDING_HUMAN_APPROVAL",
        "promotion_status": "PENDING_HUMAN_APPROVAL",
        "candidate_ref": "refs/nexus/candidate/9",
        "candidate_tree_sha": TREE,
        "promotion_packet": {
            "candidate_commit_sha": COMMIT,
            "candidate_tree_sha": TREE_2,
            "candidate_state_hash": "state-hash",
            "verified_receipt_hash": "receipt-hash",
            "candidate_ref": "ignored",
        },
        "cleanup_eligible": True,
        "cleanup_decision": "DEFERRED",
        "cleanup_blocker": "busy",
        "cleanup_performed": "yes",
        "cleanup_performed_at": "2026-10-18T00:00:00Z",
        "state_retention_status": "ACTIVE",
        "archive_eligible": 0,
    }
    assert SelfHostedTaskService._task_action_envelope(state) == {
        "schema": "nexus.self_hosted_task_action.v1",
        "task_id": "task-9",
        "task_status": "PENDING_HUMAN_APPROVAL",
        "promotion_status": "PENDING_HUMAN_APPROVAL",
        "action_state": "ACTION_REQUIRED",
        "attention_required": True,
        "next_action": "approve_candidate",
        "recommended_tool": "nexus_candidate_approve",
        "candidate_commit_sha": COMMIT,
        "candidate_ref": "refs/nexus/candidate/9",
        "candidate": {
            "candidate_commit_sha": COMMIT,
            "candidate_tree_sha": TREE,
            "candidate_state_hash": "state-hash",
            "verified_receipt_hash": "receipt-hash",
        },
        "cleanup_status": {
            "cleanup_eligible": True,
            "cleanup_decision": "DEFERRED",
            "cleanup_blocker": "busy",
            "cleanup_performed": "yes",
            "cleanup_performed_at": "2026-10-18T00:00:00Z",
            "state_retention_status": "ACTIVE",
            "archive_eligible": 0,
        },
    }


def test_envelope_defaults_for_a_bare_state() -> None:
    action = SelfHostedTaskService._task_action_envelope({
        "status": "SUBMITTED",
        "promotion_status": "",
    })
    assert action["promotion_status"] is None
    assert action["candidate_commit_sha"] is None
    assert action["candidate_ref"] is None
    assert action["candidate"] == {
        "candidate_commit_sha": None,
        "candidate_tree_sha": None,
        "candidate_state_hash": None,
        "verified_receipt_hash": None,
    }
    assert action["cleanup_status"] == {
        "cleanup_eligible": False,
        "cleanup_decision": None,
        "cleanup_blocker": None,
        "cleanup_performed": False,
        "cleanup_performed_at": None,
        "state_retention_status": None,
        "archive_eligible": False,
    }


def test_envelope_non_mapping_packet_is_ignored() -> None:
    action = _envelope(status="SUBMITTED", promotion_packet=["x"], candidate_state_hash="s")
    assert action["candidate"] == {
        "candidate_commit_sha": None,
        "candidate_tree_sha": None,
        "candidate_state_hash": "s",
        "verified_receipt_hash": None,
    }


def test_envelope_stringifies_status_and_promotion_status() -> None:
    action = _envelope(status=0, promotion_status=0)
    assert action["task_status"] == "UNKNOWN"
    assert action["promotion_status"] is None
    action = _envelope(status=["SUBMITTED"], promotion_status=5)
    assert action["task_status"] == "['SUBMITTED']"
    assert action["promotion_status"] == "5"


def test_envelope_accepts_any_mapping_and_does_not_mutate() -> None:
    state = {
        "task_id": "t",
        "status": "FINAL_BLOCK",
        "verified_receipt": {"verified": True},
        "attempt_resolution": {"verdict": "PROVEN"},
        "promotion_packet": {"candidate_tree_sha": TREE},
    }
    frozen = copy.deepcopy(state)
    proxied = SelfHostedTaskService._task_action_envelope(MappingProxyType(state))
    assert proxied == SelfHostedTaskService._task_action_envelope(state)
    assert state == frozen


# ---------------------------------------------------------------------------
# _candidate_commit


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (
            {
                "candidate_commit_sha": COMMIT,
                "promotion_packet": {"candidate_commit_sha": COMMIT_2},
            },
            COMMIT,
        ),
        (
            {"candidate_commit_sha": "", "promotion_packet": {"candidate_commit_sha": COMMIT_2}},
            COMMIT_2,
        ),
        (
            {"candidate_commit_sha": None, "promotion_packet": {"candidate_commit_sha": COMMIT_2}},
            COMMIT_2,
        ),
        ({"promotion_packet": {"candidate_commit_sha": ""}}, ""),
        ({"candidate_commit_sha": "", "promotion_packet": {}}, None),
        ({"promotion_packet": "not-a-mapping"}, None),
        ({"candidate_commit_sha": 0, "promotion_packet": None}, None),
        ({}, None),
        ({"candidate_commit_sha": "not-validated"}, "not-validated"),
    ],
)
def test_candidate_commit(state: dict[str, Any], expected: Any) -> None:
    assert SelfHostedTaskService._candidate_commit(state) == expected


# ---------------------------------------------------------------------------
# _terminal_failure_blocker / _projected_blocker


@pytest.mark.parametrize("status", ["FINAL_BLOCK", "RETAINED_FOR_REVIEW", "INTEGRATION_FAILED"])
def test_terminal_failure_blocker_evidence(status: str) -> None:
    raw = "  boom\n  happened  "
    state = {
        "status": status,
        "error": raw,
        "worker_provider": " codex ",
        "request": {"provider": "agy", "model": " gpt-x "},
        "exit_code": "3",
        "execution_outcome": 17,
    }
    assert SelfHostedTaskService._terminal_failure_blocker(state) == {
        "code": "WORKER_EXECUTION_FAILED",
        "detail": "worker execution failed",
        "error_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "failure_stage": "worker_execution",
        "provider": "codex",
        "model": "gpt-x",
        "exit_code": 3,
        "execution_outcome": "17",
    }


@pytest.mark.parametrize(
    "state",
    [
        {"status": "SUBMITTED", "error": "boom"},
        {"status": "INTEGRATION_FAILED_PRE_APPLY", "error": "boom"},
        {"status": "CANCELLED", "error": "boom"},
        {"error": "boom"},
        {"status": "FINAL_BLOCK"},
        {"status": "FINAL_BLOCK", "error": None},
        {"status": "FINAL_BLOCK", "error": ""},
        {"status": "FINAL_BLOCK", "error": " \n\t "},
        {"status": "FINAL_BLOCK", "error": 0},
    ],
)
def test_terminal_failure_blocker_absent(state: dict[str, Any]) -> None:
    assert SelfHostedTaskService._terminal_failure_blocker(state) is None


def test_terminal_failure_blocker_minimal_and_optional_fields() -> None:
    base = {"status": "FINAL_BLOCK", "error": 42}
    minimal = SelfHostedTaskService._terminal_failure_blocker(base)
    assert minimal is not None
    assert minimal == {
        "code": "WORKER_EXECUTION_FAILED",
        "detail": "worker execution failed",
        "error_sha256": hashlib.sha256(b"42").hexdigest(),
        "failure_stage": "worker_execution",
    }
    for extra, expected in [
        ({"request": {"provider": " agy "}}, {"provider": "agy"}),
        ({"worker_provider": "", "request": {"provider": "agy"}}, {"provider": "agy"}),
        ({"worker_provider": "  ", "request": {"provider": "agy"}}, {}),
        ({"request": "not-a-mapping", "worker_provider": "w"}, {"provider": "w"}),
        ({"request": {"model": "  "}}, {}),
        ({"exit_code": 0}, {"exit_code": 0}),
        ({"exit_code": None}, {}),
        ({"exit_code": "nope"}, {}),
        ({"exit_code": [1]}, {}),
        ({"exit_code": 2.9}, {"exit_code": 2}),
        ({"execution_outcome": ""}, {}),
        ({"execution_outcome": "TIMEOUT"}, {"execution_outcome": "TIMEOUT"}),
    ]:
        assert SelfHostedTaskService._terminal_failure_blocker({**base, **extra}) == {
            **minimal,
            **expected,
        }, extra


def test_terminal_failure_blocker_detail_goes_through_the_bounded_text_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Any] = []
    monkeypatch.setattr(
        service_module, "_bounded_failure_text", lambda value: seen.append(value) or "BOUNDED"
    )
    blocker = SelfHostedTaskService._terminal_failure_blocker({
        "status": "FINAL_BLOCK",
        "error": "x",
    })
    assert blocker is not None and blocker["detail"] == "BOUNDED"
    assert seen == ["worker execution failed"]


def test_projected_blocker_prefers_a_present_blocker() -> None:
    blocker = {"code": "OWN"}
    state = {"status": "FINAL_BLOCK", "error": "boom", "blocker": blocker}
    assert SelfHostedTaskService._projected_blocker(state) is blocker
    # a present falsy, non-None blocker is returned as is
    assert SelfHostedTaskService._projected_blocker({**state, "blocker": False}) is False
    assert SelfHostedTaskService._projected_blocker({**state, "blocker": {}}) == {}


def test_projected_blocker_falls_back_to_the_terminal_failure_blocker() -> None:
    state = {"status": "FINAL_BLOCK", "error": "boom"}
    expected = SelfHostedTaskService._terminal_failure_blocker(state)
    assert expected is not None
    assert SelfHostedTaskService._projected_blocker(state) == expected
    assert SelfHostedTaskService._projected_blocker({**state, "blocker": None}) == expected
    assert (
        SelfHostedTaskService._projected_blocker({"status": "SUBMITTED", "blocker": None}) is None
    )


# ---------------------------------------------------------------------------
# _settled_candidate_less_final_block


def test_settled_candidate_less_final_block_accepts_the_settled_shape() -> None:
    assert SelfHostedTaskService._settled_candidate_less_final_block(SETTLED_FINAL_BLOCK) is True
    for extra in [
        {"cleanup_decision": "ALREADY_REMOVED"},
        {"cleanup_decision": "TARGET_CLEANED"},
        {"reconciliation_required": False},
        {"reconciliation_status": "RECONCILED"},
        {"reconciliation_status": "NOT_REQUIRED"},
        {"reconciliation_status": None},
        {"reconciliation_decision": "NO_MUTATION_OBSERVED"},
        {"uncertain_mutation": False},
        {"uncertain_mutation": "true"},
        {"candidate_created": False},
        {"candidate_created": 0},
        {"candidate_status": ""},
        {"candidate_status": "NOT_CREATED"},
        {"candidate_status": "FINAL_BLOCK"},
        {"state_retention_status": "TERMINAL"},
        {"state_retention_status": "ARCHIVED"},
        {"approved_binding": {}},
        {"merge_performed": False},
        {"promotion_packet": {"candidate_commit_sha": "", "other": COMMIT}},
        {"promotion_packet": "not-a-mapping"},
        {"candidate_commit_sha": ""},
    ]:
        assert (
            SelfHostedTaskService._settled_candidate_less_final_block({
                **SETTLED_FINAL_BLOCK,
                **extra,
            })
            is True
        ), extra


@pytest.mark.parametrize(
    "extra",
    [
        {"status": "CANCELLED"},
        {"status": "RETAINED_FOR_REVIEW"},
        {"promotion_status": None},
        {"promotion_status": "PENDING_HUMAN_APPROVAL"},
        {"cleanup_decision": None},
        {"cleanup_decision": "RETAINED"},
        {"cleanup_blocker": "busy"},
        {"reconciliation_required": True},
        {"reconciliation_status": "PENDING"},
        {"reconciliation_decision": "RETAINED_FOR_REVIEW"},
        {"uncertain_mutation": True},
        {"candidate_created": True},
        {"candidate_created": 1.5},
        {"candidate_status": "CAPTURED"},
        {"state_retention_status": "ACTIVE"},
        {"approved_binding": {"x": 1}},
        {"integration_receipt": {"x": 1}},
        {"integration_result_sha": COMMIT},
        {"merge_performed": True},
        {"candidate_commit_sha": COMMIT},
        {"candidate_tree_sha": TREE},
        {"candidate_state_hash": "s"},
        {"verified_receipt_hash": "r"},
        {"candidate_ref": "refs/x"},
        {"promotion_packet": {"candidate_commit_sha": COMMIT}},
        {"promotion_packet": {"candidate_tree_sha": TREE}},
        {"promotion_packet": {"candidate_state_hash": "s"}},
        {"promotion_packet": {"verified_receipt_hash": "r"}},
        {"promotion_packet": {"candidate_ref": "refs/x"}},
    ],
)
def test_settled_candidate_less_final_block_rejects(extra: dict[str, Any]) -> None:
    assert (
        SelfHostedTaskService._settled_candidate_less_final_block({**SETTLED_FINAL_BLOCK, **extra})
        is False
    )


# ---------------------------------------------------------------------------
# _with_task_action


def test_with_task_action_copies_and_overwrites() -> None:
    state = {"task_id": "t", "status": "SUBMITTED", "task_action": {"stale": True}, "x": [1]}
    frozen = copy.deepcopy(state)
    result = SelfHostedTaskService._with_task_action(state)
    assert state == frozen
    assert result is not state
    assert result["x"] is state["x"]  # shallow copy
    assert result["task_action"] == _envelope(status="SUBMITTED")
    assert {k: v for k, v in result.items() if k != "task_action"} == {
        k: v for k, v in state.items() if k != "task_action"
    }


def test_with_task_action_envelope_sees_the_state_without_its_old_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_task_action_envelope",
        classmethod(lambda cls, state: seen.append(dict(state)) or {"patched": True}),
    )
    result = SelfHostedTaskService._with_task_action({"task_id": "t", "task_action": "old"})
    assert result == {"task_id": "t", "task_action": {"patched": True}}
    assert seen == [{"task_id": "t", "task_action": "old"}]


# ---------------------------------------------------------------------------
# _approval_requirements


def _required_state(**changes: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "promotion_packet": {
            "authority_change_required": True,
            "candidate_commit_sha": COMMIT,
            "candidate_tree_sha": TREE,
            "authority_findings_sha256": FINDINGS,
        },
        "verified_receipt": {
            "authority_change_required": True,
            "candidate_commit_sha": COMMIT,
            "candidate_tree_sha": TREE,
            "authority_findings_sha256": FINDINGS,
        },
    }
    state.update(changes)
    return state


def _requirements(state: Any) -> dict[str, Any]:
    return SelfHostedTaskService._approval_requirements(state)


APPROVABLE_BINDING = {
    "bound_task_id": "task-1",
    "bound_attempt_id": "attempt-1",
    "candidate_commit_sha": COMMIT,
    "candidate_tree_sha": TREE,
    "authority_findings_sha256": FINDINGS,
}


def test_approval_requirements_approvable() -> None:
    assert _requirements(_required_state()) == {
        "schema": "nexus.architecture_approval_requirements.v1",
        "required": True,
        "status": "APPROVABLE",
        "completeness": "COMPLETE",
        "approvability": "APPROVABLE",
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "binding": APPROVABLE_BINDING,
        "missing": [],
        "mismatches": [],
        "reasons": [],
        "stale": False,
    }


def test_approval_requirements_not_required_for_an_empty_state() -> None:
    assert _requirements({}) == {
        "schema": "nexus.architecture_approval_requirements.v1",
        "required": False,
        "status": "NOT_REQUIRED",
        "completeness": "NOT_REQUIRED",
        "approvability": "NOT_REQUIRED",
        "task_id": "",
        "attempt_id": "",
        "binding": {
            "bound_task_id": "",
            "bound_attempt_id": "",
            "candidate_commit_sha": "",
            "candidate_tree_sha": "",
            "authority_findings_sha256": "",
        },
        "missing": [
            "authority_findings_sha256",
            "bound_attempt_id",
            "bound_task_id",
            "candidate_commit_sha",
            "candidate_tree_sha",
        ],
        "mismatches": [],
        "reasons": [],
        "stale": False,
    }


def test_approval_requirements_required_with_everything_missing() -> None:
    result = _requirements({"promotion_packet": {"authority_change_required": True}})
    assert (
        result["required"],
        result["status"],
        result["completeness"],
        result["approvability"],
    ) == (
        True,
        "NOT_APPROVABLE",
        "INCOMPLETE",
        "NOT_APPROVABLE",
    )
    assert result["missing"] == [
        "authority_findings_sha256",
        "bound_attempt_id",
        "bound_task_id",
        "candidate_commit_sha",
        "candidate_tree_sha",
    ]
    assert result["mismatches"] == ["authority_change_required"]
    assert result["reasons"] == [
        "mismatch:authority_change_required",
        "missing:authority_findings_sha256",
        "missing:bound_attempt_id",
        "missing:bound_task_id",
        "missing:candidate_commit_sha",
        "missing:candidate_tree_sha",
    ]


@pytest.mark.parametrize(
    ("packet_flag", "receipt_flag", "required", "mismatch"),
    [
        (True, True, True, False),
        (True, False, True, True),
        (False, True, True, True),
        (False, False, False, False),
    ],
)
def test_approval_requirements_authority_change_flags(
    packet_flag: bool, receipt_flag: bool, required: bool, mismatch: bool
) -> None:
    state = _required_state()
    state["promotion_packet"] = {
        **state["promotion_packet"],
        "authority_change_required": packet_flag,
    }
    state["verified_receipt"] = {
        **state["verified_receipt"],
        "authority_change_required": receipt_flag,
    }
    result = _requirements(state)
    assert result["required"] is required
    assert result["mismatches"] == (["authority_change_required"] if mismatch else [])
    assert result["status"] == (
        "NOT_REQUIRED" if not required else "NOT_APPROVABLE" if mismatch else "APPROVABLE"
    )


@pytest.mark.parametrize("flag", ["true", 1, None, [True]])
def test_approval_requirements_non_bool_flag_is_an_input_reason(flag: Any) -> None:
    state = _required_state()
    state["promotion_packet"] = {**state["promotion_packet"], "authority_change_required": flag}
    result = _requirements(state)
    assert "invalid_type:promotion_packet.authority_change_required" in result["reasons"]
    # the invalid flag counts as False: required via the receipt, mismatching
    assert result["required"] is True
    assert result["mismatches"] == ["authority_change_required"]
    assert result["status"] == "NOT_APPROVABLE"


def test_approval_requirements_not_required_but_input_reasons_is_not_approvable() -> None:
    result = _requirements({"task_id": 5, "promotion_packet": "bad"})
    assert (
        result["required"],
        result["status"],
        result["completeness"],
        result["approvability"],
    ) == (
        False,
        "NOT_APPROVABLE",
        "INCOMPLETE",
        "NOT_APPROVABLE",
    )
    # missing / mismatch reasons are only added when approval is required
    assert result["reasons"] == [
        "invalid_type:task.task_id",
        "malformed_source:promotion_packet:expected_mapping",
    ]


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"promotion_packet": "bad"}, "malformed_source:promotion_packet:expected_mapping"),
        ({"promotion_packet": ["bad"]}, "malformed_source:promotion_packet:expected_mapping"),
        (
            {"promotion_packet": {}},
            "malformed_source:promotion_packet:empty_or_missing_contract_fields",
        ),
        ({"verified_receipt": 0}, "malformed_source:verified_receipt:expected_mapping"),
        (
            {"verified_receipt": {}},
            "malformed_source:verified_receipt:empty_or_missing_contract_fields",
        ),
        ({"task_id": 5}, "invalid_type:task.task_id"),
        ({"attempt_id": ["a"]}, "invalid_type:task.attempt_id"),
        ({"candidate_commit_sha": 7}, "invalid_type:task.candidate_commit_sha"),
        ({"candidate_commit_sha": "XYZ"}, "invalid_format:task.candidate_commit_sha"),
        ({"candidate_commit_sha": COMMIT.upper()}, "invalid_format:task.candidate_commit_sha"),
        ({"candidate_commit_sha": COMMIT + "a"}, "invalid_format:task.candidate_commit_sha"),
        ({"candidate_tree_sha": "t"}, "invalid_format:task.candidate_tree_sha"),
        ({"candidate": {"commit_sha": "zz"}}, "invalid_format:candidate.commit_sha"),
        ({"candidate": {"tree_sha": 1}}, "invalid_type:candidate.tree_sha"),
        (
            {"candidate": {"candidate_commit_sha": "zz"}},
            "invalid_format:candidate.candidate_commit_sha",
        ),
    ],
)
def test_approval_requirements_input_reasons(changes: dict[str, Any], reason: str) -> None:
    result = _requirements(_required_state(**changes))
    assert reason in result["reasons"]
    assert result["status"] == "NOT_APPROVABLE"
    assert result["completeness"] == "INCOMPLETE"


@pytest.mark.parametrize("source", ["promotion_packet", "verified_receipt"])
@pytest.mark.parametrize(
    "findings",
    ["c" * 40, "c" * 63, "c" * 65, "C" * 64, "g" * 64, " " + "c" * 63],
)
def test_approval_requirements_findings_hash_must_be_64_lowercase_hex(
    source: str, findings: str
) -> None:
    # pins the authority_findings_sha256 pattern ([0-9a-f]{64}, full match)
    state = _required_state()
    state[source] = {**state[source], "authority_findings_sha256": findings}
    result = _requirements(state)
    assert result["reasons"] == [f"invalid_format:{source}.authority_findings_sha256"]
    assert result["status"] == "NOT_APPROVABLE"


def test_approval_requirements_str_subclass_is_an_invalid_type() -> None:
    class Sha(str):
        pass

    result = _requirements(_required_state(candidate_commit_sha=Sha(COMMIT), task_id=Sha("task-1")))
    assert "invalid_type:task.candidate_commit_sha" in result["reasons"]
    assert "invalid_type:task.task_id" in result["reasons"]
    assert result["task_id"] == ""


def test_approval_requirements_empty_and_blank_values_are_skipped() -> None:
    result = _requirements(
        _required_state(
            candidate_commit_sha="   ", candidate_tree_sha="", candidate={"commit_sha": None}
        )
    )
    assert result["status"] == "APPROVABLE"
    assert result["binding"] == APPROVABLE_BINDING


def test_approval_requirements_values_are_stripped() -> None:
    state = _required_state(task_id="  task-1  ", attempt_id="\tattempt-1\n")
    state["promotion_packet"] = {
        **state["promotion_packet"],
        "candidate_commit_sha": f"  {COMMIT} ",
    }
    result = _requirements(state)
    assert result["status"] == "APPROVABLE"
    assert result["binding"] == APPROVABLE_BINDING
    blank = _requirements(_required_state(task_id="   "))
    assert blank["task_id"] == ""
    assert "missing:bound_task_id" in blank["reasons"]


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"candidate_commit_sha": COMMIT_2}, "candidate_commit_sha"),
        ({"candidate": {"commit_sha": COMMIT_2}}, "candidate_commit_sha"),
        (
            {"candidate": {"candidate_commit_sha": COMMIT, "commit_sha": COMMIT_2}},
            "candidate_commit_sha",
        ),
        ({"candidate_tree_sha": TREE_2}, "candidate_tree_sha"),
        ({"candidate": {"tree_sha": TREE_2}}, "candidate_tree_sha"),
    ],
)
def test_approval_requirements_mismatches(changes: dict[str, Any], field: str) -> None:
    result = _requirements(_required_state(**changes))
    assert result["mismatches"] == [field]
    assert f"mismatch:{field}" in result["reasons"]
    assert result["binding"][field] == ""
    assert result["status"] == "NOT_APPROVABLE"


def test_approval_requirements_findings_mismatch_between_packet_and_receipt() -> None:
    state = _required_state()
    state["verified_receipt"] = {
        **state["verified_receipt"],
        "authority_findings_sha256": FINDINGS_2,
    }
    result = _requirements(state)
    assert result["mismatches"] == ["authority_findings_sha256"]


def test_approval_requirements_values_agreeing_across_sources_are_bound() -> None:
    state = _required_state(
        candidate_commit_sha=COMMIT,
        candidate_tree_sha=TREE,
        candidate={"candidate_commit_sha": COMMIT, "commit_sha": COMMIT, "tree_sha": TREE},
    )
    result = _requirements(state)
    assert result["status"] == "APPROVABLE"


def test_approval_requirements_candidate_only_sources() -> None:
    state = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "candidate": {"commit_sha": COMMIT, "tree_sha": TREE},
        "promotion_packet": {
            "authority_change_required": True,
            "authority_findings_sha256": FINDINGS,
        },
        "verified_receipt": {"authority_change_required": True},
    }
    result = _requirements(state)
    assert result["status"] == "APPROVABLE"
    assert result["binding"] == APPROVABLE_BINDING


def test_approval_requirements_findings_are_not_read_from_the_task_or_candidate() -> None:
    state = _required_state(
        authority_findings_sha256=FINDINGS_2, candidate={"authority_findings_sha256": FINDINGS_2}
    )
    assert _requirements(state)["binding"]["authority_findings_sha256"] == FINDINGS
    state = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "authority_findings_sha256": FINDINGS,
        "candidate_commit_sha": COMMIT,
        "candidate_tree_sha": TREE,
        "promotion_packet": {"authority_change_required": True},
    }
    assert _requirements(state)["missing"] == ["authority_findings_sha256"]


def test_approval_requirements_non_mapping_candidate_is_ignored_without_reason() -> None:
    result = _requirements(_required_state(candidate="not-a-mapping"))
    assert result["status"] == "APPROVABLE"
    assert result["reasons"] == []


def test_approval_requirements_none_sources_are_absent_without_reason() -> None:
    result = _requirements({"promotion_packet": None, "verified_receipt": None})
    assert result["reasons"] == []
    assert result["status"] == "NOT_REQUIRED"


@pytest.mark.parametrize("where", ["approved_binding", "promotion_packet", "verified_receipt"])
def test_approval_requirements_stale_when_an_approval_is_already_present(where: str) -> None:
    state = _required_state()
    current = state.get(where) or {}
    state[where] = {**current, "architecture_approval": {"approved": True}}
    result = _requirements(state)
    assert result["stale"] is True
    assert result["status"] == "NOT_APPROVABLE"
    assert "stale_approval_requirements" in result["missing"]
    assert "missing:stale_approval_requirements" in result["reasons"]
    assert "stale:approval_requirements" in result["reasons"]


def test_approval_requirements_none_approval_is_not_stale() -> None:
    state = _required_state(approved_binding={"architecture_approval": None})
    assert _requirements(state)["stale"] is False


@pytest.mark.parametrize(
    ("promotion_status", "stale"),
    [
        ("APPROVED", True),
        ("INTEGRATED", True),
        ("APPROVAL_INVALIDATED", True),
        ("PENDING_HUMAN_APPROVAL", False),
        (None, False),
    ],
)
def test_approval_requirements_stale_promotion_status(promotion_status: Any, stale: bool) -> None:
    result = _requirements(_required_state(promotion_status=promotion_status))
    assert result["stale"] is stale
    assert result["status"] == ("NOT_APPROVABLE" if stale else "APPROVABLE")


def test_approval_requirements_stale_but_not_required() -> None:
    state = {
        "approved_binding": {"architecture_approval": {"x": 1}},
        "promotion_status": "APPROVED",
    }
    result = _requirements(state)
    assert result["required"] is False
    assert result["stale"] is True
    assert result["status"] == "NOT_REQUIRED"
    assert result["reasons"] == ["stale:approval_requirements"]
    assert "stale_approval_requirements" not in result["missing"]
    # not required + approved promotion status alone is not stale
    assert _requirements({"promotion_status": "APPROVED"})["stale"] is False


@pytest.mark.parametrize(
    ("blocker", "reasons"),
    [
        ({"approval_requirements_reasons": ["r1", "r2"], "code": "C"}, ["r1", "r2"]),
        ({"approval_requirements_reasons": [], "code": "C"}, []),
        ({"approval_requirements_reasons": ["ok", ""], "code": "C"}, ["invalid_state:C"]),
        ({"approval_requirements_reasons": ["ok", 1], "code": "C"}, ["invalid_state:C"]),
        ({"approval_requirements_reasons": "r1", "code": "C"}, ["invalid_state:C"]),
        ({"code": "STATE_JSON_INVALID"}, ["invalid_state:STATE_JSON_INVALID"]),
        ({"code": 5}, ["invalid_state:UNKNOWN"]),
        ({}, ["invalid_state:UNKNOWN"]),
        ("not-a-mapping", ["invalid_state:UNKNOWN"]),
        (None, ["invalid_state:UNKNOWN"]),
    ],
)
def test_approval_requirements_invalid_state_reasons(blocker: Any, reasons: list[str]) -> None:
    result = _requirements({"state_valid": False, "blocker": blocker})
    assert result["reasons"] == sorted(reasons)
    assert result["status"] == ("NOT_APPROVABLE" if reasons else "NOT_REQUIRED")


def test_approval_requirements_invalid_state_only_when_explicitly_false() -> None:
    for valid in (None, 0, "", True):
        result = _requirements({"state_valid": valid, "blocker": {"code": "C"}})
        assert result["reasons"] == [], valid


def test_approval_requirements_reasons_are_deduplicated_and_sorted() -> None:
    state = _required_state(
        state_valid=False,
        blocker={"approval_requirements_reasons": ["z", "a", "z"]},
        candidate_commit_sha="bad",
        candidate={"candidate_commit_sha": "bad"},
    )
    result = _requirements(state)
    assert result["reasons"] == [
        "a",
        "invalid_format:candidate.candidate_commit_sha",
        "invalid_format:task.candidate_commit_sha",
        "z",
    ]


def test_approval_requirements_accepts_any_mapping_and_does_not_mutate() -> None:
    state = _required_state(candidate={"commit_sha": COMMIT})
    frozen = copy.deepcopy(state)
    proxied = {
        key: MappingProxyType(value) if isinstance(value, dict) else value
        for key, value in state.items()
    }
    assert _requirements(MappingProxyType(proxied)) == _requirements(state)
    assert state == frozen


# ---------------------------------------------------------------------------
# facade-module names read by the moved code resolve through the facade


def test_late_bound_invalid_state_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "INVALID_STATE_STATUSES", frozenset({"SUBMITTED"}))
    assert _row(_envelope(status="SUBMITTED")) == INSPECT_LIFECYCLE


def test_late_bound_durable_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        service_module,
        "DURABLE_SELF_HOSTED_STATUSES",
        task_lifecycle.DURABLE_SELF_HOSTED_STATUSES - {"SUBMITTED"},
    )
    assert _row(_envelope(status="SUBMITTED")) == INSPECT_LIFECYCLE
    assert _row(_envelope(status="VERIFIED")) == STATUS_ROWS["VERIFIED"]


def test_late_bound_pending_candidate_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        service_module,
        "PENDING_CANDIDATE_STATUSES",
        task_lifecycle.PENDING_CANDIDATE_STATUSES | {"SUBMITTED"},
    )
    assert _row(_envelope(status="SUBMITTED")) == (
        "ACTION_REQUIRED",
        True,
        "approve_candidate",
        "nexus_candidate_approve",
    )


def test_late_bound_terminal_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        service_module, "TERMINAL_STATUSES", task_lifecycle.TERMINAL_STATUSES | {"SUBMITTED"}
    )
    assert _row(_envelope(status="SUBMITTED")) == ("TERMINAL", False, "none", None)


def test_late_bound_active_execution_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        service_module,
        "ACTIVE_EXECUTION_STATUSES",
        task_lifecycle.ACTIVE_EXECUTION_STATUSES - {"SUBMITTED"},
    )
    assert _row(_envelope(status="SUBMITTED")) == INSPECT_LIFECYCLE


def test_late_bound_resumable_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        service_module, "RESUMABLE_STATUSES", task_lifecycle.RESUMABLE_STATUSES - {"VERIFIED"}
    )
    assert _row(_envelope(status="VERIFIED")) == INSPECT_LIFECYCLE


def test_facade_status_sets_are_the_runtime_objects() -> None:
    for name in (
        "INVALID_STATE_STATUSES",
        "DURABLE_SELF_HOSTED_STATUSES",
        "PENDING_CANDIDATE_STATUSES",
        "TERMINAL_STATUSES",
        "ACTIVE_EXECUTION_STATUSES",
        "RESUMABLE_STATUSES",
    ):
        assert getattr(service_module, name) is getattr(task_lifecycle, name), name


# ---------------------------------------------------------------------------
# class patches of one projection are reached from the others (cls dispatch)


def test_class_patch_of_candidate_commit_reaches_the_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        SelfHostedTaskService, "_candidate_commit", staticmethod(lambda state: "PATCHED")
    )
    action = _envelope(status="SUBMITTED")
    assert action["candidate_commit_sha"] == "PATCHED"
    assert action["candidate"]["candidate_commit_sha"] == "PATCHED"
    # a patched commit turns the verified-uncommitted recovery into a receipt inspection
    action = _envelope(
        status="FINAL_BLOCK",
        verified_receipt={"verified": True},
        attempt_resolution={"verdict": "PROVEN"},
    )
    assert action["next_action"] == "inspect_receipt_and_candidate"


def test_class_patch_of_settled_rule_reaches_the_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_settled_candidate_less_final_block",
        classmethod(lambda cls, state: calls.append(state.get("status")) or True),
    )
    assert _row(_envelope(status="RETAINED_FOR_REVIEW"))[:2] == ("TERMINAL", False)
    # only consulted for the terminal failure statuses
    assert _row(_envelope(status="SUBMITTED")) == STATUS_ROWS["SUBMITTED"]
    assert calls == ["RETAINED_FOR_REVIEW"]


def test_class_patch_of_terminal_failure_blocker_reaches_projected_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_terminal_failure_blocker",
        classmethod(lambda cls, state: {"patched": 1}),
    )
    assert SelfHostedTaskService._projected_blocker({"status": "SUBMITTED"}) == {"patched": 1}


def test_subclass_overrides_are_dispatched_through_cls() -> None:
    class Sub(SelfHostedTaskService):
        @staticmethod
        def _candidate_commit(state: Any) -> str:
            return "SUB"

        @classmethod
        def _terminal_failure_blocker(cls, state: Any) -> dict[str, Any]:
            return {"sub": True}

        @classmethod
        def _settled_candidate_less_final_block(cls, state: Any) -> bool:
            return True

        @classmethod
        def _task_action_envelope(cls, state: Any) -> dict[str, Any]:
            return {"sub_envelope": super()._task_action_envelope(state)["action_state"]}

    assert Sub._projected_blocker({}) == {"sub": True}
    assert Sub._with_task_action({"status": "FINAL_BLOCK"})["task_action"] == {
        "sub_envelope": "TERMINAL"
    }
    action = SelfHostedTaskService._task_action_envelope.__func__(Sub, {"status": "SUBMITTED"})
    assert action["candidate_commit_sha"] == "SUB"


def test_class_patch_of_envelope_reaches_the_facade_write_and_read_paths(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_task_action_envelope",
        classmethod(lambda cls, state: {"patched": state.get("status")}),
    )
    written = service._write_state("t", {"task_id": "t", "status": "SUBMITTED"})
    assert written["task_action"] == {"patched": "SUBMITTED"}
    assert service._read_state("t")["task_action"] == {"patched": "SUBMITTED"}  # type: ignore[index]
    assert service._read_state_snapshot("t")["task_action"] == {"patched": "SUBMITTED"}  # type: ignore[index]
    path = service._state_path("bad")
    path.write_text("[]", encoding="utf-8")
    invalid = service._read_state_snapshot("bad")
    assert invalid is not None and invalid["task_action"] == {"patched": "BLOCKED_INVALID_STATE"}


def test_class_patch_of_with_task_action_reaches_the_facade_validators(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_with_task_action",
        classmethod(lambda cls, state: {**state, "wrapped": True}),
    )
    path = service.state_dir / "t.json"
    valid = SelfHostedTaskService._validate_state_payload(
        "t", {"task_id": "t", "status": "SUBMITTED"}, path
    )
    assert valid["wrapped"] is True
    invalid = SelfHostedTaskService._invalid_state_status(
        "t", code="C", detail="d", source_path=path
    )
    assert invalid["wrapped"] is True


def test_class_patch_of_approval_requirements_reaches_the_read_projection(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    service._write_state("t", {"task_id": "t", "status": "SUBMITTED"})
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_approval_requirements",
        staticmethod(lambda state: {"patched": True}),
    )
    task = service.get_task("t")
    assert task is not None and task["approval_requirements"] == {"patched": True}


# ---------------------------------------------------------------------------
# no lock, no I/O in the projections; the write path keeps its lock / I/O order


class IORecorder:
    """Records the state lock, the projections and the store's atomic-write effects."""

    PROJECTIONS = (
        "_candidate_commit",
        "_terminal_failure_blocker",
        "_projected_blocker",
        "_settled_candidate_less_final_block",
        "_task_action_envelope",
        "_with_task_action",
        "_approval_requirements",
    )
    FACADE = (
        "_normalize_state_write",
        "_validate_state_payload",
        "_load_state_path",
        "_state_path",
        "_latest_archived_state",
    )

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.events: list[str] = []
        events = self.events
        cls = SelfHostedTaskService
        lock = inspect.getattr_static(cls, "_state_lock")

        @contextmanager
        def state_lock(self_: Any) -> Iterator[None]:
            events.append("lock+")
            with lock(self_):
                yield
            events.append("lock-")

        monkeypatch.setattr(cls, "_state_lock", state_lock)
        for name in self.PROJECTIONS + self.FACADE:
            static = inspect.getattr_static(cls, name)
            func = static.__func__ if isinstance(static, (staticmethod, classmethod)) else static
            wrapped = self._wrap(name, func)
            if isinstance(static, staticmethod):
                wrapped = staticmethod(wrapped)
            elif isinstance(static, classmethod):
                wrapped = classmethod(wrapped)
            monkeypatch.setattr(cls, name, wrapped)
        real_fsync, real_replace, real_os_open = os.fsync, Path.replace, os.open

        def fsync(fd: int) -> None:
            events.append("fsync")
            real_fsync(fd)

        def replace(self_: Path, target: Any) -> Path:
            events.append(f"replace:{Path(target).name}")
            return real_replace(self_, target)

        def os_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
            events.append("os.open:" + ("write" if flags & (os.O_WRONLY | os.O_RDWR) else "read"))
            return real_os_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(os, "fsync", fsync)
        monkeypatch.setattr(Path, "replace", replace)
        monkeypatch.setattr(os, "open", os_open)

    def _wrap(self, name: str, func: Any) -> Any:
        events = self.events

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            events.append(name)
            return func(*args, **kwargs)

        return wrapped


def test_projections_take_no_lock_and_do_no_io(
    service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {
        **SETTLED_FINAL_BLOCK,
        "error": "boom",
        "verified_receipt": {"verified": True, "authority_change_required": True},
        "attempt_resolution": {"verdict": "PROVEN"},
    }
    recorder = IORecorder(monkeypatch)
    service._task_action_envelope(state)
    service._with_task_action(state)
    service._projected_blocker(state)
    service._approval_requirements(state)
    assert recorder.events == [
        "_task_action_envelope",
        "_candidate_commit",
        "_settled_candidate_less_final_block",
        "_with_task_action",
        "_task_action_envelope",
        "_candidate_commit",
        "_settled_candidate_less_final_block",
        "_projected_blocker",
        "_terminal_failure_blocker",
        "_approval_requirements",
    ]
    assert not service.state_dir.exists()


def _recorded_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[SelfHostedTaskService, IORecorder]:
    # The service binds ``_normalize_state_write`` into its state store when it is
    # constructed, so the recorder is installed first.
    recorder = IORecorder(monkeypatch)
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    return service, recorder


def test_write_state_lock_and_io_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, recorder = _recorded_service(tmp_path, monkeypatch)
    written = service._write_state("t", {"task_id": "t", "status": "FINAL_BLOCK", "error": "x"})
    assert recorder.events == [
        "lock+",
        "_normalize_state_write",
        "_task_action_envelope",
        "_candidate_commit",
        "_settled_candidate_less_final_block",
        "os.open:write",
        "fsync",
        "replace:t.json",
        "os.open:read",
        "fsync",
        "lock-",
    ]
    assert written["task_action"] == _envelope(status="FINAL_BLOCK", error="x")
    on_disk = service._read_state_snapshot("t")
    assert on_disk is not None and on_disk["task_action"] == written["task_action"]


def test_create_mutate_and_read_lock_and_io_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, recorder = _recorded_service(tmp_path, monkeypatch)
    _, created = service._create_state("t", {"task_id": "t", "status": "SUBMITTED"})
    assert created is True
    create_events = list(recorder.events)
    recorder.events.clear()
    service._mutate_state("t", lambda value: value.update(status="WORKER_RUNNING"))
    mutate_events = list(recorder.events)
    recorder.events.clear()
    state = service._read_state("t")
    read_events = list(recorder.events)
    recorder.events.clear()
    service._read_state_snapshot("t")
    snapshot_events = list(recorder.events)
    recorder.events.clear()
    _, created_again = service._create_state("t", {"task_id": "t", "status": "SUBMITTED"})
    again_events = list(recorder.events)
    write_tail = [
        "_normalize_state_write",
        "_task_action_envelope",
        "_candidate_commit",
        "os.open:write",
        "fsync",
        "replace:t.json",
        "os.open:read",
        "fsync",
    ]
    read_tail = [
        "_load_state_path",
        "_validate_state_payload",
        "_with_task_action",
        "_task_action_envelope",
        "_candidate_commit",
    ]
    # the destination and archive checks of a create run under the lock
    assert create_events == ["lock+", "_state_path", "_latest_archived_state", *write_tail, "lock-"]
    assert mutate_events == ["lock+", *write_tail, "lock-"]
    assert read_events == ["_state_path", "lock+", *read_tail, "lock-"]
    assert snapshot_events == read_tail[1:]
    assert again_events == ["lock+", "_state_path", *read_tail, "lock-"]
    assert created_again is False
    assert state is not None and state["task_action"] == _envelope(status="WORKER_RUNNING")
