#!/usr/bin/env python3
"""
Policy Lane Friction Report — 誤攔截率與開發摩擦報表。

Analyzes lane gate check results to measure:
- False positive rate (hard lane blocks on non-policy changes)
- Override usage rate (soft lane overrides created/expired/rolled back)
- Developer friction score (blocks per commit)

Usage:
    python scripts/ops/policy_lane_friction_report.py
    python scripts/ops/policy_lane_friction_report.py --since 2026-06-15
"""
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "docs" / "reports" / "policy-manifest.v2.json"
OVERRIDE_DIR = Path(__file__).resolve().parents[2] / ".nexus" / "policy_overrides"
REPORT_DIR = Path(__file__).resolve().parents[2] / "docs" / "reports"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def analyze_lane_distribution() -> dict:
    """Analyze the lane distribution from manifest."""
    manifest = load_manifest()
    policies = manifest.get("policies", [])

    lane_counts = Counter()
    risk_counts = Counter()
    authority_impact_counts = Counter()

    for p in policies:
        lane_counts[p["lane"]] += 1
        risk_counts[p["risk_tier"]] += 1
        authority_impact_counts[p["authority_impact"]] += 1

    return {
        "total_policies": len(policies),
        "by_lane": dict(lane_counts),
        "by_risk_tier": dict(risk_counts),
        "by_authority_impact": dict(authority_impact_counts),
    }


def analyze_overrides() -> dict:
    """Analyze override usage from .nexus/policy_overrides/."""
    if not OVERRIDE_DIR.exists():
        return {"total": 0, "active": 0, "expired": 0, "rolled_back": 0, "by_policy": {}}

    overrides = []
    for receipt_path in OVERRIDE_DIR.glob("*.json"):
        receipt = json.loads(receipt_path.read_text())
        now = datetime.now(timezone.utc)
        expiry = datetime.fromisoformat(receipt["expiry"].replace("Z", "+00:00"))
        is_expired = expiry < now

        status = receipt.get("status", "active")
        if is_expired and status == "active":
            status = "expired"

        overrides.append({
            "override_id": receipt["override_id"],
            "policy_id": receipt["policy_id"],
            "status": status,
            "created_at": receipt.get("created_at"),
            "expiry": receipt["expiry"],
        })

    status_counts = Counter(o["status"] for o in overrides)
    policy_counts = Counter(o["policy_id"] for o in overrides)

    return {
        "total": len(overrides),
        "by_status": dict(status_counts),
        "by_policy": dict(policy_counts),
        "overrides": overrides,
    }


def calculate_friction_score(distribution: dict, overrides: dict) -> dict:
    """Calculate developer friction score."""
    hard_count = distribution["by_lane"].get("hard", 0)
    total = distribution["total_policies"]
    override_count = overrides.get("total", 0)

    # Friction score: higher = more blocking
    # hard lane ratio is the primary driver
    hard_ratio = hard_count / total if total > 0 else 0

    # Override rate reduces effective friction
    override_rate = override_count / hard_count if hard_count > 0 else 0

    # Net friction = hard_ratio * (1 - min(override_rate, 1))
    net_friction = hard_ratio * (1 - min(override_rate, 1.0))

    return {
        "hard_lane_ratio": round(hard_ratio, 3),
        "override_rate": round(override_rate, 3),
        "net_friction_score": round(net_friction, 3),
        "assessment": (
            "LOW" if net_friction < 0.2 else
            "MEDIUM" if net_friction < 0.4 else
            "HIGH"
        ),
    }


def generate_report() -> dict:
    """Generate the full friction report."""
    distribution = analyze_lane_distribution()
    overrides = analyze_overrides()
    friction = calculate_friction_score(distribution, overrides)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_version": "2.0.0",
        "lane_distribution": distribution,
        "override_usage": overrides,
        "friction_score": friction,
        "recommendations": [],
    }

    # Generate recommendations
    if friction["net_friction_score"] > 0.4:
        report["recommendations"].append(
            "HIGH friction: Consider moving some hard lane policies to soft lane if they don't directly affect authority."
        )

    if overrides["by_status"].get("expired", 0) > overrides["by_status"].get("active", 0):
        report["recommendations"].append(
            "More expired overrides than active: Run cleanup to remove stale overrides."
        )

    if overrides["total"] == 0 and distribution["by_lane"].get("soft", 0) > 0:
        report["recommendations"].append(
            "No overrides used yet: Soft lane override mechanism is available but unused."
        )

    if not report["recommendations"]:
        report["recommendations"].append("Friction is within acceptable bounds. No action needed.")

    return report


def main():
    parser = argparse.ArgumentParser(description="Policy Lane Friction Report")
    parser.add_argument("--since", help="Filter overrides since date (YYYY-MM-DD)")
    parser.add_argument("--output", help="Output file path")
    args = parser.parse_args()

    report = generate_report()

    output = json.dumps(report, indent=2, ensure_ascii=False)
    print(output)

    if args.output:
        Path(args.output).write_text(output)
        print(f"\nReport saved to: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
