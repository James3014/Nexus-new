# ruff: noqa: E701
import hashlib
import plistlib
from pathlib import Path

import pytest

from nexus.contracts import gateway_deployment as contract
from nexus.contracts.gateway_deployment import (
    CURRENT_PROFILE,
    DESIRED_PROFILE,
    GATEWAY_LIFECYCLE_REVISION,
    HOST_AUTHORITY_BUNDLE_SCHEMA,
    HOST_AUTHORITY_BUNDLE_SCOPE,
    HOST_CARD_ID,
    HOST_CARD_PATH,
    HOST_CARD_SHA256,
    REPOSITORY,
    SOURCE_BASE_MERGE,
    SOURCE_BASE_TREE,
    AuthorityReceipt,
    ContractError,
    DeploymentProfile,
    DeploymentState,
    EffectClass,
    GatewayDeploymentRequest,
    GitIdentity,
    HostEffectAuthorityBundle,
    HostEffectAuthorityReceipt,
    IdentityEvidence,
    PostflightIdentity,
    QuiescenceEvidence,
    RollbackCapture,
    canonical_hash,
    select_host_effect_authority_receipt,
    transition,
    validate_authority_freshness,
    validate_current_identity,
    validate_host_effect_authority,
    validate_host_effect_authority_bundle,
    validate_profile,
    validate_request,
)


def _request():
    payload = plistlib.dumps(
        {
            "Label": "com.nexus.mcp.gateway.direct",
            "RunAtLoad": True,
            "KeepAlive": True,
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
        lifecycle=GATEWAY_LIFECYCLE_REVISION,
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
        GATEWAY_LIFECYCLE_REVISION,
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
        host_card_sha256="f4c581f0062c6b3d65c9ca8f7029a96caa76b2e35d95cc6bccae874c0945f514",
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


def _bundle_fixture(*, revoked=False, child_revoked=False):
    base = _request().host_authority
    children = []
    for operation, effect, suffix in (
        ("install-artifact", EffectClass.INSTALL_ARTIFACT, "install"),
        ("reload", EffectClass.GATEWAY_RELOAD, "reload"),
        ("rollback", EffectClass.GATEWAY_ROLLBACK, "rollback"),
    ):
        child = HostEffectAuthorityReceipt(**{
            **base.__dict__,
            "operation": operation,
            "effect_class": effect,
            "receipt_id": f"bundle-{suffix}",
            "request_id": f"bundle-request-{suffix}",
            "idempotency_fence": f"bundle-fence-{suffix}",
            "revocation_state": "REVOKED"
            if (child_revoked and suffix == "reload")
            else "NOT_REVOKED",
            "revoked_at": "2026-08-23T00:00:00Z"
            if (child_revoked and suffix == "reload")
            else None,
            "revocation_reason": "owner" if (child_revoked and suffix == "reload") else None,
        })
        child = HostEffectAuthorityReceipt(**{
            **child.__dict__,
            "receipt_hash": canonical_hash({
                k: v for k, v in child.__dict__.items() if k != "receipt_hash"
            }),
        })
        children.append(child)
    bundle = HostEffectAuthorityBundle(
        schema=HOST_AUTHORITY_BUNDLE_SCHEMA,
        bundle_version=1,
        bundle_id="bundle-fixture",
        bundle_hash="0" * 64,
        scope=HOST_AUTHORITY_BUNDLE_SCOPE,
        repository=REPOSITORY,
        host_card_path=HOST_CARD_PATH,
        host_card_id=HOST_CARD_ID,
        host_card_sha256=HOST_CARD_SHA256,
        source_base_merge=SOURCE_BASE_MERGE,
        source_base_tree=SOURCE_BASE_TREE,
        correction_merge_sha="1" * 40,
        correction_tree_sha="2" * 40,
        independent_acceptance_receipt_hash="3" * 64,
        final_manager_sha256="4" * 64,
        current_main_sha="5" * 40,
        issued_at="2026-08-22T00:00:00Z",
        expires_at="2026-08-24T00:00:00Z",
        revocation_state="REVOKED" if revoked else "NOT_REVOKED",
        revoked_at="2026-08-23T00:00:00Z" if revoked else None,
        revocation_reason="owner" if revoked else None,
        receipts=tuple(children),
    )
    return HostEffectAuthorityBundle(**{
        **bundle.__dict__,
        "bundle_hash": canonical_hash({
            k: v for k, v in bundle.__dict__.items() if k != "bundle_hash"
        }),
    })


def test_host_card_sha256_matches_tracked_authority_card():
    card_path = Path(__file__).resolve().parents[2] / HOST_CARD_PATH
    assert hashlib.sha256(card_path.read_bytes()).hexdigest() == (
        "f4c581f0062c6b3d65c9ca8f7029a96caa76b2e35d95cc6bccae874c0945f514"
    )
    assert HOST_CARD_SHA256 == ("f4c581f0062c6b3d65c9ca8f7029a96caa76b2e35d95cc6bccae874c0945f514")


@pytest.mark.parametrize("scope", ["child", "bundle"])
def test_stale_host_card_sha256_is_rejected_after_rehashing(scope):
    stale_sha256 = "fcd22da4ef92b7cde004523fe900c06bc1b9e67715049c95383c581e640f631f"
    valid_bundle = _bundle_fixture()

    def rehash_receipt(receipt):
        return HostEffectAuthorityReceipt(**{
            **receipt.__dict__,
            "receipt_hash": canonical_hash({
                k: v for k, v in receipt.__dict__.items() if k != "receipt_hash"
            }),
        })

    if scope == "child":
        stale_child = rehash_receipt(
            HostEffectAuthorityReceipt(**{
                **valid_bundle.receipts[1].__dict__,
                "host_card_sha256": stale_sha256,
            })
        )
        receipts = (valid_bundle.receipts[0], stale_child, valid_bundle.receipts[2])
        altered = HostEffectAuthorityBundle(**{**valid_bundle.__dict__, "receipts": receipts})
    else:
        receipts = tuple(
            rehash_receipt(
                HostEffectAuthorityReceipt(**{
                    **receipt.__dict__,
                    "host_card_sha256": stale_sha256,
                })
            )
            for receipt in valid_bundle.receipts
        )
        altered = HostEffectAuthorityBundle(**{
            **valid_bundle.__dict__,
            "host_card_sha256": stale_sha256,
            "receipts": receipts,
        })

    altered = HostEffectAuthorityBundle(**{
        **altered.__dict__,
        "bundle_hash": canonical_hash({
            k: v for k, v in altered.__dict__.items() if k != "bundle_hash"
        }),
    })

    with pytest.raises(
        ContractError,
        match="host authority.*(host_card_sha256|provenance) mismatch",
    ):
        validate_host_effect_authority_bundle(altered)


@pytest.mark.parametrize("field", ["current_profile_hash", "desired_profile_hash"])
def test_standalone_bundle_binds_frozen_profile_hashes(field):
    bundle = _bundle_fixture()
    assert validate_host_effect_authority(bundle.receipts[1])
    assert validate_host_effect_authority_bundle(bundle) == bundle

    altered_child = HostEffectAuthorityReceipt(**{
        **bundle.receipts[1].__dict__,
        field: "a" * 64,
    })
    altered_child = HostEffectAuthorityReceipt(**{
        **altered_child.__dict__,
        "receipt_hash": canonical_hash({
            k: v for k, v in altered_child.__dict__.items() if k != "receipt_hash"
        }),
    })
    receipts = tuple(
        altered_child if i == 1 else receipt for i, receipt in enumerate(bundle.receipts)
    )
    altered_bundle = HostEffectAuthorityBundle(**{**bundle.__dict__, "receipts": receipts})
    altered_bundle = HostEffectAuthorityBundle(**{
        **altered_bundle.__dict__,
        "bundle_hash": canonical_hash({
            k: v for k, v in altered_bundle.__dict__.items() if k != "bundle_hash"
        }),
    })

    with pytest.raises(ContractError, match=f"host authority {field} mismatch"):
        validate_host_effect_authority(altered_child)
    with pytest.raises(ContractError, match=f"host authority {field} mismatch"):
        validate_host_effect_authority_bundle(altered_bundle)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("revoked_at", "2026-08-23T00:00:01Z"),
        ("revocation_reason", "reviewer"),
    ],
)
def test_revoked_child_fields_must_equal_bundle(field, replacement):
    bundle = _bundle_fixture(revoked=True, child_revoked=True)
    index = next(i for i, receipt in enumerate(bundle.receipts) if receipt.operation == "reload")
    child = HostEffectAuthorityReceipt(**{
        **bundle.receipts[index].__dict__,
        field: replacement,
    })
    child = HostEffectAuthorityReceipt(**{
        **child.__dict__,
        "receipt_hash": canonical_hash({
            k: v for k, v in child.__dict__.items() if k != "receipt_hash"
        }),
    })
    receipts = tuple(child if i == index else receipt for i, receipt in enumerate(bundle.receipts))
    altered = HostEffectAuthorityBundle(**{**bundle.__dict__, "receipts": receipts})
    altered = HostEffectAuthorityBundle(**{
        **altered.__dict__,
        "bundle_hash": canonical_hash({
            k: v for k, v in altered.__dict__.items() if k != "bundle_hash"
        }),
    })

    with pytest.raises(ContractError, match="revoked child fields mismatch"):
        validate_host_effect_authority_bundle(altered)


def test_bundle_is_exactly_ordered_three_child_hash_sealed():
    bundle = _bundle_fixture()
    assert tuple(child.operation for child in bundle.receipts) == (
        "install-artifact",
        "reload",
        "rollback",
    )
    assert validate_host_effect_authority_bundle(bundle) == bundle
    reordered = HostEffectAuthorityBundle(**{
        **bundle.__dict__,
        "receipts": tuple(reversed(bundle.receipts)),
    })
    with pytest.raises(ContractError):
        validate_host_effect_authority_bundle(reordered)
    with pytest.raises(ContractError):
        HostEffectAuthorityBundle.model_validate({**bundle.model_dump(), "extra": True})


@pytest.mark.parametrize(
    "mutation",
    [
        lambda b: b.receipts[:2],
        lambda b: b.receipts + (b.receipts[0],),
        lambda b: tuple(
            HostEffectAuthorityReceipt(**{**b.receipts[0].__dict__, "operation": "install"})
            if i == 0
            else r
            for i, r in enumerate(b.receipts)
        ),
    ],
)
def test_bundle_missing_extra_alias_children_fail_closed(mutation):
    bundle = _bundle_fixture()
    altered = HostEffectAuthorityBundle(**{**bundle.__dict__, "receipts": mutation(bundle)})
    with pytest.raises(ContractError):
        validate_host_effect_authority_bundle(altered)


def test_bundle_duplicate_ids_requests_and_fences_are_rejected():
    bundle = _bundle_fixture()
    duplicate = HostEffectAuthorityReceipt(**{
        **bundle.receipts[1].__dict__,
        "receipt_id": bundle.receipts[0].receipt_id,
        "receipt_hash": "0" * 64,
    })
    duplicate = HostEffectAuthorityReceipt(**{
        **duplicate.__dict__,
        "receipt_hash": canonical_hash({
            k: v for k, v in duplicate.__dict__.items() if k != "receipt_hash"
        }),
    })
    altered = HostEffectAuthorityBundle(**{
        **bundle.__dict__,
        "receipts": (bundle.receipts[0], duplicate, bundle.receipts[2]),
    })
    with pytest.raises(ContractError, match="duplicate receipt"):
        validate_host_effect_authority_bundle(altered)


def test_revoked_bundle_parses_as_evidence_but_never_selects():
    bundle = _bundle_fixture(revoked=True, child_revoked=True)
    assert validate_host_effect_authority_bundle(bundle).revocation_state == "REVOKED"
    request = _request()
    with pytest.raises(ContractError, match="revoked"):
        select_host_effect_authority_receipt(bundle, request, now="2026-08-23T00:00:00Z")


@pytest.mark.parametrize(
    "now",
    [
        pytest.param("2026-08-21T00:00:00Z", id="stale"),
        pytest.param("2026-08-25T00:00:00Z", id="future"),
    ],
)
def test_bundle_selection_rejects_future_or_stale_validity(now):
    bundle = _bundle_fixture()
    request = _request()
    child = bundle.receipts[1]
    values = {
        **request.__dict__,
        "request_id": child.request_id,
        "idempotency_fence": child.idempotency_fence,
        "host_authority": child,
        "operation": "reload",
        "effect_class": EffectClass.GATEWAY_RELOAD,
    }
    values["request_hash"] = canonical_hash({
        k: v for k, v in values.items() if k not in {"request_hash", "schema"}
    })
    with pytest.raises(ContractError):
        select_host_effect_authority_receipt(bundle, GatewayDeploymentRequest(**values), now=now)


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


def test_host_receipt_version_is_exactly_one():
    request = _request()
    altered = request.host_authority.__class__(**{
        **request.host_authority.__dict__,
        "receipt_version": 2,
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
    with pytest.raises(ContractError, match="schema/version"):
        validate_request(request.__class__(**values))


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


def test_dirty_current_profile_roundtrip_is_frozen_and_only_rollback_profile():
    roundtrip = DeploymentProfile.model_validate(CURRENT_PROFILE.model_dump())
    assert roundtrip == CURRENT_PROFILE
    assert validate_profile(roundtrip) == CURRENT_PROFILE
    dirty_desired = DeploymentProfile.model_validate({
        **DESIRED_PROFILE.model_dump(),
        "git": {**DESIRED_PROFILE.git.model_dump(), "clean": False},
    })
    with pytest.raises(ContractError):
        validate_profile(dirty_desired)
    arbitrary_dirty = DeploymentProfile.model_validate({
        **CURRENT_PROFILE.model_dump(),
        "git": {
            **CURRENT_PROFILE.git.model_dump(),
            "root": "/tmp/foreign",
            "toplevel": "/tmp/foreign",
        },
    })
    with pytest.raises(ContractError):
        validate_profile(arbitrary_dirty)


def _exact_wrapper_payload():
    return plistlib.dumps(
        {
            "Label": contract.LABEL,
            "ProgramArguments": ["/bin/zsh", "-c", contract.CURRENT_WRAPPER_COMMAND],
            "RunAtLoad": True,
            "KeepAlive": True,
            "WorkingDirectory": contract.CURRENT_ROOT,
            "StandardOutPath": contract.STDOUT,
            "StandardErrorPath": contract.STDERR,
        },
        fmt=plistlib.FMT_XML,
        sort_keys=False,
    )


def _request_with_rollback_payload(payload):
    request = _request()
    parsed = plistlib.loads(payload)
    digest = hashlib.sha256(payload).hexdigest()
    rollback = RollbackCapture(**{
        **request.rollback.__dict__,
        "plist_sha256": digest,
        "plist_bytes_sha256": digest,
        "plist_bytes_hex": payload.hex(),
        "program_arguments_hash": canonical_hash(parsed.get("ProgramArguments")),
        "environment_hash": canonical_hash(parsed.get("EnvironmentVariables")),
    })
    current_identity = IdentityEvidence(**{
        **request.current_identity.__dict__,
        "plist_sha256": digest,
        "plist_bytes_sha256": digest,
    })
    values = {**request.__dict__, "rollback": rollback, "current_identity": current_identity}
    values["request_hash"] = canonical_hash({
        key: value for key, value in values.items() if key not in {"request_hash", "schema"}
    })
    return GatewayDeploymentRequest(**values)


def test_exact_current_wrapper_bytes_are_the_only_wrapper_rollback_identity():
    payload = _exact_wrapper_payload()
    assert hashlib.sha256(payload).hexdigest() == contract.CURRENT_WRAPPER_PLIST_SHA256
    assert validate_request(_request_with_rollback_payload(payload)).rollback.plist_bytes_hex


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(
            lambda value: value["ProgramArguments"].__setitem__(0, "/bin/bash"), id="shell"
        ),
        pytest.param(
            lambda value: value["ProgramArguments"].__setitem__(
                2, value["ProgramArguments"][2].replace(contract.ENV_FILE, "/tmp/evil.env")
            ),
            id="env-file",
        ),
        pytest.param(
            lambda value: value["ProgramArguments"].__setitem__(
                2,
                value["ProgramArguments"][2].replace(
                    "PYTHONDONTWRITEBYTECODE=1", "PYTHONDONTWRITEBYTECODE=0"
                ),
            ),
            id="export",
        ),
        pytest.param(
            lambda value: value["ProgramArguments"].__setitem__(
                2, value["ProgramArguments"][2].replace(contract.CURRENT_ROOT, "/tmp/foreign", 1)
            ),
            id="root",
        ),
        pytest.param(
            lambda value: value["ProgramArguments"].__setitem__(
                2, value["ProgramArguments"][2].replace(contract.STATE_DIR, "/tmp/state")
            ),
            id="state",
        ),
        pytest.param(
            lambda value: value["ProgramArguments"].__setitem__(
                2, value["ProgramArguments"][2].replace(contract.INTERPRETER, "/tmp/python")
            ),
            id="interpreter",
        ),
        pytest.param(
            lambda value: value["ProgramArguments"].__setitem__(
                2, value["ProgramArguments"][2].replace(contract.ENTRYPOINT, "scripts/ops/other.py")
            ),
            id="entrypoint",
        ),
        pytest.param(lambda value: value.__setitem__("ThrottleInterval", 1), id="extra-field"),
        pytest.param(lambda value: value.__setitem__("RunAtLoad", False), id="run-at-load"),
        pytest.param(lambda value: value.__setitem__("KeepAlive", False), id="keep-alive"),
    ],
)
def test_current_wrapper_semantic_mutation_matrix_rejects_rehashed_payload(mutation):
    parsed = plistlib.loads(_exact_wrapper_payload())
    mutation(parsed)
    payload = plistlib.dumps(parsed, fmt=plistlib.FMT_XML, sort_keys=False)
    with pytest.raises(ContractError):
        validate_request(_request_with_rollback_payload(payload))


def test_current_wrapper_byte_mutation_rejects_even_when_plist_semantics_match():
    with pytest.raises(ContractError, match="legacy rollback wrapper hash mismatch"):
        validate_request(_request_with_rollback_payload(_exact_wrapper_payload() + b"\n"))


def test_direct_rollback_rejects_foreign_entrypoint_with_matching_suffix():
    request = _request()
    parsed = plistlib.loads(bytes.fromhex(request.rollback.plist_bytes_hex))
    parsed["ProgramArguments"][1] = "/tmp/foreign/" + contract.ENTRYPOINT
    payload = plistlib.dumps(parsed, fmt=plistlib.FMT_XML)
    with pytest.raises(ContractError, match="rollback program arguments mismatch"):
        validate_request(_request_with_rollback_payload(payload))


def test_gateway_lifecycle_revision_cannot_be_substituted_by_quiescence_state():
    request = _request()
    postflight = PostflightIdentity(**{
        **request.postflight.__dict__,
        "lifecycle": request.quiescence.lifecycle_state,
    })
    values = {**request.__dict__, "postflight": postflight}
    values["request_hash"] = canonical_hash({
        key: value for key, value in values.items() if key not in {"request_hash", "schema"}
    })
    with pytest.raises(ContractError, match="action/task/lifecycle mismatch"):
        validate_request(GatewayDeploymentRequest(**values))


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("repository", "Other/Repository"),
        ("host_card_path", "tasks/other.md"),
        ("host_card_id", "TASK-OTHER"),
        ("host_card_sha256", "a" * 64),
        ("source_base_merge", "a" * 40),
        ("source_base_tree", "b" * 40),
        ("correction_merge_sha", "c" * 40),
        ("correction_tree_sha", "d" * 40),
        ("independent_acceptance_receipt_hash", "e" * 64),
        ("final_manager_sha256", "f" * 64),
        ("current_main_sha", "9" * 40),
    ],
)
def test_every_shared_bundle_child_provenance_mutation_rejects_after_full_rehash(
    field, replacement
):
    bundle = _bundle_fixture()
    child = HostEffectAuthorityReceipt(**{
        **bundle.receipts[1].__dict__,
        field: replacement,
    })
    child = HostEffectAuthorityReceipt(**{
        **child.__dict__,
        "receipt_hash": canonical_hash({
            key: value for key, value in child.__dict__.items() if key != "receipt_hash"
        }),
    })
    altered = HostEffectAuthorityBundle(**{
        **bundle.__dict__,
        "receipts": (bundle.receipts[0], child, bundle.receipts[2]),
    })
    altered = HostEffectAuthorityBundle(**{
        **altered.__dict__,
        "bundle_hash": canonical_hash({
            key: value for key, value in altered.__dict__.items() if key != "bundle_hash"
        }),
    })
    with pytest.raises(ContractError, match="child 1 provenance mismatch"):
        validate_host_effect_authority_bundle(altered)


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
