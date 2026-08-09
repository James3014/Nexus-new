from __future__ import annotations

import json
from pathlib import Path

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
