#!/usr/bin/env python3
"""
Policy Override Receipt Checker — 驗證 override receipt 的合法性。

Usage:
    python scripts/ops/check_policy_override_receipt.py --receipt-path .nexus/policy_overrides/OVR-001.json
    python scripts/ops/check_policy_override_receipt.py --policy-id P-COST-01 --check-expiry
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


def validate_override_receipt(receipt: dict) -> dict:
    """Validate an override receipt for completeness and legality."""
    errors = []

    # Required fields
    required_fields = ["override_id", "policy_id", "lane", "who", "why", "scope", "expiry", "rollback_plan", "created_at"]
    for field in required_fields:
        if field not in receipt:
            errors.append(f"MISSING_FIELD: {field}")

    # Lane check: hard lane cannot be overridden
    lane = receipt.get("lane")
    if lane == "hard":
        errors.append("HARD_LANE_OVERRIDE_BLOCKED")

    # Expiry check
    expiry = receipt.get("expiry")
    if expiry:
        try:
            expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            if expiry_dt < datetime.now(timezone.utc):
                errors.append("OVERRIDE_EXPIRED")
        except ValueError:
            errors.append("OVERRIDE_EXPIRY_INVALID")

    # Manifest cross-check
    manifest = load_manifest()
    policy_id = receipt.get("policy_id")
    policy = find_policy(manifest, policy_id)
    if not policy:
        errors.append(f"POLICY_NOT_FOUND: {policy_id}")
    elif policy.get("lane") == "hard":
        errors.append("POLICY_IS_HARD_LANE_NO_OVERRIDE")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "receipt_id": receipt.get("override_id"),
        "policy_id": policy_id,
        "lane": lane,
    }


def check_policy_overrides(policy_id: str) -> dict:
    """Check if a policy has any active overrides."""
    if not OVERRIDE_DIR.exists():
        return {"has_active_override": False, "overrides": []}

    active = []
    for receipt_file in OVERRIDE_DIR.glob("*.json"):
        try:
            receipt = json.loads(receipt_file.read_text())
            if receipt.get("policy_id") != policy_id:
                continue
            validation = validate_override_receipt(receipt)
            if validation["valid"]:
                active.append({
                    "receipt_id": receipt.get("override_id"),
                    "expiry": receipt.get("expiry"),
                    "who": receipt.get("who"),
                    "why": receipt.get("why"),
                })
        except (json.JSONDecodeError, KeyError):
            continue

    return {
        "has_active_override": len(active) > 0,
        "overrides": active,
    }


def main():
    parser = argparse.ArgumentParser(description="Policy Override Receipt Checker")
    parser.add_argument("--receipt-path", help="Path to override receipt JSON")
    parser.add_argument("--policy-id", help="Policy ID to check overrides for")
    parser.add_argument("--check-expiry", action="store_true", help="Check if overrides are expired")
    args = parser.parse_args()

    if args.receipt_path:
        receipt = json.loads(Path(args.receipt_path).read_text())
        result = validate_override_receipt(receipt)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["valid"] else 1)

    elif args.policy_id:
        result = check_policy_overrides(args.policy_id)
        print(json.dumps(result, indent=2))
        sys.exit(0 if not result["has_active_override"] else 1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
