import sys
import time
import os

# Link the compiled Rust Native Core
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "nexus-core", "target", "release"))
import nexus_core

armor_name = "NEXUS-v17 [SINGULARITY PRIME]"
target_file = os.path.join(os.path.dirname(__file__), "..", "nexus-reflex", "src", "main.rs")

print(f"====================================================================")
print(f"🛡️  ACTIVATING NEW ARMOR: {armor_name} 🛡️")
print(f"====================================================================")
print("Initiating Class-5 Stress Test (1,000 continuous AST physical scans)...\n")

t0 = time.time()
iterations = 1000

# Perform the scan 1000 times natively in memory
for _ in range(iterations):
    _ = nexus_core.scan_and_diagnose(target_file)

t1 = time.time()
total_time_ms = (t1 - t0) * 1000
avg_time_ms = total_time_ms / iterations

print(f"[STRESS TEST COMPLETED]")
print(f"✅ Executed {iterations} full AST sensory scans.")
print(f"⏱️ Total Time for 1,000 scans: {total_time_ms:.2f} ms")
print(f"⚡ Average Time per scan: {avg_time_ms:.4f} ms")
print(f"\n[PERFORMANCE BENCHMARK]")
print(f"🔴 Nexus v16 (Subprocess + IPC): ~150.00 ms per scan")
print(f"🟢 {armor_name} (Zero-IPC Sync)  : {avg_time_ms:.4f} ms per scan")

speedup = 150.0 / avg_time_ms
print(f"🚀 Acceleration Factor         : {speedup:.1f}x Faster")
print(f"====================================================================")
