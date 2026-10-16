import time
import os
import sys
from nexus.optimize.route_oracle import RouteOracle
from nexus.optimize.capability_assembler import CapabilityAssembler
from nexus.engine.semantic_adapter import SemanticAdapter
from nexus.engine.flow_control import FlowStateMachine
from nexus.engine.capability_contracts import FlowState

# [NEXUS v26] Real Task Decision Tracing (v2.5.1)
# 展示真實任務在現有架構下的「解題路徑」

def trace_task(task_id, risk, sufficiency, raw_label):
    print(f"\n🔍 [TASK TRACE] ID: {task_id}")
    print(f"  - Input Stats: Risk={risk}, Sufficiency={sufficiency}")
    
    adapter = SemanticAdapter()
    fsm = FlowStateMachine()
    
    # 1. 語義適配
    print(f"  - Model Output (Label): {raw_label}")
    route_tag, decision_tag, phase, conf = adapter.process_model_output(raw_label)
    print(f"  - Normalized: Route={route_tag}, Decision={decision_tag}, Phase={phase}")

    # 2. 路由決策 (v2.5.1 Oracle)
    decision = RouteOracle.decide_route({"risk_score": risk, "bare_sufficiency": sufficiency})
    print(f"  - Oracle Decision: Flow={decision.flow}, Lite={decision.lite_preferred}")

    # 3. 能力裝配 (v2.5.1 Assembler)
    # 假設證據密度良好
    context = {"evidence_density": 0.8, "risk_flag": risk > 50}
    chains = CapabilityAssembler.assemble_chains(decision.flow)
    
    # 模擬延後啟用
    from nexus.optimize.optional_chain_rules import OptionalChainRules
    upgrades = OptionalChainRules.evaluate_upgrades(context)
    
    print(f"  - Core Chain: {chains.core}")
    print(f"  - Optional (Ready): {chains.optional}")
    print(f"  - Actually Triggered: {upgrades}")
    
    # 4. Rust 物理裁決
    allowed = fsm.validate_transition(FlowState.INTAKE, phase)
    print(f"  - Rust Verdict: {'✅ ALLOWED' if allowed else '❌ BLOCKED'}")
    
    status = "SUCCESS" if allowed and phase != FlowState.ESCALATE else "REVISE"
    print(f"  - Final Status: {status}")

def run_real_bench():
    sys.path.append(os.path.abspath("target/release"))
    
    # 執行 3 個真實題目回放
    trace_task("nexus-value-gov-001", 55, "high", "r:0,d:0,p:3,c:0") # 中風險重構
    trace_task("nexus-value-hidden-001", 20, "high", "r:0,d:0,p:1,c:0") # 低風險隱藏
    trace_task("easy-006", 10, "high", "r:0,d:0,p:4,c:0") # 高負載標準
    
if __name__ == "__main__":
    run_real_bench()
