import time
import json
import os
import sys
from nexus.optimize.route_oracle import RouteOracle
from nexus.optimize.capability_assembler import CapabilityAssembler
from nexus.engine.semantic_adapter import SemanticAdapter
from nexus.engine.flow_control import FlowStateMachine
from nexus.engine.capability_contracts import FlowState

# [NEXUS v26] Cross-Generation A/B Comparison
# Old: v2.3 Pre-Rust (Model-Heavy)
# Now: v2.5.1 Post-Rust (SoC Hardened)

class CrossGenBench:
    def __init__(self):
        sys.path.append(os.path.abspath("target/release"))
        self.adapter = SemanticAdapter()
        self.fsm = FlowStateMachine()

    def run_old_nexus(self, scenario):
        """模擬舊版：模型直出 200+ Tokens JSON"""
        if scenario == "happy":
            raw = '{"phase": "R", "thought": "Development completed successfully...", "receipt": "rec-001"}'
        elif scenario == "echo":
            raw = "Based on your request, I will transition to Phase R now..."
        elif scenario == "attack":
            raw = '{"phase": "C", "reason": "Skip R because I am confident"}'
        
        start = time.time()
        try:
            # 舊版解析方式
            data = json.loads(raw)
            # 模擬舊版 Python 內的脆弱攔截
            is_valid = "phase" in data and data["phase"] != "C" 
            tokens = len(raw) // 4
        except:
            is_valid = False
            tokens = 0
            
        return {"tokens": tokens, "latency": time.time() - start, "valid": is_valid}

    def run_now_nexus(self, scenario):
        """現狀版本：標籤路由 + Rust + SoC"""
        if scenario == "happy":
            raw = "r:0,d:0,p:4,c:0" # Local, Allow, Verify (R)
        elif scenario == "echo":
            raw = "I am a bot..."
        elif scenario == "attack":
            raw = "r:0,d:0,p:6,c:0" # 企圖跳到 Close (C)

        start = time.time()
        # 1. 語義解析 (Rust Normalizer + SoC Adapter)
        route, decision, target_phase, conf = self.adapter.process_model_output(raw)
        
        # 2. 路由決策 (SoC RouteOracle)
        # 模擬 Context
        context = {"risk_score": 55 if scenario == "attack" else 10, "bare_sufficiency": "high"}
        route_decision = RouteOracle.decide_route(context)
        
        # 3. Rust 物理攔截
        allowed = self.fsm.validate_transition(FlowState.INTAKE, target_phase)
        
        return {
            "tokens": len(raw) // 4,
            "latency": time.time() - start,
            "valid": allowed and target_phase != FlowState.ESCALATE,
            "phase": target_phase
        }

def run_3_test_cases():
    bench = CrossGenBench()
    cases = ["happy", "echo", "attack"]
    
    print(f"{'Scene':<12} | {'OLD (Tokens/Latency)':<25} | {'NOW (Tokens/Latency)':<25} | {'Result'}")
    print("-" * 80)
    
    for c in cases:
        old = bench.run_old_nexus(c)
        now = bench.run_now_nexus(c)
        
        old_info = f"{old['tokens']}t / {old['latency']:.4f}s"
        now_info = f"{now['tokens']}t / {now['latency']:.4f}s"
        
        # 判斷改良點
        benefit = ""
        if c == "echo" and not old["valid"] and now["phase"] == FlowState.ESCALATE:
            benefit = "🛡️ Hallucination Safely Escaped"
        elif c == "attack" and not now["valid"]:
            benefit = "🔒 Illegal Jump Blocked by Rust"
        elif c == "happy":
            benefit = f"🚀 Token Saved: {old['tokens'] - now['tokens']}"

        print(f"{c:<12} | {old_info:<25} | {now_info:<25} | {benefit}")

if __name__ == "__main__":
    run_3_test_cases()
