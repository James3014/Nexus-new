import sys
import time
import os

# Link the compiled Rust Native Chip
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "nexus-core", "target", "release"))

print("🚀 Booting Nexus v16.5 Hybrid Singularity ...\n")
t0 = time.time()

try:
    # 1. Nerve loads the Muscle & Eye into same memory space
    import nexus_core
    t_load = time.time()
    
    # Target: The old reflex source code
    target_file = os.path.join(os.path.dirname(__file__), "..", "nexus-reflex", "src", "main.rs")
    
    print("[NERVE: PYTHON] Delegating AST Sensing to MUSCLE (Rust Native Core) via Memory Binding...")
    # 2. Execute Zero-IPC audit
    result = nexus_core.scan_and_diagnose(target_file)
    t_scan = time.time()
    
    print("\n====================================================================")
    print("🛡️ NEXUS-V16.5 HYBRID SINGULARITY ACTIVE | ZERO-IPC ARCHITECTURE 🛡️")
    print("====================================================================")
    print(f"✅ PyO3 Core Injection: {(t_load - t0)*1000:.3f} ms")
    print(f"--------------------------------------------------------------------")
    print(result)
    print(f"--------------------------------------------------------------------")
    print(f"✅ Global Execution Time (Nerve -> Muscle -> Nerve): {(t_scan - t_load)*1000:.3f} ms")
    print(f"🔥 SOTA Total Boot to Action Time: {(t_scan - t0)*1000:.3f} ms")
    print("====================================================================")

except ImportError as e:
    print(f"\n❌ Failed to load Hybrid Core: {e}")
    print("Did you run `cargo build --release` and copy the .so file?")
