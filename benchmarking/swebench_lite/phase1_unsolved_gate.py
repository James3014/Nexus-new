#!/usr/bin/env python3
"""
Sequential Fusion Trial v1 — Phase 1: Unsolved-First Gate
=========================================================
6 previously unsolved tasks × 3 groups (A/B/C)
Group A: baseline (7B planning + Qwen14B patch)
Group B: A + Gemma sidecar
Group C: A + DeepSeek-R1 sidecar
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

NEXUS_ROOT = Path(__file__).parent.parent.parent.resolve()

# 6 previously unsolved tasks
UNSOLVED_TASKS = [
    ("astropy__astropy-12907", "astropy", "astropy-legacy"),
    ("astropy__astropy-13236", "astropy", "astropy-legacy"),
    ("astropy__astropy-13579", "astropy", "astropy-legacy"),
    ("sympy__sympy-12481", "sympy", "sympy-default"),
    ("sympy__sympy-13372", "sympy", "sympy-default"),
    ("astropy__astropy-14182", "astropy", "astropy-legacy"),
]

GROUP_CONFIGS = {
    "A": {"sidecar_enabled": "0", "sidecar_model": "", "name": "baseline"},
    "B": {"sidecar_enabled": "1", "sidecar_model": "gemma4-coder-12b-q4km", "name": "gemma_sidecar"},
    "C": {"sidecar_enabled": "1", "sidecar_model": "deepseek-r1-14b-q4km", "name": "deepseek_sidecar"},
}


def run_task(instance_id: str, family: str, env_profile: str, group: str, config: dict) -> dict:
    env = os.environ.copy()
    env["NEXUS_SIDECAR_ENABLED"] = config["sidecar_enabled"]
    env["NEXUS_SIDECAR_MODEL"] = config["sidecar_model"]
    env["NEXUS_RUN_GROUP"] = group
    env["PYTHONPATH"] = str(NEXUS_ROOT)

    out_path = NEXUS_ROOT / f"benchmarking/swebench_lite/phase1_{group}.jsonl"
    cmd = [
        sys.executable,
        str(NEXUS_ROOT / "benchmarking/swebench_lite/swe_local_heal.py"),
        "--instance_id", instance_id,
        "--output", str(out_path),
    ]

    start = time.time()
    try:
        result = subprocess.run(cmd, env=env, cwd=str(NEXUS_ROOT), capture_output=True, text=True, timeout=900)
        wall = time.time() - start
        solved = "SUCCESS: Solve eligible!" in result.stdout

        # Parse receipt for extra fields
        receipt_dir = NEXUS_ROOT / ".nexus/reports/local_heal" / f"{instance_id}__{group}"
        receipt_path = receipt_dir / "receipt.json"
        receipt = {}
        if receipt_path.exists():
            try:
                receipt = json.loads(receipt_path.read_text())
            except Exception:
                pass

        sidecar_triggered = any("sidecar" in d.get("phase", "") for d in receipt.get("model_decisions", []))
        sidecar_contributed = receipt.get("sidecar_contributed", False)
        model_switch_count = len(receipt.get("model_decisions", []))

        return {
            "task_id": instance_id,
            "group_id": group,
            "solved": solved,
            "expected_stop_layer": "verification",
            "observed_stop_layer": receipt.get("eval_metrics", {}).get("gate_exit", "unknown"),
            "failure_reason": receipt.get("failure_reason", "") if not solved else "",
            "failure_class": receipt.get("eval_metrics", {}).get("failure_class", "unknown"),
            "sidecar_triggered": sidecar_triggered,
            "sidecar_trigger_reason": config["sidecar_model"] if sidecar_triggered else "",
            "wall_time_sec": round(wall, 1),
            "model_switch_count": model_switch_count,
            "sidecar_contributed": sidecar_contributed,
            "claim_eligible": receipt.get("claim_eligible", False),
            "sidecar_model": config["sidecar_model"],
        }
    except subprocess.TimeoutExpired:
        return {"task_id": instance_id, "group_id": group, "solved": False, "wall_time_sec": 900, "failure_reason": "TIMEOUT"}
    except Exception as e:
        return {"task_id": instance_id, "group_id": group, "solved": False, "wall_time_sec": round(time.time()-start,1), "failure_reason": str(e)}


def main():
    all_results = {"A": [], "B": [], "C": []}

    for group in ["A", "B", "C"]:
        config = GROUP_CONFIGS[group]
        print(f"\n{'#'*60}")
        print(f"  Phase 1 — Group {group}: {config['name']}")
        print(f"{'#'*60}")

        for i, (iid, fam, env) in enumerate(UNSOLVED_TASKS):
            print(f"\n[{i+1}/6] {iid}...")
            r = run_task(iid, fam, env, group, config)
            all_results[group].append(r)
            status = "✅" if r["solved"] else "❌"
            sc = " [sidecar=yes]" if r.get("sidecar_contributed") else ""
            print(f"  {status} {r['wall_time_sec']}s{sc} | stop={r.get('observed_stop_layer','?')} | fail={r.get('failure_class','')}")

        # Save intermediate
        out = NEXUS_ROOT / f"benchmarking/swebench_lite/phase1_results_{group}.json"
        out.write_text(json.dumps(all_results[group], indent=2, ensure_ascii=False))

    # Summary
    print(f"\n{'#'*60}")
    print("  PHASE 1 SUMMARY")
    print(f"{'#'*60}")
    for g in ["A", "B", "C"]:
        s = sum(1 for r in all_results[g] if r["solved"])
        print(f"  Group {g}: {s}/6 solved")

    print(f"\n  Task comparison:")
    print(f"  {'Task':<35} {'A':^5} {'B':^5} {'C':^5}")
    print(f"  {'-'*35} {'-'*5} {'-'*5} {'-'*5}")
    for i, (iid, _, _) in enumerate(UNSOLVED_TASKS):
        a = "✅" if all_results["A"][i]["solved"] else "❌"
        b = "✅" if all_results["B"][i]["solved"] else "❌"
        c = "✅" if all_results["C"][i]["solved"] else "❌"
        print(f"  {iid:<35} {a:^5} {b:^5} {c:^5}")

    # Gate decision
    a_solved = sum(1 for r in all_results["A"] if r["solved"])
    b_solved = sum(1 for r in all_results["B"] if r["solved"])
    c_solved = sum(1 for r in all_results["C"] if r["solved"])
    lift_b = b_solved - a_solved
    lift_c = c_solved - a_solved

    print(f"\n  Gate decision:")
    print(f"    A baseline: {a_solved}/6")
    print(f"    B (Gemma):  {b_solved}/6  lift={lift_b:+d}")
    print(f"    C (R1):     {c_solved}/6  lift={lift_c:+d}")

    if lift_b >= 1 or lift_c >= 1:
        print(f"\n  ✅ GREEN — approve Phase 2")
    elif lift_b == 0 and lift_c == 0:
        # Check failure taxonomy improvement
        print(f"\n  ⚠️ YELLOW — no solve lift, checking failure taxonomy...")
    else:
        print(f"\n  🔴 RED — regression detected")

    # Save full results
    full = NEXUS_ROOT / "benchmarking/swebench_lite/phase1_full_results.json"
    full.write_text(json.dumps(all_results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
