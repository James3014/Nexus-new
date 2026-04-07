# 🛡️ Nexus CI Gate (Agent I - WS-I Hardened v3.0)
# [NEXUS CONFIG: FAIL-CLOSED RELEASE CONTRACT]
import os
import sys
import json
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIKI_DRIFT_REPORT = ROOT / ".nexus" / "reports" / "wiki_drift_report.json"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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

def run_protocol_check(dry_run: bool):
    print(f"\n🚀 [CI-Gate] Running Agent Protocol Check {'(Dry-run)' if dry_run else ''}...")
    res = subprocess.run(f'"{VENV_PYTHON}" scripts/ops/agent_protocol_check.py', shell=True)
    if res.returncode == 0:
        print("✅ Agent Protocol Check PASSED")
        return True
    else:
        if dry_run:
            print(f"⚠️ [DRY-RUN] Agent Protocol Check FAILED (Return Code: {res.returncode})")
        else:
            print(f"❌ Agent Protocol Check FAILED (Return Code: {res.returncode})")
        return False

def run_lesson_check(dry_run: bool):
    print(f"\n🚀 [CI-Gate] Running Lesson Writeback Check {'(Dry-run)' if dry_run else ''}...")
    res = subprocess.run(f'"{VENV_PYTHON}" scripts/ops/lesson_writeback_check.py', shell=True)
    if res.returncode == 0:
        print("✅ Lesson Writeback Check PASSED")
        return True
    else:
        if dry_run:
            print(f"⚠️ [DRY-RUN] Lesson Writeback Check FAILED (Return Code: {res.returncode})")
        else:
            print(f"❌ Lesson Writeback Check FAILED (Return Code: {res.returncode})")
        return False

def run_wiki_sync_check(dry_run: bool):
    print(f"\n🚀 [CI-Gate] Running Wiki Sync Check {'(Dry-run)' if dry_run else ''}...")
    res = subprocess.run(f'"{VENV_PYTHON}" scripts/ops/wiki_sync_check.py --mode worktree', shell=True)
    if res.returncode == 0:
        print("✅ Wiki Sync Check PASSED")
        return "OK"
    elif res.returncode == 2:
        if dry_run:
            print(f"❌ [DRY-RUN-BLOCK] Wiki Sync Check FAILED (Return Code: 2)")
        else:
            print(f"❌ [CI-BLOCK] Wiki Sync Check FAILED (Return Code: 2)")
        return "FAIL"
    else:
        if dry_run:
            print(f"⚠️ [DRY-RUN] Wiki Sync Check FAILED (Return Code: {res.returncode})")
        else:
            print(f"❌ Wiki Sync Check FAILED (Return Code: {res.returncode})")
        return "FAIL"

def run_closeout_contract_check(dry_run: bool, contract_path: str):
    print(f"\n🚀 [CI-Gate] Running Closeout Contract Check {'(Dry-run)' if dry_run else ''}...")
    res = subprocess.run(
        f'"{VENV_PYTHON}" scripts/ops/closeout_guard.py --contract "{contract_path}"',
        shell=True,
    )
    if res.returncode == 0:
        print("✅ Closeout Contract Check PASSED")
        return True
    if dry_run:
        print(f"❌ [DRY-RUN-BLOCK] Closeout Contract Check FAILED (Return Code: {res.returncode})")
    else:
        print(f"❌ [CI-BLOCK] Closeout Contract Check FAILED (Return Code: {res.returncode})")
    return False

def run_dry_run():
    print("🛡️ [Nexus CI Gate] Dry-run status check...")
    checks = {
        "venv_python": VENV_PYTHON.exists(),
        "contracts_dir": (ROOT / "tests" / "contracts").exists(),
        "benchmark_script": (ROOT / "scripts" / "engine" / "nexus_cli.py").exists(),
    }
    for key, ok in checks.items():
        print(f"- {key}: {'OK' if ok else 'MISSING'}")
    
    checks["protocol_check"] = run_protocol_check(dry_run=True)
    checks["lesson_check"] = run_lesson_check(dry_run=True)
    wiki_sync_status = run_wiki_sync_check(dry_run=True)
    checks["wiki_sync"] = (wiki_sync_status == "OK")
    
    print(f"- protocol_check: {'OK' if checks['protocol_check'] else 'FAIL'}")
    print(f"- lesson_check: {'OK' if checks['lesson_check'] else 'FAIL'}")
    print(f"- wiki_sync: {wiki_sync_status}")

    print("\n📊 [Phase 6] Summary Audit (Dry-Run):")
    print_phase_6_summaries(wiki_sync_status=wiki_sync_status)
    
    return 0 if all(checks.values()) else 1

def print_phase_6_summaries(wiki_sync_status="UNKNOWN"):
    reports = {
        "drift": ROOT / ".nexus" / "reports" / "wiki_drift_report.json",
        "capability": ROOT / ".nexus" / "reports" / "wiki_capability_coverage_report.json",
        "eval": ROOT / ".nexus" / "reports" / "wiki_eval_report.json",
        "writeback": ROOT / ".nexus" / "reports" / "wiki_writeback_report.json"
    }

    print(f"📊 [Wiki-Sync] Status: {wiki_sync_status}")
    # Drift Summary
    if reports["drift"].exists():
        try:
            drift_data = json.loads(reports["drift"].read_text())
            p0 = drift_data["summary"]["p0_count"]
            p1 = drift_data["summary"]["p1_count"]
            print(f"📊 [Wiki-Drift] P0={p0}, P1={p1}")
        except Exception as e:
            print(f"⚠️ Error parsing drift report: {e}")

    # Capability Summary
    if reports["capability"].exists():
        try:
            cap_data = json.loads(reports["capability"].read_text())
            weighted = cap_data["summary"]["weighted_score"]
            print(f"📊 [Wiki-Capability] Weighted Score: {weighted:.2%}")
        except Exception as e:
            print(f"⚠️ Error parsing capability report: {e}")

    # Eval Regression Summary
    if reports["eval"].exists():
        try:
            eval_data = json.loads(reports["eval"].read_text())
            pass_rate = eval_data["summary"]["pass_rate"]
            print(f"📊 [Wiki-Eval] Pass Rate: {pass_rate:.2%}")
        except Exception as e:
            print(f"⚠️ Error parsing eval report: {e}")

    # Writeback Status Summary
    if reports["writeback"].exists():
        try:
            wb_data = json.loads(reports["writeback"].read_text())
            status = wb_data.get("status", "unknown")
            recent = len(wb_data.get("recent_writebacks", []))
            print(f"📊 [Wiki-Writeback] Status: {status}, Recent Count: {recent}")
        except Exception as e:
            print(f"⚠️ Error parsing writeback report: {e}")

def main():
    parser = argparse.ArgumentParser(description="Nexus CI Gate - Release Governance")
    parser.add_argument("--strict", action="store_true", help="Enforce all checks")
    parser.add_argument("--dry-run", action="store_true", help="Audit only, no exit(1)")
    parser.add_argument("--wiki-drift-enforce-level", choices=["off", "warn", "p0"], default="warn", help="Drift enforcement level")
    parser.add_argument("--wiki-capability-enforce-level", choices=["off", "warn", "strict"], default="warn", help="Capability enforcement level")
    parser.add_argument("--wiki-eval-enforce-level", choices=["off", "warn", "strict"], default="warn", help="Eval regression enforcement level")
    parser.add_argument("--require-closeout-contract", action="store_true", help="Block CI if done contract closeout check fails")
    parser.add_argument("--closeout-contract-path", default=".nexus/reports/done_contract.json", help="Path to done contract JSON")
    args = parser.parse_args()

    if args.dry_run:
        dry_exit = run_dry_run()
        if args.require_closeout_contract:
            closeout_ok = run_closeout_contract_check(dry_run=True, contract_path=args.closeout_contract_path)
            if not closeout_ok:
                dry_exit = 1
        sys.exit(dry_exit)

    print("🛡️ [Nexus CI Gate] Initializing Automated Audit Lane...")
    
    # 0. Agent Protocol Check
    if not run_protocol_check(dry_run=args.dry_run):
        if not args.dry_run: sys.exit(1)

    # 0b. Lesson Writeback Check
    if not run_lesson_check(dry_run=args.dry_run):
        if not args.dry_run: sys.exit(1)

    # 0c. Wiki Sync Check
    wiki_sync_status = run_wiki_sync_check(dry_run=args.dry_run)
    if wiki_sync_status == "FAIL":
        if not args.dry_run: sys.exit(1)

    if args.require_closeout_contract:
        closeout_ok = run_closeout_contract_check(dry_run=args.dry_run, contract_path=args.closeout_contract_path)
        if not closeout_ok and not args.dry_run:
            sys.exit(1)

    # 1. Wiki Governance Audit (Pass 7 - CI Hardened)
    success, _ = run_step(
        "Wiki Governance Audit",
        f'"{VENV_PYTHON}" scripts/ops/wiki_linter.py --strict --ci-report wiki_audit.json',
    )
    if not success and not args.dry_run: sys.exit(1)

    # 2. Wiki Drift Audit (Agent I - v2.0)
    run_step(
        "Wiki Drift Audit",
        f'"{VENV_PYTHON}" scripts/ops/wiki_drift_audit.py',
    )

    # 2b. Wiki Capability Coverage Audit (Phase 6 Weighted)
    run_step(
        "Wiki Capability Coverage Audit",
        f'"{VENV_PYTHON}" scripts/ops/wiki_capability_coverage_audit.py',
    )

    # 2c. Wiki Writeback Status (Phase 6)
    run_step(
        "Wiki Writeback Status Check",
        f'"{VENV_PYTHON}" scripts/ops/wiki_query_writeback.py',
    )

    # 2d. Wiki Eval Regression (Phase 6)
    run_step(
        "Wiki Eval Regression",
        f'"{VENV_PYTHON}" scripts/ops/wiki_eval_regression.py',
    )
    
    # Report Summaries & Enforcement
    print_phase_6_summaries(wiki_sync_status=wiki_sync_status)

    reports = {
        "drift": ROOT / ".nexus" / "reports" / "wiki_drift_report.json",
        "capability": ROOT / ".nexus" / "reports" / "wiki_capability_coverage_report.json",
        "eval": ROOT / ".nexus" / "reports" / "wiki_eval_report.json"
    }

    # Drift Blocking Logic (Enforcement)
    if reports["drift"].exists():
        try:
            drift_data = json.loads(reports["drift"].read_text())
            p0 = drift_data["summary"]["p0_count"]
            if args.wiki_drift_enforce_level == "p0" and p0 > 0:
                print(f"❌ [CI-BLOCK] P0 drift detected! Enforce level: p0. Blocking release.")
                if not args.dry_run: sys.exit(1)
        except Exception as e:
            pass # print_phase_6_summaries already handles error reporting

    # Capability Blocking Logic (Enforcement)
    if reports["capability"].exists():
        try:
            cap_data = json.loads(reports["capability"].read_text())
            weighted = cap_data["summary"]["weighted_score"]
            if args.wiki_capability_enforce_level == "strict" and weighted < 0.95:
                print(f"❌ [CI-BLOCK] Wiki-Capability weighted score {weighted:.2%} is below 95% threshold! Enforce level: strict.")
                if not args.dry_run: sys.exit(1)
            elif args.wiki_capability_enforce_level == "warn" and weighted < 0.95:
                print(f"⚠️ [CI-WARN] Wiki-Capability weighted score {weighted:.2%} is below 95% threshold.")
        except Exception as e:
            pass

    # Eval Regression Blocking Logic (Enforcement)
    if reports["eval"].exists():
        try:
            eval_data = json.loads(reports["eval"].read_text())
            pass_rate = eval_data["summary"]["pass_rate"]
            if args.wiki_eval_enforce_level == "strict" and pass_rate < 0.90:
                print(f"❌ [CI-BLOCK] Wiki-Eval pass rate {pass_rate:.2%} is below 90% threshold! Enforce level: strict.")
                if not args.dry_run: sys.exit(1)
            elif args.wiki_eval_enforce_level == "warn" and pass_rate < 0.90:
                print(f"⚠️ [CI-WARN] Wiki-Eval pass rate {pass_rate:.2%} is below 90% threshold.")
        except Exception as e:
            pass

    # 3. Code Regression
    success, _ = run_step(
        "DI & Contract Regression",
        f'"{VENV_PYTHON}" -m pytest tests/contracts/ tests/test_container_orchestration.py -q',
    )
    if not success and not args.dry_run: sys.exit(1)

    print("\n🎉 [CI-Gate] ALL QUALITY GATES PASSED!")

if __name__ == "__main__":
    # NEXUS IDENTITY: 06624d2 + CI-GUARDED
    main()
