from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops.update_manifest_drills import (
    LANES,
    TEST_POLICY_ID,
    update_manifest,
    update_manifest_file,
)


def _source_manifest() -> dict:
    return {
        "manifest_version": "2.0.0",
        "policies": [
            {"policy_id": "P-HARD-01", "lane": "hard", "test_entrypoints": []},
            {"policy_id": "P-SOFT-01", "lane": "soft"},
            {"policy_id": TEST_POLICY_ID, "lane": "hard"},
        ],
        "summary": {
            "hard_lane": 99,
            "lane_distribution": {"hard": {"count": 99, "policies": []}},
        },
    }


def test_updater_is_idempotent_and_keeps_one_test_fixture() -> None:
    first = update_manifest(_source_manifest())
    second = update_manifest(first)

    assert second == first
    ids = [policy["policy_id"] for policy in second["policies"]]
    assert len(ids) == len(set(ids))
    assert ids.count(TEST_POLICY_ID) == 1


def test_summary_and_lane_distribution_are_exact_policy_projections() -> None:
    updated = update_manifest(_source_manifest())
    policies = updated["policies"]
    summary = updated["summary"]

    assert summary["total_policies"] == len(policies)
    for lane in LANES:
        expected = [policy["policy_id"] for policy in policies if policy["lane"] == lane]
        assert summary[f"{lane}_lane"] == len(expected)
        projection = summary["lane_distribution"].get(lane, {"count": 0, "policies": []})
        assert projection == {"count": len(expected), "policies": expected}


def test_second_file_update_is_byte_identical(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_source_manifest()), encoding="utf-8")

    update_manifest_file(path)
    first = path.read_bytes()
    update_manifest_file(path)

    assert path.read_bytes() == first


_MISSING = object()


@pytest.mark.parametrize(
    "status",
    [
        "drilled-2026-10-15",
        "drilled-2026-06-15",
        "drilled-2026-07-01",
    ],
    ids=["newer-real-drill", "older-real-drill", "other-date-real-drill"],
)
def test_existing_real_drill_status_is_preserved(status: str) -> None:
    manifest = _source_manifest()
    for policy in manifest["policies"]:
        if policy["policy_id"] == "P-HARD-01":
            policy["rollback_drill_status"] = status
            break
    updated = update_manifest(manifest)
    p_hard = next(p for p in updated["policies"] if p["policy_id"] == "P-HARD-01")
    assert p_hard.get("rollback_drill_status") == status


@pytest.mark.parametrize(
    "raw_status",
    [
        _MISSING,
        None,
        "",
        "no-drill",
        "drilled-soon",
        "drilled-2026-13-45",
        "DRILLED-2026-10-15",
    ],
    ids=[
        "missing",
        "null",
        "empty",
        "no-drill",
        "garbage-text",
        "invalid-calendar-date",
        "wrong-case",
    ],
)
def test_missing_or_invalid_drill_status_is_filled(raw_status: object) -> None:
    manifest = _source_manifest()
    for policy in manifest["policies"]:
        if policy["policy_id"] == "P-HARD-01":
            if raw_status is _MISSING:
                policy.pop("rollback_drill_status", None)
            else:
                policy["rollback_drill_status"] = raw_status
            break
    updated = update_manifest(manifest)
    p_hard = next(p for p in updated["policies"] if p["policy_id"] == "P-HARD-01")
    assert p_hard.get("rollback_drill_status") == "drilled-2026-06-15"


def test_updater_on_tmp_copy_of_real_manifest_keeps_real_drills(tmp_path: Path) -> None:
    from scripts.ops.check_policy_lane_gate import _is_drilled

    repo_root = Path(__file__).resolve().parents[2]
    real_manifest_path = repo_root / "docs" / "reports" / "policy-manifest.v2.json"
    real_manifest_bytes = real_manifest_path.read_bytes()
    real_manifest = json.loads(real_manifest_bytes.decode("utf-8"))

    tmp_copy = tmp_path / "manifest.json"
    tmp_copy.write_bytes(real_manifest_bytes)

    before = {
        policy["policy_id"]: policy.get("rollback_drill_status")
        for policy in real_manifest.get("policies", [])
        if _is_drilled(policy.get("rollback_drill_status"))
    }
    assert before, "Expected non-empty set of policies with real drill status"
    assert any(status != "drilled-2026-06-15" for status in before.values()), (
        "Expected at least one policy with status != 'drilled-2026-06-15'"
    )

    update_manifest_file(tmp_copy)

    after_manifest = json.loads(tmp_copy.read_text(encoding="utf-8"))
    after_policies = {p["policy_id"]: p for p in after_manifest.get("policies", [])}

    for policy_id, expected_status in before.items():
        assert policy_id in after_policies
        assert after_policies[policy_id].get("rollback_drill_status") == expected_status

    assert real_manifest_path.read_bytes() == real_manifest_bytes


def test_updater_is_idempotent_on_preserved_statuses() -> None:
    manifest = _source_manifest()
    for policy in manifest["policies"]:
        if policy["policy_id"] == "P-HARD-01":
            policy["rollback_drill_status"] = "drilled-2026-10-15"
            break
    first = update_manifest(manifest)
    second = update_manifest(first)
    assert second == first
