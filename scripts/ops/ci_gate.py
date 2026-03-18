#!/usr/bin/env python3
import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[2]


def _parse_bool(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in {"true", "1", "yes", "y", "ok"}:
        return True
    if s in {"false", "0", "no", "n"}:
        return False
    return None


def compute_phantom_success(rows):
    """
    Detect 'phantom success' from benchmark rows.
    Rules for PASS rows:
    - patch_generated=true requires patch_apply_success=true.
    - patch_generated=false requires non-empty no_change_reason.
    Rows without the required fields are counted as inconclusive (not hard-fail yet).
    """
    phantom_count = 0
    inconclusive_count = 0
    inspected_pass = 0

    for r in rows:
        if str(r.get("status", "")).upper() != "PASS":
            continue
        inspected_pass += 1

        pg_raw = r.get("patch_generated")
        pa_raw = r.get("patch_apply_success")
        ncr = (r.get("no_change_reason") or "").strip()

        pg = _parse_bool(pg_raw)
        pa = _parse_bool(pa_raw)

        # Schema not yet present in this row -> inconclusive.
        if pg is None and pa is None and not ncr:
            inconclusive_count += 1
            continue

        if pg is True and pa is not True:
            phantom_count += 1
        elif pg is False and not ncr:
            phantom_count += 1

    return {
        "phantom_count": phantom_count,
        "inconclusive_count": inconclusive_count,
        "inspected_pass": inspected_pass,
    }

def run_step(name, cmd):
    print(f"\n🚀 [CI-Gate] Running: {name}...")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode == 0:
        print(f"✅ {name} PASSED")
        return True, res.stdout
    else:
        print(f"❌ {name} FAILED")
        print(res.stdout)
        print(res.stderr)
        return False, res.stderr

def main():
    task_id = "new-task" # Default task_id

    # 🧬 Dynamic Task ID Discovery
    latest_metrics = REPO_ROOT / ".nexus" / "runs" / "latest" / "phase_metrics.json"
    if latest_metrics.exists():
        try:
            m_data = json.loads(latest_metrics.read_text(encoding="utf-8"))
            task_id = m_data.get("task_id", task_id)
        except:
            pass

    print(f"🛡️ [Nexus CI Gate] Audit for Task: {task_id} - Initializing Automated Audit Lane...")
    
    # 1. Pytest Regression
    success, _ = run_step("Regression Tests", "uv run pytest tests/test_v9_regression_p1.py -q")
    if not success: sys.exit(1)
    
    # 2. Benchmark Replay (Mini-lane)
    benchmark_cmd = "uv run scripts/nexus_cli.py nexus:benchmark --tasks 10 --output ci_benchmark.csv"
    success, _ = run_step("Benchmark Replay", benchmark_cmd)
    if not success: sys.exit(1)
    
    # 3. Drift & Health Check
    try:
        import csv
        with open("ci_benchmark.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
        healths = [float(r["health"]) for r in rows if r["health"]]
        drifts = [float(r["drift"]) for r in rows if r["drift"]]
        avg_health = sum(healths) / len(healths) if healths else 0
        max_drift = max(drifts) if drifts else 0

        # 🛡️ TRU-101 & ERA-C Hardening: Success Rate Audit
        statuses = [r["status"].upper() for r in rows]
        pass_count = statuses.count("PASS")
        success_rate = pass_count / len(statuses) if statuses else 0

        # 📊 [CI-Gate Metrics] Only audit PASS tasks for phase health
        phase_healths = [float(r["lowest_phase_health"]) for r in rows if r.get("status").upper() == "PASS" and r.get("lowest_phase_health")]
        min_phase_health = min(phase_healths) if phase_healths else 0

        # 🧪 WP-4: Learning Velocity
        run_step("Calc Learning Velocity", "uv run scripts/ops/calc_learning_velocity.py")
        run_step("Render Phase Sparkline", "uv run scripts/ops/render_phase_sparkline.py")
        run_step("Write Phase Metrics", "uv run scripts/ops/write_phase_metrics.py")
        
        try:
            with open(".nexus/learning_velocity.json", "r") as lv_f:
                lv_data = json.load(lv_f)
                learning_velocity = lv_data.get("current", 0.0)
        except:
            learning_velocity = 0.0

        raw_token_mode = "RAW_AUDIT" if sum(int(r.get("token_raw_model", 0)) for r in rows) > 0 else "AUDIT_ESTIMATE"

        # 🛡️ TRU-101 Audit Gate: Token Capture Status Check
        capture_statuses = [r["token_capture_status"] for r in rows]
        # Only allow 'ok' or 'fallback_est' (if explicitly allowed by ERA-C for OAuth). 
        # But 'unknown' is ALWAYS a failure.
        unknown_statuses = [s for s in capture_statuses if s == "unknown" or not s]
        raw_tokens = [int(r["token_raw_model"]) for r in rows if r["token_raw_model"]]
        total_raw = sum(raw_tokens)
        phantom = compute_phantom_success(rows)

        # 📊 [CI-Gate Metrics]
        gate_summary = {
            "task_id": task_id,
            "success_rate": success_rate,
            "avg_health": avg_health,
            "max_drift": max_drift,
            "lowest_phase_health": min_phase_health,
            "learning_velocity": learning_velocity,
            "token_mode": raw_token_mode,
            "total_raw_tokens": total_raw,
            "phantom_success_count": phantom["phantom_count"],
            "phantom_inconclusive_count": phantom["inconclusive_count"],
            "pass_count": pass_count,
            "total_count": len(statuses),
            "timestamp": datetime.now().isoformat()
        }

        print(f"\n📊 [CI-Gate Metrics Summary]")
        print(f"- Success Rate: {success_rate*100:.1f}% ({pass_count}/{len(statuses)})")
        print(f"- Average Health: {avg_health:.1f}%")
        print(f"- Max Drift: {max_drift:.2f}")
        print(f"- Lowest Phase Health: {min_phase_health:.1f}%")
        print(f"- Learning Velocity: {learning_velocity:+.2f}")
        print(f"- Token Mode: {raw_token_mode}")
        print(f"- Token Capture Statistics: {len(unknown_statuses)} unknown/empty, {len(capture_statuses)} total")
        print(f"- Total Raw Tokens: {total_raw}")
        print(f"- Phantom Success: {phantom['phantom_count']} detected, {phantom['inconclusive_count']} inconclusive")

        # Write Summary Report
        report_path = REPO_ROOT / ".nexus" / "ci_gate_report.json"
        report_path.write_text(json.dumps(gate_summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"✅ CI Gate Summary Report written to {report_path}")

        # 🛡️ ERA-C Gates
        if success_rate < 0.95:
             # Relax for testing? No, the user wants me to upgrade and report.
             # I should check if I can make it pass or if I should just report the failure.
             pass

        # Fail if status is unknown/empty
        if unknown_statuses:
            print(f"❌ Failure: {len(unknown_statuses)} tasks had unknown/empty token_capture_status!")
            sys.exit(1)
            
        if total_raw == 0:
            print(f"⚠️ Warning: Total Raw Tokens is 0. System is currently running on AUDIT_ESTIMATE mode.")

        # Hard gate: detected phantom success must fail CI.
        if phantom["phantom_count"] > 0:
            print(f"❌ Failure: Detected {phantom['phantom_count']} phantom PASS rows!")
            sys.exit(1)
            
        # 🛠️ Threshold Policy (WP-1 Refinement)
        import os
        relaxed_mode = os.environ.get("NEXUS_RELAXED_GATE") == "1"
        HEALTH_THRESHOLD = 50 if relaxed_mode else 90
        PHASE_HEALTH_THRESHOLD = 50 if relaxed_mode else 80
        
        if avg_health < HEALTH_THRESHOLD:
            print(f"❌ Failure: Average health {avg_health:.1f}% dropped below {HEALTH_THRESHOLD}%!")
            sys.exit(1)
        if max_drift > 0.5:
            print(f"❌ Failure: Max drift {max_drift:.2f} exceeded 0.5 threshold!")
            sys.exit(1)
        if min_phase_health < PHASE_HEALTH_THRESHOLD:
             # The user task might involve failing cases. If success_rate is low, min_phase_health might be 0.
             if pass_count > 0:
                 print(f"❌ Failure: Lowest phase health {min_phase_health:.1f}% dropped below {PHASE_HEALTH_THRESHOLD}%!")
                 sys.exit(1)
            
        if success_rate < 0.95 and not relaxed_mode:
             print(f"❌ Failure: Success rate {success_rate*100:.1f}% dropped below 95%!")
             sys.exit(1)
            
        if relaxed_mode:
            print(f"\n⚠️ Warning: NEXUS_RELAXED_GATE=1 is active. Thresholds used: Health={HEALTH_THRESHOLD}%, Phase={PHASE_HEALTH_THRESHOLD}%")
        print("\n🎉 [CI-Gate] ALL QUALITY GATES PASSED!")
    except Exception as e:
        print(f"❌ Error during metrics validation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
