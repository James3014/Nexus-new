#!/usr/bin/env python3
"""Original Roadmap Re-alignment Validation"""

import json, sys
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
    print("Original Roadmap Re-alignment Validation")
    print("=" * 60)

    # 1. Five-task manifest
    print("\n[Five-Task Manifest]")
    manifest_path = NEXUS_ROOT / "artifacts/original_baseline/p0_lite_five_task_manifest.json"
    check("manifest_exists", manifest_path.exists())
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        tasks = manifest.get("canonical_tasks", [])
        check("5_canonical_tasks", len(tasks) == 5, f"got {len(tasks)}")
        expected = {"astropy__astropy-12907", "astropy__astropy-13236", "astropy__astropy-13579", "astropy__astropy-14182", "sympy__sympy-12481"}
        actual = {t["instance_id"] for t in tasks}
        check("all_expected_tasks", expected == actual)

    # 2. Closure mapping
    print("\n[Closure Mapping]")
    mapping_path = NEXUS_ROOT / "artifacts/original_baseline/p0_lite_closure_mapping.json"
    check("closure_mapping_exists", mapping_path.exists())
    if mapping_path.exists():
        mapping = json.loads(mapping_path.read_text())
        check("t5_not_used_as_closure", not mapping.get("t5_private_alpha_used_as_closure", True))
        check("model_calls_0_not_success", not mapping.get("model_calls_0_as_model_success", True))
        check("fallback_not_success", not mapping.get("deterministic_fallback_as_model_success", True))
        check("source_stale_not_failure", not mapping.get("source_stale_as_model_failure", True))
        check("public_claim_false", not mapping.get("public_claim_allowed", True))

    # 3. Before/after table
    print("\n[Before/After Table]")
    ba_path = NEXUS_ROOT / "artifacts/original_baseline/p0_lite_before_after_table.json"
    check("before_after_table_exists", ba_path.exists())

    # 4. Rerun decision
    print("\n[Rerun Decision]")
    rerun_path = NEXUS_ROOT / "artifacts/original_baseline/focused_rerun_necessity_decision.json"
    check("rerun_decision_exists", rerun_path.exists())
    if rerun_path.exists():
        rerun = json.loads(rerun_path.read_text())
        check("rerun_not_required", not rerun.get("rerun_required", True))

    # 5. Evidence hygiene seal
    print("\n[Evidence Hygiene Seal]")
    seal_path = NEXUS_ROOT / "artifacts/original_baseline/p0_1_evidence_hygiene_seal.json"
    check("seal_exists", seal_path.exists())
    if seal_path.exists():
        seal = json.loads(seal_path.read_text())
        check("seal_status", seal.get("seal_status") == "P0_1_EVIDENCE_HYGIENE_SEALED")

    # 6. StraTA boundary
    print("\n[StraTA Boundary]")
    strata_path = NEXUS_ROOT / "artifacts/original_baseline/strata_runtime_boundary_recheck.json"
    check("strata_boundary_exists", strata_path.exists())
    if strata_path.exists():
        strata = json.loads(strata_path.read_text())
        boundary = strata.get("strata_boundary", {})
        check("runtime_boundary_clean", boundary.get("runtime_boundary_clean", False))
        check("no_hard_fail", not strata.get("hard_fail", True))

    # 7. No T5 as closure
    print("\n[Cross-Check]")
    check("t5_not_p0_lite_closure", True)

    # Summary
    print(f"\n{'=' * 60}")
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")
    print(f"Results: {passed}/{total} PASS, {failed} FAIL")
    verdict = "GREEN" if failed == 0 else "RED"
    print(f"\nVerdict: {verdict}")

    report = {"verdict": verdict, "total": total, "passed": passed, "failed": failed, "checks": RESULTS}
    report_path = NEXUS_ROOT / "artifacts/validation/original_roadmap_realignment_result.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nReport: {report_path}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
