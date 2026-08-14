"""Hostile read-only acceptance for the #130A claimable-work projection."""

from nexus.orchestrator import work_consumption
from nexus.orchestrator.work_consumption import (
    AdmissionDecision,
    BlockReason,
    ClaimEnforcementState,
    ClaimIntent,
    WorkItem,
    WorkItemStatus,
    WorkPriority,
    list_claimable_work,
)


def _valid(issue_id="issue-1", **overrides):
    item = {
        "issue_id": issue_id,
        "status": "READY_NOW",
        "roles": ("primary_implementer",),
        "claim_intent": "AUTONOMOUS",
        "claim_enforcement_state": "REPO_ENFORCED",
        "prerequisites_satisfied": True,
        "admission": "ALLOW",
        "priority": "P1",
    }
    item.update(overrides)
    return item


def _ids(projection):
    return [item.issue_id for item in projection.claimable]


def _reasons(projection):
    return {blocked.issue_id: blocked.reason for blocked in projection.blocked}


def test_empty_input_is_empty_projection():
    projection = list_claimable_work([], role="primary_implementer")
    assert projection.claimable == ()
    assert projection.blocked == ()


def test_repeated_listing_is_deterministic_and_read_only():
    items = [_valid("a", priority="P2"), _valid("b", priority="P0")]
    first = list_claimable_work(items, role="primary_implementer")
    second = list_claimable_work(items, role="primary_implementer")
    assert first == second
    assert _ids(first) == ["b", "a"]


def test_acquire_work_claim_never_called(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("acquire_work_claim must never be called by listing")

    def fail_claim(*_args, **_kwargs):
        raise AssertionError("claim_work must never be called by listing")

    monkeypatch.setattr(
        work_consumption, "acquire_work_claim", fail, raising=False
    )
    monkeypatch.setattr(work_consumption, "claim_work", fail_claim, raising=False)

    projection = list_claimable_work([_valid()], role="primary_implementer")
    assert [item.issue_id for item in projection.claimable] == ["issue-1"]


def test_requires_ready_now_status():
    projection = list_claimable_work(
        [
            _valid("blocked", status="BLOCKED"),
            _valid("unknown", status="UNKNOWN"),
            _valid("ready"),
        ],
        role="primary_implementer",
    )
    assert _ids(projection) == ["ready"]
    assert _reasons(projection) == {
        "blocked": BlockReason.NOT_READY,
        "unknown": BlockReason.NOT_READY,
    }


def test_requires_compatible_role():
    projection = list_claimable_work(
        [_valid("wrong-role", roles=("reviewer",))],
        role="primary_implementer",
    )
    assert projection.claimable == ()
    assert _reasons(projection) == {"wrong-role": BlockReason.ROLE_INCOMPATIBLE}


def test_requires_autonomous_claim_intent():
    projection = list_claimable_work(
        [
            _valid("manual", claim_intent="MANUAL_DISPATCH"),
            _valid("unknown", claim_intent="UNKNOWN"),
        ],
        role="primary_implementer",
    )
    assert projection.claimable == ()
    assert _reasons(projection) == {
        "manual": BlockReason.CLAIM_INTENT_NOT_AUTONOMOUS,
        "unknown": BlockReason.CLAIM_INTENT_NOT_AUTONOMOUS,
    }


def test_requires_repo_enforced_claim_state():
    projection = list_claimable_work(
        [
            _valid("projection", claim_enforcement_state="PROJECTION_ONLY"),
            _valid("unknown", claim_enforcement_state="UNKNOWN"),
        ],
        role="primary_implementer",
    )
    assert projection.claimable == ()
    assert _reasons(projection) == {
        "projection": BlockReason.PROJECTION_ONLY,
        "unknown": BlockReason.PROJECTION_ONLY,
    }


def test_requires_satisfied_prerequisites():
    projection = list_claimable_work(
        [_valid("unsatisfied", prerequisites_satisfied=False)],
        role="primary_implementer",
    )
    assert projection.claimable == ()
    assert _reasons(projection) == {
        "unsatisfied": BlockReason.PREREQUISITES_UNSATISFIED
    }


def test_requires_allowed_admission():
    projection = list_claimable_work(
        [
            _valid("denied", admission="DENY"),
            _valid("unknown", admission="UNKNOWN"),
        ],
        role="primary_implementer",
    )
    assert projection.claimable == ()
    assert _reasons(projection) == {
        "denied": BlockReason.ADMISSION_NOT_ALLOWED,
        "unknown": BlockReason.ADMISSION_NOT_ALLOWED,
    }


def test_excludes_current_owners():
    projection = list_claimable_work(
        [
            _valid("owned-field", owner="worker-x"),
            _valid("owned-set", owner=None),
            _valid("free"),
        ],
        role="primary_implementer",
        current_owners=frozenset({"owned-set"}),
    )
    assert _ids(projection) == ["free"]
    assert _reasons(projection) == {
        "owned-field": BlockReason.ALREADY_OWNED,
        "owned-set": BlockReason.ALREADY_OWNED,
    }


def test_excludes_blocked_realm_and_provider():
    projection = list_claimable_work(
        [
            _valid("realm-blocked", realm="local"),
            _valid("provider-blocked", provider="opencode"),
            _valid("free"),
        ],
        role="primary_implementer",
        blocked_realms=frozenset({"local"}),
        blocked_providers=frozenset({"opencode"}),
    )
    assert _ids(projection) == ["free"]
    assert _reasons(projection) == {
        "realm-blocked": BlockReason.REALM_BLOCKED,
        "provider-blocked": BlockReason.PROVIDER_BLOCKED,
    }


def test_malformed_items_fail_closed_and_do_not_affect_others():
    cases = [
        {},
        {"issue_id": "", "status": "READY_NOW"},
        _valid("bad-status", status="MAYBE"),
        _valid("bad-intent", claim_intent="WHATEVER"),
        _valid("bad-prereq", prerequisites_satisfied="yes"),
        _valid("bad-priority", priority="P9"),
        _valid("bad-roles", roles=()),
        _valid("bad-owner", owner=123),
        _valid("bad-successor", direct_successor="yes"),
        {k: v for k, v in _valid("missing-role-key").items() if k != "roles"},
    ]
    projection = list_claimable_work(
        [_valid("good")] + cases, role="primary_implementer"
    )
    assert _ids(projection) == ["good"]
    for issue_id in (
        "<unknown>",
        "",
        "bad-status",
        "bad-intent",
        "bad-prereq",
        "bad-priority",
        "bad-roles",
        "bad-owner",
        "bad-successor",
        "missing-role-key",
    ):
        assert _reasons(projection)[issue_id] == BlockReason.MALFORMED


def test_direct_successor_ordered_first_even_when_lower_priority():
    projection = list_claimable_work(
        [
            _valid("p0"),
            _valid("successor", direct_successor=True, priority="P2"),
        ],
        role="primary_implementer",
    )
    assert _ids(projection) == ["successor", "p0"]


def test_priority_ordering_p0_p1_p2():
    projection = list_claimable_work(
        [
            _valid("p2", priority="P2"),
            _valid("p1", priority="P1"),
            _valid("p0", priority="P0"),
        ],
        role="primary_implementer",
    )
    assert _ids(projection) == ["p0", "p1", "p2"]


def test_ties_preserve_input_order():
    projection = list_claimable_work(
        [
            _valid("p1-first", priority="P1"),
            _valid("p1-second", priority="P1"),
            _valid("p2-first", priority="P2"),
            _valid("p2-second", priority="P2"),
        ],
        role="primary_implementer",
    )
    assert _ids(projection) == [
        "p1-first",
        "p1-second",
        "p2-first",
        "p2-second",
    ]


def test_workitem_instance_input_is_accepted():
    item = WorkItem(
        issue_id="instance",
        status=WorkItemStatus.READY_NOW,
        roles=frozenset({"primary_implementer"}),
        claim_intent=ClaimIntent.AUTONOMOUS,
        claim_enforcement_state=ClaimEnforcementState.REPO_ENFORCED,
        prerequisites_satisfied=True,
        admission=AdmissionDecision.ALLOW,
        priority=WorkPriority.P0,
    )
    projection = list_claimable_work([item], role="primary_implementer")
    assert _ids(projection) == ["instance"]


def test_eligible_item_keeps_full_identity():
    projection = list_claimable_work([_valid("kept")], role="primary_implementer")
    (item,) = projection.claimable
    assert item.issue_id == "kept"
    assert item.status is WorkItemStatus.READY_NOW
    assert item.claim_intent is ClaimIntent.AUTONOMOUS
    assert item.claim_enforcement_state is ClaimEnforcementState.REPO_ENFORCED
    assert item.prerequisites_satisfied is True
    assert item.admission is AdmissionDecision.ALLOW
    assert item.priority is WorkPriority.P1
