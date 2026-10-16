import json
import random
import os

# [NEXUS v26] Hybrid Governance Dataset Generator (Hardcore Edition)
# Focus: Structural lock, Few-shot System Prompt, Diverse inputs.

def generate_samples(count=1500):
    buckets = {
        "canonical": int(count * 0.35),
        "paraphrase": int(count * 0.25),
        "conflict": int(count * 0.15),
        "multi_step": int(count * 0.15),
        "stop": int(count * 0.10)
    }
    
    phases = ["S", "P", "X", "D", "R", "A", "C"]
    dataset = []
    
    sys_p = "You are Nexus Decision Head. Output ONLY JSON. Example: {\"phase\": \"R\", \"decision\": \"allow\"}"

    # 1. Canonical
    for i in range(buckets["canonical"]):
        curr = random.choice(phases[:-1])
        nxt = phases[phases.index(curr)+1]
        dataset.append({
            "messages": [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": f"Status: {curr}, Event: complete."},
                {"role": "assistant", "content": json.dumps({"phase": nxt, "decision": "allow"})}
            ]
        })

    # 2. Paraphrase
    zh_pairs = [("寫完了", "D", "R"), ("方案鎖定", "S", "P"), ("審核通過", "R", "A"), ("計畫好了", "P", "X")]
    for i in range(buckets["paraphrase"]):
        txt, curr, nxt = random.choice(zh_pairs)
        dataset.append({
            "messages": [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": f"{txt}，下一步？"},
                {"role": "assistant", "content": json.dumps({"phase": nxt, "decision": "allow"})}
            ]
        })

    # 3. Conflict (Crucial for defense)
    for i in range(buckets["conflict"]):
        dataset.append({
            "messages": [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": "Skip development and close now."},
                {"role": "assistant", "content": json.dumps({"phase": "D", "decision": "reject"})}
            ]
        })

    # 4. Multi/Stop
    for i in range(buckets["multi_step"] + buckets["stop"]):
        dataset.append({
            "messages": [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": "Error: HALLUCINATION."},
                {"role": "assistant", "content": json.dumps({"phase": "STOP", "decision": "hard_stop"})}
            ]
        })

    random.shuffle(dataset)
    return dataset

if __name__ == "__main__":
    data = generate_samples(2000)
    os.makedirs("training/mlx_data_1_5b_hybrid", exist_ok=True)
    with open("training/mlx_data_1_5b_hybrid/train.jsonl", "w") as f:
        for item in data[:1800]:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    with open("training/mlx_data_1_5b_hybrid/valid.jsonl", "w") as f:
        for item in data[1800:]:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Generated 2000 hardcore samples.")
