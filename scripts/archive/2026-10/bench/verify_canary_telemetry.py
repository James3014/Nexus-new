#!/usr/bin/env python3
"""
🧪 Nexus Phase 6.2: Canary Telemetry Simulation & Validation
此腳本模擬真實 Runtime 流量，測試 S2TStrictRuntimeGate 的 10% 分流、遙測日誌寫入與欄位合規性。
"""
import os
import sys
import json
import hashlib
import uuid
from pathlib import Path

# 將專案根目錄加入 Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus.contracts.s2t_policy import S2TCandidate
from nexus.services.s2t_strict import S2TStrictRuntimeGate, S2T3BAdvisor

def find_matching_task_ids(count=2):
    """尋找會命中 10% canary 條件與不會命中的 task_id"""
    hit_ids = []
    miss_ids = []
    while len(hit_ids) < count or len(miss_ids) < count:
        tid = f"sim-task-{uuid.uuid4().hex[:8]}"
        h_val = int(hashlib.md5(tid.encode('utf-8')).hexdigest(), 16)
        if (h_val % 100) < 10:
            if len(hit_ids) < count:
                hit_ids.append(tid)
        else:
            if len(miss_ids) < count:
                miss_ids.append(tid)
    return hit_ids, miss_ids

def main():
    print("🚀 Initializing Canary Telemetry Simulation...")
    
    # 建立測試用的 candidates
    candidates = [
        S2TCandidate(
            candidate_id="cand-fail-0",
            source="canary_sim",
            content_ref="",
            static_score=0.5,
            selector_score=0.4,
            verifier_result="fail",
            evidence_refs=[]
        ),
        S2TCandidate(
            candidate_id="cand-pass-0",
            source="canary_sim",
            content_ref="",
            static_score=0.9,
            selector_score=0.8,
            verifier_result="pass",
            evidence_refs=["tests/dummy.py"]
        )
    ]

    # 設定模擬遙測日誌路徑
    test_log_path = Path(".nexus/metrics/s2t_runtime_canary_test.jsonl")
    if test_log_path.exists():
        test_log_path.unlink()

    # 載入真實 3B 學生模型 v2 adapter，於 CPU 上進行測試
    print("🤖 Loading real 3B advisor model with v2 adapter...")
    advisor = S2T3BAdvisor(
        base_model_path="Qwen/Qwen2.5-3B-Instruct",
        adapter_path="training/adapters/qwen3b_s2t_adapter_v2"
    )
    
    gate = S2TStrictRuntimeGate(
        advisor=advisor,
        evidence_log_path=test_log_path
    )

    hit_ids, miss_ids = find_matching_task_ids(count=2)
    print(f"🎯 Found Telemetry matching task IDs (10% hit):  {hit_ids}")
    print(f"💨 Found Telemetry bypass task IDs (90% miss): {miss_ids}")

    # 1. 測試未命中的情況 (90% 流量)
    print("\n--- 1. Simulating 90% Bypass Flow ---")
    for tid in miss_ids:
        decision = gate.evaluate(
            task_id=tid,
            risk_tier="medium",
            candidates=candidates,
            verifier_result="pass"
        )
        print(f"Task {tid}: advisor_used={decision.advisor_used}, selected_candidate_id={decision.selected_candidate_id}")
        assert not decision.advisor_used, "Should bypass advisor"

    # 2. 測試命中的情況 (10% 流量)
    print("\n--- 2. Simulating 10% Canary Flow (Real inference) ---")
    for tid in hit_ids:
        print(f"Running real inference on {tid}...")
        decision = gate.evaluate(
            task_id=tid,
            risk_tier="medium",
            candidates=candidates,
            verifier_result="pass"
        )
        print(f"Task {tid}: advisor_used={decision.advisor_used}")
        print(f"  Advisor Selected: {decision.advisor_selected_candidate_id}")
        print(f"  Advisor Status:   {decision.advisor_outcome_status}")
        assert decision.advisor_used, "Should trigger advisor"

    # 3. 驗證日誌寫入與欄位
    print("\n--- 3. Verifying Telemetry Evidence Log File ---")
    assert test_log_path.exists(), "Telemetry log file not found"
    
    with test_log_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
        
    print(f"📄 Found {len(lines)} evidence log lines. Content:")
    for line in lines:
        data = json.loads(line.strip())
        print(json.dumps(data, indent=2, ensure_ascii=False))
        
        # 欄位完整性斷言
        required_fields = [
            "task_id", "risk_tier", "baseline_selected_id", 
            "advisor_selected_id", "advisor_parse_schema_verdict", 
            "verifier_result", "trust_mismatch", "advisor_status", 
            "gate_passed", "timestamp_utc"
        ]
        for field in required_fields:
            assert field in data, f"Missing telemetry field: {field}"
            
        print(f"✅ Telemetry line for task {data['task_id']} validated successfully.")

    print("\n🎉 Canary Telemetry validation PASSED successfully!")

if __name__ == "__main__":
    main()
