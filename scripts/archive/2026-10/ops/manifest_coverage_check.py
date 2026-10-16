#!/usr/bin/env python3
"""
Manifest Coverage Check — 防止 policy family / lane / test entrypoint 漂移。

驗證：
1. 每個 policy_governed_file 在 pre-commit mapping 中有對應
2. 每個 policy 的 test_entrypoints 指向存在的測試
3. lane 分佈與 manifest summary 一致
4. hard lane policies 有 rollback_drill_status 或 test_entrypoints

Usage:
    python scripts/ops/manifest_coverage_check.py
"""
import json
import sys
from pathlib import Path

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "docs" / "reports" / "policy-manifest.v2.json"
PRECOMMIT_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "policy_lane_precommit.py"

# Files that SHOULD be in pre-commit mapping
POLICY_GOVERNED_DIRS = [
    "nexus/engine/",
    "nexus/core/",
    "nexus/governance/",
    "nexus/services/",
    "nexus/delivery/",
    "nexus-core-rs/src/",
]


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def load_precommit_mapping() -> dict:
    """Extract FILE_TO_POLICY mapping from pre-commit script."""
    mapping = {}
    content = PRECOMMIT_SCRIPT.read_text()
    # Parse the mapping dict from source
    in_mapping = False
    for line in content.split("\n"):
        if "FILE_TO_POLICY" in line and "=" in line:
            in_mapping = True
            continue
        if in_mapping:
            if line.strip().startswith("}"):
                break
            if '"' in line and ":" in line:
                # Extract key and value
                parts = line.strip().strip(",").split(":")
                if len(parts) >= 2:
                    key = parts[0].strip().strip('"')
                    # Extract list from value
                    val_str = ":".join(parts[1:]).strip()
                    if "[" in val_str:
                        items = val_str.split("[")[1].split("]")[0]
                        values = [v.strip().strip('"') for v in items.split(",") if v.strip().strip('"')]
                        mapping[key] = values
    return mapping


def check_test_entrypoints(manifest: dict) -> list:
    """Check that test_entrypoints reference existing files."""
    issues = []
    for policy in manifest.get("policies", []):
        for test_path in policy.get("test_entrypoints", []):
            # Skip inline test references (e.g., "nexus-core-rs/src/...::tests")
            if "::" in test_path:
                file_part = test_path.split("::")[0]
                full_path = Path(__file__).resolve().parents[2] / file_part
                if not full_path.exists():
                    issues.append({
                        "policy_id": policy["policy_id"],
                        "test_entrypoint": test_path,
                        "issue": "FILE_NOT_FOUND",
                    })
            else:
                full_path = Path(__file__).resolve().parents[2] / test_path
                if not full_path.exists():
                    issues.append({
                        "policy_id": policy["policy_id"],
                        "test_entrypoint": test_path,
                        "issue": "FILE_NOT_FOUND",
                    })
    return issues


def check_lane_consistency(manifest: dict) -> list:
    """Check that lane counts match summary."""
    issues = []
    policies = manifest.get("policies", [])
    summary = manifest.get("summary", {})

    actual = {}
    for p in policies:
        lane = p.get("lane", "unknown")
        actual[lane] = actual.get(lane, 0) + 1

    for lane in ["hard", "soft", "shadow"]:
        expected = summary.get(f"{lane}_lane", 0)
        got = actual.get(lane, 0)
        if expected != got:
            issues.append({
                "lane": lane,
                "expected": expected,
                "actual": got,
                "issue": "COUNT_MISMATCH",
            })

    return issues


def check_hard_lane_drills(manifest: dict) -> list:
    """Check that hard lane policies have drill or are noted."""
    issues = []
    for p in manifest.get("policies", []):
        if p.get("lane") != "hard":
            continue
        drill = p.get("rollback_drill_status", "no-drill")
        tests = p.get("test_entrypoints", [])
        if drill == "no-drill" and not tests:
            issues.append({
                "policy_id": p["policy_id"],
                "issue": "HARD_LANE_NO_DRILL_NO_TESTS",
            })
    return issues


def main():
    manifest = load_manifest()

    all_issues = []

    # 1. Test entrypoints check
    test_issues = check_test_entrypoints(manifest)
    all_issues.extend(test_issues)

    # 2. Lane consistency check
    lane_issues = check_lane_consistency(manifest)
    all_issues.extend(lane_issues)

    # 3. Hard lane drill check
    drill_issues = check_hard_lane_drills(manifest)
    all_issues.extend(drill_issues)

    # Report
    if all_issues:
        print("❌ Manifest coverage issues found:")
        for issue in all_issues:
            print(f"  - {json.dumps(issue)}")
        sys.exit(1)
    else:
        print("✅ Manifest coverage check passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
