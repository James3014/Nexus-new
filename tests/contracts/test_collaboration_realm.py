import pytest
from pydantic import ValidationError

from nexus.contracts.collaboration_realm import (
    CollaborationExecutionRealm,
    CollaborationRepoBinding,
    ControlPlaneRepoBinding,
    RuntimeActivationBinding,
)


def _values(**overrides):
    values = {
        "control_plane": {
            "repo_root": "/srv/nexus/control",
            "revision": "1" * 40,
        },
        "collaboration": {
            "repository": {
                "repository_id": "James3014/Nexus-new",
                "canonical_remote": "https://github.com/James3014/Nexus-new.git",
            },
            "base": {"branch": "main", "head_sha": "2" * 40},
            "repo_root": "/srv/nexus/collaboration",
        },
        "runtime_activation": {
            "realm_id": "local-runtime",
            "activation_authorized": False,
        },
        "execution_root": "/srv/nexus/execution",
    }
    values.update(overrides)
    return values


def test_issue_builds_normalized_frozen_realm_with_canonical_hash():
    realm = CollaborationExecutionRealm.issue(
        **_values(
            execution_root="/srv/nexus/collaboration/../execution",
        )
    )

    assert realm.schema == "nexus.collaboration_execution_realm.v1"
    assert realm.execution_root == "/srv/nexus/execution"
    assert len(realm.binding_hash) == 64
    assert realm.runtime_activation.activation_authorized is False
    with pytest.raises(ValidationError):
        realm.execution_root = "/other"


def test_hash_tampering_is_rejected():
    realm = CollaborationExecutionRealm.issue(**_values())
    payload = realm.model_dump(mode="json")
    payload["binding_hash"] = "0" * 64

    with pytest.raises(ValidationError, match="BINDING_HASH_MISMATCH"):
        CollaborationExecutionRealm.model_validate(payload)


def test_extra_fields_are_forbidden_at_each_contract_boundary():
    with pytest.raises(ValidationError):
        CollaborationExecutionRealm.issue(**_values(unexpected=True))
    with pytest.raises(ValidationError):
        ControlPlaneRepoBinding(
            repo_root="/srv/nexus/control",
            revision="1" * 40,
            unexpected=True,
        )


@pytest.mark.parametrize("revision", ["1" * 39, "1" * 41, "A" * 40, "z" * 40])
def test_revision_must_be_lowercase_full_sha(revision):
    with pytest.raises(ValidationError, match="REVISION_INVALID"):
        ControlPlaneRepoBinding(repo_root="/srv/nexus/control", revision=revision)


@pytest.mark.parametrize("path", ["relative", "", " /srv/nexus/control", "/srv/nexus\\control"])
def test_roots_must_be_absolute_normalized_paths(path):
    with pytest.raises(ValidationError, match="REPO_ROOT_INVALID"):
        ControlPlaneRepoBinding(repo_root=path, revision="1" * 40)


@pytest.mark.parametrize(
    ("control_root", "collaboration_root", "execution_root"),
    [
        ("/srv/nexus/control", "/srv/nexus/control/repo", "/srv/nexus/execution"),
        ("/srv/nexus/control", "/srv/nexus/collaboration", "/srv/nexus/control/run"),
        ("/srv/nexus/control", "/srv/nexus/collaboration", "/srv/nexus/collaboration/run"),
        ("/srv/nexus/control", "/srv/nexus/collaboration", "/srv/nexus/collaboration"),
    ],
)
def test_roots_must_be_physically_disjoint(control_root, collaboration_root, execution_root):
    values = _values(
        control_plane={"repo_root": control_root, "revision": "1" * 40},
        collaboration={
            **_values()["collaboration"],
            "repo_root": collaboration_root,
        },
        execution_root=execution_root,
    )
    with pytest.raises(ValidationError, match="ROOT_BOUNDARY_CONFLICT"):
        CollaborationExecutionRealm.issue(**values)


def test_activation_true_is_rejected():
    with pytest.raises(ValidationError):
        RuntimeActivationBinding(realm_id="local-runtime", activation_authorized=True)


def test_safe_ids_are_enforced():
    with pytest.raises(ValidationError, match="REALM_ID_INVALID"):
        RuntimeActivationBinding(realm_id="realm/with/slash")
    with pytest.raises(ValidationError, match="REMOTE_NAME_INVALID"):
        CollaborationRepoBinding(
            **_values()["collaboration"],
            remote_name="origin/main",
        )
