import json
import os
import subprocess
from pathlib import Path

def verify():
    jsonl_file = "nexus_hard_10.jsonl"
    if not os.path.exists(jsonl_file):
        print(f"❌ Find no {jsonl_file}")
        return

    runs_base = Path(".nexus/runs")
    results = []
    
    with open(jsonl_file, "r") as f:
        for line in f:
            data = json.loads(line)
            task_id = data["task_id"]
            
            # Find the latest run directory for this task
            task_dirs = list(runs_base.glob(f"*/{task_id}"))
            if not task_dirs:
                print(f"❓ No run dir for {task_id}")
                continue
                
            task_dir = sorted(task_dirs, key=os.path.getmtime)[-1]
            print(f"🧪 Testing {task_id} in {task_dir}...")
            
            # Run pytest
            try:
                # We need to make sure project root is in PYTHONPATH
                env = os.environ.copy()
                env["PYTHONPATH"] = str(task_dir) + ":" + env.get("PYTHONPATH", "")
                
                # Check mpmath
                cmd = ["python3", "-c", "import mpmath; print('mpmath ok')"]
                subprocess.run(cmd, capture_output=True, check=True, env=env)
                
                # Run actual tests (repro tests)
                # Usually name is test_repro.py or similar
                # Based on coordinator.py, it was applied to existing test files?
                # No, we applied repro.patch to existing files.
                # So we run the repo tests.
                test_cmd = ["pytest", str(task_dir / "sympy/core/tests/test_basic.py")]
                run_res = subprocess.run(test_cmd, capture_output=True, text=True, env=env)
                
                passed = run_res.returncode == 0
                results.append({"task_id": task_id, "actual_pass": passed, "log": run_res.stdout[-200:]})
                print(f"   Result: {'✅ PASS' if passed else '❌ FAIL'}")
            except Exception as e:
                print(f"   ❌ ERROR: {e}")
                results.append({"task_id": task_id, "actual_pass": False, "error": str(e)})

    # Final Summary
    print("\n" + "="*30)
    print("📈 PHYSICAL TRUTH SUMMARY")
    print("="*30)
    total = len(results)
    passed_count = len([r for r in results if r["actual_pass"]])
    print(f"Actual Pass Rate: {passed_count}/{total} ({passed_count/total*100:.1f}%)")
    
if __name__ == "__main__":
    verify()
