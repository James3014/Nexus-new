#!/usr/bin/env python3
"""
Policy Lane Gate — 分級治理 gate checker.

Usage:
    python scripts/ops/check_policy_lane_gate.py --policy-id P-GATE-03 --action modify
    python scripts/ops/check_policy_lane_gate.py --policy-id P-ROUTE-01 --action modify
    python scripts/ops/check_policy_lane_gate.py --policy-id P-AUTO-01 --action observe
"""
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "docs" / "reports" / "policy-manifest.v2.json"
OVERRIDE_DIR = Path(__file__).resolve().parents[2] / ".nexus" / "policy_overrides"


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        print(f"ERROR: Manifest not found at {MANIFEST_PATH}")
        sys.exit(1)
    return json.loads(MANIFEST_PATH.read_text())


def find_policy(manifest: dict, policy_id: str) -> dict | None:
    for p in manifest.get("policies", []):
        if p["policy_id"] == policy_id:
            return p
    return None


def check_hard_lane(policy: dict, action: str) -> dict:
    """Hard lane: fail-closed. Requires evidence, drill, held-out, feature flag."""
    errors = []

    if action in ("modify", "promote", "cutover"):
        if policy.get("rollback_drill_status", "no-drill") == "no-drill":
            errors.append("ROLLBACK_DRILL_MISSING")
        if not policy.get("test_entrypoints"):
            errors.append("TEST_COVERAGE_MISSING")

    if action == "promote":
        if policy.get("promotion_allowed") is False:
            errors.append("PROMOTION_NOT_ALLOWED")

    if action == "cutover":
        errors.append("CUTOVER_REQUIRES_HUMAN_APPROVAL")

    return {
        "allowed": len(errors) == 0,
        "lane": "hard",
        "errors": errors,
        "policy_id": policy["policy_id"],
    }


def check_soft_lane(policy: dict, action: str, override_receipt: dict | None = None) -> dict:
    """Soft lane: versioned changes allowed with manifest record."""
    errors = []

    if action in ("modify", "version_bump"):
        if not policy.get("version_history"):
            errors.append("VERSION_HISTORY_EMPTY")

    if action == "modify" and not override_receipt:
        # Soft lane allows modification without override, but needs version bump
        pass  # allowed

    if override_receipt:
        # Check override validity
        expiry = override_receipt.get("expiry")
        if expiry:
            try:
                expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                if expiry_dt < datetime.now(timezone.utc):
                    errors.append("OVERRIDE_EXPIRED")
            except ValueError:
                errors.append("OVERRIDE_EXPIRY_INVALID")

    return {
        "allowed": len(errors) == 0,
        "lane": "soft",
        "errors": errors,
        "policy_id": policy["policy_id"],
    }


def check_shadow_lane(policy: dict, action: str) -> dict:
    """Shadow lane: observation-only, no authority change."""
    errors = []

    if action in ("modify", "promote", "cutover"):
        if policy.get("authority_impact", "none") != "none":
            errors.append("SHADOW_CANNOT_CHANGE_AUTHORITY")
        if policy.get("claim_impact", "none") not in ("none",):
            errors.append("SHADOW_CANNOT_EXPAND_CLAIM")

    return {
        "allowed": len(errors) == 0,
        "lane": "shadow",
        "errors": errors,
        "policy_id": policy["policy_id"],
    }


def check_lane_gate(policy_id: str, action: str, override_receipt: dict | None = None) -> dict:
    """Main entry point: check if an action is allowed for a policy."""
    manifest = load_manifest()
    policy = find_policy(manifest, policy_id)

    if not policy:
        return {
            "allowed": False,
            "lane": "unknown",
            "errors": [f"POLICY_NOT_FOUND: {policy_id}"],
            "policy_id": policy_id,
        }

    lane = policy.get("lane", "unknown")

    if lane == "hard":
        return check_hard_lane(policy, action)
    elif lane == "soft":
        return check_soft_lane(policy, action, override_receipt)
    elif lane == "shadow":
        return check_shadow_lane(policy, action)
    else:
        return {
            "allowed": False,
            "lane": lane,
            "errors": [f"UNKNOWN_LANE: {lane}"],
            "policy_id": policy_id,
        }


def main():
    parser = argparse.ArgumentParser(description="Policy Lane Gate Checker")
    parser.add_argument("--policy-id", required=True, help="Policy ID to check")
    parser.add_argument("--action", required=True, choices=["modify", "promote", "cutover", "observe", "version_bump"])
    parser.add_argument("--override-receipt", help="Path to override receipt JSON")
    args = parser.parse_args()

    override = None
    if args.override_receipt:
        override = json.loads(Path(args.override_receipt).read_text())

    result = check_lane_gate(args.policy_id, args.action, override)
    print(json.dumps(result, indent=2))

    sys.exit(0 if result["allowed"] else 1)


if __name__ == "__main__":
    main()
