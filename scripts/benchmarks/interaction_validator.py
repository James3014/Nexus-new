#!/usr/bin/env python3
import subprocess
import json
import yaml
from pathlib import Path
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".nexus" / "governance_policy.yaml"
SAMPLER_BIN = REPO_ROOT / "scripts/benchmarks/credible_sampler.py"

def run_interaction_test(scenario_name: str, overrides: dict):
    print(f"\n🚀 [Interaction-Tier] Running Scenario: {scenario_name}")
    
    # 1. 物理備份並覆寫政策
    original_content = POLICY_PATH.read_text()
    policy = yaml.safe_load(original_content)
    
    # 注入 overrides
    for k, v in overrides.items():
        policy["default"]["meta_evolution"][k] = v
        
    POLICY_PATH.write_text(yaml.dump(policy))
    
    try:
        # 2. 真實執行可信採樣
        res = subprocess.run([
            "python3", str(SAMPLER_BIN),
            "--target-file", "nexus/core/handoff_bundle.py",
            "--n-samples", "3"
        ], capture_output=True, text=True)
        
        # 3. 提取真實數據
        # 從 JSON 報告中讀取 mu/sigma
        report_path = REPO_ROOT / ".nexus" / "reports" / "credible_sampling_report.json"
        report = json.loads(report_path.read_text())
        
        mu = report["summary"]["mu"]
        sigma = report["summary"]["sigma"]
        
        print(f"📊 Result: mu={mu:.4f}, sigma={sigma:.4f}")
        return mu, sigma
    finally:
        # 4. 物理還原
        POLICY_PATH.write_text(original_content)

if __name__ == "__main__":
    print("🌌 [v24.2] Initiating Real Pairwise Interaction Validation...")
    
    # 場景 A: 平衡模式 (Baseline)
    mu_base, _ = run_interaction_test("Balanced (Default)", {})
    
    # 場景 B: 高侵略性 × 嚴格治理 (Stress Test)
    # 測試這兩者是否會發生互相放大導致的退化
    mu_stress, _ = run_interaction_test("High Aggression x Strict Entropy", {
        "global_nas_aggression": 0.95,
        "system_entropy_tolerance": 5.0
    })
    
    delta = mu_stress - mu_base
    print("\n" + "="*50)
    print(f"📉 Interaction Delta: {delta:+.4f}")
    if delta < -0.1:
        print("❌ [DEGRADED] Interaction effect detected. Parameters are conflicting.")
    else:
        print("🟢 [COHERENT] Systems are resonating harmoniously.")
    print("="*50)
