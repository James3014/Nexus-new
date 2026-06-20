#!/usr/bin/env python3
"""T4.1 Model Candidate Registry Validation"""

import yaml
import sys
from pathlib import Path

REGISTRY_PATH = Path("/Users/jameschen/Workspace/nexus/configs/model_candidates/t4_1_model_candidate_registry_v1.yaml")

def main():
    print("=" * 50)
    print("T4.1 Registry Validation")
    print("=" * 50)

    errors = []
    warnings = []

    # 1. Parse YAML
    try:
        with open(REGISTRY_PATH) as f:
            registry = yaml.safe_load(f)
        print("  PASS: YAML parses")
    except Exception as e:
        print(f"  FAIL: YAML parse error: {e}")
        return 1

    # 2. Check candidate count
    candidates = registry.get("candidates", [])
    if len(candidates) == 6:
        print(f"  PASS: 6 candidates present")
    else:
        errors.append(f"Expected 6 candidates, got {len(candidates)}")
        print(f"  FAIL: {len(candidates)} candidates")

    # 3. Check unique candidate_ids
    ids = [c["candidate_id"] for c in candidates]
    if len(ids) == len(set(ids)):
        print("  PASS: All candidate_ids unique")
    else:
        errors.append("Duplicate candidate_ids found")

    # 4. Check known instances
    known = {"astropy__astropy-13236", "sympy__sympy-12419", "sympy__sympy-13647",
             "astropy__astropy-14365", "astropy__astropy-14309", "sympy__sympy-13852"}
    actual = {c["instance_id"] for c in candidates}
    if known == actual:
        print("  PASS: All 6 known candidates present")
    else:
        errors.append(f"Missing: {known - actual}, Extra: {actual - known}")

    # 5. Check no public claim
    for c in candidates:
        if c.get("public_claim_allowed"):
            errors.append(f"{c['instance_id']}: public_claim_allowed=true")
        if c.get("export_as_public_claim"):
            errors.append(f"{c['instance_id']}: export_as_public_claim=true")
    if not any(c.get("public_claim_allowed") for c in candidates):
        print("  PASS: No public_claim_allowed=true")

    # 6. Check attribution
    for c in candidates:
        if c.get("model_patch_reward") == 1.0 and not c.get("attribution_clean"):
            errors.append(f"{c['instance_id']}: model_patch_reward=1.0 but attribution_clean=false")
    if not errors:
        print("  PASS: Attribution clean for all reward=1.0")

    # 7. Check stale source replay
    for c in candidates:
        if c.get("candidate_status") == "stale_source_anchor" and c.get("replay_eligible"):
            errors.append(f"{c['instance_id']}: stale but replay_eligible=true")
        if c.get("candidate_status") == "historical_clean_candidate" and c.get("replay_eligible"):
            warnings.append(f"{c['instance_id']}: historical but replay_eligible=true")
    if not errors:
        print("  PASS: Stale/historical candidates not replay_eligible")

    # 8. Check active replayable have source anchor
    for c in candidates:
        if c.get("candidate_status") == "active_replayable":
            if c.get("source_anchor_status") not in ("anchored", "reconciled"):
                warnings.append(f"{c['instance_id']}: active but anchor={c.get('source_anchor_status')}")
    print("  PASS: Active candidates have source anchor (warnings may exist)")

    # Summary
    print(f"\n{'=' * 50}")
    if errors:
        print(f"FAIL: {len(errors)} errors")
        for e in errors:
            print(f"  - {e}")
        return 1
    else:
        print("PASS: All validations passed")
        if warnings:
            print(f"  Warnings: {len(warnings)}")
            for w in warnings:
                print(f"  - {w}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
