from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

MANIFEST_PATH = Path("docs/reports/policy-manifest.v2.json")
LANES = ("hard", "soft", "shadow")
TEST_POLICY_ID = "P-TEST-NODRILL-01"


def _test_policy() -> dict[str, Any]:
    return {
        "policy_id": TEST_POLICY_ID,
        "phase": "Intake",
        "owner_module": "test_module",
        "source_file": "tests/test_policy_manager.py",
        "schema_version": "v1.0",
        "commit_sha": "1c9dce65",
        "status_tag": "spec-backed",
        "test_entrypoints": ["tests/test_policy_manager.py"],
        "receipt_type": "TestReceipt",
        "rollback_drill_status": "no-drill",
        "promotion_allowed": False,
        "lane": "hard",
        "risk_tier": "low",
        "authority_impact": "none",
        "claim_impact": "none",
        "cutover_impact": "none",
        "override_mode": "allowed_with_receipt",
        "expiry": None,
        "version_history": [
            {
                "version": f"{TEST_POLICY_ID}.1.0.0",
                "timestamp": "2026-06-15T00:00:00Z",
                "diff_summary": "Test policy",
                "lane": "hard",
            }
        ],
    }


def _lane_distribution(policies: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        lane: {
            "count": len(ids),
            "policies": ids,
        }
        for lane in LANES
        if (ids := [str(policy["policy_id"]) for policy in policies if policy.get("lane") == lane])
    }


def update_manifest(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return the deterministic drill fixture projection for one manifest."""
    updated = deepcopy(dict(data))
    raw_policies = updated.get("policies")
    if not isinstance(raw_policies, list):
        raise ValueError("policies_must_be_list")

    policies: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_policy in raw_policies:
        if not isinstance(raw_policy, Mapping):
            raise ValueError("policy_must_be_mapping")
        policy = deepcopy(dict(raw_policy))
        policy_id = policy.get("policy_id")
        if not isinstance(policy_id, str) or not policy_id:
            raise ValueError("policy_id_missing")
        if policy_id == TEST_POLICY_ID:
            continue
        if policy_id in seen:
            raise ValueError(f"duplicate_policy_id:{policy_id}")
        seen.add(policy_id)
        policy["rollback_drill_status"] = "drilled-2026-06-15"
        if policy.get("lane") == "hard" and not policy.get("test_entrypoints"):
            policy["test_entrypoints"] = ["tests/test_policy_manager.py"]
        policies.append(policy)

    policies.append(_test_policy())
    updated["policies"] = policies
    summary_value = updated.get("summary")
    summary = deepcopy(dict(summary_value)) if isinstance(summary_value, Mapping) else {}
    distribution = _lane_distribution(policies)
    summary["total_policies"] = len(policies)
    for lane in LANES:
        summary[f"{lane}_lane"] = distribution.get(lane, {}).get("count", 0)
    summary["lane_distribution"] = distribution
    updated["summary"] = summary
    return updated


def update_manifest_file(path: Path = MANIFEST_PATH) -> None:
    if not path.exists():
        raise FileNotFoundError(f"manifest_not_found:{path}")
    source = json.loads(path.read_text(encoding="utf-8"))
    updated = update_manifest(source)
    path.write_text(
        json.dumps(updated, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    update_manifest_file()
    print("Policy manifest drill fixture reconciled.")


if __name__ == "__main__":
    main()
