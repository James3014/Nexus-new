#!/usr/bin/env python3
import time
import subprocess
import json
import os
from typing import Dict, List

LEAN_CTX_BIN = "/Users/jameschen/.local/bin/lean-ctx"

def get_token_count(text: str) -> int:
    return len(text) // 4

def test_all_modes(sample_file: str) -> List[Dict]:
    modes = ["full", "aggressive", "map", "signatures", "entropy"]
    results = []
    
    with open(sample_file, "r") as f:
        content = f.read()
    orig_tokens = get_token_count(content)

    print(f"--- NEXUS RESEARCH: COMPRESSION MATRIX ON {sample_file} ---")

    for mode in modes:
        start_time = time.perf_counter()
        try:
            result = subprocess.run(
                [LEAN_CTX_BIN, "read", sample_file, "-m", mode],
                capture_output=True, text=True, check=True
            )
            end_time = time.perf_counter()
            
            comp_content = result.stdout
            comp_tokens = get_token_count(comp_content)
            latency = end_time - start_time
            saving = ((comp_tokens - orig_tokens) / orig_tokens) * 100.0
            
            results.append({
                "mode": mode,
                "tokens": comp_tokens,
                "delta_pct": round(saving, 2),
                "latency_s": round(latency, 4)
            })
            print(f"Mode {mode:12}: {comp_tokens} tokens ({saving:6.2f}%) | {latency:.4f}s")
        except Exception as e:
            print(f"Mode {mode} failed: {e}")
            
    return results

if __name__ == "__main__":
    test_all_modes("scripts/ops/leanctx_real_validation.py")
