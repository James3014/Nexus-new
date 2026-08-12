from __future__ import annotations

import copy

import pytest

from scripts.ops.cleanup_integration_guard import GuardError, post_apply, preflight

BASE_SHA = "1" * 40
HEAD_SHA = "2" * 40
HEAD_TREE = "3" * 40
MERGE_SHA = "4" * 40
MERGE_TREE = HEAD_TREE


def _manifest() -> dict[str, object]:
    return {
        "schema": "nexus.cleanup_integration_manifest.v1",
        "repository": "James3014/Nexus-new",
        "pr_number": 71,
        "base_ref": "main",
        "base_sha": BASE_SHA,
        "head_sha": HEAD_SHA,
        "head_tree": HEAD_TREE,
        "changed_paths": [
            "nexus/core/nexus_transaction.py",
            "nexus/policy/compatibility.py",
        ],
        "deleted_paths": [
            "nexus/core/nexus_transaction.py",
            "nexus/policy/compatibility.py",
        ],
        "required_checks": [
            {"context": "Exact-base impact gate", "integration_id": 15368},
            {"context": "Trusted verifier (default branch)", "integration_id": 15368},
        ],
    }


def _live_snapshot() -> dict[str, object]:
    return {
        "schema": "nexus.cleanup_integration_live_snapshot.v1",
        "repository": "James3014/Nexus-new",
        "pr_number": 71,
        "base_ref": "main",
        "base_sha": BASE_SHA,
        "head_sha": HEAD_SHA,
        "head_tree": HEAD_TREE,
        "pr_state": "open",
        "draft": False,
        "mergeable": True,
        "target_clean": True,
        "checks": [
            {
                "context": "Exact-base impact gate",
                "integration_id": 15368,
                "head_sha": HEAD_SHA,
                "status": "completed",
                "conclusion": "success",
            },
            {
                "context": "Trusted verifier (default branch)",
                "integration_id": 15368,
                "head_sha": HEAD_SHA,
                "status": "completed",
                "conclusion": "success",
            },
        ],
    }


def _post_snapshot(preflight_receipt: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "nexus.cleanup_integration_post_snapshot.v1",
        "repository": "James3014/Nexus-new",
        "pr_number": 71,
        "base_ref": "main",
        "cas_token": preflight_receipt["cas_token"],
        "manifest_sha256": preflight_receipt["manifest_sha256"],
        "merge_sha": MERGE_SHA,
        "merge_tree": MERGE_TREE,
        "current_base_sha": MERGE_SHA,
        "parents": [BASE_SHA, HEAD_SHA],
        "changed_paths": [
            "nexus/core/nexus_transaction.py",
            "nexus/policy/compatibility.py",
        ],
        "path_states": {
            "nexus/core/nexus_transaction.py": False,
            "nexus/policy/compatibility.py": False,
        },
        "checks": copy.deepcopy(preflight_receipt["required_checks"]),
    }


def test_exact_head_dry_run_preflight_passes() -> None:
    receipt = preflight(_manifest(), _live_snapshot(), dry_run=True)

    assert receipt["status"] == "PASS"
    assert receipt["phase"] == "preflight"
    assert receipt["dry_run"] is True
    assert receipt["base_sha"] == BASE_SHA
    assert receipt["head_sha"] == HEAD_SHA
    assert receipt["head_tree"] == HEAD_TREE
    assert isinstance(receipt["cas_token"], str)
    assert len(receipt["cas_token"]) == 64


def test_stale_head_fails_closed() -> None:
    snapshot = _live_snapshot()
    snapshot["head_sha"] = "9" * 40

    with pytest.raises(GuardError, match="snapshot.head_sha: stale or drifted"):
        preflight(_manifest(), snapshot, dry_run=True)


def test_base_drift_fails_closed() -> None:
    snapshot = _live_snapshot()
    snapshot["base_sha"] = "8" * 40

    with pytest.raises(GuardError, match="snapshot.base_sha: stale or drifted"):
        preflight(_manifest(), snapshot, dry_run=True)


def test_same_name_check_from_wrong_integration_does_not_satisfy_requirement() -> None:
    snapshot = _live_snapshot()
    checks = copy.deepcopy(snapshot["checks"])
    assert isinstance(checks, list)
    assert isinstance(checks[1], dict)
    checks[1]["integration_id"] = 99999
    snapshot["checks"] = checks

    with pytest.raises(GuardError, match="missing required checks"):
        preflight(_manifest(), snapshot, dry_run=True)


def test_stale_required_check_head_fails_closed() -> None:
    snapshot = _live_snapshot()
    checks = copy.deepcopy(snapshot["checks"])
    assert isinstance(checks, list)
    assert isinstance(checks[0], dict)
    checks[0]["head_sha"] = "7" * 40
    snapshot["checks"] = checks

    with pytest.raises(GuardError, match="stale check head"):
        preflight(_manifest(), snapshot, dry_run=True)


@pytest.mark.parametrize(
    ("status", "conclusion"),
    [("in_progress", None), ("completed", "failure"), ("completed", "cancelled")],
)
def test_non_success_required_check_fails_closed(
    status: str, conclusion: str | None
) -> None:
    snapshot = _live_snapshot()
    checks = copy.deepcopy(snapshot["checks"])
    assert isinstance(checks, list)
    assert isinstance(checks[0], dict)
    checks[0]["status"] = status
    checks[0]["conclusion"] = conclusion
    snapshot["checks"] = checks

    with pytest.raises(GuardError, match="required check not successful"):
        preflight(_manifest(), snapshot, dry_run=True)


def test_duplicate_required_check_fails_closed() -> None:
    snapshot = _live_snapshot()
    checks = copy.deepcopy(snapshot["checks"])
    assert isinstance(checks, list)
    checks.append(copy.deepcopy(checks[0]))
    snapshot["checks"] = checks

    with pytest.raises(GuardError, match="duplicate required check"):
        preflight(_manifest(), snapshot, dry_run=True)


def test_dirty_target_fails_closed() -> None:
    snapshot = _live_snapshot()
    snapshot["target_clean"] = False

    with pytest.raises(GuardError, match="target must be clean"):
        preflight(_manifest(), snapshot, dry_run=True)


def test_changed_manifest_cannot_reuse_preflight_receipt() -> None:
    manifest = _manifest()
    receipt = preflight(manifest, _live_snapshot(), dry_run=False)
    changed = copy.deepcopy(manifest)
    changed["deleted_paths"] = ["nexus/core/nexus_transaction.py"]

    with pytest.raises(GuardError, match="manifest binding drift"):
        post_apply(changed, receipt, _post_snapshot(receipt))


def test_dry_run_receipt_cannot_authorize_post_apply() -> None:
    receipt = preflight(_manifest(), _live_snapshot(), dry_run=True)

    with pytest.raises(GuardError, match="dry-run receipt cannot authorize"):
        post_apply(_manifest(), receipt, _post_snapshot(receipt))


def test_tampered_preflight_snapshot_binding_fails_closed() -> None:
    receipt = preflight(_manifest(), _live_snapshot(), dry_run=False)
    tampered = copy.deepcopy(receipt)
    tampered["snapshot_sha256"] = "f" * 64

    with pytest.raises(GuardError, match="snapshot binding drift"):
        post_apply(_manifest(), tampered, _post_snapshot(receipt))


def test_tampered_preflight_cas_token_fails_closed() -> None:
    receipt = preflight(_manifest(), _live_snapshot(), dry_run=False)
    tampered = copy.deepcopy(receipt)
    tampered["cas_token"] = "f" * 64
    snapshot = _post_snapshot(receipt)
    snapshot["cas_token"] = tampered["cas_token"]

    with pytest.raises(GuardError, match="CAS token binding drift"):
        post_apply(_manifest(), tampered, snapshot)


def test_concurrent_target_movement_fails_closed() -> None:
    receipt = preflight(_manifest(), _live_snapshot(), dry_run=False)
    snapshot = _post_snapshot(receipt)
    snapshot["current_base_sha"] = "6" * 40

    with pytest.raises(GuardError, match="target moved after apply"):
        post_apply(_manifest(), receipt, snapshot)


def test_post_apply_wrong_resulting_tree_fails_closed() -> None:
    receipt = preflight(_manifest(), _live_snapshot(), dry_run=False)
    snapshot = _post_snapshot(receipt)
    snapshot["merge_tree"] = "6" * 40

    with pytest.raises(GuardError, match="resulting tree differs from approved head tree"):
        post_apply(_manifest(), receipt, snapshot)


def test_non_exact_merge_parentage_fails_closed() -> None:
    receipt = preflight(_manifest(), _live_snapshot(), dry_run=False)
    snapshot = _post_snapshot(receipt)
    snapshot["parents"] = [BASE_SHA, "6" * 40]

    with pytest.raises(GuardError, match="concurrent base/head drift or non-exact merge"):
        post_apply(_manifest(), receipt, snapshot)


def test_post_apply_changed_path_inventory_drift_fails_closed() -> None:
    receipt = preflight(_manifest(), _live_snapshot(), dry_run=False)
    snapshot = _post_snapshot(receipt)
    snapshot["changed_paths"] = ["nexus/core/nexus_transaction.py"]

    with pytest.raises(GuardError, match="physical diff drift"):
        post_apply(_manifest(), receipt, snapshot)


def test_post_apply_rejects_deleted_path_that_still_exists() -> None:
    receipt = preflight(_manifest(), _live_snapshot(), dry_run=False)
    snapshot = _post_snapshot(receipt)
    states = copy.deepcopy(snapshot["path_states"])
    assert isinstance(states, dict)
    states["nexus/policy/compatibility.py"] = True
    snapshot["path_states"] = states

    with pytest.raises(GuardError, match="deleted paths still present"):
        post_apply(_manifest(), receipt, snapshot)


def test_post_apply_rejects_cas_token_replay() -> None:
    receipt = preflight(_manifest(), _live_snapshot(), dry_run=False)
    snapshot = _post_snapshot(receipt)
    snapshot["cas_token"] = "0" * 64

    with pytest.raises(GuardError, match="replay or binding drift"):
        post_apply(_manifest(), receipt, snapshot)


def test_post_apply_rechecks_required_check_source() -> None:
    receipt = preflight(_manifest(), _live_snapshot(), dry_run=False)
    snapshot = _post_snapshot(receipt)
    checks = copy.deepcopy(snapshot["checks"])
    assert isinstance(checks, list)
    assert isinstance(checks[1], dict)
    checks[1]["integration_id"] = 99999
    snapshot["checks"] = checks

    with pytest.raises(GuardError, match="missing required checks"):
        post_apply(_manifest(), receipt, snapshot)


def test_exact_post_apply_snapshot_passes() -> None:
    receipt = preflight(_manifest(), _live_snapshot(), dry_run=False)
    post = post_apply(_manifest(), receipt, _post_snapshot(receipt))

    assert post["status"] == "PASS"
    assert post["phase"] == "post_apply"
    assert post["merge_sha"] == MERGE_SHA
    assert post["merge_tree"] == MERGE_TREE
    assert post["cas_token"] == receipt["cas_token"]
