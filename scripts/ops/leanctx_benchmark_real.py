#!/usr/bin/env python3
import time
import subprocess
import json
import os
import shutil
from typing import Dict, List

LEAN_CTX_BIN = "/Users/jameschen/.local/bin/lean-ctx"

def get_token_count(text: str) -> int:
    # Approximate: 4 chars per token
    return len(text) // 4

def run_large_benchmark(sample_file: str) -> Dict:
    if not os.path.exists(LEAN_CTX_BIN):
        return {"error": "lean-ctx binary not found"}
    
    if not os.path.exists(sample_file):
        return {"error": f"Sample file {sample_file} not found"}

    with open(sample_file, "r") as f:
        content = f.read()

    orig_tokens = get_token_count(content)
    
    print(f"--- STARTING LARGE SAMPLE BENCHMARK ON {sample_file} ---")
    print(f"Original size: {len(content)} bytes (~{orig_tokens} tokens)")

    # Measure real execution time using 'read' command with aggressive mode
    start_time = time.perf_counter()
    result = subprocess.run(
        [LEAN_CTX_BIN, "read", sample_file, "-m", "aggressive"],
        capture_output=True, text=True, check=True
    )
    end_time = time.perf_counter()

    compressed_content = result.stdout
    compressed_tokens = get_token_count(compressed_content)
    latency = end_time - start_time
    
    token_saving = ((compressed_tokens - orig_tokens) / orig_tokens) * 100.0 if orig_tokens > 0 else 0

    return {
        "sample_file": sample_file,
        "original_tokens": orig_tokens,
        "compressed_tokens": compressed_tokens,
        "token_delta_pct": round(token_saving, 2),
        "latency_s": round(latency, 4),
        "status": "COMPLETED",
        "recommendation": "GO" if token_saving < 0 else "NO_GO"
    }

if __name__ == "__main__":
    res = run_large_benchmark("MUSE-NEXUS-Engine-Specification-v22-Eternal.md")
    print("\n--- LARGE SAMPLE REAL DATA REPORT ---")
    print(json.dumps(res, indent=2))
