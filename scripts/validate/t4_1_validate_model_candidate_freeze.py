#!/usr/bin/env python3
"""T4.1 Validation: Model Candidate Freeze"""

import json, sys, yaml
from pathlib import Path

NEXUS_ROOT = Path("/Users/jameschen/Workspace/nexus")
RESULTS = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    RESULTS.append({"name": name, "status": status, "detail": detail})
    print(f"  {'✓' if condition else '✗'} {name}" + (f" ({detail})" if detail else ""))
    return condition


def main():
    print("=" * 60)
    print("T4.1: Model Candidate Freeze Validation")
    print("=" * 60)

    # 1. Registry exists
    print("\n[Registry]")
    reg_path = NEXUS_ROOT / "configs/model_candidates/t4_1_frozen_model_candidate_registry.yaml"
    check("registry_exists", reg_path.exists())
    if reg_path.exists():
        reg = yaml.safe_load(reg_path.read_text())
        candidates = reg.get("candidates", [])
        check("has_20_candidates", len(candidates) == 20, f"got {len(candidates)}")

        # 2. All have evidence tier
        all_have_tier = all(c.get("evidence_tier") for c in candidates)
        check("all_have_evidence_tier", all_have_tier)

        # 3. All have source revision status
        all_have_source = all(c.get("source_revision_status") for c in candidates)
        check("all_have_source_revision_status", all_have_source)

        # 4. public_claim_allowed=false for all
        no_public = all(not c.get("public_claim_allowed", False) for c in candidates)
        check("public_claim_allowed_false_all", no_public)

        # 5. export_as_public_claim=false for all
        no_export_public = all(not c.get("export_as_public_claim", False) for c in candidates)
        check("export_as_public_claim_false_all", no_export_public)

        # 6. model_calls=0 cannot have model_patch_reward=1.0
        for c in candidates:
            if c.get("model_calls", 0) == 0 and c.get("model_patch_reward", 0) > 0:
                check("model_calls_0_no_reward", False, c["instance_id"])
        check("model_calls_0_no_reward", True)

        # 7. source-stale not model failure
        for c in candidates:
            if "stale" in c.get("source_revision_status", "") or "patched" in c.get("source_revision_status", ""):
                if c.get("count_as_model_failure", False):
                    check("source_stale_not_model_failure", False, c["instance_id"])
        check("source_stale_not_model_failure", True)

        # 8. Historical clean not active replayable
        for c in candidates:
            if "stale" in c.get("source_revision_status", "") or "patched" in c.get("source_revision_status", ""):
                if c.get("evidence_tier") == "active_replayable":
                    check("historical_clean_not_active", False, c["instance_id"])
        check("historical_clean_not_active", True)

    # 9. T4.2 manifest
    print("\n[T4.2 Manifest]")
    manifest_path = NEXUS_ROOT / "configs/model_candidates/t4_1_t4_2_clean_room_replay_manifest.yaml"
    check("manifest_exists", manifest_path.exists())
    if manifest_path.exists():
        manifest = yaml.safe_load(manifest_path.read_text())
        replay = manifest.get("replay_candidates", [])
        blocked = manifest.get("replay_blocked", [])
        check("manifest_has_replay_candidates", len(replay) > 0, f"{len(replay)}")
        check("manifest_has_blocked", len(blocked) > 0, f"{len(blocked)}")

        # No source_revision_unknown in manifest
        for c in replay:
            if "unknown" in c.get("source_snapshot_hash", ""):
                check("no_unknown_in_manifest", False, c["instance_id"])
        check("no_unknown_in_manifest", True)

    # 10. Reports exist
    print("\n[Reports]")
    check("hygiene_summary_exists", (NEXUS_ROOT / "docs/reports/t4_1_source_revision_hygiene_summary.md").exists())
    check("historical_policy_exists", (NEXUS_ROOT / "docs/reports/t4_1_historical_clean_candidate_policy.md").exists())
    check("export_boundary_exists", (NEXUS_ROOT / "docs/reports/t4_1_export_claim_boundary.md").exists())
    check("freeze_report_exists", (NEXUS_ROOT / "docs/reports/t4_1_model_candidate_evidence_freeze.md").exists())

    # Summary
    print(f"\n{'=' * 60}")
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")
    print(f"Results: {passed}/{total} PASS, {failed} FAIL")

    verdict = "GREEN" if failed == 0 else "RED"
    print(f"\nT4.1 Validation Verdict: {verdict}")

    report = {"verdict": verdict, "total": total, "passed": passed, "failed": failed, "checks": RESULTS}
    report_path = NEXUS_ROOT / "artifacts/validation/t4_1_model_candidate_freeze_result.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nReport: {report_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
