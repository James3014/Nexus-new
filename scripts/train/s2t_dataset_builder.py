import json
import os
from pathlib import Path
import yaml

# Paths
S2T_TRACE_PATH = Path(".nexus/reports/token_ab/runs_raw.jsonl")
RULES_PATH = Path("training/allowlist_rules.yaml")
OUTPUT_PATH = Path("training/dataset_sft_skeleton_v1.jsonl")

def load_allowlist():
    with open(RULES_PATH, "r") as f:
        return yaml.safe_load(f)

def build_sft_sample(event, allowlist):
    """
    將 S2T Trace 轉化為 7B Skeleton 訓練樣本
    聚焦於：Current Phase -> Next Phase + Receipt Readiness
    """
    # 這裡實作從 event 提取 skeleton 邏輯的篩選
    # 只保留成功的路徑，並過濾掉 patch 細節
    instruction = f"Task Context: {event.get('task_type')}, Current Phase: {event.get('phase')}"
    
    # 模擬 7B 腦幹的正確決策
    chosen_thought = f"Phase {event.get('phase')} completed with success. Preparing receipt and transitioning."
    chosen_action = {
        "next_step": "PHASE_TRANSITION",
        "payload": {
            "target": "R" if event.get('phase') == "X" else "C",
            "reason": "gate_passed"
        }
    }
    
    return {
        "messages": [
            {"role": "system", "content": "You are the Nexus Skeleton Engine. Focus on orchestration and governance."},
            {"role": "user", "content": instruction},
            {"role": "assistant", "content": f"<thought>{chosen_thought}</thought>\n```json\n{json.dumps(chosen_action)}\n```"}
        ]
    }

def main():
    if not S2T_TRACE_PATH.exists():
        print("❌ S2T Traces not found.")
        return

    allowlist = load_allowlist()
    samples = []
    
    with open(S2T_TRACE_PATH, "r") as f:
        for line in f:
            event = json.loads(line)
            # 只取成功的穩定且訓練合規的路徑
            if event.get("success") == 1 and event.get("training_eligible", True) == True:
                samples.append(build_sft_sample(event, allowlist))
    
    with open(OUTPUT_PATH, "w") as f:
        for s in samples:
            f.write(json.dumps(s) + "\n")
            
    print(f"✅ Build {len(samples)} skeleton SFT samples at {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
