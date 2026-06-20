#!/usr/bin/env python3
"""T4.3: Source Snapshot Backfill + Replay Fixture Freezing"""

import json, subprocess, sys, hashlib, re, yaml
from pathlib import Path

NEXUS_ROOT = Path("/Users/jameschen/Workspace/nexus")
RUN_GROUP = "T4_3_SOURCE_SNAPSHOT_BACKFIX"

CANDIDATES = [
    {"instance_id": "astropy__astropy-13236", "project": "astropy", "workspace": "astropy", "target_file": "astropy/table/table.py", "buggy_block": "        # Structured ndarray gets viewed as a mixin unless already a valid\n        # mixin class\n        if (not isinstance(data, Column) and not data_is_mixin\n                and isinstance(data, np.ndarray) and len(data.dtype) > 1):\n            data = data.view(NdarrayMixin)\n            data_is_mixin = True", "t4_2_status": "verified", "first_success": "T3_2"},
    {"instance_id": "sympy__sympy-12419", "project": "sympy", "workspace": "sympy", "target_file": "sympy/polys/polytools.py", "buggy_line": "        if not p:", "fixed_line": "        if p is None or p.is_zero:", "t4_2_status": "stale", "first_success": "T3_6"},
    {"instance_id": "sympy__sympy-13647", "project": "sympy", "workspace": "sympy", "target_file": "sympy/simplify/simplify.py", "buggy_line": "        if not expr:", "fixed_line": "        if expr is None or expr.is_zero:", "t4_2_status": "stale", "first_success": "T3_6"},
    {"instance_id": "astropy__astropy-14365", "project": "astropy", "workspace": "astropy", "target_file": "astropy/io/fits/card.py", "buggy_line": '    value_str = f"{value:.16G}"', "fixed_line": '    value_str = f"{value:.15G}"', "t4_2_status": "stale", "first_success": "T3_6"},
    {"instance_id": "astropy__astropy-14309", "project": "astropy", "workspace": "astropy", "target_file": "astropy/io/fits/card.py", "buggy_line": '    value_str = f"{value:.16G}"', "fixed_line": '    value_str = f"{value:.15G}"', "t4_2_status": "stale", "first_success": "T3_7"},
    {"instance_id": "sympy__sympy-13852", "project": "sympy", "workspace": "sympy", "target_file": "sympy/functions/special/zeta_functions.py", "buggy_line": "from sympy.core import Function, S, sympify, pi", "fixed_line": "from sympy.core import Function, S, sympify, pi, I", "t4_2_status": "verified", "first_success": "T3_8"},
]


def get_source_hash(ws):
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(NEXUS_ROOT / ".nexus/workspaces" / ws), capture_output=True, text=True, timeout=10)
        return r.stdout.strip()[:12] if r.returncode == 0 else "unknown"
    except:
        return "unknown"


def find_buggy(source, cand):
    if "buggy_block" in cand:
        return cand["buggy_block"] in source, cand["buggy_block"]
    else:
        return cand["buggy_line"] in source, cand["buggy_line"]


def try_restore_sympy_buggy(cand):
    """Try to find the buggy line in git history."""
    ws = NEXUS_ROOT / ".nexus/workspaces" / cand["workspace"]
    buggy = cand.get("buggy_line", "")
    if not buggy:
        return False, "no_buggy_line", ""

    # Search git log for commits that might have the buggy line
    try:
        r = subprocess.run(["git", "log", "--oneline", "-20"], cwd=str(ws), capture_output=True, text=True, timeout=10)
        commits = r.stdout.strip().split('\n')

        for commit in commits:
            commit_hash = commit.split()[0]
            # Check if file at that commit has the buggy line
            r2 = subprocess.run(["git", "show", f"{commit_hash}:{cand['target_file']}"], cwd=str(ws), capture_output=True, text=True, timeout=10)
            if r2.returncode == 0 and buggy in r2.stdout:
                return True, "restored_from_git", commit_hash
    except Exception as e:
        pass

    return False, "not_restorable", ""


def main():
    print("=" * 70)
    print("T4.3: Source Snapshot Backfill + Replay Fixture Freezing")
    print("=" * 70)

    fixture_manifest = {"fixture_version": "1.0.0", "created": "2026-06-18", "candidates": []}
    registry_v12 = {"registry_version": "1.2.0", "t4_3_date": "2026-06-18", "candidates": []}

    for cand in CANDIDATES:
        iid = cand["instance_id"]
        print(f"\n{'=' * 55}")
        print(f"CANDIDATE: {iid}")
        print("=" * 55)

        ws = NEXUS_ROOT / ".nexus/workspaces" / cand["workspace"]
        current_hash = get_source_hash(cand["workspace"])
        source = (ws / cand["target_file"]).read_text() if (ws / cand["target_file"]).exists() else ""
        buggy_found, buggy_text = find_buggy(source, cand)

        result = {
            "instance_id": iid, "project": cand["project"],
            "current_source_hash": current_hash,
            "buggy_found": buggy_found,
            "t4_2_status": cand["t4_2_status"],
            "first_success_run": cand["first_success"],
        }

        if cand["t4_2_status"] == "verified":
            result["fixture_status"] = "verified_current"
            result["fixture_ready"] = True
            result["fixture_block_reason"] = ""
            result["source_snapshot_hash"] = current_hash
            result["backfill_status"] = "no_backfill_needed"
            print(f"  Status: verified_current, fixture_ready=True")
        else:
            # Try backfill
            restored, restore_method, restore_hash = try_restore_sympy_buggy(cand)
            if restored:
                result["fixture_status"] = "ready_reconciled"
                result["fixture_ready"] = True
                result["fixture_block_reason"] = ""
                result["source_snapshot_hash"] = restore_hash
                result["backfill_status"] = "restored_from_git"
                result["backfill_method"] = restore_method
                print(f"  Backfill: {restore_method} from {restore_hash}")
            else:
                result["fixture_status"] = "historical_only"
                result["fixture_ready"] = False
                result["fixture_block_reason"] = "source_snapshot_missing"
                result["source_snapshot_hash"] = ""
                result["backfill_status"] = "not_restorable"
                print(f"  Backfill: not_restorable, historical_only")

        fixture_manifest["candidates"].append(result)
        registry_v12["candidates"].append(result)

    # Summary
    print(f"\n{'=' * 70}")
    print("T4.3 RESULTS")
    print(f"{'=' * 70}")

    fixture_ready = sum(1 for c in fixture_manifest["candidates"] if c["fixture_ready"])
    historical_only = sum(1 for c in fixture_manifest["candidates"] if not c["fixture_ready"])
    restored = sum(1 for c in fixture_manifest["candidates"] if "restored" in c.get("backfill_status", ""))

    for c in fixture_manifest["candidates"]:
        print(f"  {c['instance_id']}: fixture={c['fixture_status']} ready={c['fixture_ready']} backfill={c.get('backfill_status','N/A')}")

    print(f"\nFixture-ready: {fixture_ready}/6 | Historical-only: {historical_only}/6 | Restored: {restored}/6")

    if fixture_ready >= 4:
        verdict = "GREEN"
    elif fixture_ready >= 2:
        verdict = "YELLOW"
    else:
        verdict = "RED"

    print(f"\nT4.3 Verdict: {verdict}")

    # Write outputs
    fm_path = NEXUS_ROOT / "configs/model_candidates/t4_3_replay_fixture_manifest.yaml"
    fm_path.write_text(yaml.dump(fixture_manifest, default_flow_style=False, allow_unicode=True))
    print(f"\nFixture manifest: {fm_path}")

    r_path = NEXUS_ROOT / "configs/model_candidates/t4_3_model_candidate_registry_v1_2.yaml"
    r_path.write_text(yaml.dump(registry_v12, default_flow_style=False, allow_unicode=True))
    print(f"Registry v1.2: {r_path}")

    summary = {"verdict": verdict, "fixture_ready": fixture_ready, "historical_only": historical_only, "restored": restored}
    sp = NEXUS_ROOT / ".nexus/reports/local_heal" / RUN_GROUP / "summary.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__": sys.exit(main())
