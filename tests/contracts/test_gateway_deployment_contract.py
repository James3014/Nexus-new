# ruff: noqa: E701
import hashlib
import plistlib
from pathlib import Path

import pytest

from nexus.contracts import gateway_deployment as contract
from nexus.contracts.gateway_deployment import (
    CURRENT_PROFILE,
    DESIRED_PROFILE,
    ENTRYPOINT,
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
    InterpreterIdentity,
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


def test_r1_manifest_readiness_and_reconcile_contract_is_typed_and_hash_bound():
    from nexus.contracts.gateway_deployment import (
        DeploymentManifest,
        DeploymentReadiness,
        EffectClass,
        GatewayReconcileOutcome,
        RecoveryEntrypointIdentity,
        RecoverySourceSet,
        ResultClass,
        derive_deployment_manifest,
        validate_deployment_manifest,
    )

    values = {
        "repository": REPOSITORY,
        "accepted_commit": "a" * 40,
        "accepted_tree": "b" * 40,
        "accepted_entrypoint": RecoveryEntrypointIdentity(
            path=ENTRYPOINT, blob_oid="0" * 40, sha256="1" * 64
        ),
        "desired_commit": "c" * 40,
        "desired_tree": "d" * 40,
        "desired_entrypoint": RecoveryEntrypointIdentity(
            path=ENTRYPOINT, blob_oid="e" * 40, sha256="f" * 64
        ),
        "predecessor_commit": "1" * 40,
        "predecessor_tree": "2" * 40,
        "predecessor_entrypoint": RecoveryEntrypointIdentity(
            path=ENTRYPOINT, blob_oid="3" * 40, sha256="4" * 64
        ),
        "interpreter": InterpreterIdentity(),
    }
    source_set = RecoverySourceSet(**values, source_set_sha256=canonical_hash(values))
    manifest = derive_deployment_manifest(source_set, role="desired")
    assert validate_deployment_manifest(manifest) == manifest
    assert manifest.model_validate(manifest.model_dump()) == manifest
    assert DeploymentReadiness.TARGET_READY.value == "TARGET_READY"
    assert EffectClass.GATEWAY_DURABLE_RECOVERY.value == "GATEWAY_DURABLE_RECOVERY"
    outcome = GatewayReconcileOutcome(
        request_id="r-1",
        request_hash="f" * 64,
        idempotency_fence="f-1",
        desired_manifest_id=manifest.deployment_id,
        predecessor_manifest_id="previous-1",
        physical_observation={"label": "com.nexus.mcp.gateway.direct"},
        effect_started=False,
        result=ResultClass.BLOCKED,
        evidence_hash="0" * 64,
    )
    assert outcome.model_validate(outcome.model_dump()) == outcome
    with pytest.raises(ContractError):
        DeploymentManifest.model_validate({**manifest.model_dump(), "root": "/tmp/caller"})
    with pytest.raises(ContractError, match="manager-derived"):
        validate_deployment_manifest(
            manifest.__class__(**{**manifest.__dict__, "deployment_id": "caller-choice"})
        )
    with pytest.raises(ContractError, match="ownership/mode"):
        validate_deployment_manifest(
            manifest.__class__(**{
                **manifest.__dict__,
                "owner_uid": 999999,
                "owner_gid": 999999,
                "mode": 0o755,
                "manifest_sha256": canonical_hash({
                    **{
                        key: value
                        for key, value in manifest.model_dump().items()
                        if key != "manifest_sha256"
                    },
                    "owner_uid": 999999,
                    "owner_gid": 999999,
                    "mode": 0o755,
                }),
            })
        )


def test_legacy_host_authority_cannot_authorize_durable_recovery():
    request = _request()
    altered = HostEffectAuthorityReceipt(**{
        **request.host_authority.__dict__,
        "operation": "gateway-recover",
        "effect_class": EffectClass.GATEWAY_DURABLE_RECOVERY,
    })
    with pytest.raises(ContractError):
        validate_host_effect_authority(altered)


def test_r1_recovery_authority_is_a_distinct_hash_domain():
    from nexus.contracts.gateway_deployment import RecoveryAuthorityReceipt

    assert RecoveryAuthorityReceipt.SCHEMA == "nexus.gateway.durable_recovery_authority.v2"
    # B1 binds the eventual host receipt to the accepted source bytes.  This
    # is only schema coverage: no receipt is issued by a source test.
    required = set(RecoveryAuthorityReceipt.__dataclass_fields__)
    assert {
        "current_main_sha",
        "accepted_source_merge",
        "accepted_source_tree",
        "final_manager_sha256",
        "independent_acceptance_receipt_hash",
        "desired_commit",
        "desired_tree",
        "desired_manifest_sha256",
        "predecessor_commit",
        "predecessor_tree",
        "predecessor_manifest_sha256",
        "predecessor_artifact_format",
        "predecessor_artifact_sha256",
        "predecessor_artifact_size",
    } <= required


def test_r1_recovery_card_hash_matches_tracked_card_bytes():
    from nexus.contracts.gateway_deployment import (
        RECOVERY_CARD_PATH,
        RECOVERY_CARD_SHA256,
    )

    repository_root = Path(__file__).resolve().parents[2]
    tracked_card = repository_root / RECOVERY_CARD_PATH
    assert tracked_card.is_file()
    assert hashlib.sha256(tracked_card.read_bytes()).hexdigest() == RECOVERY_CARD_SHA256


def _r1_authority_fixture():
    from nexus.contracts.gateway_deployment import (
        RECOVERY_CARD_PATH,
        RECOVERY_CARD_SHA256,
        SOURCE_BASE_MERGE,
        SOURCE_BASE_TREE,
        EffectClass,
        RecoveryAuthorityReceipt,
        RecoveryEntrypointIdentity,
        RecoverySourceSet,
        derive_deployment_manifest,
    )

    source_values = {
        "repository": REPOSITORY,
        "accepted_commit": "1" * 40,
        "accepted_tree": "2" * 40,
        "accepted_entrypoint": RecoveryEntrypointIdentity(
            path=ENTRYPOINT, blob_oid="0" * 40, sha256="1" * 64
        ),
        "desired_commit": contract.OWNER_ACTIVATION_DESIRED_COMMIT,
        "desired_tree": contract.OWNER_ACTIVATION_DESIRED_TREE,
        "desired_entrypoint": RecoveryEntrypointIdentity(
            path=ENTRYPOINT, blob_oid="5" * 40, sha256="6" * 64
        ),
        "predecessor_commit": contract.OWNER_ACTIVATION_PREDECESSOR_COMMIT,
        "predecessor_tree": contract.OWNER_ACTIVATION_PREDECESSOR_TREE,
        "predecessor_entrypoint": RecoveryEntrypointIdentity(
            path=ENTRYPOINT, blob_oid="9" * 40, sha256="a" * 64
        ),
        "interpreter": InterpreterIdentity(),
    }
    source_set = RecoverySourceSet(**source_values, source_set_sha256=canonical_hash(source_values))
    desired = derive_deployment_manifest(source_set, role="desired")
    predecessor = derive_deployment_manifest(source_set, role="predecessor")
    values = {
        "schema": RecoveryAuthorityReceipt.SCHEMA,
        "receipt_version": 2,
        "receipt_id": "receipt-r1",
        "card_sha256": RECOVERY_CARD_SHA256,
        "source_base_merge": SOURCE_BASE_MERGE,
        "source_base_tree": SOURCE_BASE_TREE,
        "current_main_sha": source_set.accepted_commit,
        "operation": "gateway-recover",
        "effect_class": EffectClass.GATEWAY_DURABLE_RECOVERY,
        "service_label": contract.LABEL,
        "plist_path": contract.PLIST,
        "endpoint": contract.ENDPOINT,
        "desired_manifest_id": desired.deployment_id,
        "desired_manifest_sha256": desired.manifest_sha256,
        "predecessor_manifest_id": predecessor.deployment_id,
        "predecessor_manifest_sha256": predecessor.manifest_sha256,
        "request_id": "request-r1",
        "idempotency_fence": "fence-r1",
        "issued_at": "2026-08-24T00:00:00Z",
        "expires_at": "2026-08-27T00:00:00Z",
        "revocation_state": "NOT_REVOKED",
        "revoked_at": None,
        "revocation_reason": None,
        "issuer_id": "owner-james",
        "coordinator_id": "coordinator-codex",
        "authorized_actor_id": "coordinator-codex",
        "owner_activation_id": contract.OWNER_ACTIVATION_ID,
        "owner_activation_sha256": contract.OWNER_ACTIVATION_SHA256,
        "source_thread": contract.OWNER_SOURCE_THREAD,
        "standing_grant_id": contract.STANDING_GRANT_ID,
        "standing_grant_receipt_sha256": contract.STANDING_GRANT_RECEIPT_SHA256,
        "repository": REPOSITORY,
        "host_card_path": RECOVERY_CARD_PATH,
        "accepted_source_merge": source_set.accepted_commit,
        "accepted_source_tree": source_set.accepted_tree,
        "final_manager_sha256": "b" * 64,
        "independent_acceptance_receipt_hash": "c" * 64,
        "authority_floor_commit": source_set.accepted_commit,
        "authority_floor_tree": source_set.accepted_tree,
        "desired_commit": source_set.desired_commit,
        "desired_tree": source_set.desired_tree,
        "predecessor_commit": source_set.predecessor_commit,
        "predecessor_tree": source_set.predecessor_tree,
        "predecessor_artifact_format": "git-bundle-self-contained-v1",
        "predecessor_artifact_sha256": "d" * 64,
        "predecessor_artifact_size": 4096,
        "source_set": source_set,
        "desired_manifest": desired,
        "predecessor_manifest": predecessor,
    }
    receipt = RecoveryAuthorityReceipt(**values, receipt_hash=canonical_hash(values))
    return receipt


def _r1_rebind_authority_fixture(
    receipt,
    *,
    activation_id,
    activation_sha256,
    source_thread,
    desired_commit,
    desired_tree,
    predecessor_commit,
    predecessor_tree,
):
    from nexus.contracts.gateway_deployment import (
        RecoveryAuthorityReceipt,
        RecoverySourceSet,
        derive_deployment_manifest,
    )

    source_values = receipt.source_set.model_dump()
    source_values.update({
        "desired_commit": desired_commit,
        "desired_tree": desired_tree,
        "predecessor_commit": predecessor_commit,
        "predecessor_tree": predecessor_tree,
    })
    source_values["source_set_sha256"] = canonical_hash({
        key: value for key, value in source_values.items() if key != "source_set_sha256"
    })
    source_set = RecoverySourceSet.model_validate(source_values)
    desired = derive_deployment_manifest(source_set, role="desired")
    predecessor = derive_deployment_manifest(source_set, role="predecessor")
    values = receipt.model_dump()
    values.update({
        "owner_activation_id": activation_id,
        "owner_activation_sha256": activation_sha256,
        "source_thread": source_thread,
        "desired_commit": desired_commit,
        "desired_tree": desired_tree,
        "predecessor_commit": predecessor_commit,
        "predecessor_tree": predecessor_tree,
        "source_set": source_set.model_dump(),
        "desired_manifest": desired.model_dump(),
        "desired_manifest_id": desired.deployment_id,
        "desired_manifest_sha256": desired.manifest_sha256,
        "predecessor_manifest": predecessor.model_dump(),
        "predecessor_manifest_id": predecessor.deployment_id,
        "predecessor_manifest_sha256": predecessor.manifest_sha256,
    })
    values["receipt_hash"] = canonical_hash({
        key: value for key, value in values.items() if key != "receipt_hash"
    })
    return RecoveryAuthorityReceipt.model_validate(values)


def _r1_task002_authority_fixture(*, historical_activation=False):
    receipt = _r1_authority_fixture()
    return _r1_rebind_authority_fixture(
        receipt,
        activation_id=(
            contract.OWNER_ACTIVATION_ID
            if historical_activation
            else contract.TASK002_RECOVERY_ACTIVATION_ID
        ),
        activation_sha256=(
            contract.OWNER_ACTIVATION_SHA256
            if historical_activation
            else contract.TASK002_RECOVERY_ACTIVATION_SHA256
        ),
        source_thread=(
            contract.OWNER_SOURCE_THREAD
            if historical_activation
            else contract.TASK002_RECOVERY_SOURCE_COMMENT
        ),
        desired_commit=contract.TASK002_RECOVERY_DESIRED_COMMIT,
        desired_tree=contract.TASK002_RECOVERY_DESIRED_TREE,
        predecessor_commit=contract.TASK002_RECOVERY_PREDECESSOR_COMMIT,
        predecessor_tree=contract.TASK002_RECOVERY_PREDECESSOR_TREE,
    )


def test_r1_recovery_authority_accepts_current_card_and_rejects_rehashed_stale_card():
    from nexus.contracts.gateway_deployment import (
        RecoveryAuthorityReceipt,
        validate_recovery_authority,
    )

    receipt = _r1_authority_fixture()
    assert validate_recovery_authority(receipt) == receipt
    values = {
        **receipt.__dict__,
        "card_sha256": "c8882d47df5375091808a0d6e5340d6a80e9af6976ea4a8a4eed1d1983809487",
    }
    values["receipt_hash"] = canonical_hash({
        key: value for key, value in values.items() if key != "receipt_hash"
    })
    with pytest.raises(ContractError, match="Card mismatch"):
        validate_recovery_authority(RecoveryAuthorityReceipt(**values))


def test_g20_old_r2_authority_and_request_are_not_executable_under_successor_contract():
    from nexus.contracts.gateway_deployment import (
        GatewayRecoveryRequest,
        RecoveryAuthorityReceipt,
        validate_recovery_authority,
        validate_recovery_request,
    )

    receipt = _r1_authority_fixture()
    old_receipt = {
        **receipt.model_dump(),
        "schema": "nexus.gateway.durable_recovery_authority.v1",
        "receipt_version": 1,
    }
    old_receipt["receipt_hash"] = canonical_hash({
        key: value for key, value in old_receipt.items() if key != "receipt_hash"
    })
    with pytest.raises(ContractError, match="schema|operation"):
        validate_recovery_authority(RecoveryAuthorityReceipt.model_validate(old_receipt))

    request = _r1_request_fixture(receipt)
    old_request = GatewayRecoveryRequest(**{
        **request.__dict__,
        "schema": "nexus.gateway.durable_recovery_request.v1",
    })
    with pytest.raises(ContractError, match="schema"):
        validate_recovery_request(old_request)


def test_r1_historical_activation_cannot_authorize_task002_recovery_target():
    from nexus.contracts.gateway_deployment import validate_recovery_authority

    receipt = _r1_task002_authority_fixture(historical_activation=True)
    with pytest.raises(ContractError, match="historical activation"):
        validate_recovery_authority(receipt)


def test_r1_task002_activation_accepts_only_exact_authorized_target():
    from nexus.contracts.gateway_deployment import validate_recovery_authority

    receipt = _r1_task002_authority_fixture()
    assert validate_recovery_authority(receipt) == receipt


def test_r1_historical_activation_accepts_only_exact_historical_target():
    from nexus.contracts.gateway_deployment import (
        recovery_activation_authority_class,
        validate_recovery_authority,
    )

    receipt = _r1_authority_fixture()
    assert receipt.owner_activation_id == contract.OWNER_ACTIVATION_ID
    assert receipt.desired_commit == contract.OWNER_ACTIVATION_DESIRED_COMMIT
    assert receipt.predecessor_tree == contract.OWNER_ACTIVATION_PREDECESSOR_TREE
    assert validate_recovery_authority(receipt) == receipt
    assert recovery_activation_authority_class(receipt) == (
        contract.RECOVERY_AUTHORITY_LEGACY_EXACT_TARGET_BOUND
    )


def test_r1_historical_activation_rejects_new_main_target_after_full_rehash():
    from nexus.contracts.gateway_deployment import validate_recovery_authority

    # 9dffad79... is only a dispatch-time source baseline; the historical
    # activation must never authorize it (or any other new main target).
    receipt = _r1_rebind_authority_fixture(
        _r1_authority_fixture(),
        activation_id=contract.OWNER_ACTIVATION_ID,
        activation_sha256=contract.OWNER_ACTIVATION_SHA256,
        source_thread=contract.OWNER_SOURCE_THREAD,
        desired_commit="9dffad79ea30d6f2a1b8bee64ac1048e1ae59f35"[:40],
        desired_tree="f" * 40,
        predecessor_commit="e" * 40,
        predecessor_tree="d" * 40,
    )
    with pytest.raises(ContractError, match="historical activation"):
        validate_recovery_authority(receipt)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("desired_commit", "a" * 40),
        ("desired_tree", "b" * 40),
        ("predecessor_commit", "c" * 40),
        ("predecessor_tree", "d" * 40),
    ],
)
def test_r1_historical_activation_rejects_single_target_substitution(field, replacement):
    from nexus.contracts.gateway_deployment import validate_recovery_authority

    receipt = _r1_authority_fixture()
    target = {
        "desired_commit": receipt.desired_commit,
        "desired_tree": receipt.desired_tree,
        "predecessor_commit": receipt.predecessor_commit,
        "predecessor_tree": receipt.predecessor_tree,
    }
    target[field] = replacement
    altered = _r1_rebind_authority_fixture(
        receipt,
        activation_id=contract.OWNER_ACTIVATION_ID,
        activation_sha256=contract.OWNER_ACTIVATION_SHA256,
        source_thread=contract.OWNER_SOURCE_THREAD,
        **target,
    )
    with pytest.raises(ContractError, match="historical activation"):
        validate_recovery_authority(altered)


FUTURE_ACTIVATION_ID = "OWNER_ISSUE526_FUTURE_TRACKED_20260902"
FUTURE_ACTIVATION_SHA256 = "9" * 64
FUTURE_ACTIVATION_SOURCE_THREAD = "future-thread-20260902"


def _r1_future_authority_fixture():
    receipt = _r1_authority_fixture()
    return _r1_rebind_authority_fixture(
        receipt,
        activation_id=FUTURE_ACTIVATION_ID,
        activation_sha256=FUTURE_ACTIVATION_SHA256,
        source_thread=FUTURE_ACTIVATION_SOURCE_THREAD,
        desired_commit="5" * 40,
        desired_tree="6" * 40,
        predecessor_commit="7" * 40,
        predecessor_tree="8" * 40,
    )


def test_r1_future_activation_is_structurally_valid_without_code_constants():
    from nexus.contracts.gateway_deployment import validate_recovery_authority

    # A future Owner activation is representable with NO new Python constant:
    # the receipt passes full structural contract validation as-is.
    receipt = _r1_future_authority_fixture()
    assert validate_recovery_authority(receipt) == receipt


def test_r1_future_activation_is_not_authority_without_tracked_provenance():
    from nexus.contracts.gateway_deployment import recovery_activation_authority_class

    # STRUCTURAL RECEIPT VALIDITY != RECOVERY AUTHORITY.  A future activation
    # is classified as requiring fixed tracked-main provenance; the manager
    # must prove byte-identity with the fixed tracked receipt on a freshly
    # verified authority mirror before any Gateway effect (proven at the
    # manager level in tests/ops/test_mcp_gateway_durable.py).
    receipt = _r1_future_authority_fixture()
    assert recovery_activation_authority_class(receipt) == (
        contract.RECOVERY_AUTHORITY_FUTURE_TRACKED_PROVENANCE_REQUIRED
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"activation_id": contract.OWNER_ACTIVATION_ID},
        {"activation_sha256": contract.OWNER_ACTIVATION_SHA256},
        {"source_thread": contract.OWNER_SOURCE_THREAD},
        {"activation_id": contract.TASK002_RECOVERY_ACTIVATION_ID},
        {"activation_sha256": contract.TASK002_RECOVERY_ACTIVATION_SHA256},
        {"source_thread": contract.TASK002_RECOVERY_SOURCE_COMMENT},
    ],
)
def test_r1_legacy_activation_components_never_grant_future_generality(changes):
    from nexus.contracts.gateway_deployment import (
        recovery_activation_authority_class,
        validate_recovery_authority,
    )

    # A caller cannot take a legacy identity component (or a legacy lineage)
    # and reuse it as a generic future activation against a new target.
    receipt = _r1_rebind_authority_fixture(
        _r1_future_authority_fixture(),
        activation_id=changes.get("activation_id", FUTURE_ACTIVATION_ID),
        activation_sha256=changes.get("activation_sha256", FUTURE_ACTIVATION_SHA256),
        source_thread=changes.get("source_thread", FUTURE_ACTIVATION_SOURCE_THREAD),
        desired_commit="a" * 40,
        desired_tree="b" * 40,
        predecessor_commit="c" * 40,
        predecessor_tree="d" * 40,
    )
    assert recovery_activation_authority_class(receipt) == (
        contract.RECOVERY_AUTHORITY_LEGACY_EXACT_TARGET_BOUND
    )
    with pytest.raises(ContractError, match="historical activation|activation lineage|TASK-002"):
        validate_recovery_authority(receipt)


def test_r1_expired_receipt_fails_freshness():
    from nexus.contracts.gateway_deployment import validate_recovery_authority

    receipt = _r1_authority_fixture()
    with pytest.raises(ContractError, match="stale"):
        validate_recovery_authority(receipt, now="2099-01-01T00:00:00Z")


def test_r1_receipt_hash_substitution_fails_closed():
    from nexus.contracts.gateway_deployment import (
        RecoveryAuthorityReceipt,
        validate_recovery_authority,
    )

    receipt = _r1_authority_fixture()
    forged = RecoveryAuthorityReceipt(**{**receipt.__dict__, "receipt_hash": "f" * 64})
    with pytest.raises(ContractError, match="hash mismatch"):
        validate_recovery_authority(forged)


def test_r1_stale_manager_binding_fails_closed():
    from nexus.contracts.gateway_deployment import (
        RecoveryAuthorityReceipt,
        validate_recovery_authority,
    )

    receipt = _r1_authority_fixture()
    forged = RecoveryAuthorityReceipt(**{
        **receipt.__dict__,
        "final_manager_sha256": "not-a-hash",
    })
    with pytest.raises(ContractError, match="invalid final manager"):
        validate_recovery_authority(forged)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("desired_commit", "a" * 40),
        ("desired_tree", "b" * 40),
        ("predecessor_commit", "c" * 40),
        ("predecessor_tree", "d" * 40),
    ],
)
def test_r1_task002_activation_rejects_rehashed_target_substitution(field, replacement):
    from nexus.contracts.gateway_deployment import validate_recovery_authority

    receipt = _r1_task002_authority_fixture()
    target = {
        "desired_commit": receipt.desired_commit,
        "desired_tree": receipt.desired_tree,
        "predecessor_commit": receipt.predecessor_commit,
        "predecessor_tree": receipt.predecessor_tree,
    }
    target[field] = replacement
    altered = _r1_rebind_authority_fixture(
        receipt,
        activation_id=contract.TASK002_RECOVERY_ACTIVATION_ID,
        activation_sha256=contract.TASK002_RECOVERY_ACTIVATION_SHA256,
        source_thread=contract.TASK002_RECOVERY_SOURCE_COMMENT,
        **target,
    )
    with pytest.raises(ContractError, match="TASK-002 recovery activation target"):
        validate_recovery_authority(altered)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("owner_activation_id", "OWNER_UNKNOWN"),
        ("owner_activation_id", contract.OWNER_ACTIVATION_ID),
        ("owner_activation_sha256", contract.OWNER_ACTIVATION_SHA256),
        ("source_thread", contract.OWNER_SOURCE_THREAD),
    ],
)
def test_r1_task002_activation_rejects_unknown_or_mixed_lineage(field, replacement):
    from nexus.contracts.gateway_deployment import (
        RecoveryAuthorityReceipt,
        validate_recovery_authority,
    )

    receipt = _r1_task002_authority_fixture()
    values = {**receipt.model_dump(), field: replacement}
    values["receipt_hash"] = canonical_hash({
        key: value for key, value in values.items() if key != "receipt_hash"
    })
    altered = RecoveryAuthorityReceipt.model_validate(values)
    with pytest.raises(ContractError, match="activation lineage"):
        validate_recovery_authority(altered)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("issuer_id", "other-owner"),
        ("coordinator_id", "other-coordinator"),
        ("authorized_actor_id", "other-actor"),
        ("owner_activation_id", "other-activation"),
        ("owner_activation_sha256", "d" * 64),
        ("source_thread", "other-thread"),
        ("standing_grant_id", "other-grant"),
        ("standing_grant_receipt_sha256", "e" * 64),
        ("host_card_path", "tasks/other.md"),
    ],
)
def test_r1_authority_wrong_lineage_rejects_after_full_rehash(field, replacement):
    from nexus.contracts.gateway_deployment import (
        RecoveryAuthorityReceipt,
        validate_recovery_authority,
    )

    receipt = _r1_authority_fixture()
    values = {**receipt.__dict__, field: replacement}
    values["receipt_hash"] = canonical_hash({
        key: value for key, value in values.items() if key != "receipt_hash"
    })
    with pytest.raises(ContractError, match="authority"):
        validate_recovery_authority(RecoveryAuthorityReceipt(**values))


@pytest.mark.parametrize(
    "changes",
    [
        {"revocation_state": "NOT_REVOKED", "revoked_at": "2026-08-25T00:00:00Z"},
        {"revocation_state": "REVOKED", "revoked_at": None, "revocation_reason": None},
        {
            "revocation_state": "REVOKED",
            "revoked_at": "2026-08-25T00:00:00Z",
            "revocation_reason": "withdrawn",
        },
    ],
)
def test_r1_authority_revocation_states_fail_closed(changes):
    from nexus.contracts.gateway_deployment import (
        RecoveryAuthorityReceipt,
        validate_recovery_authority,
    )

    receipt = _r1_authority_fixture()
    values = {**receipt.__dict__, **changes}
    values["receipt_hash"] = canonical_hash({
        key: value for key, value in values.items() if key != "receipt_hash"
    })
    with pytest.raises(ContractError, match="revocation|revoked"):
        validate_recovery_authority(RecoveryAuthorityReceipt(**values))


def _r1_request_fixture(receipt):
    from nexus.contracts.gateway_deployment import GatewayRecoveryRequest

    values = {
        "request_id": receipt.request_id,
        "idempotency_fence": receipt.idempotency_fence,
        "operation": receipt.operation,
        "effect_class": receipt.effect_class,
        "recovery_authority_id": receipt.receipt_id,
        "recovery_authority_hash": receipt.receipt_hash,
        "desired_manifest_id": receipt.desired_manifest_id,
        "desired_manifest_hash": receipt.desired_manifest_sha256,
        "predecessor_manifest_id": receipt.predecessor_manifest_id,
        "predecessor_manifest_hash": receipt.predecessor_manifest_sha256,
    }
    return GatewayRecoveryRequest(**values, request_hash=canonical_hash(values))


def _r1_bundle_evidence_fixture():
    from nexus.contracts.gateway_deployment import (
        BareStoreEvidence,
        BundleRoleHead,
        SourceBundleEvidence,
    )

    receipt = _r1_authority_fixture()
    request = _r1_request_fixture(receipt)
    fresh = "d" * 40
    fresh_tree = "e" * 40
    bare = BareStoreEvidence(
        path="/fixed/repository.git",
        repository=REPOSITORY,
        origin=contract.REMOTE,
        is_bare=True,
        alternates_absent=True,
        owner_uid=501,
        owner_gid=20,
        mode=0o700,
        object_set_sha256="1" * 64,
    )
    heads = (
        BundleRoleHead("fresh-main", "refs/nexus-r1/fresh-main", fresh),
        BundleRoleHead("desired", "refs/nexus-r1/desired", receipt.desired_commit),
        BundleRoleHead("predecessor", "refs/nexus-r1/predecessor", receipt.predecessor_commit),
    )
    values = {
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "idempotency_fence": request.idempotency_fence,
        "receipt_id": receipt.receipt_id,
        "receipt_hash": receipt.receipt_hash,
        "source_set_sha256": receipt.source_set.source_set_sha256,
        "observed_fresh_main_commit": fresh,
        "observed_fresh_main_tree": fresh_tree,
        "role_heads": heads,
        "bundle_sha256": "5" * 64,
        "bundle_size": 100,
        "bundle_verified": True,
        "bare_store": bare,
        "observed_at": "2026-08-25T00:00:00Z",
    }
    evidence = SourceBundleEvidence(**values, evidence_hash=canonical_hash(values))
    return {
        "receipt": receipt,
        "request": request,
        "source_set": receipt.source_set,
        "fresh": fresh,
        "fresh_tree": fresh_tree,
        "bare": bare,
        "evidence": evidence,
    }


def _validate_r1_bundle_fixture(fixture, evidence=None):
    from nexus.contracts.gateway_deployment import validate_source_bundle_evidence

    return validate_source_bundle_evidence(
        evidence or fixture["evidence"],
        request=fixture["request"],
        receipt=fixture["receipt"],
        source_set=fixture["source_set"],
        expected_fresh_main_commit=fixture["fresh"],
        expected_fresh_main_tree=fixture["fresh_tree"],
        expected_bare_store=fixture["bare"],
    )


def test_r1_semantic_change_changes_ids_but_bundle_observation_does_not():
    from nexus.contracts.gateway_deployment import (
        RecoveryEntrypointIdentity,
        RecoverySourceSet,
        derive_deployment_manifest,
    )

    receipt = _r1_authority_fixture()
    original = derive_deployment_manifest(receipt.source_set, role="desired")
    values = {
        **receipt.source_set.__dict__,
        "desired_entrypoint": RecoveryEntrypointIdentity(**{
            **receipt.source_set.desired_entrypoint.__dict__,
            "sha256": "f" * 64,
        }),
    }
    values["source_set_sha256"] = canonical_hash({
        key: value for key, value in values.items() if key != "source_set_sha256"
    })
    changed = derive_deployment_manifest(RecoverySourceSet(**values), role="desired")
    assert changed.deployment_id != original.deployment_id
    accepted_values = {
        **receipt.source_set.__dict__,
        "accepted_entrypoint": RecoveryEntrypointIdentity(**{
            **receipt.source_set.accepted_entrypoint.__dict__,
            "sha256": "e" * 64,
        }),
    }
    accepted_values["source_set_sha256"] = canonical_hash({
        key: value for key, value in accepted_values.items() if key != "source_set_sha256"
    })
    accepted_changed = derive_deployment_manifest(
        RecoverySourceSet(**accepted_values), role="desired"
    )
    assert accepted_changed.deployment_id != original.deployment_id
    assert "bundle" not in set(receipt.source_set.__dataclass_fields__)
    first_fixture = _r1_bundle_evidence_fixture()
    first = _validate_r1_bundle_fixture(first_fixture)
    second_values = {
        **first.__dict__,
        "bundle_sha256": "6" * 64,
    }
    second_values["evidence_hash"] = canonical_hash({
        key: value for key, value in second_values.items() if key != "evidence_hash"
    })
    second = _validate_r1_bundle_fixture(first_fixture, first.__class__(**second_values))
    assert first.evidence_hash != second.evidence_hash
    assert (
        derive_deployment_manifest(receipt.source_set, role="desired").deployment_id
        == original.deployment_id
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("request_id", "other-request"),
        ("request_hash", "a" * 64),
        ("idempotency_fence", "other-fence"),
        ("receipt_id", "other-receipt"),
        ("receipt_hash", "b" * 64),
        ("source_set_sha256", "c" * 64),
        ("observed_fresh_main_tree", "d" * 40),
    ],
)
def test_r1_bundle_evidence_rejects_self_rehashed_context_substitution(field, replacement):
    fixture = _r1_bundle_evidence_fixture()
    evidence = fixture["evidence"]
    values = {**evidence.__dict__, field: replacement}
    values["evidence_hash"] = canonical_hash({
        key: value for key, value in values.items() if key != "evidence_hash"
    })
    with pytest.raises(ContractError, match="trusted"):
        _validate_r1_bundle_fixture(fixture, evidence.__class__(**values))


def test_r1_bundle_evidence_rejects_role_swap_arbitrary_commits_and_wrong_origin():
    from nexus.contracts.gateway_deployment import BareStoreEvidence, BundleRoleHead

    fixture = _r1_bundle_evidence_fixture()
    evidence = fixture["evidence"]
    mutations = [
        {
            "role_heads": (
                evidence.role_heads[0],
                BundleRoleHead(
                    "desired",
                    "refs/nexus-r1/desired",
                    fixture["source_set"].predecessor_commit,
                ),
                BundleRoleHead(
                    "predecessor",
                    "refs/nexus-r1/predecessor",
                    fixture["source_set"].desired_commit,
                ),
            ),
        },
        {
            "role_heads": (
                evidence.role_heads[0],
                BundleRoleHead("desired", "refs/nexus-r1/desired", "f" * 40),
                evidence.role_heads[2],
            ),
        },
        {
            "bare_store": BareStoreEvidence(**{
                **fixture["bare"].__dict__,
                "origin": "https://example.invalid/wrong.git",
            }),
        },
        {
            "bare_store": BareStoreEvidence(**{
                **fixture["bare"].__dict__,
                "path": "/wrong/repository.git",
            }),
        },
    ]
    for mutation in mutations:
        values = {**evidence.__dict__, **mutation}
        values["evidence_hash"] = canonical_hash({
            key: value for key, value in values.items() if key != "evidence_hash"
        })
        with pytest.raises(ContractError, match="trusted"):
            _validate_r1_bundle_fixture(fixture, evidence.__class__(**values))


def test_r1b_recovery_request_is_separate_and_has_no_legacy_authority_body():
    from nexus.contracts.gateway_deployment import GatewayRecoveryRequest, validate_recovery_request

    values = {
        "request_id": "r1b-1",
        "idempotency_fence": "f1b-1",
        "operation": "gateway-recover",
        "effect_class": EffectClass.GATEWAY_DURABLE_RECOVERY,
        "recovery_authority_id": "receipt-1",
        "recovery_authority_hash": "a" * 64,
        "desired_manifest_id": "desired-1",
        "desired_manifest_hash": "b" * 64,
        "predecessor_manifest_id": "previous-1",
        "predecessor_manifest_hash": "c" * 64,
    }
    request = GatewayRecoveryRequest(**values)
    request = GatewayRecoveryRequest(**{
        **request.__dict__,
        "request_hash": canonical_hash(values),
    })
    assert validate_recovery_request(request) == request
    with pytest.raises(ContractError):
        GatewayRecoveryRequest.model_validate({**request.model_dump(), "authority": {}})
    with pytest.raises(ContractError):
        validate_recovery_request(
            GatewayRecoveryRequest.model_validate({**request.model_dump(), "operation": "recover"})
        )


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


_R1B2_LEDGER_V2_KEYS = {
    "schema",
    "request_id",
    "request_hash",
    "state",
    "sequence",
    "parent_hash",
    "record_hash",
    "authority_schema",
    "receipt_id",
    "receipt_hash",
    "card_sha256",
    "accepted_source_merge",
    "accepted_source_tree",
    "final_manager_sha256",
    "independent_acceptance_receipt_hash",
    "source_set_sha256",
    "desired_manifest_id",
    "desired_manifest_hash",
    "predecessor_manifest_id",
    "predecessor_manifest_hash",
    "source_bundle_evidence_hash",
    "operation",
    "effect_class",
    "idempotency_fence",
    "pre_effect_identity",
    "observed_identity",
}


def _r1b2_ledger_values(state="PREFLIGHTED", *, sequence=2, parent_hash="1" * 64):
    fixture = _r1_bundle_evidence_fixture()
    request = fixture["request"]
    receipt = fixture["receipt"]
    values = {
        "schema": "nexus.gateway.ledger.v2",
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "state": state,
        "sequence": sequence,
        "parent_hash": parent_hash,
        "authority_schema": receipt.schema,
        "receipt_id": receipt.receipt_id,
        "receipt_hash": receipt.receipt_hash,
        "card_sha256": receipt.card_sha256,
        "accepted_source_merge": receipt.accepted_source_merge,
        "accepted_source_tree": receipt.accepted_source_tree,
        "final_manager_sha256": receipt.final_manager_sha256,
        "independent_acceptance_receipt_hash": (receipt.independent_acceptance_receipt_hash),
        "source_set_sha256": receipt.source_set.source_set_sha256,
        "desired_manifest_id": receipt.desired_manifest_id,
        "desired_manifest_hash": receipt.desired_manifest_sha256,
        "predecessor_manifest_id": receipt.predecessor_manifest_id,
        "predecessor_manifest_hash": receipt.predecessor_manifest_sha256,
        "source_bundle_evidence_hash": fixture["evidence"].evidence_hash,
        "operation": request.operation,
        "effect_class": request.effect_class,
        "idempotency_fence": request.idempotency_fence,
        "pre_effect_identity": {"deployment_id": receipt.predecessor_manifest_id},
        "observed_identity": {},
    }
    if state == "REQUESTED":
        values["source_bundle_evidence_hash"] = None
    values["record_hash"] = canonical_hash(values)
    return fixture, values


def test_r1b2_ledger_v2_strict_schema_keys_hash_and_nullable_evidence():
    from nexus.contracts.gateway_deployment import (
        RecoveryLedgerRecord,
        validate_recovery_ledger_record,
    )

    fixture, values = _r1b2_ledger_values()
    record = RecoveryLedgerRecord.model_validate(values)
    assert set(record.model_dump()) == _R1B2_LEDGER_V2_KEYS
    assert record.schema == "nexus.gateway.ledger.v2"
    assert (
        validate_recovery_ledger_record(
            record,
            request=fixture["request"],
            receipt=fixture["receipt"],
            source_bundle_evidence=fixture["evidence"],
            expected_sequence=2,
            expected_parent_hash="1" * 64,
        )
        == record
    )
    requested_fixture, requested_values = _r1b2_ledger_values(
        "REQUESTED", sequence=1, parent_hash=""
    )
    requested = RecoveryLedgerRecord.model_validate(requested_values)
    assert (
        validate_recovery_ledger_record(
            requested,
            request=requested_fixture["request"],
            receipt=requested_fixture["receipt"],
            source_bundle_evidence=None,
            expected_sequence=1,
            expected_parent_hash="",
        )
        == requested
    )
    for mutation in (
        {**values, "schema": "nexus.gateway.ledger.v1"},
        {**values, "unexpected": True},
        {key: value for key, value in values.items() if key != "receipt_hash"},
        {**values, "source_bundle_evidence_hash": None},
    ):
        with pytest.raises((ContractError, TypeError, ValueError)):
            validate_recovery_ledger_record(
                RecoveryLedgerRecord.model_validate(mutation),
                request=fixture["request"],
                receipt=fixture["receipt"],
                source_bundle_evidence=fixture["evidence"],
                expected_sequence=2,
                expected_parent_hash="1" * 64,
            )


def test_r1b2_recovery_binding_hash_covers_every_immutable_input():
    from nexus.contracts.gateway_deployment import derive_recovery_ledger_binding

    fixture = _r1_bundle_evidence_fixture()
    request = fixture["request"]
    receipt = fixture["receipt"]
    evidence = fixture["evidence"]
    expected = canonical_hash({
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "authority_schema": receipt.schema,
        "receipt_id": receipt.receipt_id,
        "receipt_hash": receipt.receipt_hash,
        "card_sha256": receipt.card_sha256,
        "accepted_source_merge": receipt.accepted_source_merge,
        "accepted_source_tree": receipt.accepted_source_tree,
        "final_manager_sha256": receipt.final_manager_sha256,
        "independent_acceptance_receipt_hash": (receipt.independent_acceptance_receipt_hash),
        "source_set_sha256": receipt.source_set.source_set_sha256,
        "desired_manifest_id": receipt.desired_manifest_id,
        "desired_manifest_hash": receipt.desired_manifest_sha256,
        "predecessor_manifest_id": receipt.predecessor_manifest_id,
        "predecessor_manifest_hash": receipt.predecessor_manifest_sha256,
        "source_bundle_evidence_hash": evidence.evidence_hash,
        "operation": request.operation,
        "effect_class": request.effect_class,
        "idempotency_fence": request.idempotency_fence,
    })
    assert (
        derive_recovery_ledger_binding(
            request=request,
            receipt=receipt,
            source_bundle_evidence=evidence,
        )
        == expected
    )


def test_r1b2_ledger_v2_rejects_v1_field_injection_and_v1_omission():
    from nexus.contracts.gateway_deployment import RecoveryLedgerRecord

    _, values = _r1b2_ledger_values()
    for v1_field in (
        "host_receipt_hash",
        "source_base_merge",
        "source_base_tree",
        "host_card_sha256",
    ):
        with pytest.raises((ContractError, TypeError, ValueError)):
            RecoveryLedgerRecord.model_validate({**values, v1_field: "f" * 64})
    assert not (
        {"authority_schema", "receipt_id", "source_set_sha256"}
        & {
            "schema",
            "request_id",
            "request_hash",
            "state",
            "sequence",
            "parent_hash",
            "record_hash",
            "pre_effect_identity",
            "observed_identity",
            "host_receipt_hash",
            "source_base_merge",
            "source_base_tree",
            "host_card_sha256",
            "effect_class",
            "operation",
            "idempotency_fence",
        }
    )


def test_r1b2_recovery_transition_exact_edges_and_no_uncertain_reentry():
    allowed = (
        ("REQUESTED", "PREFLIGHTED"),
        ("PREFLIGHTED", "TARGET_READY"),
        ("TARGET_READY", "ROLLBACK_READY"),
        ("TARGET_READY", "ROLLBACK_UNAVAILABLE"),
        ("ROLLBACK_UNAVAILABLE", "BLOCKED"),
        ("ROLLBACK_READY", "EFFECT_STARTED"),
        ("EFFECT_STARTED", "SERVICE_OBSERVED"),
        ("EFFECT_STARTED", "UNCERTAIN_EFFECT"),
        ("UNCERTAIN_EFFECT", "SERVICE_OBSERVED"),
        ("UNCERTAIN_EFFECT", "ROLLED_BACK"),
        ("UNCERTAIN_EFFECT", "BLOCKED"),
        ("SERVICE_OBSERVED", "IDENTITY_VERIFIED"),
        ("IDENTITY_VERIFIED", "CLIENT_BOUND"),
        ("CLIENT_BOUND", "VERIFIED"),
    )
    for previous, current in allowed:
        assert transition(previous, current).value == current
    forbidden = (
        ("TARGET_READY", "EFFECT_STARTED"),
        ("ROLLBACK_UNAVAILABLE", "EFFECT_STARTED"),
        ("UNCERTAIN_EFFECT", "EFFECT_STARTED"),
        ("UNCERTAIN_EFFECT", "PREFLIGHTED"),
        ("VERIFIED", "EFFECT_STARTED"),
        ("ROLLED_BACK", "EFFECT_STARTED"),
    )
    for previous, current in forbidden:
        with pytest.raises(ContractError):
            transition(previous, current)


def test_r1b2_already_desired_plan_ack_and_physical_identity_are_strict():
    from nexus.contracts.gateway_deployment import (
        RecoveryEffectAck,
        RecoveryEffectPlan,
        RecoveryPhysicalIdentity,
        validate_recovery_effect_ack,
        validate_recovery_effect_plan,
        validate_recovery_physical_identity,
    )

    fixture = _r1_bundle_evidence_fixture()
    request = fixture["request"]
    receipt = fixture["receipt"]
    desired_root = (
        "/Users/jameschen/Library/Application Support/Nexus/gateway-direct/"
        f"deployments/{receipt.desired_manifest_id}"
    )
    predecessor_root = (
        "/Users/jameschen/Library/Application Support/Nexus/gateway-direct/"
        f"deployments/{receipt.predecessor_manifest_id}"
    )
    plan_values = {
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "idempotency_fence": request.idempotency_fence,
        "receipt_id": receipt.receipt_id,
        "receipt_hash": receipt.receipt_hash,
        "source_set_sha256": receipt.source_set.source_set_sha256,
        "desired_manifest_id": receipt.desired_manifest_id,
        "desired_manifest_hash": receipt.desired_manifest_sha256,
        "predecessor_manifest_id": receipt.predecessor_manifest_id,
        "predecessor_manifest_hash": receipt.predecessor_manifest_sha256,
        "desired_root": desired_root,
        "predecessor_root": predecessor_root,
        "service_label": contract.LABEL,
        "plist_path": contract.PLIST,
        "endpoint": contract.ENDPOINT,
        "pre_effect_identity_hash": "1" * 64,
    }
    plan = RecoveryEffectPlan(**plan_values, plan_hash=canonical_hash(plan_values))
    assert validate_recovery_effect_plan(plan, request=request, receipt=receipt) == plan
    ack_values = {
        "plan_hash": plan.plan_hash,
        "acknowledged": True,
        "applied": False,
        "already_desired": True,
        "effect_kind": "GATEWAY_DURABLE_RECOVERY",
    }
    ack = RecoveryEffectAck(**ack_values, evidence_hash=canonical_hash(ack_values))
    assert validate_recovery_effect_ack(ack, plan=plan) == ack
    assert set(ack.model_dump()) == {
        "plan_hash",
        "acknowledged",
        "applied",
        "already_desired",
        "effect_kind",
        "evidence_hash",
    }
    invalid_ack_values = {
        **ack_values,
        "applied": True,
        "already_desired": True,
    }
    with pytest.raises(ContractError):
        validate_recovery_effect_ack(
            RecoveryEffectAck(
                **invalid_ack_values,
                evidence_hash=canonical_hash(invalid_ack_values),
            ),
            plan=plan,
        )
    physical_values = {
        "loaded": True,
        "service_label": contract.LABEL,
        "pid": 123,
        "start_identity": "pid-123-start-1",
        "listener": contract.ENDPOINT,
        "plist_sha256": "2" * 64,
        "deployment_id": receipt.desired_manifest_id,
        "root": desired_root,
        "head": receipt.desired_commit,
        "tree": receipt.desired_tree,
        "server_instance": "server-1",
        "observed_at": "2026-08-25T00:00:00Z",
    }
    physical = RecoveryPhysicalIdentity(
        **physical_values, evidence_hash=canonical_hash(physical_values)
    )
    assert (
        validate_recovery_physical_identity(
            physical,
            expected_manifest=receipt.desired_manifest,
            expected_root=desired_root,
        )
        == physical
    )
