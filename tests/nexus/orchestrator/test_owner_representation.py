"""Hostile / negative / replay suite for EXTERNAL_PUBLICATION /
OWNER_REPRESENTATION authority (#827).

Uses fixtures, mocks, and temp remotes only.  No real third-party repository
or user is ever contacted.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from nexus.contracts.autonomy_goal import canonical_autonomy_hash
from nexus.contracts.owner_representation import (
    ExternalDestination,
    ExternalDestinationKind,
    ExternalPublicationEffect,
    ExternalPublicationProposal,
    InternalCollaborationBound,
    OwnerRepresentationBlocked,
    OwnerRepresentationGrant,
    OwnerRepresentationGrantSpec,
    OwnerRepresentationOutcome,
    OwnerRepresentationReason,
    PublicationDerivation,
    canonical_publication_content_hash,
    classification,
    evaluate_owner_representation,
)
from nexus.orchestrator.owner_representation import (
    OwnerRepresentationPublisher,
    PreparedPublication,
    TransportDispatchedButUnacknowledged,
    WriteOutcome,
    bind_external_publication,
)
from nexus.orchestrator.owner_representation_store import OwnerRepresentationGrantStore
from nexus.security.owner_representation_transport_inventory import (
    PublicationRouteState,
    assert_no_unknown_routes,
    classify_transport_route,
    physical_witnesses_for,
    transport_inventory_status,
)

NOW = datetime.now(timezone.utc)
THIRD_PARTY = ExternalDestination(
    host="github.com", owner_account="Waishnav", repository="devspace"
)
OWNER_REPO = ExternalDestination(
    host="github.com", owner_account="James3014", repository="Nexus-new"
)
UNKNOWN_HOST = ExternalDestination(
    host="pubsub.example.com", owner_account="acme", repository="board"
)


@pytest.fixture
def repo_root() -> Path:
    # tests/nexus/orchestrator/test_owner_representation.py -> repository root
    return Path(__file__).resolve().parents[3]


def _dest(**overrides) -> ExternalDestination:
    values = {"host": "github.com", "owner_account": "Waishnav", "repository": "devspace"}
    values.update(overrides)
    return ExternalDestination(**values)


def _proposal(**overrides) -> ExternalPublicationProposal:
    values = {
        "destination": THIRD_PARTY,
        "effect": ExternalPublicationEffect.CREATE_ISSUE,
        "title": "Upstream regression noticed after build",
        "body": "Repro steps and evidence.",
        "purpose": "report upstream regression on third-party repo",
        "content_hash": canonical_publication_content_hash(
            "Upstream regression noticed after build", "Repro steps and evidence."
        ),
        "actor": "coordinator-codex",
        "transport": "fixture",
        "operation_id": "op-1",
        "derivation": PublicationDerivation.EXPLICIT_OWNER_DECISION,
    }
    values.update(overrides)
    return ExternalPublicationProposal(**values)


def _grant(**overrides) -> OwnerRepresentationGrant:
    values = {
        "grant_id": "g-827-1",
        "issued_by": "owner-james",
        "owner_id": "owner-james",
        "coordinator_id": "coordinator-codex",
        "destination": THIRD_PARTY,
        "effect": ExternalPublicationEffect.CREATE_ISSUE,
        "content_hash": canonical_publication_content_hash(
            "Upstream regression noticed after build", "Repro steps and evidence."
        ),
        "purpose": "report upstream regression on third-party repo",
        "actor": "coordinator-codex",
        "transport": "fixture",
        "operation_id": "op-1",
        "granted_at": NOW - timedelta(minutes=5),
        "expires_at": NOW + timedelta(hours=1),
    }
    values.update(overrides)
    spec = OwnerRepresentationGrantSpec.model_validate(values)
    return OwnerRepresentationGrant.model_validate({
        **spec.model_dump(mode="json"),
        "grant_hash": canonical_autonomy_hash(spec.model_dump(mode="json")),
    })


def _issue_grant(
    grant_store: OwnerRepresentationGrantStore, **overrides
) -> OwnerRepresentationGrant:
    """Issue a durable, store-backed grant (the only authoritative form)."""
    grant = _grant(**overrides)
    grant_store.issue(grant)
    return grant


class FakeRemote:
    """Physical side-effect witness: every write appends a record.

    `issue_id_ctr` simulates the remote object id returned for a created
    issue/PR, giving readback something to find.
    """

    def __init__(self) -> None:
        self.writes: list[dict] = []
        self.issue_id_ctr = 1000
        self.fail_next: str | None = None
        self.unack_next: bool = False

    def write(self, proposal: ExternalPublicationProposal) -> WriteOutcome:
        if self.fail_next is not None:
            mode, self.fail_next = self.fail_next, None
            return WriteOutcome(status="FAILED", detail=mode)
        if self.unack_next:
            self.unack_next = False
            raise TransportDispatchedButUnacknowledged()
        self.issue_id_ctr += 1
        marker = str(self.issue_id_ctr)
        self.writes.append({
            "marker": marker,
            "op": proposal.operation_id,
            "effect": proposal.effect.value,
            "destination": proposal.destination.repository_id,
            "title": proposal.title,
            "body": proposal.body,
            "purpose": proposal.purpose,
            "actor": proposal.actor,
        })
        return WriteOutcome(status="ACK", remote_marker=marker)

    def readback(self, proposal: ExternalPublicationProposal) -> str | None:
        for entry in reversed(self.writes):
            if entry["op"] == proposal.operation_id and entry["effect"] == proposal.effect.value:
                return entry["marker"]
        return None


@pytest.fixture
def remote() -> FakeRemote:
    return FakeRemote()


@pytest.fixture
def grant_store(tmp_path: Path) -> OwnerRepresentationGrantStore:
    return OwnerRepresentationGrantStore(root=tmp_path / "grant-authority")


@pytest.fixture
def publisher(
    tmp_path: Path,
    remote: FakeRemote,
    grant_store: OwnerRepresentationGrantStore,
) -> OwnerRepresentationPublisher:
    return OwnerRepresentationPublisher(
        operation_root=tmp_path / "ops",
        write_transport=remote.write,
        readback_transport=remote.readback,
        grant_store=grant_store,
    )


# ---------------------------------------------------------------------------
# Capability / inference never implies Owner-representation authority
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "derivation",
    [
        PublicationDerivation.PUSH_DENIED,
        PublicationDerivation.TASK_COMPLETION,
        PublicationDerivation.WORKER_OUTPUT,
        PublicationDerivation.UNTYPED,
    ],
)
def test_inference_derivations_never_authorize_external_publication(derivation):
    decision = bind_external_publication(_proposal(derivation=derivation))
    assert decision.outcome is OwnerRepresentationOutcome.BLOCKED
    assert decision.publication_authorized is False
    assert decision.reason_codes
    assert (
        OwnerRepresentationReason.PUBLICATION_AUTHORITY_NON_INFERABLE in decision.reason_codes
        or (
            OwnerRepresentationReason.PUSH_DENIED_IS_NOT_PUBLICATION_AUTHORITY
            in decision.reason_codes
            and derivation is PublicationDerivation.PUSH_DENIED
        )
    )


def test_push_denied_is_not_issue_publication_authority():
    """Regression anchor: \"push failed\" can never mint an issue elsewhere."""
    proposal = _proposal(derivation=PublicationDerivation.PUSH_DENIED)
    decision = bind_external_publication(proposal)
    assert decision.outcome is OwnerRepresentationOutcome.BLOCKED
    assert (
        OwnerRepresentationReason.PUSH_DENIED_IS_NOT_PUBLICATION_AUTHORITY in decision.reason_codes
    )
    assert decision.publication_authorized is False


def test_authenticated_identity_is_not_owner_authorized():
    """AUTHENTICATED != OWNER_AUTHORIZED."""
    decision = bind_external_publication(
        _proposal(
            actor="any-signed-in-worker",
            derivation=PublicationDerivation.WORKER_OUTPUT,
        )
    )
    assert decision.outcome is OwnerRepresentationOutcome.BLOCKED
    assert OwnerRepresentationReason.PUBLICATION_AUTHORITY_NON_INFERABLE in decision.reason_codes


def test_can_edit_code_is_not_can_publish():
    """CAN_EDIT_CODE != CAN_PUBLISH."""
    decision = bind_external_publication(_proposal(derivation=PublicationDerivation.UNTYPED))
    assert decision.outcome is OwnerRepresentationOutcome.BLOCKED
    assert OwnerRepresentationReason.PUBLICATION_AUTHORITY_NON_INFERABLE in decision.reason_codes


def test_can_commit_is_not_can_publish():
    decision = bind_external_publication(
        _proposal(derivation=PublicationDerivation.TASK_COMPLETION)
    )
    assert decision.outcome is OwnerRepresentationOutcome.BLOCKED
    assert OwnerRepresentationReason.PUBLICATION_AUTHORITY_NON_INFERABLE in decision.reason_codes


def test_can_push_is_not_can_represent_owner():
    decision = bind_external_publication(_proposal(derivation=PublicationDerivation.WORKER_OUTPUT))
    assert decision.outcome is OwnerRepresentationOutcome.BLOCKED
    assert OwnerRepresentationReason.PUBLICATION_AUTHORITY_NON_INFERABLE in decision.reason_codes


def test_can_merge_is_not_can_represent_owner():
    decision = bind_external_publication(
        _proposal(derivation=PublicationDerivation.TASK_COMPLETION)
    )
    assert decision.outcome is OwnerRepresentationOutcome.BLOCKED
    assert OwnerRepresentationReason.PUBLICATION_AUTHORITY_NON_INFERABLE in decision.reason_codes


def test_model_worker_output_is_not_owner_statement():
    decision = bind_external_publication(_proposal(derivation=PublicationDerivation.WORKER_OUTPUT))
    assert decision.outcome is OwnerRepresentationOutcome.BLOCKED
    assert OwnerRepresentationReason.PUBLICATION_AUTHORITY_NON_INFERABLE in decision.reason_codes


def test_no_grant_never_reaches_transport(
    publisher: OwnerRepresentationPublisher, remote: FakeRemote
):
    """A privileged but grant-less proposal must fail before any write."""
    proposal = _proposal(derivation=PublicationDerivation.EXPLICIT_OWNER_DECISION)
    with pytest.raises(OwnerRepresentationBlocked):
        publisher.prepare(proposal, grant=None)
    assert remote.writes == []


# ---------------------------------------------------------------------------
# Exact one-shot grant matching
# ---------------------------------------------------------------------------


def test_exact_grant_matches_and_authorizes():
    grant = _grant()
    decision = bind_external_publication(_proposal(), grant)
    assert decision.outcome is OwnerRepresentationOutcome.GRANT_MATCH
    assert decision.publication_authorized is True
    assert decision.grant_hash == grant.grant_hash


def test_grant_requires_every_bound_field():
    grant = _grant()
    assert (
        OwnerRepresentationReason.DESTINATION_MISMATCH
        in bind_external_publication(_proposal(destination=OWNER_REPO), grant).reason_codes
    )
    assert (
        OwnerRepresentationReason.FOLLOWUP_NOT_IMPLIED
        in bind_external_publication(
            _proposal(effect=ExternalPublicationEffect.COMMENT, target="42"), grant
        ).reason_codes
    )
    assert (
        OwnerRepresentationReason.ACTOR_MISMATCH
        in bind_external_publication(_proposal(actor="someone-else"), grant).reason_codes
    )
    assert (
        OwnerRepresentationReason.TRANSPORT_MISMATCH
        in bind_external_publication(_proposal(transport="other-transport"), grant).reason_codes
    )
    assert (
        OwnerRepresentationReason.OPERATION_MISMATCH
        in bind_external_publication(_proposal(operation_id="op-2"), grant).reason_codes
    )


def test_create_issue_grant_does_not_imply_comment_or_fork():
    grant = _grant(effect=ExternalPublicationEffect.CREATE_ISSUE)
    comment = _proposal(effect=ExternalPublicationEffect.COMMENT, target="42", operation_id="op-1")
    decision = bind_external_publication(comment, grant)
    assert decision.outcome is OwnerRepresentationOutcome.BLOCKED
    assert OwnerRepresentationReason.FOLLOWUP_NOT_IMPLIED in decision.reason_codes
    fork_proposal = _proposal(effect=ExternalPublicationEffect.PUBLIC_FORK)
    fork_decision = bind_external_publication(fork_proposal, grant)
    assert fork_decision.outcome is OwnerRepresentationOutcome.BLOCKED
    assert OwnerRepresentationReason.FOLLOWUP_NOT_IMPLIED in fork_decision.reason_codes


def test_public_fork_grant_never_implies_other_effects():
    grant = _grant(effect=ExternalPublicationEffect.PUBLIC_FORK)
    other = _grant(effect=ExternalPublicationEffect.CREATE_ISSUE)
    assert grant.grant_hash != other.grant_hash
    decision = bind_external_publication(
        _proposal(effect=ExternalPublicationEffect.CREATE_ISSUE), grant
    )
    assert decision.outcome is OwnerRepresentationOutcome.BLOCKED


# ---------------------------------------------------------------------------
# Content / purpose substitution
# ---------------------------------------------------------------------------


def test_content_substitution_is_blocked():
    grant = _grant()
    tampered = _proposal(
        title="Completely different remark",
        body="Repro steps and evidence.",
        content_hash=canonical_publication_content_hash(
            "Completely different remark", "Repro steps and evidence."
        ),
    )
    decision = bind_external_publication(tampered, grant)
    assert decision.outcome is OwnerRepresentationOutcome.BLOCKED
    assert OwnerRepresentationReason.CONTENT_SUBSTITUTION in decision.reason_codes


def test_purpose_substitution_is_blocked():
    grant = _grant()
    different_purpose = _proposal(purpose="publicly advertise this project")
    decision = bind_external_publication(different_purpose, grant)
    assert decision.outcome is OwnerRepresentationOutcome.BLOCKED
    assert OwnerRepresentationReason.PURPOSE_SUBSTITUTION in decision.reason_codes


# ---------------------------------------------------------------------------
# Grant expiry / revocation / staleness / standing mode
# ---------------------------------------------------------------------------


def test_expired_grant_is_blocked():
    grant = _grant(granted_at=NOW - timedelta(days=2), expires_at=NOW - timedelta(days=1))
    decision = bind_external_publication(_proposal(), grant, now=NOW)
    assert decision.outcome is OwnerRepresentationOutcome.BLOCKED
    assert OwnerRepresentationReason.GRANT_EXPIRED in decision.reason_codes


def test_revoked_grant_is_blocked():
    grant = _grant(
        revoked_at=NOW - timedelta(minutes=1),
        revocation_reason="owner rescinded",
    )
    decision = bind_external_publication(_proposal(), grant, now=NOW)
    assert decision.outcome is OwnerRepresentationOutcome.BLOCKED
    assert OwnerRepresentationReason.GRANT_REVOKED in decision.reason_codes


def test_superseded_grant_is_stale_and_blocked():
    grant = _grant(superseded_by="g-827-2")
    decision = bind_external_publication(_proposal(), grant)
    assert decision.outcome is OwnerRepresentationOutcome.BLOCKED
    assert OwnerRepresentationReason.GRANT_SUPERSEDED in decision.reason_codes


def test_standing_external_grant_is_not_supported():
    with pytest.raises(ValidationError):
        _grant(replay_mode="STANDING")


def test_non_one_shot_replay_mode_never_accepted_by_evaluator():
    # STANDING mode is structurally rejected at the model boundary; the
    # evaluator is therefore never handed a valid STANDING grant.
    with pytest.raises(ValidationError):
        _grant(replay_mode="STANDING")
    # A malformed/STANDING grant mapping fails closed to BLOCKED in the
    # evaluator.  A grant never authorizes a standing external publication.
    standing_dict = {**_grant().model_dump(mode="json"), "replay_mode": "STANDING"}
    decision = evaluate_owner_representation(standing_dict, _proposal())
    assert decision.outcome is OwnerRepresentationOutcome.BLOCKED
    assert decision.publication_authorized is False
    assert OwnerRepresentationReason.GRANT_INVALID in decision.reason_codes


# ---------------------------------------------------------------------------
# Destination classification, fail-closed
# ---------------------------------------------------------------------------


def test_unknown_destination_classifies_blocked():
    kind = classification(UNKNOWN_HOST, ExternalPublicationEffect.CREATE_ISSUE)
    assert kind is ExternalDestinationKind.UNKNOWN
    decision = bind_external_publication(
        _proposal(destination=UNKNOWN_HOST), _grant(destination=UNKNOWN_HOST)
    )
    assert decision.outcome is OwnerRepresentationOutcome.BLOCKED
    assert OwnerRepresentationReason.DESTINATION_UNKNOWN in decision.reason_codes


def test_bound_internal_collaboration_is_passthrough_not_publication():
    bound = InternalCollaborationBound(
        contract_id="internal-1",
        owner_id="owner-james",
        destination=OWNER_REPO,
        authorized_effects=(ExternalPublicationEffect.CREATE_ISSUE,),
    )
    proposal = _proposal(destination=OWNER_REPO)
    decision = bind_external_publication(proposal, _grant(), (bound,))
    assert decision.outcome is OwnerRepresentationOutcome.BLOCKED
    assert OwnerRepresentationReason.INTERNAL_AUTOMATION_PASSTHROUGH in decision.reason_codes


def test_internal_bound_never_validates_external_passthrough_to_writer(
    publisher: OwnerRepresentationPublisher, remote: FakeRemote
):
    bound = InternalCollaborationBound(
        contract_id="internal-1",
        owner_id="owner-james",
        destination=OWNER_REPO,
        authorized_effects=(ExternalPublicationEffect.CREATE_ISSUE,),
    )
    prepared = publisher.prepare(_proposal(destination=OWNER_REPO), grant=None, boundary=(bound,))
    assert prepared.state == "INTERNAL_PASSTHROUGH"
    result = publisher.publish(prepared)
    assert result["published"] is False
    assert remote.writes == []


# ---------------------------------------------------------------------------
# Durable one-shot publisher: no replay, reconciliation, no duplicate effect
# ---------------------------------------------------------------------------


def test_happy_path_publishes_exactly_once_and_completes(
    publisher: OwnerRepresentationPublisher,
    remote: FakeRemote,
    grant_store: OwnerRepresentationGrantStore,
):
    prepared = publisher.prepare(_proposal(), _issue_grant(grant_store))
    assert prepared.state == "PREPARED"
    result = publisher.publish(prepared)
    assert result["state"] == "COMPLETED"
    assert len(remote.writes) == 1


def test_completed_one_shot_cannot_be_replayed(
    publisher: OwnerRepresentationPublisher,
    remote: FakeRemote,
    grant_store: OwnerRepresentationGrantStore,
):
    proposal = _proposal()
    prepared = publisher.prepare(proposal, _issue_grant(grant_store))
    publisher.publish(prepared)
    with pytest.raises(OwnerRepresentationBlocked) as exc:
        publisher.publish(prepared)
    assert OwnerRepresentationReason.REPLAY_FORBIDDEN.value in str(exc.value)
    assert len(remote.writes) == 1


def test_same_grant_cannot_drive_a_different_operation(
    publisher: OwnerRepresentationPublisher,
    remote: FakeRemote,
    grant_store: OwnerRepresentationGrantStore,
):
    # Grant bound to op-1: publish consumes its one-shot ledger entry.
    grant_op1 = _issue_grant(grant_store, operation_id="op-1")
    first = publisher.prepare(_proposal(operation_id="op-1"), grant_op1)
    publisher.publish(first)
    assert len(remote.writes) == 1
    # Prepare op-2 legitimately with its own grant so its operation file is in
    # PREPARED state, then forge a PreparedPublication for op-2 that reuses the
    # already-consumed grant.  The consumed-grant ledger must refuse it.
    grant_op2 = _issue_grant(grant_store, grant_id="g-827-2", operation_id="op-2")
    publisher.prepare(_proposal(operation_id="op-2"), grant_op2)
    forged = PreparedPublication(
        operation_id="op-2",
        proposal=_proposal(operation_id="op-2"),
        grant=grant_op1,
        kind=ExternalDestinationKind.THIRD_PARTY_OR_EXTERNAL_OWNER_REPRESENTATION,
        state="PREPARED",
    )
    with pytest.raises(OwnerRepresentationBlocked) as exc:
        publisher.publish(forged)
    assert OwnerRepresentationReason.GRANT_REUSED.value in str(exc.value)
    assert len(remote.writes) == 1


def test_unsolicited_publish_without_prepare_is_blocked(
    publisher: OwnerRepresentationPublisher, remote: FakeRemote
):
    prepared = PreparedPublication(
        operation_id="never-prepared",
        proposal=_proposal(operation_id="never-prepared"),
        grant=_grant(operation_id="never-prepared"),
        kind=ExternalDestinationKind.THIRD_PARTY_OR_EXTERNAL_OWNER_REPRESENTATION,
        state="PREPARED",
    )
    with pytest.raises(OwnerRepresentationBlocked) as exc:
        publisher.publish(prepared)
    assert OwnerRepresentationReason.DISPATCH_NOT_PREPARED.value in str(exc.value)
    assert remote.writes == []


def test_unacknowledged_dispatch_reconciles_read_only_no_duplicate(
    publisher: OwnerRepresentationPublisher,
    remote: FakeRemote,
    grant_store: OwnerRepresentationGrantStore,
):
    remote.unack_next = True
    prepared = publisher.prepare(_proposal(), _issue_grant(grant_store))
    with pytest.raises(OwnerRepresentationBlocked) as exc:
        publisher.publish(prepared)
    assert OwnerRepresentationReason.RECONCILIATION_REQUIRED.value in str(exc.value)
    # Remote never saw the write; operation parked at OUTCOME_UNKNOWN.
    result = publisher.reconcile(prepared)
    assert result is None
    assert remote.writes == []


def test_write_lands_then_ack_lost_reconciles_read_only(
    publisher: OwnerRepresentationPublisher,
    remote: FakeRemote,
    grant_store: OwnerRepresentationGrantStore,
):
    """Remote write lands but ACK is lost -> OUTCOME_UNKNOWN -> readback-only."""
    proposal = _proposal()
    original_write = publisher.write_transport
    original_readback = publisher.readback_transport

    def write_then_lose_ack(_proposal):
        try:
            remote.write(_proposal)  # effect lands
            raise TransportDispatchedButUnacknowledged()
        except TransportDispatchedButUnacknowledged:
            raise
        return None

    publisher.write_transport = write_then_lose_ack
    prepared = publisher.prepare(proposal, _issue_grant(grant_store))
    with pytest.raises(OwnerRepresentationBlocked) as exc:
        publisher.publish(prepared)
    assert OwnerRepresentationReason.RECONCILIATION_REQUIRED.value in str(exc.value)
    assert len(remote.writes) == 1  # effect landed exactly once

    # Blind redispatch must be blocked, not doubled.
    publisher.write_transport = original_write
    with pytest.raises(OwnerRepresentationBlocked) as exc:
        publisher.publish(prepared)
    assert OwnerRepresentationReason.RECONCILIATION_REQUIRED.value in str(exc.value)
    assert len(remote.writes) == 1  # no duplicate effect

    # Readback-only reconciliation finds the marker and completes.
    publisher.readback_transport = original_readback
    result = publisher.reconcile(prepared)
    assert result is not None and result["state"] == "COMPLETED"
    assert len(remote.writes) == 1


def test_ack_but_readback_missing_parks_at_outcome_unknown(
    publisher: OwnerRepresentationPublisher,
    remote: FakeRemote,
    grant_store: OwnerRepresentationGrantStore,
):
    original_write = publisher.write_transport
    original_readback = publisher.readback_transport

    def write_without_marker(proposal):
        outcome = original_write(proposal)
        outcome.remote_marker = None
        return outcome

    publisher.write_transport = write_without_marker
    publisher.readback_transport = lambda p: None
    prepared = publisher.prepare(_proposal(), _issue_grant(grant_store))
    with pytest.raises(OwnerRepresentationBlocked) as exc:
        publisher.publish(prepared)
    assert OwnerRepresentationReason.RECONCILIATION_REQUIRED.value in str(exc.value)
    assert len(remote.writes) == 1
    # Reconcile can now find the marker through the (restored) real readback.
    publisher.readback_transport = original_readback
    result = publisher.reconcile(prepared)
    assert result is not None and result["state"] == "COMPLETED"
    assert len(remote.writes) == 1


def test_transport_exception_parks_outcome_unknown_not_second_write(
    publisher: OwnerRepresentationPublisher,
    remote: FakeRemote,
    grant_store: OwnerRepresentationGrantStore,
):
    def explode(_proposal):
        raise RuntimeError("socket reset mid-request")

    original_readback = publisher.readback_transport
    publisher.write_transport = explode
    prepared = publisher.prepare(_proposal(), _issue_grant(grant_store))
    with pytest.raises(OwnerRepresentationBlocked) as exc:
        publisher.publish(prepared)
    assert OwnerRepresentationReason.RECONCILIATION_REQUIRED.value in str(exc.value)
    assert remote.writes == []
    # readback says nothing landed; stays parked.
    assert publisher.reconcile(prepared) is None
    publisher.readback_transport = original_readback
    assert publisher.reconcile(prepared) is None


def test_operation_dir_durable_state_written_for_prepare(
    publisher: OwnerRepresentationPublisher, remote: FakeRemote
):
    proposal = _proposal()
    publisher.prepare(proposal, _grant())
    state_file = publisher._operation_path(proposal.operation_id)
    assert state_file.exists()


# ---------------------------------------------------------------------------
# Proposal / grant structural integrity
# ---------------------------------------------------------------------------


def test_proposal_content_hash_must_match_title_body():
    with pytest.raises(ValidationError) as exc:
        _proposal(content_hash="0" * 64)
    assert "CONTENT_HASH_MISMATCH" in str(exc.value)


def test_proposal_comment_requires_target_and_issue_bans_target():
    with pytest.raises(ValidationError):
        _proposal(effect=ExternalPublicationEffect.COMMENT)
    with pytest.raises(ValidationError):
        _proposal(effect=ExternalPublicationEffect.CREATE_ISSUE, target="42")


def test_destination_rejects_schemes_and_path_junk():
    assert _dest(host="github.com").host == "github.com"
    with pytest.raises(ValidationError):
        _dest(host="ssh://github.com")
    with pytest.raises(ValidationError):
        _dest(host="https://github.com/nested")
    with pytest.raises(ValidationError):
        _dest(host="github.com", owner_account="../evil")
    with pytest.raises(ValidationError):
        _dest(host="git@github.com")


def test_grant_requires_expiry_after_grant_and_revocation_binding():
    with pytest.raises(ValidationError):
        _grant(granted_at=NOW, expires_at=NOW - timedelta(minutes=1))
    with pytest.raises(ValidationError):
        _grant(revoked_at=NOW, revocation_reason=None)


# ---------------------------------------------------------------------------
# Transport inventory fails closed
# ---------------------------------------------------------------------------


def test_inventory_has_no_unknown_by_default():
    assert_no_unknown_routes()
    assert classify_transport_route("does_not_exist") is PublicationRouteState.UNKNOWN_BLOCKED
    status = transport_inventory_status()
    assert status["chatgpt_connector"] == "OWNER_INTERACTIVE_GATED"
    assert status["governed_push"] == "BOUNDED_INTERNAL_ONLY"


@pytest.mark.parametrize(
    "pattern_name",
    [
        "gh_cli_issue_pr_create",
        "gh_cli_api_write",
        "github_issues_create",
        "github_comments_create",
        "github_octokit_create_pr",
        "http_write_to_github",
        "http_write_to_issues_endpoint",
    ],
)
def test_no_silent_github_write_sink_in_source(repo_root: Path, pattern_name: str):
    from nexus.security.owner_representation_transport_inventory import (
        FORBIDDEN_PROGRAMMATIC_GITHUB_WRITE_PATTERNS,
    )

    pattern = next(
        pat
        for pat, _name, _why in FORBIDDEN_PROGRAMMATIC_GITHUB_WRITE_PATTERNS
        if _name == pattern_name
    )
    offenders: list[str] = []
    for py in sorted((repo_root / "nexus").rglob("*.py")) + sorted(
        (repo_root / "scripts").rglob("*.py")
    ):
        # The inventory itself declares these patterns as data; skip it.
        if "owner_representation_transport_inventory" in str(py):
            continue
        # Morning-report guidance text predates this authority boundary; it is
        # inventoried as human-facing guidance, never an invocation.
        if py.name == "morning_report.py":
            continue
        for lineno, line in enumerate(
            py.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if re.search(pattern, line):
                offenders.append(f"{py.relative_to(repo_root)}:{lineno}")
    assert offenders == [], f"silent GitHub write sink matched {pattern}: {offenders}"


# ---------------------------------------------------------------------------
# BLOCKER 1: store-backed trust.  A grant object is inert without a durable
# OwnerRepresentationGrantStore receipt; the seam revalidates the store fresh
# immediately before dispatch.
# ---------------------------------------------------------------------------


def test_self_minted_grant_without_store_receipt_is_blocked(
    publisher: OwnerRepresentationPublisher,
    remote: FakeRemote,
):
    """A grant object no canonical store ever issued must fail closed."""
    self_minted = _grant()
    prepared = publisher.prepare(_proposal(), self_minted)
    assert prepared.state == "PREPARED"
    with pytest.raises(OwnerRepresentationBlocked) as exc:
        publisher.publish(prepared)
    assert OwnerRepresentationReason.GRANT_NOT_ISSUED.value in str(exc.value)
    assert remote.writes == []


@pytest.mark.parametrize("forged_field", [{"owner_id": "attacker"}, {"issued_by": "attacker"}])
def test_forged_grant_object_never_authorizes(publisher, remote, forged_field):
    """Forged ownership identity, even with a self-consistent hash, is blocked."""
    grant = _grant(**forged_field)
    prepared = publisher.prepare(_proposal(), grant)
    with pytest.raises(OwnerRepresentationBlocked) as exc:
        publisher.publish(prepared)
    assert OwnerRepresentationReason.GRANT_NOT_ISSUED.value in str(exc.value)
    assert remote.writes == []


def test_stale_serialized_grant_blocked_after_canonical_revocation(
    publisher: OwnerRepresentationPublisher,
    remote: FakeRemote,
    grant_store: OwnerRepresentationGrantStore,
):
    grant = _issue_grant(grant_store)
    stale = OwnerRepresentationGrant.model_validate(grant.model_dump(mode="json"))
    grant_store.revoke(
        grant.grant_hash,
        revoked_by="owner-james",
        reason="owner rescinded",
    )
    prepared = publisher.prepare(_proposal(), stale)
    with pytest.raises(OwnerRepresentationBlocked) as exc:
        publisher.publish(prepared)
    assert OwnerRepresentationReason.GRANT_REVOKED.value in str(exc.value)
    assert remote.writes == []


# ---------------------------------------------------------------------------
# BLOCKER 2: fenced transitions, consumed-grant ledger, single winner
# ---------------------------------------------------------------------------


def test_completed_operation_cannot_be_reprepared(
    publisher: OwnerRepresentationPublisher,
    remote: FakeRemote,
    grant_store: OwnerRepresentationGrantStore,
):
    grant = _issue_grant(grant_store)
    proposal = _proposal()
    prepared = publisher.prepare(proposal, grant)
    publisher.publish(prepared)
    assert len(remote.writes) == 1
    with pytest.raises(OwnerRepresentationBlocked) as exc:
        publisher.prepare(proposal, grant)
    assert OwnerRepresentationReason.OPERATION_TERMINAL_OR_INFLIGHT.value in str(exc.value)
    assert len(remote.writes) == 1


def test_two_publisher_instances_share_single_winner(
    publisher: OwnerRepresentationPublisher,
    remote: FakeRemote,
    grant_store: OwnerRepresentationGrantStore,
):
    """Two instances sharing operation_root/store serialize to one effect."""
    grant = _issue_grant(grant_store)
    prepared_a = publisher.prepare(_proposal(), grant)
    twin = OwnerRepresentationPublisher(
        operation_root=publisher.operation_root,
        write_transport=remote.write,
        readback_transport=remote.readback,
        grant_store=grant_store,
    )
    prepared_b = twin.prepare(_proposal(), grant)
    assert remote.writes == []
    assert prepared_a.state == "PREPARED" and prepared_b.state == "PREPARED"
    first = publisher.publish(prepared_a)
    assert first["state"] == "COMPLETED"
    with pytest.raises(OwnerRepresentationBlocked) as exc:
        twin.publish(prepared_b)
    assert OwnerRepresentationReason.REPLAY_FORBIDDEN.value in str(exc.value)
    assert len(remote.writes) == 1


# ---------------------------------------------------------------------------
# BLOCKER 3: inventory classification + no broad GitHub credential passthrough
# ---------------------------------------------------------------------------


def test_inventory_classifies_devspace_and_seam():
    assert_no_unknown_routes()
    status = transport_inventory_status()
    assert (
        status["devspace_worker"] == PublicationRouteState.INCAPABLE_OF_EXTERNAL_PUBLICATION.value
    )
    assert (
        status["owner_representation_seam"]
        == PublicationRouteState.EXTERNAL_PUBLICATION_AUTHORITY_ENFORCED.value
    )
    assert "UNKNOWN_BLOCKED" not in set(status.values())


def test_enforced_and_incapable_route_witnesses_exist(repo_root: Path):
    for route_id in ("owner_representation_seam", "devspace_worker"):
        witnesses = physical_witnesses_for(route_id)
        assert witnesses, f"{route_id} has no physical witnesses"
        for witness in witnesses:
            assert (repo_root / witness).is_file(), f"{route_id} witness missing on disk: {witness}"
    seam = physical_witnesses_for("owner_representation_seam")
    assert "nexus/orchestrator/owner_representation.py" in seam
    assert "nexus/orchestrator/owner_representation_store.py" in seam


def test_inventory_docstring_marks_source_scope_limitation():
    import nexus.security.owner_representation_transport_inventory as inventory

    assert "INCAPABILITY_IS_SOURCE_SCOPE_ONLY" in inventory.__doc__


@pytest.mark.parametrize(
    "argv",
    [
        ("issue", "create", "-R", "acme/demo", "--title", "x"),
        ("--silent", "issue", "create", "--title", "x"),
        ("pr", "create", "--title", "x", "--body", "y", "--repo", "z"),
        ("api", "repos/acme/demo/issues", "-f", "title=x"),
    ],
)
def test_cli_worker_forbids_gh_publication_invocations(tmp_path, argv):
    from nexus.executors.cli_worker import CliWorkerRequest

    with pytest.raises(ValueError, match="gh"):
        CliWorkerRequest(executable="gh", argv=argv, cwd=str(tmp_path))


def test_build_isolated_env_strips_github_credentials(monkeypatch):
    from nexus.services.agy_account_pool import (
        GITHUB_CREDENTIAL_KEYS,
        SENSITIVE_API_KEYS,
        build_isolated_env,
    )

    assert set(GITHUB_CREDENTIAL_KEYS) <= set(SENSITIVE_API_KEYS)
    for key in (*GITHUB_CREDENTIAL_KEYS, "GEMINI_API_KEY"):
        monkeypatch.setenv(key, "secret")
    isolated = build_isolated_env(home_dir="/isolated/home")
    for key in GITHUB_CREDENTIAL_KEYS:
        assert key not in isolated
