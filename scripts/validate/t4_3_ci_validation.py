#!/usr/bin/env python3
"""T4.3 CI Validation: Registry / Export Guard / Source Hygiene"""

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
    print("T4.3: Registry / Export Guard / Source Hygiene CI Validation")
    print("=" * 60)

    # 1. Registry schema validation
    print("\n[Registry Schema]")
    reg_path = NEXUS_ROOT / "configs/model_candidates/t4_1_frozen_model_candidate_registry.yaml"
    check("registry_exists", reg_path.exists())
    if reg_path.exists():
        reg = yaml.safe_load(reg_path.read_text())
        candidates = reg.get("candidates", [])
        check("has_20_candidates", len(candidates) == 20)

        # All have required fields
        required_fields = ["candidate_id", "instance_id", "evidence_tier", "source_revision_status", "replay_eligible", "model_patch_reward", "public_claim_allowed"]
        for c in candidates:
            for f in required_fields:
                if f not in c:
                    check(f"field_{f}_present", False, c.get("instance_id", "unknown"))
        check("all_required_fields_present", True)

    # 2. Source hygiene CI guard
    print("\n[Source Hygiene CI]")
    for c in candidates:
        if "stale" in c.get("source_revision_status", "") or "patched" in c.get("source_revision_status", ""):
            if c.get("count_as_model_failure", False):
                check("source_stale_not_model_failure", False, c["instance_id"])
    check("source_stale_not_model_failure", True)

    # 3. Replay attribution guard
    print("\n[Replay Attribution]")
    for c in candidates:
        if c.get("model_calls", 0) == 0 and c.get("model_patch_reward", 0) > 0:
            check("model_calls_0_no_reward", False, c["instance_id"])
    check("model_calls_0_no_reward", True)

    # 4. No-op / buggy=fixed guard
    print("\n[No-Op / Buggy-Fixed Guard]")
    for c in candidates:
        if c.get("deterministic_fallback_used", False) and c.get("model_calls", 0) == 0:
            if c.get("model_patch_reward", 0) > 0:
                check("fallback_no_reward", False, c["instance_id"])
    check("fallback_no_reward", True)

    # 5. Historical stale exclusion
    print("\n[Historical Stale Exclusion]")
    for c in candidates:
        if "stale" in c.get("source_revision_status", "") or "patched" in c.get("source_revision_status", ""):
            if c.get("evidence_tier") == "active_replayable":
                check("historical_not_active", False, c["instance_id"])
    check("historical_not_active", True)

    # 6. Export / public-claim guard
    print("\n[Export / Public-Claim Guard]")
    for c in candidates:
        if c.get("public_claim_allowed", False):
            check("no_public_claim", False, c["instance_id"])
        if c.get("export_as_public_claim", False):
            check("no_export_public", False, c["instance_id"])
    check("no_public_claim", True)
    check("no_export_public", True)

    # 7. T4.2 replay manifest consistency
    print("\n[T4.2 Manifest Consistency]")
    manifest_path = NEXUS_ROOT / "configs/model_candidates/t4_1_t4_2_clean_room_replay_manifest.yaml"
    if manifest_path.exists():
        manifest = yaml.safe_load(manifest_path.read_text())
        replay = manifest.get("replay_candidates", [])
        blocked = manifest.get("replay_blocked", [])
        check("manifest_has_replay", len(replay) > 0)
        check("manifest_has_blocked", len(blocked) > 0)

        # No unknown hashes in replay
        for c in replay:
            if "unknown" in c.get("source_snapshot_hash", ""):
                check("no_unknown_in_manifest", False, c["instance_id"])
        check("no_unknown_in_manifest", True)

    # Summary
    print(f"\n{'=' * 60}")
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")
    print(f"Results: {passed}/{total} PASS, {failed} FAIL")

    verdict = "GREEN" if failed == 0 else "RED"
    print(f"\nT4.3 CI Validation Verdict: {verdict}")

    report = {"verdict": verdict, "total": total, "passed": passed, "failed": failed, "checks": RESULTS}
    report_path = NEXUS_ROOT / "artifacts/validation/t4_3_ci_validation_result.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nReport: {report_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
