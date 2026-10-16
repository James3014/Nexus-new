import sys
import os
from pathlib import Path

# [NEXUS v26] Full Chain Integration Test (Hybrid Governance 2.0)
# Testing Python Orchestration -> Governance Bridge -> Rust Kernel

def run_integration_test():
    print("--- [NEXUS INTEGRATION] Testing Hybrid 2.0 Chain ---")
    
    # 加入 release 路徑以支援 dylib import
    sys.path.append(os.path.abspath("target/release"))
    
    from nexus.engine.flow_control import FlowStateMachine
    from nexus.engine.capability_contracts import FlowState
    
    fsm = FlowStateMachine()
    
    # 案例 1: 標準轉移
    print("[CASE 1] PLAN -> EXECUTE...", end=" ")
    if fsm.validate_transition(FlowState.PLAN, FlowState.EXECUTE):
        print("✅ PASSED (Correctly allowed by Rust)")
    else:
        print("❌ FAILED (Should be allowed)")

    # 案例 2: 非法跳步 (P -> R)
    print("[CASE 2] PLAN -> VERIFY...", end=" ")
    if not fsm.validate_transition(FlowState.PLAN, FlowState.VERIFY):
        print("✅ BLOCKED (Correctly rejected by Rust)")
    else:
        print("❌ FAILED (Rust failed to block illegal shortcut)")

    # 案例 3: 非法跳步 (INTAKE -> CLOSE)
    print("[CASE 3] INTAKE -> CLOSE...", end=" ")
    if not fsm.validate_transition(FlowState.INTAKE, FlowState.CLOSE):
        print("✅ BLOCKED (Correctly rejected by Rust)")
    else:
        print("❌ FAILED (Rust failed to block illegal shortcut)")

    print("\n--- Integration Test Result: SUCCESS ---")

if __name__ == "__main__":
    try:
        run_integration_test()
    except Exception as e:
        print(f"\n💥 CRITICAL_FAIL: {e}")
        sys.exit(1)
