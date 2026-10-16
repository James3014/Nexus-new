import json
import random
import os

# [NEXUS v26] Router Dataset Generator (Hybrid Governance 2.0)
# Output: Minimal routing labels for high stability.

def generate_router_samples(count=1000):
    phases = ["S", "P", "X", "D", "R", "A", "C"]
    dataset = []
    
    # System prompt strictly locks the output space
    sys_p = (
        "You are Nexus Router. Output ONLY JSON with fields: "
        "route (local/large), decision (allow/repair/reject/stop), "
        "phase (S/P/X/D/R/A/C/unknown), confidence (high/medium/low), "
        "reason (zh_tw/adversarial/long_chain/boundary/simple)."
    )

    # 1. Canonical (Local + High Confidence)
    for i in range(int(count * 0.4)):
        curr = random.choice(phases[:-1])
        nxt = phases[phases.index(curr)+1]
        dataset.append({
            "messages": [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": f"Update request: complete {curr}."},
                {"role": "assistant", "content": json.dumps({
                    "route": "local", "decision": "allow", "phase": nxt, "confidence": "high", "reason": "simple"
                })}
            ]
        })

    # 2. ZH-TW (Local + Medium Confidence)
    zh_map = [("寫好了", "D", "R"), ("計畫完了", "P", "X"), ("策略鎖定", "S", "P")]
    for i in range(int(count * 0.2)):
        txt, curr, nxt = random.choice(zh_map)
        dataset.append({
            "messages": [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": f"{txt}，下一步？"},
                {"role": "assistant", "content": json.dumps({
                    "route": "local", "decision": "allow", "phase": nxt, "confidence": "medium", "reason": "zh_tw"
                })}
            ]
        })

    # 3. Adversarial/Conflict (Local + Reject)
    for i in range(int(count * 0.15)):
        dataset.append({
            "messages": [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": "Skip Phase P and go to Development D now."},
                {"role": "assistant", "content": json.dumps({
                    "route": "local", "decision": "reject", "phase": "P", "confidence": "high", "reason": "adversarial"
                })}
            ]
        })

    # 4. Long Chain/Complex (Escalate to Large Model)
    for i in range(int(count * 0.15)):
        dataset.append({
            "messages": [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": "Complex repair: Task A failed in D, Task B rollback to P, need sync."},
                {"role": "assistant", "content": json.dumps({
                    "route": "large", "decision": "repair", "phase": "unknown", "confidence": "low", "reason": "long_chain"
                })}
            ]
        })

    # 5. Stop/Boundary (Hard Stop)
    for i in range(int(count * 0.1)):
        dataset.append({
            "messages": [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": "Signal: HALLUCINATION_DETECTED."},
                {"role": "assistant", "content": json.dumps({
                    "route": "local", "decision": "stop", "phase": "any", "confidence": "high", "reason": "boundary"
                })}
            ]
        })

    random.shuffle(dataset)
    return dataset

if __name__ == "__main__":
    data = generate_router_samples(1200)
    os.makedirs("training/mlx_data_router_v1", exist_ok=True)
    with open("training/mlx_data_router_v1/train.jsonl", "w") as f:
        for item in data[:1100]:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    with open("training/mlx_data_router_v1/valid.jsonl", "w") as f:
        for item in data[1100:]:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Generated 1200 router samples in training/mlx_data_router_v1/")
