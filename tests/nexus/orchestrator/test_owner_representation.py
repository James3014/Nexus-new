"""Hostile / negative / replay suite for EXTERNAL_PUBLICATION /
OWNER_REPRESENTATION authority (#827).

Uses fixtures, mocks, and temp remotes only.  No real third-party repository
or user is ever contacted.
"""

from __future__ import annotations

import base64
import json
import os
import re
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

import nexus.orchestrator.owner_representation as owner_publisher_module
import nexus.orchestrator.owner_representation_store as owner_store_module
import nexus.orchestrator.standing_grant_store as standing_store_module
from nexus.contracts.autonomy_goal import (
    AutonomyActionClass,
    RepositoryIdentity,
    StandingGrantContext,
    canonical_autonomy_hash,
)
from nexus.contracts.owner_representation import (
    ExternalDestination,
    ExternalDestinationKind,
    ExternalPublicationEffect,
    ExternalPublicationProposal,
    InternalCollaborationBound,
    OwnerExactPublicationAuthorizationSpec,
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
from nexus.orchestrator.owner_representation_store import (
    OwnerRepresentationGrantBlocked,
    OwnerRepresentationGrantStore,
    consume_exact_owner_authorization,
    exact_owner_publication_authorization_exists,
    mint_owner_representation_publication_issuance_permit,
    owner_issues_exact_publication_authorization,
)
from nexus.orchestrator.standing_grant_store import (
    StandingGrantKey,
    StandingGrantReceipt,
    _load_receipt_at,
    _write_standing_grant_receipt_at,
)
from nexus.security.owner_representation_transport_inventory import (
    PublicationRouteState,
    assert_no_unknown_routes,
    classify_transport_route,
    physical_witnesses_for,
    transport_inventory_status,
)

_production_verify_owner_signature = owner_store_module._verify_owner_signature

NOW = datetime.now(timezone.utc)

# Test-only issuer boundary: production never provisions a private key.  The
# hostile tests call the production verifier directly with forged signatures.
_production_owner_issuer = owner_issues_exact_publication_authorization


def owner_issues_exact_publication_authorization(*args, **kwargs):
    kwargs.setdefault("owner_key_id", "fixture")
    kwargs.setdefault("owner_signature", "fixture-signature")
    return _production_owner_issuer(*args, **kwargs)


@pytest.fixture(autouse=True)
def fixture_owner_trust_root(monkeypatch, tmp_path):
    trust_root = tmp_path / "trusted-keys"
    trust_root.mkdir(mode=0o700, exist_ok=True)
    key = trust_root / "owner-james--fixture.pem"
    key.write_text("fixture", encoding="utf-8")
    key.chmod(0o600)
    monkeypatch.setattr(owner_store_module, "OWNER_AUTHORIZATION_TRUST_ROOT", trust_root)
    monkeypatch.setattr(owner_store_module, "_verify_owner_signature", lambda auth: None)
    # Explicit test-only transport mapping; production has no fixture
    # whitelist and uses the immutable canonical inventory mapping.
    monkeypatch.setattr(
        owner_publisher_module,
        "route_for_transport",
        lambda identity: "owner_representation_seam" if identity == "fixture" else None,
    )


THIRD_PARTY = ExternalDestination(
    host="github.com", owner_account="Waishnav", repository="devspace"
)
OWNER_REPO = ExternalDestination(
    host="github.com", owner_account="James3014", repository="Nexus-new"
)
UNKNOWN_HOST = ExternalDestination(
    host="pubsub.example.com", owner_account="acme", repository="board"
)

# The durable Owner standing grant that authorizes grant issuance is scoped to
# the exact THIRD_PARTY destination used by the issued test grants.
OWNER_REPRESENTATION_STANDING_REPOSITORY = RepositoryIdentity(
    repository_id="Waishnav/devspace",
    canonical_remote="https://github.com/Waishnav/devspace.git",
)


@pytest.fixture
def repo_root() -> Path:
    # tests/nexus/orchestrator/test_owner_representation.py -> repository root
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def standing_grant_path(tmp_path: Path) -> Path:
    """One durable Owner standing grant authorizing OWNER_REPRESENTATION_GRANT_ISSUE."""
    path = tmp_path / "standing-grant.json"
    context = StandingGrantContext.issue(
        owner_id="owner-james",
        coordinator_id="coordinator-codex",
        repository=OWNER_REPRESENTATION_STANDING_REPOSITORY,
        thread_id="thread-coord-1",
        goal_id="goal-827",
        allowed_actions=(AutonomyActionClass.OWNER_REPRESENTATION_GRANT_ISSUE,),
        issued_at=NOW - timedelta(hours=2),
        expires_at=NOW + timedelta(hours=2),
    )
    receipt = StandingGrantReceipt.issue(grant_id="standing-grant-827", context=context)
    _write_standing_grant_receipt_at(receipt, path)
    return path


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
    return OwnerRepresentationGrant.model_validate(
        {
            **spec.model_dump(mode="json"),
            "grant_hash": canonical_autonomy_hash(spec.model_dump(mode="json")),
        }
    )


def _issue_grant(
    grant_store: OwnerRepresentationGrantStore, **overrides
) -> OwnerRepresentationGrant:
    """Issue a durable, store-backed grant (the only authoritative form).

    Mint the exact sealed one-shot issuance permit bound to the fixture's
    durable Owner standing-grant receipt and exact Owner publication
    authorization at one fixed instant, then issue the same grant with that
    permit at the same instant.  A replayed, forged, or different-grant permit
    can never drive a receipt.
    """
    grant = _grant(**overrides)
    now = datetime.now(timezone.utc)
    owner_issues_exact_publication_authorization(
        grant,
        issued_at=now,
        authority_root=grant_store.root,
    )
    permit = mint_owner_representation_publication_issuance_permit(
        grant,
        authority_root=grant_store.root,
        standing_grant_path=grant_store.standing_grant_path,
        requested_at=now,
    )
    grant_store.issue(grant, issuance_permit=permit, requested_at=now)
    return grant


def _rotate_standing_grant(
    standing_grant_path: Path, *, grant_id: str, expires_delta: timedelta
) -> StandingGrantReceipt:
    """CAS-supersede the fixture standing grant so the next permit slot is fresh.

    One standing-grant receipt authorizes exactly one one-shot issuance permit;
    a second grant needs a rotated (CAS-superseded) standing-grant receipt.
    """
    predecessor = _load_receipt_at(standing_grant_path, now=NOW)
    context = StandingGrantContext.issue(
        owner_id="owner-james",
        coordinator_id="coordinator-codex",
        repository=OWNER_REPRESENTATION_STANDING_REPOSITORY,
        thread_id="thread-coord-1",
        goal_id="goal-827",
        allowed_actions=(AutonomyActionClass.OWNER_REPRESENTATION_GRANT_ISSUE,),
        issued_at=NOW - timedelta(hours=2),
        expires_at=NOW + expires_delta,
    )
    receipt = StandingGrantReceipt.issue(
        grant_id=grant_id,
        context=context,
        supersedes_grant_hash=predecessor.receipt_hash,
    )
    _write_standing_grant_receipt_at(
        receipt, standing_grant_path, expected_receipt_hash=predecessor.receipt_hash
    )
    return receipt


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
        self.writes.append(
            {
                "marker": marker,
                "op": proposal.operation_id,
                "effect": proposal.effect.value,
                "destination": proposal.destination.repository_id,
                "title": proposal.title,
                "body": proposal.body,
                "purpose": proposal.purpose,
                "actor": proposal.actor,
            }
        )
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
def grant_store(tmp_path: Path, standing_grant_path: Path) -> OwnerRepresentationGrantStore:
    return OwnerRepresentationGrantStore(
        root=tmp_path / "grant-authority",
        standing_grant_path=standing_grant_path,
    )


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


def test_production_owner_issuance_requires_exact_key(tmp_path):
    grant = _grant()
    with pytest.raises(OwnerRepresentationGrantBlocked):
        owner_store_module.authorize_owner_representation_grant_issuance(
            grant, requested_at=NOW, standing_grant_path=None, standing_grant_key=None
        )


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
    # already-consumed grant.  The consumed-grant ledger must refuse it.  The
    # second grant needs its own one-shot permit slot, so the standing grant is
    # rotated (CAS-superseded) first.
    _rotate_standing_grant(
        grant_store.standing_grant_path,
        grant_id="standing-grant-827-r2",
        expires_delta=timedelta(hours=3),
    )
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


def test_prepare_fsyncs_containing_operation_directory_after_replace(
    publisher: OwnerRepresentationPublisher, remote: FakeRemote, monkeypatch
):
    """Atomic operation state must persist its rename across a crash."""
    fsync_is_directory: list[bool] = []
    real_fsync = os.fsync

    def recording_fsync(fd: int) -> None:
        fsync_is_directory.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        real_fsync(fd)

    monkeypatch.setattr(owner_publisher_module.os, "fsync", recording_fsync)
    publisher.prepare(_proposal(), _grant())
    assert any(fsync_is_directory)


def test_publish_rejects_prepared_proposal_identity_mismatch(
    publisher: OwnerRepresentationPublisher,
    remote: FakeRemote,
    grant_store: OwnerRepresentationGrantStore,
):
    grant = _issue_grant(grant_store)
    prepared = publisher.prepare(_proposal(), grant)
    forged = PreparedPublication(
        operation_id=prepared.operation_id,
        proposal=_proposal(operation_id="op-forged"),
        grant=prepared.grant,
        kind=prepared.kind,
        state=prepared.state,
    )
    with pytest.raises(OwnerRepresentationBlocked, match="OPERATION_CONFLICT"):
        publisher.publish(forged)
    assert remote.writes == []


def test_publish_rejects_prepared_store_identity_mismatch(
    publisher: OwnerRepresentationPublisher,
    remote: FakeRemote,
    grant_store: OwnerRepresentationGrantStore,
    tmp_path: Path,
):
    grant = _issue_grant(grant_store)
    prepared = publisher.prepare(_proposal(), grant)
    other_store = OwnerRepresentationGrantStore(tmp_path / "other-authority")
    other_publisher = OwnerRepresentationPublisher(
        operation_root=publisher.operation_root,
        write_transport=remote.write,
        readback_transport=remote.readback,
        grant_store=other_store,
    )
    with pytest.raises(OwnerRepresentationBlocked, match="OPERATION_CONFLICT"):
        other_publisher.publish(prepared)
    assert remote.writes == []


def test_unknown_transport_status_parks_without_redispatch(
    publisher: OwnerRepresentationPublisher,
    remote: FakeRemote,
    grant_store: OwnerRepresentationGrantStore,
):
    publisher.write_transport = lambda proposal: WriteOutcome(status="UNRECOGNIZED")
    prepared = publisher.prepare(_proposal(), _issue_grant(grant_store))
    with pytest.raises(OwnerRepresentationBlocked, match="RECONCILIATION_REQUIRED"):
        publisher.publish(prepared)
    assert remote.writes == []
    operation = json.loads(
        publisher._operation_path(prepared.operation_id).read_text(encoding="utf-8")
    )
    assert operation["state"] == "OUTCOME_UNKNOWN"


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
    assert status["chatgpt_connector"] == "UNKNOWN_BLOCKED"
    assert status["codex_cli_pat"] == "UNKNOWN_BLOCKED"
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
    assert status["devspace_worker"] == PublicationRouteState.UNKNOWN_BLOCKED.value
    assert (
        status["owner_representation_seam"]
        == PublicationRouteState.EXTERNAL_PUBLICATION_AUTHORITY_ENFORCED.value
    )
    # The seam is the sole authority-enforced external write route; the
    # devspace route is registered but fail-closed (never usable).
    assert (
        list(status.values()).count(
            PublicationRouteState.EXTERNAL_PUBLICATION_AUTHORITY_ENFORCED.value
        )
        == 1
    )
    assert PublicationRouteState.UNKNOWN_BLOCKED.value in set(status.values())


def test_prepare_rejects_unregistered_transport_even_with_exact_owner_grant(
    publisher: OwnerRepresentationPublisher,
    grant_store: OwnerRepresentationGrantStore,
    remote: FakeRemote,
):
    proposal = _proposal(transport="made_up_transport", operation_id="op-unregistered")
    grant = _issue_grant(grant_store, transport="made_up_transport", operation_id="op-unregistered")
    with pytest.raises(OwnerRepresentationBlocked, match="TRANSPORT_UNREGISTERED"):
        publisher.prepare(proposal, grant)
    assert remote.writes == []


def test_prepare_rejects_unknown_blocked_route_even_with_explicit_binding(
    publisher: OwnerRepresentationPublisher,
    grant_store: OwnerRepresentationGrantStore,
    remote: FakeRemote,
    monkeypatch,
):
    proposal = _proposal(transport="fixture", operation_id="op-unknown-route")
    grant = _issue_grant(grant_store, operation_id="op-unknown-route")
    monkeypatch.setattr(
        owner_publisher_module,
        "route_for_transport",
        lambda identity: "devspace_worker" if identity == "fixture" else None,
    )
    blocked_publisher = OwnerRepresentationPublisher(
        operation_root=publisher.operation_root / "blocked",
        write_transport=remote.write,
        readback_transport=remote.readback,
        grant_store=grant_store,
    )
    with pytest.raises(OwnerRepresentationBlocked, match="TRANSPORT_ROUTE_BLOCKED"):
        blocked_publisher.prepare(proposal, grant)
    assert remote.writes == []


def test_publish_revalidates_transport_before_consuming_grant_or_writing(
    publisher: OwnerRepresentationPublisher,
    grant_store: OwnerRepresentationGrantStore,
    remote: FakeRemote,
    monkeypatch,
):
    proposal = _proposal(transport="fixture", operation_id="op-route-revoked")
    grant = _issue_grant(grant_store, operation_id="op-route-revoked")
    prepared = publisher.prepare(proposal, grant)
    monkeypatch.setattr(owner_publisher_module, "route_for_transport", lambda identity: None)
    with pytest.raises(OwnerRepresentationBlocked, match="TRANSPORT_UNREGISTERED"):
        publisher.publish(prepared)
    assert remote.writes == []
    assert not (publisher.operation_root / "consumed_grants" / f"{grant.grant_hash}.json").exists()


def test_devspace_route_state_matches_physical_evidence(repo_root: Path):
    status = transport_inventory_status()
    assert status["devspace_worker"] == PublicationRouteState.UNKNOWN_BLOCKED.value
    worker_registry_source = (repo_root / "nexus/executors/worker_registry.py").read_text(
        encoding="utf-8"
    )
    assert "devspace" not in worker_registry_source.lower()
    assert "nexus/executors/cli_worker.py" in physical_witnesses_for("devspace_worker")


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


# ---------------------------------------------------------------------------
# BLOCKER 1 (re-verification): issuance requires live Owner standing-grant
# authority; a worker can never self-authorize a canonical store receipt.
# ---------------------------------------------------------------------------


def test_worker_cannot_create_authority_store_receipt(grant_store):
    """A worker calling issue() without an Owner issuance permit gets no receipt."""
    with pytest.raises(OwnerRepresentationGrantBlocked) as exc:
        grant_store.issue(_grant(), issuance_permit=None)
    assert OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REQUIRED.value in str(exc.value)
    grants_dir = grant_store.root / "grants"
    assert not grants_dir.exists() or not any(grants_dir.iterdir())


def test_forged_owner_identity_cannot_issue_receipt(grant_store, standing_grant_path):
    """An attacker cannot present a minted permit but claim a different Owner identity."""
    forged = _grant(owner_id="attacker", issued_by="attacker")
    owner_issues_exact_publication_authorization(
        forged,
        issued_at=NOW,
        authority_root=grant_store.root,
    )
    permit = mint_owner_representation_publication_issuance_permit(
        forged,
        authority_root=grant_store.root,
        standing_grant_path=standing_grant_path,
        requested_at=NOW,
    )
    with pytest.raises(OwnerRepresentationGrantBlocked) as exc:
        grant_store.issue(forged, issuance_permit=permit, requested_at=NOW)
    assert OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REJECTED.value in str(exc.value)


def test_replayed_authorization_cannot_issue_another_grant(grant_store, standing_grant_path):
    """A permit minted for grant A can never be replayed to issue grant B."""
    grant_a = _grant()
    grant_b = _grant(grant_id="g-827-2", operation_id="op-2")
    owner_issues_exact_publication_authorization(
        grant_a,
        issued_at=NOW,
        authority_root=grant_store.root,
    )
    permit_a = mint_owner_representation_publication_issuance_permit(
        grant_a,
        authority_root=grant_store.root,
        standing_grant_path=standing_grant_path,
        requested_at=NOW,
    )
    with pytest.raises(OwnerRepresentationGrantBlocked) as exc:
        grant_store.issue(grant_b, issuance_permit=permit_a, requested_at=NOW)
    assert OwnerRepresentationReason.ISSUANCE_AUTHORIZATION_REJECTED.value in str(exc.value)


def test_stale_or_replaced_owner_issuance_authority_blocks(
    grant_store, standing_grant_path, publisher, remote
):
    """A grant issued under today's authority must not publish once the standing
    grant has been replaced (context/receipt hash changed)."""
    _issue_grant(grant_store)
    predecessor = _load_receipt_at(standing_grant_path, now=NOW)
    replacement_context = StandingGrantContext.issue(
        owner_id="owner-james",
        coordinator_id="coordinator-codex",
        repository=OWNER_REPRESENTATION_STANDING_REPOSITORY,
        thread_id="thread-coord-1",
        goal_id="goal-827",
        allowed_actions=(AutonomyActionClass.OWNER_REPRESENTATION_GRANT_ISSUE,),
        issued_at=NOW - timedelta(hours=2),
        expires_at=NOW + timedelta(hours=3),
    )
    _write_standing_grant_receipt_at(
        StandingGrantReceipt.issue(
            grant_id="standing-grant-827b",
            context=replacement_context,
            supersedes_grant_hash=predecessor.receipt_hash,
        ),
        standing_grant_path,
        expected_receipt_hash=predecessor.receipt_hash,
    )
    prepared = publisher.prepare(_proposal(), _grant())
    with pytest.raises(OwnerRepresentationBlocked) as exc:
        publisher.publish(prepared)
    assert OwnerRepresentationReason.ISSUANCE_AUTHORITY_CHANGED.value in str(exc.value)
    assert remote.writes == []


def test_revoked_owner_issuance_authority_blocks_publish(
    grant_store, standing_grant_path, publisher, remote
):
    """Publishing after the Owner standing grant is revoked fails closed."""
    _issue_grant(grant_store)
    predecessor = _load_receipt_at(standing_grant_path, now=NOW)
    revoked_context = StandingGrantContext.issue(
        owner_id="owner-james",
        coordinator_id="coordinator-codex",
        repository=OWNER_REPRESENTATION_STANDING_REPOSITORY,
        thread_id="thread-coord-1",
        goal_id="goal-827",
        allowed_actions=(AutonomyActionClass.OWNER_REPRESENTATION_GRANT_ISSUE,),
        issued_at=NOW - timedelta(hours=2),
        expires_at=NOW + timedelta(hours=2),
        revoked_at=NOW - timedelta(minutes=1),
        revocation_reason="standing authority revoked",
    )
    _write_standing_grant_receipt_at(
        StandingGrantReceipt.issue(
            grant_id="standing-grant-827-revoked",
            context=revoked_context,
            supersedes_grant_hash=predecessor.receipt_hash,
        ),
        standing_grant_path,
        expected_receipt_hash=predecessor.receipt_hash,
    )
    prepared = publisher.prepare(_proposal(), _grant())
    with pytest.raises(OwnerRepresentationBlocked) as exc:
        publisher.publish(prepared)
    assert OwnerRepresentationReason.ISSUANCE_AUTHORITY_NOT_LIVE.value in str(exc.value)
    assert remote.writes == []


# ---------------------------------------------------------------------------
# BLOCKER 2 (re-verification): one Owner standing-grant receipt drives exactly
# one exact grant exactly once; the issuance permit is non-reusable and the
# consumption fence survives grant-receipt destruction.
# ---------------------------------------------------------------------------


def test_one_standing_grant_cannot_mint_both_a_and_b(grant_store, standing_grant_path):
    """A single Owner standing-grant receipt authorizes exactly ONE permit."""
    grant_a = _grant()
    grant_b = _grant(grant_id="g-827-2", operation_id="op-2")
    owner_issues_exact_publication_authorization(
        grant_a,
        issued_at=NOW,
        authority_root=grant_store.root,
    )
    owner_issues_exact_publication_authorization(
        grant_b,
        issued_at=NOW,
        authority_root=grant_store.root,
    )
    mint_owner_representation_publication_issuance_permit(
        grant_a,
        authority_root=grant_store.root,
        standing_grant_path=standing_grant_path,
        requested_at=NOW,
    )
    with pytest.raises(OwnerRepresentationGrantBlocked) as exc:
        mint_owner_representation_publication_issuance_permit(
            grant_b,
            authority_root=grant_store.root,
            standing_grant_path=standing_grant_path,
            requested_at=NOW,
        )
    assert OwnerRepresentationReason.ISSUANCE_PERMIT_SLOT_CONSUMED.value in str(exc.value)
    assert "grant_b_receipt_does_not_exist" in str(exc.value)


def test_hostile_owner_authorization_issues_exact_grant_once(grant_store, standing_grant_path):
    """One Owner authorization issues exact grant A exactly once, nothing else."""
    grant_a = _grant()
    grant_b = _grant(grant_id="g-827-2", operation_id="op-2")
    now = datetime.now(timezone.utc)
    owner_issues_exact_publication_authorization(
        grant_a,
        issued_at=now,
        authority_root=grant_store.root,
    )
    owner_issues_exact_publication_authorization(
        grant_b,
        issued_at=now,
        authority_root=grant_store.root,
    )
    permit = mint_owner_representation_publication_issuance_permit(
        grant_a,
        authority_root=grant_store.root,
        standing_grant_path=standing_grant_path,
        requested_at=now,
    )
    receipt_path = grant_store.issue(grant_a, issuance_permit=permit, requested_at=now)
    assert receipt_path.exists()
    # A different grant can never share that standing-grant receipt's permit.
    with pytest.raises(OwnerRepresentationGrantBlocked) as exc:
        mint_owner_representation_publication_issuance_permit(
            grant_b,
            authority_root=grant_store.root,
            standing_grant_path=standing_grant_path,
            requested_at=now,
        )
    assert OwnerRepresentationReason.ISSUANCE_PERMIT_SLOT_CONSUMED.value in str(exc.value)
    assert "grant_b_receipt_does_not_exist" in str(exc.value)
    # Re-issuing the same grant is refused while the receipt still exists.
    with pytest.raises(OwnerRepresentationGrantBlocked) as exc:
        grant_store.issue(grant_a, issuance_permit=permit, requested_at=now)
    assert OwnerRepresentationReason.GRANT_ALREADY_ISSUED.value in str(exc.value)


def test_consumed_permit_blocks_reissue_even_if_receipt_missing(grant_store, standing_grant_path):
    """Destroying the grant receipt cannot resurrect a consumed permit."""
    grant_a = _grant()
    now = datetime.now(timezone.utc)
    owner_issues_exact_publication_authorization(
        grant_a,
        issued_at=now,
        authority_root=grant_store.root,
    )
    permit = mint_owner_representation_publication_issuance_permit(
        grant_a,
        authority_root=grant_store.root,
        standing_grant_path=standing_grant_path,
        requested_at=now,
    )
    receipt_path = grant_store.issue(grant_a, issuance_permit=permit, requested_at=now)
    receipt_path.unlink()
    with pytest.raises(OwnerRepresentationGrantBlocked) as exc:
        grant_store.issue(grant_a, issuance_permit=permit, requested_at=now)
    assert OwnerRepresentationReason.GRANT_REUSED.value in str(exc.value)


# ---------------------------------------------------------------------------
# Section 5: Mandatory independent hostile oracle (#827)
# ---------------------------------------------------------------------------


def test_worker_in_memory_owner_authorization_requires_persisted_owner_record(
    grant_store, standing_grant_path
):
    """A worker-created hash-valid auth is not an Owner decision."""
    grant = _grant()
    forged = _production_owner_issuer(
        grant, issued_at=NOW, owner_key_id="fixture", owner_signature="forged"
    )
    with pytest.raises(
        OwnerRepresentationGrantBlocked,
        match="EXACT_OWNER_AUTHORIZATION_REQUIRED",
    ):
        consume_exact_owner_authorization(
            grant,
            owner_authorization=forged,
            authority_root=grant_store.root,
            standing_grant_path=standing_grant_path,
            requested_at=NOW,
        )
    assert not (grant_store.root / "permits").exists()


def test_worker_cannot_substitute_persisted_owner_auth_a_for_grant_b(
    grant_store, standing_grant_path
):
    grant_a = _grant()
    grant_b = _grant(grant_id="worker-selected-b", operation_id="op-b")
    auth_a = owner_issues_exact_publication_authorization(
        grant_a, issued_at=NOW, authority_root=grant_store.root
    )
    with pytest.raises(
        OwnerRepresentationGrantBlocked,
        match="EXACT_OWNER_AUTHORIZATION_MISMATCH",
    ):
        consume_exact_owner_authorization(
            grant_b,
            owner_authorization=auth_a,
            authority_root=grant_store.root,
            standing_grant_path=standing_grant_path,
            requested_at=NOW,
        )


def test_real_rsa_owner_signature_accepts_and_rejects_tamper(
    grant_store, standing_grant_path, publisher, remote, monkeypatch, tmp_path
):
    """Use /usr/bin/openssl RSA-3072 signing; no verifier stubs involved."""
    import nexus.orchestrator.owner_representation_store as store

    trust_root = tmp_path / "trusted-keys"
    trust_root.mkdir(mode=0o700, exist_ok=True)
    private_key = tmp_path / "owner-private.pem"
    public_key = trust_root / "owner-james--rsa.pem"
    subprocess.run([store.OPENSSL_BINARY, "genrsa", "-out", str(private_key), "3072"], check=True)
    subprocess.run(
        [store.OPENSSL_BINARY, "rsa", "-in", str(private_key), "-pubout", "-out", str(public_key)],
        check=True,
    )
    private_key.chmod(0o600)
    public_key.chmod(0o600)
    real_lstat = Path.lstat

    def trusted_lstat(path):
        result = real_lstat(path)
        if Path(path) in {trust_root, public_key} or Path(path) in trust_root.parents:
            values = list(result)
            values[4] = 0
            # Preserve symlink metadata so the production lstat boundary is
            # exercised, while making only this test fixture's real
            # directories look like deployment-owned root directories.
            if Path(path) != public_key and not stat.S_ISLNK(result.st_mode):
                values[0] = (values[0] & ~0o17777) | stat.S_IFDIR | 0o700
            return type(result)(values)
        return result

    monkeypatch.setattr(Path, "lstat", trusted_lstat)
    monkeypatch.setattr(store, "OWNER_AUTHORIZATION_TRUST_ROOT", trust_root)
    monkeypatch.setattr(store, "_verify_owner_signature", _production_verify_owner_signature)
    grant = _grant(grant_id="rsa-real")
    spec = OwnerExactPublicationAuthorizationSpec.model_validate(
        {
            "schema": "nexus.owner_exact_publication_authorization.v1",
            "authorization_id": f"auth-{grant.grant_hash}",
            "owner_id": grant.owner_id,
            "coordinator_id": grant.coordinator_id,
            "destination": grant.destination,
            "effect": grant.effect,
            "target": grant.target,
            "content_hash": grant.content_hash,
            "purpose": grant.purpose,
            "actor": grant.actor,
            "transport": grant.transport,
            "operation_id": grant.operation_id,
            "grant_hash": grant.grant_hash,
            "owner_key_id": "rsa",
            "owner_signature": "placeholder",
            "issued_at": NOW,
            "expires_at": grant.expires_at,
        }
    )
    payload = json.dumps(
        spec.model_dump(mode="json", exclude={"owner_signature"}),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    payload_path = tmp_path / "payload"
    signature_path = tmp_path / "signature"
    payload_path.write_bytes(payload)
    subprocess.run(
        [
            store.OPENSSL_BINARY,
            "dgst",
            "-sha256",
            "-sign",
            str(private_key),
            "-out",
            str(signature_path),
            str(payload_path),
        ],
        check=True,
    )
    auth = owner_issues_exact_publication_authorization(
        grant,
        issued_at=NOW,
        authority_root=grant_store.root,
        owner_key_id="rsa",
        owner_signature=base64.b64encode(signature_path.read_bytes()).decode(),
    )
    permit = consume_exact_owner_authorization(
        grant,
        owner_authorization=auth,
        authority_root=grant_store.root,
        standing_grant_path=standing_grant_path,
        requested_at=NOW,
    )
    assert permit["authorization_hash"] == auth.authorization_hash
    receipt = grant_store.issue(grant, issuance_permit=permit, requested_at=NOW)
    assert receipt.exists()
    prepared = publisher.prepare(_proposal(), grant)
    public_key.unlink()
    with pytest.raises(OwnerRepresentationBlocked, match="AUTHORIZATION"):
        publisher.publish(prepared)
    assert remote.writes == []
    subprocess.run(
        [store.OPENSSL_BINARY, "rsa", "-in", str(private_key), "-pubout", "-out", str(public_key)],
        check=True,
    )
    public_key.chmod(0o600)
    assert publisher.publish(prepared)["state"] == "COMPLETED"
    with pytest.raises(OwnerRepresentationBlocked, match="REPLAY_FORBIDDEN"):
        publisher.publish(prepared)
    assert len(remote.writes) == 1

    bad_auth = auth.model_copy(update={"owner_signature": base64.b64encode(b"wrong").decode()})
    with pytest.raises(OwnerRepresentationGrantBlocked, match="EXACT_OWNER_AUTHORIZATION_REJECTED"):
        store._verify_owner_signature(bad_auth)
    bad_grant = _grant(grant_id="rsa-bad-signature", operation_id="op-bad")
    with pytest.raises(OwnerRepresentationGrantBlocked, match="EXACT_OWNER_AUTHORIZATION_REJECTED"):
        owner_issues_exact_publication_authorization(
            bad_grant,
            issued_at=NOW,
            authority_root=grant_store.root,
            owner_key_id="rsa",
            owner_signature=base64.b64encode(b"wrong").decode(),
        )
    assert not (grant_store.root / "authorizations" / f"{bad_grant.grant_hash}.json").exists()

    # Every fixed trust-root ancestor is part of the security boundary.  A
    # writable ancestor owned by a non-root user must fail closed even when
    # the key and signature themselves are valid.
    def non_root_ancestor_lstat(path):
        result = trusted_lstat(path)
        if Path(path) == trust_root.parent:
            values = list(result)
            values[4] = os.geteuid() or 501
            values[0] = (values[0] & ~0o17777) | stat.S_IFDIR | 0o700
            return type(result)(values)
        return result

    monkeypatch.setattr(Path, "lstat", non_root_ancestor_lstat)
    with pytest.raises(OwnerRepresentationGrantBlocked, match="EXACT_OWNER_AUTHORIZATION_REJECTED"):
        store._verify_owner_signature(auth)


def test_mandatory_hostile_oracle_worker_cannot_mint_arbitrary_publication_without_owner_exact_authorization(
    grant_store, standing_grant_path, remote, publisher
):
    """Hostile oracle: Broad standing authority + worker-selected grant without
    exact Owner authorization MUST fail on the first attempt.
    """

    def valid_owner_standing_grant():
        # Broad standing grant with OWNER_REPRESENTATION_GRANT_ISSUE exists.
        receipt = _load_receipt_at(standing_grant_path, now=NOW)
        assert (
            AutonomyActionClass.OWNER_REPRESENTATION_GRANT_ISSUE in receipt.context.allowed_actions
        )
        return standing_grant_path

    def exact_owner_publication_authorization_exists() -> bool:
        auth_dir = grant_store.root / "authorizations"
        if not auth_dir.exists():
            return False
        return any(p.name.endswith(".json") for p in auth_dir.iterdir() if p.is_file())

    def worker_constructs_exact_publication_grant(**overrides):
        return _grant(**overrides)

    def mint_or_issue(grant, *, standing_authority):
        now = datetime.now(timezone.utc)
        permit = mint_owner_representation_publication_issuance_permit(
            grant,
            authority_root=grant_store.root,
            standing_grant_path=standing_authority,
            requested_at=now,
        )
        return grant_store.issue(grant, issuance_permit=permit, requested_at=now)

    def no_publication_permit_written() -> bool:
        permits_dir = grant_store.root / "permits"
        if not permits_dir.exists():
            return True
        records = [p for p in permits_dir.iterdir() if p.is_file() and p.name.endswith(".json")]
        return len(records) == 0

    def no_grant_receipt_written() -> bool:
        grants_dir = grant_store.root / "grants"
        if not grants_dir.exists():
            return True
        records = [p for p in grants_dir.iterdir() if p.is_file() and p.name.endswith(".json")]
        return len(records) == 0

    def no_remote_effect() -> bool:
        return len(remote.writes) == 0

    # 1. Broad standing authority exists.
    standing = valid_owner_standing_grant()

    # 2. No exact Owner publication decision exists.
    assert exact_owner_publication_authorization_exists() is False

    # 3. Worker invents publication A.
    grant_a = worker_constructs_exact_publication_grant()

    # 4. FIRST attempt must already fail.
    with pytest.raises(OwnerRepresentationGrantBlocked):
        mint_or_issue(grant_a, standing_authority=standing)

    assert no_publication_permit_written()
    assert no_grant_receipt_written()
    assert no_remote_effect()


def test_hostile_substitution_auth_a_grant_b_rejected(grant_store, standing_grant_path):
    """Owner authorizes publication A; worker tries to mint/issue publication B."""
    grant_a = _grant()
    grant_b = _grant(grant_id="g-827-diff", operation_id="op-diff")
    now = datetime.now(timezone.utc)
    auth_a = owner_issues_exact_publication_authorization(
        grant_a,
        issued_at=now,
        authority_root=grant_store.root,
    )
    with pytest.raises(OwnerRepresentationGrantBlocked) as exc:
        mint_owner_representation_publication_issuance_permit(
            grant_b,
            authority_root=grant_store.root,
            standing_grant_path=standing_grant_path,
            requested_at=now,
            owner_authorization=auth_a,
        )
    assert OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_MISMATCH.value in str(exc.value)


@pytest.mark.parametrize(
    "tamper_field,tamper_value",
    [
        ("content_hash", "a" * 64),
        ("target", "issue-999"),
        ("effect", ExternalPublicationEffect.COMMENT),
        ("purpose", "unauthorized purpose"),
        ("actor", "unauthorized_actor"),
        ("transport", "github_graphql"),
        ("operation_id", "op-tampered"),
    ],
)
def test_hostile_substitution_auth_a_tampered_field_rejected(
    grant_store, standing_grant_path, tamper_field, tamper_value
):
    """Any mutation between Owner authorization and publication grant fails fail-closed."""
    grant_a = _grant()
    now = datetime.now(timezone.utc)
    auth_a = owner_issues_exact_publication_authorization(
        grant_a,
        issued_at=now,
        authority_root=grant_store.root,
    )
    grant_tampered = _grant(**{tamper_field: tamper_value})
    with pytest.raises(OwnerRepresentationGrantBlocked) as exc:
        mint_owner_representation_publication_issuance_permit(
            grant_tampered,
            authority_root=grant_store.root,
            standing_grant_path=standing_grant_path,
            requested_at=now,
            owner_authorization=auth_a,
        )
    assert OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_MISMATCH.value in str(exc.value)


def test_hostile_replay_auth_a_rejected(grant_store, standing_grant_path):
    """Replaying exact Owner authorization A to mint a second permit fails fail-closed."""
    grant_a = _grant()
    now = datetime.now(timezone.utc)
    auth_a = owner_issues_exact_publication_authorization(
        grant_a,
        issued_at=now,
        authority_root=grant_store.root,
    )
    permit = consume_exact_owner_authorization(
        grant_a,
        owner_authorization=auth_a,
        authority_root=grant_store.root,
        standing_grant_path=standing_grant_path,
        requested_at=now,
    )
    assert permit is not None
    # If permit file is removed to simulate re-mint attempt, the consumed marker blocks it.
    permit_file = grant_store.root / "permits" / f"{permit['grant_receipt_hash']}.json"
    if permit_file.exists():
        permit_file.unlink()

    with pytest.raises(OwnerRepresentationGrantBlocked) as exc:
        consume_exact_owner_authorization(
            grant_a,
            owner_authorization=auth_a,
            authority_root=grant_store.root,
            standing_grant_path=standing_grant_path,
            requested_at=now,
        )
    assert OwnerRepresentationReason.EXACT_OWNER_AUTHORIZATION_CONSUMED.value in str(exc.value)


def test_positive_control_exact_owner_authorization_allows_a_once(
    grant_store, standing_grant_path, publisher, remote
):
    """Positive control: exact Owner authorization + exact matching publication
    succeeds once, and cannot be reused or replayed.
    """
    grant_a = _grant()
    now = datetime.now(timezone.utc)

    # 1. Owner issues exact publication authorization for A.
    auth_a = owner_issues_exact_publication_authorization(
        grant_a,
        issued_at=now,
        authority_root=grant_store.root,
    )
    assert exact_owner_publication_authorization_exists(
        grant_a.grant_hash, authority_root=grant_store.root
    )

    # 2. Worker consumes exact Owner authorization to mint permit.
    permit_a = consume_exact_owner_authorization(
        grant_a,
        owner_authorization=auth_a,
        authority_root=grant_store.root,
        standing_grant_path=standing_grant_path,
        requested_at=now,
    )
    assert permit_a["grant_hash"] == grant_a.grant_hash
    assert permit_a["authorization_id"] == auth_a.authorization_id
    assert permit_a["authorization_hash"] == auth_a.authorization_hash

    # Authorization is now consumed
    assert not exact_owner_publication_authorization_exists(
        grant_a.grant_hash, authority_root=grant_store.root
    )

    # 3. Store issues the durable receipt.
    receipt_path = grant_store.issue(grant_a, issuance_permit=permit_a, requested_at=now)
    assert receipt_path.exists()

    # 4. Publication succeeds exactly once.
    prepared = publisher.prepare(_proposal(), grant_a)
    record = publisher.publish(prepared)
    assert record["state"] == "COMPLETED"
    assert len(remote.writes) == 1

    # 5. Subsequent publication fails closed (REPLAY_FORBIDDEN).
    with pytest.raises(OwnerRepresentationBlocked) as exc:
        publisher.publish(prepared)
    assert OwnerRepresentationReason.REPLAY_FORBIDDEN.value in str(exc.value)
    assert len(remote.writes) == 1


def test_keyed_authority_rejects_simultaneous_path_and_key(
    grant_store, standing_grant_path
):
    """A keyed caller cannot fall back to an independently supplied path."""
    from nexus.orchestrator.standing_grant_store import StandingGrantKey

    grant = _grant(grant_id="key-selector", operation_id="op-key-selector")
    now = datetime.now(timezone.utc)
    owner_issues_exact_publication_authorization(
        grant, issued_at=now, authority_root=grant_store.root
    )
    key = StandingGrantKey(
        OWNER_REPRESENTATION_STANDING_REPOSITORY, "goal-827", "thread-coord-1"
    )
    with pytest.raises(OwnerRepresentationGrantBlocked, match="AMBIGUOUS_AUTHORITY_SELECTOR"):
        mint_owner_representation_publication_issuance_permit(
            grant,
            authority_root=grant_store.root,
            standing_grant_path=standing_grant_path,
            standing_grant_key=key,
            requested_at=now,
        )


def _keyed_receipt(
    *, repository: RepositoryIdentity, goal_id: str, thread_id: str, grant_id: str
) -> tuple[StandingGrantKey, StandingGrantReceipt]:
    context = StandingGrantContext.issue(
        owner_id="owner-james",
        coordinator_id="coordinator-codex",
        repository=repository,
        thread_id=thread_id,
        goal_id=goal_id,
        allowed_actions=(AutonomyActionClass.OWNER_REPRESENTATION_GRANT_ISSUE,),
        issued_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=1),
    )
    receipt = StandingGrantReceipt.issue(grant_id=grant_id, context=context)
    return standing_store_module.standing_grant_key(receipt), receipt


def _write_keyed_receipt(monkeypatch, root: Path, receipt: StandingGrantReceipt) -> Path:
    monkeypatch.setattr(standing_store_module, "DEFAULT_RECEIPT_PATH", root / "standing-grant.json")
    standing_store_module.write_keyed_standing_grant_receipt(receipt)
    return standing_store_module._keyed_receipt_path(
        standing_store_module.standing_grant_key(receipt)
    )


def test_keyed_owner_representation_full_chain_revalidates_exact_key_at_publication(
    grant_store, publisher, monkeypatch
):
    root = grant_store.root / "standing-authority"
    key_a, receipt_a = _keyed_receipt(
        repository=OWNER_REPRESENTATION_STANDING_REPOSITORY,
        goal_id="goal-key-a",
        thread_id="thread-key-a",
        grant_id="standing-key-a",
    )
    _write_keyed_receipt(monkeypatch, root, receipt_a)
    keyed_store = OwnerRepresentationGrantStore(root=grant_store.root, standing_grant_key=key_a)
    grant = _grant(
        grant_id="keyed-full-chain", operation_id="op-keyed-full-chain"
    )
    now = datetime.now(timezone.utc)
    auth = owner_issues_exact_publication_authorization(
        grant, issued_at=now, authority_root=grant_store.root
    )
    permit = consume_exact_owner_authorization(
        grant,
        owner_authorization=auth,
        authority_root=grant_store.root,
        standing_grant_key=key_a,
        requested_at=now,
    )
    keyed_store.issue(grant, issuance_permit=permit, requested_at=now)
    permit_path = grant_store.root / "permits" / f"{permit['grant_receipt_hash']}.json"
    record = json.loads(permit_path.read_text(encoding="utf-8"))
    assert record["standing_grant_key"] == key_a.digest
    assert record["permit_hash"] == canonical_autonomy_hash(
        {key: value for key, value in record.items() if key != "permit_hash"}
    )
    decision = keyed_store.authorize(
        grant.grant_hash,
        _proposal(operation_id=grant.operation_id),
        now=now + timedelta(minutes=1),
    )
    assert decision.publication_authorized is True


def test_keyed_owner_representation_rejects_key_substitution_and_ignores_corrupt_sibling(
    grant_store, monkeypatch
):
    root = grant_store.root / "standing-authority"
    key_a, receipt_a = _keyed_receipt(
        repository=OWNER_REPRESENTATION_STANDING_REPOSITORY,
        goal_id="goal-key-a2",
        thread_id="thread-key-a2",
        grant_id="standing-key-a2",
    )
    key_b, receipt_b = _keyed_receipt(
        repository=OWNER_REPRESENTATION_STANDING_REPOSITORY,
        goal_id="goal-key-b2",
        thread_id="thread-key-b2",
        grant_id="standing-key-b2",
    )
    _write_keyed_receipt(monkeypatch, root, receipt_a)
    _write_keyed_receipt(monkeypatch, root, receipt_b)
    grant = _grant(grant_id="keyed-substitution", operation_id="op-keyed-substitution")
    now = datetime.now(timezone.utc)
    auth = owner_issues_exact_publication_authorization(
        grant, issued_at=now, authority_root=grant_store.root
    )
    permit = consume_exact_owner_authorization(
        grant,
        owner_authorization=auth,
        authority_root=grant_store.root,
        standing_grant_key=key_a,
        requested_at=now,
    )
    store_b = OwnerRepresentationGrantStore(root=grant_store.root, standing_grant_key=key_b)
    with pytest.raises(OwnerRepresentationGrantBlocked):
        store_b.issue(grant, issuance_permit=permit, requested_at=now)
    store_a = OwnerRepresentationGrantStore(root=grant_store.root, standing_grant_key=key_a)
    store_a.issue(grant, issuance_permit=permit, requested_at=now)
    sibling = standing_store_module._keyed_receipt_path(key_b)
    sibling.write_text("corrupt", encoding="utf-8")
    decision = store_a.authorize(
        grant.grant_hash,
        _proposal(operation_id=grant.operation_id),
        now=now + timedelta(minutes=1),
    )
    assert decision.publication_authorized is True
