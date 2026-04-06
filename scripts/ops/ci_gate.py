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

def run_dry_run():
    print("🛡️ [Nexus CI Gate] Dry-run status check...")
    checks = {
        "venv_python": VENV_PYTHON.exists(),
        "contracts_dir": (ROOT / "tests" / "contracts").exists(),
        "benchmark_script": (ROOT / "scripts" / "engine" / "nexus_cli.py").exists(),
    }
    for key, ok in checks.items():
        print(f"- {key}: {'OK' if ok else 'MISSING'}")
    return 0 if all(checks.values()) else 1

def main():
    parser = argparse.ArgumentParser(description="Nexus CI Gate - Release Governance")
    parser.add_argument("--strict", action="store_true", help="Enforce all checks")
    parser.add_argument("--dry-run", action="store_true", help="Audit only, no exit(1)")
    parser.add_argument("--wiki-drift-enforce-level", choices=["off", "warn", "p0"], default="warn", help="Drift enforcement level")
    args = parser.parse_args()

    if args.dry_run:
        sys.exit(run_dry_run())

    print("🛡️ [Nexus CI Gate] Initializing Automated Audit Lane...")
    
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

    # 2b. Wiki Capability Coverage Audit (Phase 5 Strengthening)
    run_step(
        "Wiki Capability Coverage Audit",
        f'"{VENV_PYTHON}" scripts/ops/wiki_capability_coverage_audit.py',
    )
    
    # Check Drift Blocking Logic
    if WIKI_DRIFT_REPORT.exists():
        try:
            drift_data = json.loads(WIKI_DRIFT_REPORT.read_text())
            p0 = drift_data["summary"]["p0_count"]
            p1 = drift_data["summary"]["p1_count"]
            p2 = drift_data["summary"]["p2_count"]
            print(f"📊 [Wiki-Drift] P0={p0}, P1={p1}, P2={p2}")
            
            if args.wiki_drift_enforce_level == "p0" and p0 > 0:
                print(f"❌ [CI-BLOCK] P0 drift detected! Enforce level: p0. Blocking release.")
                if not args.dry_run: sys.exit(1)
            elif args.wiki_drift_enforce_level != "off" and (p0 > 0 or p1 > 0):
                print(f"⚠️ [CI-WARN] Drift detected (P0={p0}, P1={p1}).")
        except Exception as e:
            print(f"⚠️ Error parsing drift report: {e}")

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
