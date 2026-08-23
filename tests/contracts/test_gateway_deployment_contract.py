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
    HostEffectAuthorityReceipt,
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
    host = HostEffectAuthorityReceipt(
        schema="nexus.gateway.host_effect_authority.v1",
        receipt_version=1,
        receipt_id="host-receipt",
        receipt_hash="0" * 64,
        scope="NEXUS_GATEWAY_REBIND_HOST_EFFECT_ONLY",
        issuer_id="owner-james",
        coordinator_id="coordinator-codex",
        authorized_actor_id="coordinator-codex",
        owner_activation_id="OWNER_ISSUE526_CONTINUE_20260823",
        owner_activation_sha256="f0ed77ffe3872b083ef0b6d66526524a7091a8e3125322c84ba632f3c64ba322",
        source_thread="01a02a17-691c-7a20-ad0f-9166456416dc",
        standing_grant_id="OWNER_STANDING_COORDINATOR_20260818_DURABLE_GITHUB_WORKFLOW",
        standing_grant_receipt_sha256="3b8895f093692257d6225fbb8150b34f520e667d250c7817ad120cefd42751d5",
        source_base_merge="ac4a9ab1e0180170ca062cdc81f2142bca8bd80f",
        source_base_tree="db329f4931b55b74f1e1f9fe61f7edf4ca8422bc",
        correction_merge_sha="1" * 40,
        correction_tree_sha="2" * 40,
        independent_acceptance_receipt_hash="3" * 64,
        final_manager_sha256="4" * 64,
        current_main_sha="5" * 40,
        host_card_path="tasks/github-issue-526-host-authority-and-canary-20260823/01-gateway-host-local-canary.md",
        host_card_id="TASK-526-HOST-1",
        host_card_sha256="b6e0c0015b1098261622b7ea087869eca5e0c80a6a1d3071815aa19e520ca7b1",
        repository="James3014/Nexus-new",
        operation="reload",
        effect_class=EffectClass.GATEWAY_RELOAD,
        service_label="com.nexus.mcp.gateway.direct",
        plist_path="/Users/jameschen/Library/LaunchAgents/com.nexus.mcp.gateway.direct.plist",
        endpoint="http://127.0.0.1:8766",
        current_profile_hash=canonical_hash(CURRENT_PROFILE),
        desired_profile_hash=canonical_hash(DESIRED_PROFILE),
        request_id="r-526",
        idempotency_fence="f-526",
        issued_at="2026-08-22T00:00:00Z",
        expires_at="2026-08-24T00:00:00Z",
        revocation_state="NOT_REVOKED",
        revoked_at=None,
        revocation_reason=None,
    )
    host = HostEffectAuthorityReceipt(**{
        **host.__dict__,
        "receipt_hash": canonical_hash({
            k: v for k, v in host.__dict__.items() if k != "receipt_hash"
        }),
    })
    values["host_authority"] = host
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


def test_source_provenance_alone_can_never_validate_as_host_request():
    request = _request()
    values = {**request.__dict__, "host_authority": None}
    values["request_hash"] = canonical_hash({
        key: value for key, value in values.items() if key not in {"request_hash", "schema"}
    })
    with pytest.raises(ContractError, match="host-effect authority"):
        validate_request(GatewayDeploymentRequest(**values))


def test_host_receipt_is_strictly_bound_to_operation_and_fence():
    request = _request()
    altered = request.host_authority.__class__(**{
        **request.host_authority.__dict__,
        "idempotency_fence": "other-fence",
    })
    altered = altered.__class__(**{
        **altered.__dict__,
        "receipt_hash": canonical_hash({
            key: value for key, value in altered.__dict__.items() if key != "receipt_hash"
        }),
    })
    values = {**request.__dict__, "host_authority": altered}
    values["request_hash"] = canonical_hash({
        key: value for key, value in values.items() if key not in {"request_hash", "schema"}
    })
    with pytest.raises(ContractError, match="request/fence"):
        validate_request(GatewayDeploymentRequest(**values))


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
