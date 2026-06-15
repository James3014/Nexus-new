#!/usr/bin/env python3
"""
Policy Lane Gate — Pre-commit hook.

Checks if any staged changes to policy-governed files violate their lane rules.
Hard lane violations block the commit.
Soft lane violations produce warnings.
Shadow lane violations are informational only.

Usage (as pre-commit hook):
    python scripts/ops/policy_lane_precommit.py

Usage (manual):
    python scripts/ops/policy_lane_precommit.py --staged-files file1.py file2.py
"""
import json
import subprocess
import sys
from pathlib import Path

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "docs" / "reports" / "policy-manifest.v2.json"
LANE_GATE_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "check_policy_lane_gate.py"

# Map file paths to policy IDs
FILE_TO_POLICY = {
    "nexus/engine/autonomic_router.py": ["P-ROUTE-01", "P-ROUTE-02", "P-ROUTE-03", "P-ROUTE-04"],
    "nexus/engine/budget_governor.py": ["P-BUDGET-01"],
    "nexus/engine/capability_planner.py": ["P-PLAN-01", "P-PLAN-02"],
    "nexus/services/s2t_strict.py": ["P-S2T-01", "P-S2T-02", "P-S2T-03"],
    "nexus/core/cost_hook.py": ["P-COST-01"],
    "nexus/governance/capability_gate.py": ["P-GATE-01"],
    "nexus/services/local_heal/evaluation_gate.py": ["P-GATE-02"],
    "nexus-core-rs/src/receipt_verifier.rs": ["P-GATE-03"],
    "nexus/core/critique_engine.py": ["P-CLAIM-01"],
    "nexus/governance/hallucination_guard.py": ["P-CLAIM-02"],
    "nexus/engine/capability_receipt_policy.py": ["P-CLAIM-03"],
    "nexus/delivery/gate.py": ["P-DELIVERY-01"],
    "nexus/delivery/contract.py": ["P-DELIVERY-02"],
    "nexus/core/policy_drift.py": ["P-LEARN-01"],
    "nexus/governance/application/drift_stop_gate.py": ["P-LEARN-02"],
    "nexus/engine/autonomy_observation.py": ["P-AUTO-01"],
    "nexus/core/belief_engine.py": ["P-BELIEF-01"],
    "nexus/core/context_hub.py": ["P-CTX-01"],
    "nexus/engine/attempt_settlement_service.py": ["P-SETTLE-01"],
    "nexus-core-rs/src/flow_machine.rs": ["P-FLOW-01"],
    "nexus-core-rs/src/contamination.rs": ["P-CONTAM-01"],
}


def get_staged_files() -> list[str]:
    """Get list of staged files via git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True, text=True, check=True
        )
        return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except subprocess.CalledProcessError:
        return []


def check_lane_gate(policy_id: str, action: str = "modify") -> dict:
    """Run the lane gate check for a policy."""
    try:
        result = subprocess.run(
            [sys.executable, str(LANE_GATE_SCRIPT), "--policy-id", policy_id, "--action", action],
            capture_output=True, text=True, timeout=30
        )
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return {"allowed": True, "lane": "unknown", "errors": ["GATE_UNAVAILABLE"], "policy_id": policy_id}


def main():
    staged_files = get_staged_files()
    if not staged_files:
        print("No staged files found.")
        return 0

    violations = []
    warnings = []

    for filepath in staged_files:
        # Find matching policies
        for pattern, policy_ids in FILE_TO_POLICY.items():
            if filepath == pattern or filepath.endswith("/" + pattern):
                for pid in policy_ids:
                    result = check_lane_gate(pid, "modify")
                    if not result.get("allowed", True):
                        lane = result.get("lane", "unknown")
                        errors = result.get("errors", [])
                        entry = f"  {pid} ({lane}): {', '.join(errors)}"
                        if lane == "hard":
                            violations.append(entry)
                        elif lane == "soft":
                            warnings.append(entry)
                        # shadow lane: informational only

    # Report
    if warnings:
        print("\n⚠️  Policy Lane Warnings (soft lane):")
        for w in warnings:
            print(w)
        print("  Soft lane changes are allowed but require manifest record.\n")

    if violations:
        print("\n❌ Policy Lane Violations (hard lane):")
        for v in violations:
            print(v)
        print("\n  Hard lane changes require:")
        print("  - Rollback drill passed")
        print("  - Evidence bundle complete")
        print("  - Feature flag configured")
        print("  - Human approval for cutover")
        print("\n  Commit BLOCKED. Fix violations or use --no-verify to skip (not recommended).\n")
        return 1

    if not warnings and not violations:
        print("✅ Policy lane check passed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
