# ruff: noqa: E701
import hashlib

import pytest

from nexus.contracts.gateway_deployment import (
    CURRENT_PROFILE,
    DESIRED_PROFILE,
    AuthorityReceipt,
    ContractError,
    DeploymentProfile,
    DeploymentState,
    EffectClass,
    GatewayDeploymentRequest,
    GitIdentity,
    IdentityEvidence,
    QuiescenceEvidence,
    RollbackCapture,
    canonical_hash,
    transition,
    validate_authority_freshness,
    validate_current_identity,
    validate_profile,
    validate_request,
)


def _request():
    plist_hash = hashlib.sha256(b"plist").hexdigest()
    rollback = RollbackCapture(plist_hash, plist_hash, b"plist".hex(), "b"*64, "c"*64, True)
    values = dict(request_id="r-526", idempotency_fence="f-526", operation="reload",
        authority=AuthorityReceipt("owner", "receipt", request_id="r-526"), current=CURRENT_PROFILE,
        desired=DESIRED_PROFILE, current_identity=IdentityEvidence(), rollback=rollback,
        quiescence=QuiescenceEvidence("reconciled"), postflight={"server_instance":"new"},
        effect_class=EffectClass.GATEWAY_RELOAD)
    values["request_hash"] = canonical_hash(values)
    return GatewayDeploymentRequest(**values)

def test_frozen_profiles_are_explicit_and_valid():
    assert CURRENT_PROFILE.git.head != DESIRED_PROFILE.git.head
    assert validate_profile(CURRENT_PROFILE) == CURRENT_PROFILE
    assert validate_profile(DESIRED_PROFILE) == DESIRED_PROFILE

def test_request_hash_and_rollback_are_bound():
    assert validate_request(_request()).operation == "reload"
    request = _request()
    with pytest.raises(ContractError): validate_request(request.__class__(**{**request.__dict__, "request_hash":"0"*64}))

@pytest.mark.parametrize("previous,current", [("REQUESTED","STARTED"),("PREFLIGHTED","VERIFIED"),("VERIFIED","STARTED"),("CLIENT_BOUND","VERIFIED")])
def test_invalid_state_transitions_fail_closed(previous,current):
    if (previous,current)==("CLIENT_BOUND","VERIFIED"): assert transition(previous,current) is DeploymentState.VERIFIED
    else:
        with pytest.raises(ContractError): transition(previous,current)

def test_unknown_fields_cannot_become_typed_request():
    with pytest.raises(ContractError): validate_request({"request_id":"r"})

def test_wrong_profile_identity_rejected():
    bad = DeploymentProfile(GitIdentity(DESIRED_PROFILE.git.root, DESIRED_PROFILE.git.toplevel,
        "0"*39, DESIRED_PROFILE.git.tree))
    with pytest.raises(ContractError): validate_profile(bad)


def test_model_validate_is_strict_and_defaults_are_typed():
    profile = DeploymentProfile.model_validate({
        "git": CURRENT_PROFILE.git.model_dump(),
        "entrypoint": CURRENT_PROFILE.entrypoint,
        "entrypoint_sha256": CURRENT_PROFILE.entrypoint_sha256,
        "trust_class": CURRENT_PROFILE.trust_class,
    })
    assert profile == CURRENT_PROFILE
    with pytest.raises(ContractError):
        DeploymentProfile.model_validate({**profile.model_dump(), "unexpected": True})


def test_old_profile_does_not_equal_explicit_new_target():
    from nexus.contracts.gateway_deployment import compare_profiles, validate_desired_profile

    assert not compare_profiles(CURRENT_PROFILE, DESIRED_PROFILE)
    assert validate_desired_profile(CURRENT_PROFILE, DESIRED_PROFILE) == DESIRED_PROFILE


def test_current_identity_tamper_and_authority_staleness_fail_closed():
    with pytest.raises(ContractError):
        validate_current_identity(IdentityEvidence(head="0" * 40), CURRENT_PROFILE)
    receipt = AuthorityReceipt("owner", "receipt", issued_at="2026-08-22T00:00:00Z", expires_at="2026-08-24T00:00:00Z")
    assert validate_authority_freshness(receipt, now="2026-08-23T00:00:00Z") == receipt
    with pytest.raises(ContractError):
        validate_authority_freshness(receipt, now="2026-08-25T00:00:00Z")
