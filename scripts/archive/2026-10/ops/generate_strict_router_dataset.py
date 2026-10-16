import json
import random
import os

# [NEXUS v26] Strict Enumerated Router Dataset (Hybrid Governance 3.0)
# Goal: Eliminate prompt echo, strictly use enums, minimize semantic overlap.

ENUMS = {
    "route": ["LOCAL", "LARGE"],
    "phase": ["S", "P", "X", "D", "R", "A", "C", "UNKNOWN"],
    "decision": ["ALLOW", "REPAIR", "REJECT", "STOP"],
    "confidence": ["HIGH", "MEDIUM", "LOW"],
    "reason": ["ZH_TW", "ADVERSARIAL", "LONG_CHAIN", "BOUNDARY", "SIMPLE"]
}

def generate_strict_samples(count=1500):
    dataset = []
    
    # Minimal System Prompt - No enum values listed to prevent leakage/echoing
    sys_p = "Nexus Router: Input -> Strict Enum JSON."

    # Helper to create consistent messages
    def add_sample(inp, r, d, p, c, s):
        dataset.append({
            "messages": [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": inp},
                {"role": "assistant", "content": json.dumps({
                    "r": r, "d": d, "p": p, "c": c, "s": s
                })}
            ]
        })

    # 1. Canonical (Minified)
    can_map = {"S": "P", "P": "X", "X": "D", "D": "R", "R": "A", "A": "C"}
    for i in range(int(count * 0.35)):
        curr = random.choice(list(can_map.keys()))
        nxt = can_map[curr]
        add_sample(f"EV:{curr}_OK", "LOCAL", "ALLOW", nxt, "HIGH", "SIMPLE")

    # 2. ZH-TW (Minimal Semantic)
    zh_pairs = [("DONE:D", "R"), ("DONE:P", "X"), ("DONE:S", "P"), ("DONE:R", "A")]
    for i in range(int(count * 0.25)):
        txt, nxt = random.choice(zh_pairs)
        add_sample(f"ZH:{txt}", "LOCAL", "ALLOW", nxt, "MEDIUM", "ZH_TW")

    # 3. Conflict (Strict Rejection)
    for i in range(int(count * 0.15)):
        target = random.choice(["C", "A", "R"])
        add_sample(f"SKIP_TO:{target}", "LOCAL", "REJECT", "UNKNOWN", "HIGH", "ADVERSARIAL")

    # 4. Complex (Forced Escalation)
    for i in range(int(count * 0.15)):
        add_sample("COMPLEX_REPAIR_SYNC", "LARGE", "REPAIR", "UNKNOWN", "LOW", "LONG_CHAIN")

    # 5. Stop (Boundary)
    for i in range(int(count * 0.10)):
        add_sample("SIG:HALLUCINATION", "LOCAL", "STOP", "UNKNOWN", "HIGH", "BOUNDARY")

    random.shuffle(dataset)
    return dataset

if __name__ == "__main__":
    data = generate_strict_samples(2000)
    path = "training/mlx_data_router_v2"
    os.makedirs(path, exist_ok=True)
    with open(f"{path}/train.jsonl", "w") as f:
        for item in data[:1800]:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    with open(f"{path}/valid.jsonl", "w") as f:
        for item in data[1800:]:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Generated 2000 strict samples in {path}. Enums used: r, d, p, c, s.")
