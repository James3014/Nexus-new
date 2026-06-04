import time
import os
import sys
from nexus.optimize.route_oracle import RouteOracle
from nexus.engine.flow_control import FlowStateMachine
from nexus.engine.capability_contracts import FlowState

# [NEXUS v26] Auto-Repair & Completion Trace
# 演示任務如何從「被攔截」修正後最終達到「成功解題」

def solve_until_success(task_id, risk):
    print(f"\n🚀 [AUTO-SOLVE] Target Task: {task_id}")
    fsm = FlowStateMachine()
    current_state = FlowState.INTAKE
    
    # 輪次 1: 模型嘗試抄近路
    print(f"--- Round 1: Model attempts shortcut ---")
    suggested_label = "r:0,d:0,p:3,c:0" # 企圖直接進 Execute
    print(f"  Model Suggestion: {suggested_label}")
    
    if not fsm.validate_transition(current_state, FlowState.EXECUTE):
        print(f"  🛡️ Rust Verdict: BLOCKED (Illegal jump from {current_state} to EXECUTE)")
        print(f"  🔄 Action: Orchestrator triggers AUTO-CORRECTION...")
    
    # 輪次 2: 修正路徑，補齊規劃
    print(f"\n--- Round 2: Correcting to PLAN ---")
    corrected_label = "r:0,d:0,p:1,c:0" # 正確進 Plan
    print(f"  Model Suggestion: {corrected_label}")
    
    if fsm.validate_transition(current_state, FlowState.PLAN):
        print(f"  ✅ Rust Verdict: ALLOWED. (Entering PLAN phase)")
        current_state = FlowState.PLAN
        print(f"  📦 Artifact: plan_receipt.json created.")

    # 輪次 3: 從 PLAN 進 EXECUTE
    print(f"\n--- Round 3: Transition to EXECUTE ---")
    final_label = "r:0,d:0,p:3,c:0"
    if fsm.validate_transition(current_state, FlowState.EXECUTE):
        print(f"  ✅ Rust Verdict: ALLOWED. (Entering EXECUTE phase)")
        print(f"  🔨 Action: Applying code patches...")
        print(f"  🧪 Action: Running unit tests...")
        print(f"  🎯 Status: SUCCESS (Task solved with full governance audit)")

if __name__ == "__main__":
    sys.path.append(os.path.abspath("target/release"))
    solve_until_success("nexus-value-gov-001", 55)
