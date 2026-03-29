"""
CI Benchmark Runner — 呼叫 ./nexus_benchmark.sh 對 Subset 跑分
讀取 smoke_cases.json 或 lite 模式清單，逐題執行並彙整 JSONL 結果
"""

import argparse
import json
import subprocess
import time
import sys
from pathlib import Path

NEXUS_ROOT = Path(__file__).parent.parent.parent
SMOKE_CASES_FILE = Path(__file__).parent / "smoke_cases.json"
BENCHMARK_SCRIPT = NEXUS_ROOT / "nexus_benchmark.sh"


def load_cases(mode: str) -> list[str]:
    """載入測試題目清單"""
    if mode == "smoke":
        data = json.loads(SMOKE_CASES_FILE.read_text(encoding="utf-8"))
        return data["task_ids"]
    elif mode == "lite":
        # Lite 模式讀取 SWE-bench verified 的前 100 題
        swe_file = NEXUS_ROOT / "scripts" / "bench" / "swe-bench-verified.json"
        lines = swe_file.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(line)["task_id"] for line in lines[:100] if line.strip()]
    else:
        raise ValueError(f"Unknown mode: {mode}. Use 'smoke' or 'lite'.")


def run_single_case(task_id: str, timeout: int = 300) -> dict:
    """
    對單一 task_id 呼叫 nexus_benchmark.sh，回傳結果 dict
    """
    start = time.time()
    try:
        result = subprocess.run(
            [str(BENCHMARK_SCRIPT), "--task", task_id, "--executor", "gemini", "--reviewer", "codex"],
            cwd=NEXUS_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.time() - start
        passed = result.returncode == 0

        return {
            "task_id": task_id,
            "pass@1": passed,
            "status": "passed" if passed else "failed",
            "exit_code": result.returncode,
            "elapsed_seconds": round(elapsed, 2),
            "stdout_tail": result.stdout[-500:] if result.stdout else "",
            "stderr_tail": result.stderr[-300:] if result.stderr else "",
            "health_score": 100.0 if passed else 0.0,
        }

    except subprocess.TimeoutExpired:
        return {
            "task_id": task_id,
            "pass@1": False,
            "status": "timeout",
            "exit_code": 124,
            "elapsed_seconds": timeout,
            "stdout_tail": "",
            "stderr_tail": f"Timeout after {timeout}s",
            "health_score": 0.0,
        }
    except Exception as exc:
        return {
            "task_id": task_id,
            "pass@1": False,
            "status": "error",
            "exit_code": -1,
            "elapsed_seconds": 0.0,
            "stdout_tail": "",
            "stderr_tail": str(exc),
            "health_score": 0.0,
        }


def main():
    parser = argparse.ArgumentParser(description="Nexus CI Benchmark Runner")
    parser.add_argument("--mode", choices=["smoke", "lite"], default="smoke")
    parser.add_argument("--output", type=str, default="ci_benchmark_results.jsonl")
    parser.add_argument("--timeout", type=int, default=300, help="Seconds per case")
    args = parser.parse_args()

    cases = load_cases(args.mode)
    print(f"📋 Running {len(cases)} cases in '{args.mode}' mode", flush=True)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results = []
    with open(output_path, "w", encoding="utf-8") as f:
        for i, task_id in enumerate(cases, 1):
            print(f"[{i}/{len(cases)}] Running {task_id}...", flush=True)
            result = run_single_case(task_id, timeout=args.timeout)
            results.append(result)
            f.write(json.dumps(result) + "\n")
            f.flush()  # 確保 CI 環境中每題結果即時落盤
            status_icon = "✅" if result["pass@1"] else "❌"
            print(f"  {status_icon} {result['status']} ({result['elapsed_seconds']:.1f}s)", flush=True)

    # Final summary to stdout
    passed = sum(1 for r in results if r["pass@1"])
    total = len(results)
    rate = passed / total * 100 if total > 0 else 0
    print(f"\n{'='*40}")
    print(f"🏆 Final: {passed}/{total} passed ({rate:.1f}%)")
    print(f"📄 Results saved to: {output_path}")

    # Exit non-zero if no cases passed at all (hard failure)
    if total > 0 and passed == 0:
        print("❌ FATAL: 0 cases passed. Failing CI.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
