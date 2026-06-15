#!/usr/bin/env python3
"""
Policy Override Lifecycle Manager — soft lane override 完整流程。

Commands:
    create   — 建立 override receipt
    check    — 檢查 override 是否有效/過期
    expire   — 手動過期 override
    rollback — 回退到 override 前的版本
    list     — 列出所有 active overrides
    cleanup  — 移除過期 overrides

Usage:
    python scripts/ops/policy_override_lifecycle.py create \
        --policy-id P-COST-01 \
        --who "agent" \
        --why "Cost model tuning for benchmark" \
        --scope "COST_MODEL.read_file adjustment" \
        --expiry "2026-06-16T00:00:00Z" \
        --rollback-target "P-COST-01.1.0.0"

    python scripts/ops/policy_override_lifecycle.py check --override-id OVR-2026-06-15-001
    python scripts/ops/policy_override_lifecycle.py list
    python scripts/ops/policy_override_lifecycle.py cleanup
"""
import json
import sys
import argparse
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

OVERRIDE_DIR = Path(__file__).resolve().parents[2] / ".nexus" / "policy_overrides"
MANIFEST_PATH = Path(__file__).resolve().parents[2] / "docs" / "reports" / "policy-manifest.v2.json"


def ensure_dirs():
    OVERRIDE_DIR.mkdir(parents=True, exist_ok=True)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def save_manifest(manifest: dict):
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def generate_override_id(policy_id: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    h = hashlib.sha256(f"{policy_id}:{ts}".encode()).hexdigest()[:8]
    return f"OVR-{ts}-{h}"


def find_policy(manifest: dict, policy_id: str) -> dict | None:
    for p in manifest.get("policies", []):
        if p["policy_id"] == policy_id:
            return p
    return None


def find_version_history(manifest: dict, policy_id: str, version: str) -> dict | None:
    policy = find_policy(manifest, policy_id)
    if not policy:
        return None
    for v in policy.get("version_history", []):
        if v.get("version") == version:
            return v
    return None


# ─── Commands ──────────────────────────────────────────────────────────

def cmd_create(args):
    """Create a new override receipt."""
    ensure_dirs()
    manifest = load_manifest()
    policy = find_policy(manifest, args.policy_id)

    if not policy:
        print(json.dumps({"error": f"Policy not found: {args.policy_id}"}))
        sys.exit(1)

    if policy.get("lane") == "hard":
        print(json.dumps({"error": "HARD_LANE_OVERRIDE_BLOCKED", "policy_id": args.policy_id}))
        sys.exit(1)

    override_id = generate_override_id(args.policy_id)
    receipt = {
        "override_id": override_id,
        "policy_id": args.policy_id,
        "lane": policy["lane"],
        "who": args.who,
        "why": args.why,
        "scope": args.scope,
        "expiry": args.expiry,
        "rollback_plan": args.rollback_target,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "active"
    }

    receipt_path = OVERRIDE_DIR / f"{override_id}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2))

    # Record in manifest version history
    current_version = policy.get("schema_version", "v0.0")
    version_num = f"{policy['policy_id']}.{current_version.lstrip('v')}.override"
    version_record = {
        "version": version_num,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "diff_summary": f"Override applied: {args.why}",
        "lane": policy["lane"],
        "override_id": override_id
    }
    policy.setdefault("version_history", []).append(version_record)
    save_manifest(manifest)

    print(json.dumps({
        "status": "created",
        "override_id": override_id,
        "receipt_path": str(receipt_path),
        "policy_id": args.policy_id,
        "expiry": args.expiry,
        "rollback_target": args.rollback_target
    }, indent=2))


def cmd_check(args):
    """Check if an override is valid and not expired."""
    receipt_path = OVERRIDE_DIR / f"{args.override_id}.json"
    if not receipt_path.exists():
        print(json.dumps({"error": f"Override not found: {args.override_id}"}))
        sys.exit(1)

    receipt = json.loads(receipt_path.read_text())
    now = datetime.now(timezone.utc)
    expiry = datetime.fromisoformat(receipt["expiry"].replace("Z", "+00:00"))

    is_expired = expiry < now
    remaining_hours = (expiry - now).total_seconds() / 3600

    result = {
        "override_id": args.override_id,
        "policy_id": receipt["policy_id"],
        "status": "expired" if is_expired else "active",
        "expiry": receipt["expiry"],
        "remaining_hours": round(remaining_hours, 1),
        "who": receipt["who"],
        "why": receipt["why"],
        "rollback_target": receipt["rollback_plan"]
    }

    if is_expired:
        result["action"] = "OVERRIDE_EXPIRED — rollback recommended"
        result["auto_rollback_command"] = (
            f"python scripts/ops/policy_override_lifecycle.py rollback "
            f"--override-id {args.override_id}"
        )

    print(json.dumps(result, indent=2))
    sys.exit(0 if not is_expired else 1)


def cmd_expire(args):
    """Manually expire an override."""
    receipt_path = OVERRIDE_DIR / f"{args.override_id}.json"
    if not receipt_path.exists():
        print(json.dumps({"error": f"Override not found: {args.override_id}"}))
        sys.exit(1)

    receipt = json.loads(receipt_path.read_text())
    receipt["status"] = "expired"
    receipt["expired_at"] = datetime.now(timezone.utc).isoformat()
    receipt_path.write_text(json.dumps(receipt, indent=2))

    print(json.dumps({"status": "expired", "override_id": args.override_id}))


def cmd_rollback(args):
    """Rollback to the previous version specified in the override."""
    receipt_path = OVERRIDE_DIR / f"{args.override_id}.json"
    if not receipt_path.exists():
        print(json.dumps({"error": f"Override not found: {args.override_id}"}))
        sys.exit(1)

    receipt = json.loads(receipt_path.read_text())
    manifest = load_manifest()
    policy = find_policy(manifest, receipt["policy_id"])

    if not policy:
        print(json.dumps({"error": f"Policy not found: {receipt['policy_id']}"}))
        sys.exit(1)

    # Find the rollback target version
    rollback_target = receipt["rollback_plan"]
    target_version = find_version_history(manifest, receipt["policy_id"], rollback_target)

    if not target_version:
        print(json.dumps({"error": f"Rollback target not found: {rollback_target}"}))
        sys.exit(1)

    # Record rollback event in version history
    rollback_record = {
        "version": f"{receipt['policy_id']}.rollback",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "diff_summary": f"Rollback from override {args.override_id} to {rollback_target}",
        "lane": policy["lane"],
        "rollback_from": args.override_id,
        "rollback_to": rollback_target
    }
    policy.setdefault("version_history", []).append(rollback_record)
    save_manifest(manifest)

    # Mark override as rolled back
    receipt["status"] = "rolled_back"
    receipt["rolled_back_at"] = datetime.now(timezone.utc).isoformat()
    receipt_path.write_text(json.dumps(receipt, indent=2))

    print(json.dumps({
        "status": "rolled_back",
        "override_id": args.override_id,
        "policy_id": receipt["policy_id"],
        "rollback_to": rollback_target
    }, indent=2))


def cmd_list(args):
    """List all active overrides."""
    ensure_dirs()
    overrides = []
    for receipt_path in OVERRIDE_DIR.glob("*.json"):
        receipt = json.loads(receipt_path.read_text())
        now = datetime.now(timezone.utc)
        expiry = datetime.fromisoformat(receipt["expiry"].replace("Z", "+00:00"))
        is_expired = expiry < now

        overrides.append({
            "override_id": receipt["override_id"],
            "policy_id": receipt["policy_id"],
            "status": "expired" if is_expired else receipt.get("status", "active"),
            "who": receipt["who"],
            "why": receipt["why"],
            "expiry": receipt["expiry"],
            "remaining_hours": round((expiry - now).total_seconds() / 3600, 1)
        })

    # Sort: active first, then by expiry
    overrides.sort(key=lambda x: (x["status"] != "active", x["expiry"]))

    print(json.dumps({"overrides": overrides, "total": len(overrides)}, indent=2))


def cmd_cleanup(args):
    """Remove expired override receipts."""
    ensure_dirs()
    removed = []
    for receipt_path in OVERRIDE_DIR.glob("*.json"):
        receipt = json.loads(receipt_path.read_text())
        now = datetime.now(timezone.utc)
        expiry = datetime.fromisoformat(receipt["expiry"].replace("Z", "+00:00"))

        if expiry < now and receipt.get("status") != "rolled_back":
            receipt_path.unlink()
            removed.append(receipt["override_id"])

    print(json.dumps({"removed": removed, "count": len(removed)}, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Policy Override Lifecycle Manager")
    subparsers = parser.add_subparsers(dest="command")

    # create
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--policy-id", required=True)
    create_parser.add_argument("--who", required=True)
    create_parser.add_argument("--why", required=True)
    create_parser.add_argument("--scope", required=True)
    create_parser.add_argument("--expiry", required=True)
    create_parser.add_argument("--rollback-target", required=True)

    # check
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--override-id", required=True)

    # expire
    expire_parser = subparsers.add_parser("expire")
    expire_parser.add_argument("--override-id", required=True)

    # rollback
    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("--override-id", required=True)

    # list
    subparsers.add_parser("list")

    # cleanup
    subparsers.add_parser("cleanup")

    args = parser.parse_args()

    if args.command == "create":
        cmd_create(args)
    elif args.command == "check":
        cmd_check(args)
    elif args.command == "expire":
        cmd_expire(args)
    elif args.command == "rollback":
        cmd_rollback(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "cleanup":
        cmd_cleanup(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
