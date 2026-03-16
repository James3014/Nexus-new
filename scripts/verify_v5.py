import subprocess
import os
import sys
from pathlib import Path

def run_test(name, cmd_list, cwd):
    print(f"🔍 [Testing] {name}... ", end="", flush=True)
    try:
        res = subprocess.run(cmd_list, capture_output=True, text=True, cwd=cwd)
        if res.returncode == 0:
            print("✅ PASS")
            return True
        else:
            print("❌ FAIL")
            print(f"--- Stdout ---\n{res.stdout}")
            print(f"--- Stderr ---\n{res.stderr}")
            return False
    except Exception as e:
        print(f"🚨 ERROR: {e}")
        return False

def main():
    nexus_root = Path(__file__).resolve().parents[1]
    os.environ["PYTHONPATH"] = str(nexus_root)
    
    print("🧪 [V5 Steel] Starting Python-based Verification Suite...")
    print(f"📂 NEXUS_ROOT: {nexus_root}")
    print("-" * 48)

    tests = [
        ("Constructor Smoke", ["python3", "scripts/diagnostics/constructor_smoke_test.py"]),
        ("Benchmark Entry", ["python3", "scripts/diagnostics/benchmark_entry_smoke_test.py"]),
        ("Freeze Gate", ["python3", "scripts/diagnostics/smoke_freeze_gate.py"]),
        ("Executor Contract", ["python3", "scripts/diagnostics/executor_contract_smoke_test.py"]),
    ]

    all_passed = True
    for name, cmd in tests:
        if not run_test(name, cmd, str(nexus_root)):
            all_passed = False

    print("-" * 48)
    if all_passed:
        print("💎 [V5 Steel] ALL DIAGNOSTICS PASSED. System is hardened.")
        sys.exit(0)
    else:
        print("🚨 [V5 Steel] SOME TESTS FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    main()
