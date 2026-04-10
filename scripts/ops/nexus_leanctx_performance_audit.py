#!/usr/bin/env python3
import time
import subprocess
import json
import os
import numpy as np
from pathlib import Path
from typing import Dict, List

LEAN_CTX_BIN = "/Users/jameschen/.local/bin/lean-ctx"
SAMPLES_DIR = ".nexus"

def get_token_count(text: str) -> int:
    return len(text) // 4

def run_task(mode: str, file_path: str, task_type: str) -> Dict:
    """
    mode: 'legacy' or 'nexus-optimized'
    task_type: 'scan' or 'fix'
    """
    start_time = time.perf_counter()
    fallback_occurred = False
    
    try:
        if mode == "legacy":
            with open(file_path, "r") as f:
                content = f.read()
            tokens = get_token_count(content)
        else:
            # Nexus-Optimized Tiered Strategy
            if task_type == "scan":
                cmd = [LEAN_CTX_BIN, "read", file_path, "-m", "signatures"]
            else:
                cmd = [LEAN_CTX_BIN, "read", file_path] # Full mode for fixing
            
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode != 0:
                fallback_occurred = True
                with open(file_path, "r") as f:
                    content = f.read()
            else:
                content = res.stdout
            tokens = get_token_count(content)
            
        end_time = time.perf_counter()
        return {
            "latency": end_time - start_time,
            "tokens": tokens,
            "fallback": fallback_occurred,
            "success": True if tokens > 0 else False
        }
    except Exception:
        return {"latency": 0, "tokens": 0, "fallback": True, "success": False}

def generate_audit_report(test_file: str, iterations: int = 10):
    legacy_results = []
    opt_results = []
    
    print(f"--- STARTING FIVE-DIMENSION AUDIT ON {test_file} ({iterations} iterations) ---")
    
    for _ in range(iterations):
        # Scan Task
        legacy_results.append(run_task("legacy", test_file, "scan"))
        opt_results.append(run_task("nexus-optimized", test_file, "scan"))

    def analyze(res_list):
        latencies = [r["latency"] for r in res_list if r["success"]]
        tokens = [r["tokens"] for r in res_list if r["success"]]
        fallbacks = [1 if r["fallback"] else 0 for r in res_list]
        return {
            "p50_latency": round(float(np.percentile(latencies, 50)), 4) if latencies else 0,
            "p95_latency": round(float(np.percentile(latencies, 95)), 4) if latencies else 0,
            "avg_tokens": int(np.mean(tokens)) if tokens else 0,
            "fallback_rate": sum(fallbacks) / len(res_list) if res_list else 0
        }

    legacy_stats = analyze(legacy_results)
    opt_stats = analyze(opt_results)
    
    token_delta = ((opt_stats["avg_tokens"] - legacy_stats["avg_tokens"]) / legacy_stats["avg_tokens"]) * 100

    report = {
        "sample_size": iterations * 2,
        "metrics": {
            "legacy": legacy_stats,
            "optimized": opt_stats
        },
        "token_delta_pct": round(token_delta, 2),
        "verdict": "GO" if token_delta < -30 else "CAUTION"
    }
    return report

if __name__ == "__main__":
    target = "scripts/ops/leanctx_real_validation.py"
    report = generate_audit_report(target, 20)
    print("\n--- FINAL AUDIT COMPARISON TABLE ---")
    print(json.dumps(report, indent=2))
