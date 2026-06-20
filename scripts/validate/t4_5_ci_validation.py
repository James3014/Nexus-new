#!/usr/bin/env python3
"""T4.5: Registry / Fixture / Export Guard CI Validation"""

import yaml, json, sys
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
    print("T4.5: Registry / Fixture / Export Guard CI Validation")
    print("=" * 60)

    errors = 0

    # 1. Registry v1.2 exists and parses
    reg_path = NEXUS_ROOT / "configs/model_candidates/t4_3_model_candidate_registry_v1_2.yaml"
    print(f"\n[Registry] {reg_path.name}")
    if not reg_path.exists():
        check("registry_exists", False, "v1.2 missing")
        errors += 1
    else:
        try:
            reg = yaml.safe_load(reg_path.read_text())
            check("registry_parses", True)
        except Exception as e:
            check("registry_parses", False, str(e))
            errors += 1
            reg = None

    if reg:
        candidates = reg.get("candidates", [])
        check("6_candidates", len(candidates) == 6, f"got {len(candidates)}")
        ids = [c.get("instance_id", "") for c in candidates]
        check("unique_ids", len(ids) == len(set(ids)))

        # 2. No public claim
        for c in candidates:
            if c.get("public_claim_allowed"):
                check("no_public_claim", False, c["instance_id"])
                errors += 1
        check("no_public_claim", True)

        # 3. Stale source not counted as model failure
        for c in candidates:
            if c.get("fixture_status") == "historical_only" and c.get("fresh_model_patch_reward", 0) > 0:
                check("stale_not_model_failure", False, c["instance_id"])
                errors += 1
        check("stale_not_model_failure", True)

    # 4. Fixture manifest
    fm_path = NEXUS_ROOT / "configs/model_candidates/t4_3_replay_fixture_manifest.yaml"
    print(f"\n[Fixture] {fm_path.name}")
    if fm_path.exists():
        try:
            fm = yaml.safe_load(fm_path.read_text())
            check("fixture_parses", True)
            fc = fm.get("candidates", [])
            check("fixture_6_candidates", len(fc) == 6, f"got {len(fc)}")
            ready = sum(1 for c in fc if c.get("fixture_ready"))
            check("fixture_ready_count", ready >= 2, f"{ready}")
        except Exception as e:
            check("fixture_parses", False, str(e))
            errors += 1
    else:
        check("fixture_exists", False)
        errors += 1

    # 5. Export guard
    print(f"\n[Export Guard]")
    if reg:
        no_export_public = all(not c.get("export_as_public_claim", False) for c in candidates)
        check("no_export_as_public_claim", no_export_public)
        no_export_model_stale = True
        for c in candidates:
            if c.get("fixture_status") == "historical_only" and c.get("export_as_model_patch_success", False):
                no_export_model_stale = False
                check("stale_not_exported", False, c["instance_id"])
                errors += 1
        check("stale_not_exported", no_export_model_stale)

    # 6. Historical-only exclusion
    print(f"\n[Exclusion Guard]")
    if reg:
        excluded = [c for c in candidates if c.get("fixture_status") == "historical_only"]
        check("historical_only_classified", len(excluded) >= 2, f"{len(excluded)}")
        for c in excluded:
            if c.get("t4_4_replay_eligible"):
                check("excluded_not_replay_eligible", False, c["instance_id"])
                errors += 1
        check("excluded_not_replay_eligible", True)

    # 7. T4.2 replay report
    print(f"\n[T4.2 Evidence]")
    replay_path = NEXUS_ROOT / ".nexus/reports/local_heal/T4_4_FIXTURE_BACKED_REPLAY/summary.json"
    if replay_path.exists():
        summary = json.loads(replay_path.read_text())
        check("t4_4_summary_exists", True)
        check("t4_4_green", summary.get("verdict") == "GREEN", summary.get("verdict"))
    else:
        check("t4_4_summary_exists", False)
        errors += 1

    # Summary
    print(f"\n{'=' * 60}")
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")
    print(f"Results: {passed}/{total} PASS, {failed} FAIL")

    if failed == 0:
        print("\nT4.5 Verdict: GREEN")
        verdict = "GREEN"
    elif failed <= 2:
        print("\nT4.5 Verdict: YELLOW")
        verdict = "YELLOW"
    else:
        print("\nT4.5 Verdict: RED")
        verdict = "RED"

    # Write validation report
    report = {"verdict": verdict, "total": total, "passed": passed, "failed": failed, "checks": RESULTS}
    report_path = NEXUS_ROOT / ".nexus/reports/local_heal/T4_5_CI_VALIDATION/summary.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nReport: {report_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
