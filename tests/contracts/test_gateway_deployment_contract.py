# ruff: noqa: E701
import hashlib
import plistlib

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
    PostflightIdentity,
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
    payload = plistlib.dumps(
        {
            "Label": "com.nexus.mcp.gateway.direct",
            "ProgramArguments": [
                "/Users/jameschen/Workspace/Nexus-new/.venv/bin/python",
                CURRENT_PROFILE.git.root + "/scripts/ops/nexus_mcp_gateway_http.py",
            ],
            "WorkingDirectory": CURRENT_PROFILE.git.root,
            "StandardOutPath": "/Users/jameschen/Library/Logs/Nexus/gateway.log",
            "StandardErrorPath": "/Users/jameschen/Library/Logs/Nexus/gateway.err.log",
            "EnvironmentVariables": {"NEXUS_MCP_GATEWAY_TOKEN": "${NEXUS_MCP_GATEWAY_TOKEN}"},
        },
        fmt=plistlib.FMT_XML,
    )
    plist_hash = hashlib.sha256(payload).hexdigest()
    args = [
        "/Users/jameschen/Workspace/Nexus-new/.venv/bin/python",
        CURRENT_PROFILE.git.root + "/scripts/ops/nexus_mcp_gateway_http.py",
    ]
    env = {"NEXUS_MCP_GATEWAY_TOKEN": "${NEXUS_MCP_GATEWAY_TOKEN}"}
    rollback = RollbackCapture(
        plist_hash,
        plist_hash,
        payload.hex(),
        "b" * 64,
        "c" * 64,
        True,
        server_instance="old",
        source_root=CURRENT_PROFILE.git.root,
        source_head=CURRENT_PROFILE.git.head,
        source_tree=CURRENT_PROFILE.git.tree,
        root=CURRENT_PROFILE.git.root,
        program_arguments_hash=canonical_hash(args),
        environment_hash=canonical_hash(env),
    )
    receipt = AuthorityReceipt(
        "owner",
        "receipt",
        issued_at="2026-08-22T00:00:00Z",
        expires_at="2026-08-24T00:00:00Z",
        request_id="r-526",
    )
    receipt = AuthorityReceipt(**{
        **receipt.__dict__,
        "receipt_hash": canonical_hash({
            k: v for k, v in receipt.__dict__.items() if k != "receipt_hash"
        }),
    })
    ident = IdentityEvidence(
        plist_sha256=plist_hash,
        plist_bytes_sha256=plist_hash,
        pid=123,
        server_instance="old",
        root=CURRENT_PROFILE.git.root,
        head=CURRENT_PROFILE.git.head,
        tree=CURRENT_PROFILE.git.tree,
        source_sha256="b" * 64,
        tool_manifest_sha256="c" * 64,
        schema_sha256="d" * 64,
        permission_sha256="e" * 64,
        action="gateway-rebind",
        task_id="TASK-526-A",
        lifecycle="QUIESCENT",
        loaded=True,
        client_bound=True,
    )
    post = PostflightIdentity(
        "new",
        DESIRED_PROFILE.git.root,
        DESIRED_PROFILE.git.head,
        DESIRED_PROFILE.git.tree,
        "f" * 64,
        "a" * 64,
        "b" * 64,
        "gateway-rebind",
        "TASK-526-A",
        "QUIESCENT",
        True,
        ("gateway-rebind",),
        ("gateway-rebind",),
        True,
    )
    values = dict(
        request_id="r-526",
        idempotency_fence="f-526",
        operation="reload",
        authority=receipt,
        current=CURRENT_PROFILE,
        desired=DESIRED_PROFILE,
        current_identity=ident,
        rollback=rollback,
        quiescence=QuiescenceEvidence(
            "reconciled", "QUIESCENT", "QUIESCENT", "1" * 64, (), "reacq"
        ),
        postflight=post,
        effect_class=EffectClass.GATEWAY_RELOAD,
        stable_artifact=None,
    )
    values["request_hash"] = canonical_hash(values)
    return GatewayDeploymentRequest(**values)


def test_frozen_profiles_are_explicit_and_valid():
    assert CURRENT_PROFILE.git.head != DESIRED_PROFILE.git.head
    assert validate_profile(CURRENT_PROFILE) == CURRENT_PROFILE
    assert validate_profile(DESIRED_PROFILE) == DESIRED_PROFILE


def test_request_hash_and_rollback_are_bound():
    assert validate_request(_request()).operation == "reload"
    request = _request()
    with pytest.raises(ContractError):
        validate_request(request.__class__(**{**request.__dict__, "request_hash": "0" * 64}))


def test_rollback_plist_hashes_both_bind_to_bytes():
    request = _request()
    bad = request.rollback.__class__(**{**request.rollback.__dict__, "plist_sha256": "0" * 64})
    values = {**request.__dict__, "rollback": bad}
    values["request_hash"] = canonical_hash({
        k: v for k, v in values.items() if k not in {"request_hash", "schema"}
    })
    with pytest.raises(ContractError):
        validate_request(request.__class__(**values))


@pytest.mark.parametrize(
    "previous,current",
    [
        ("REQUESTED", "STARTED"),
        ("PREFLIGHTED", "VERIFIED"),
        ("VERIFIED", "STARTED"),
        ("CLIENT_BOUND", "VERIFIED"),
    ],
)
def test_invalid_state_transitions_fail_closed(previous, current):
    if (previous, current) == ("CLIENT_BOUND", "VERIFIED"):
        assert transition(previous, current) is DeploymentState.VERIFIED
    else:
        with pytest.raises(ContractError):
            transition(previous, current)


def test_unknown_fields_cannot_become_typed_request():
    with pytest.raises(ContractError):
        validate_request({"request_id": "r"})


def test_wrong_profile_identity_rejected():
    bad = DeploymentProfile(
        GitIdentity(
            DESIRED_PROFILE.git.root,
            DESIRED_PROFILE.git.toplevel,
            "0" * 39,
            DESIRED_PROFILE.git.tree,
        )
    )
    with pytest.raises(ContractError):
        validate_profile(bad)


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
    receipt = AuthorityReceipt(
        "owner", "receipt", issued_at="2026-08-22T00:00:00Z", expires_at="2026-08-24T00:00:00Z"
    )
    assert validate_authority_freshness(receipt, now="2026-08-23T00:00:00Z") == receipt
    with pytest.raises(ContractError):
        validate_authority_freshness(receipt, now="2026-08-25T00:00:00Z")


def test_authority_rejects_empty_future_malformed_and_substituted_receipts():
    receipt = AuthorityReceipt(
        "owner", "receipt", issued_at="2026-08-22T00:00:00Z", expires_at="2026-08-24T00:00:00Z"
    )
    for now in ("", "2026-08-21T00:00:00Z", "2026-08-25T00:00:00Z", "not-a-time"):
        with pytest.raises(ContractError):
            validate_authority_freshness(receipt, now=now)


def test_postflight_schema_is_extra_forbid_and_complete():
    with pytest.raises(ContractError):
        PostflightIdentity.model_validate({"server_instance": "x"})
    with pytest.raises(ContractError):
        PostflightIdentity.model_validate({
            **_request().postflight.model_dump(),
            "unexpected": True,
        })


def test_profile_full_identity_substitution_is_rejected():
    altered = DeploymentProfile(
        CURRENT_PROFILE.git,
        entrypoint_sha256="0" * 64,
        trust_class=CURRENT_PROFILE.trust_class,
    )
    with pytest.raises(ContractError):
        validate_profile(altered)
