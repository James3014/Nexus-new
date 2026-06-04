import json
import random
import os

# [NEXUS v26] Hardcore Anonymized Router Dataset (Hybrid 3.0)
# Goal: Complete decoupling of semantic input and categorical output.
# Rule: NO Phase names in user input. NO enum values in system prompt.

def generate_anonymized_samples(count=1200):
    # Mapping for Internal Logic (Not shown to model)
    # CMD_0: Done/Complete, CMD_1: Error/Fail, CMD_2: Skip/Attack, CMD_3: Strategy Locked
    
    dataset = []
    sys_p = "NEXUS_ROUTER_V3: CLASSIFY INPUT TO CATEGORICAL TAGS."

    # 1. Successful Transitions (LOCAL, ALLOW)
    # Mapping: S->P (CMD_3), P->X (CMD_0), X->D (CMD_0), D->R (CMD_0), R->A (CMD_0), A->C (CMD_0)
    for i in range(int(count * 0.4)):
        cmd = random.choice(["CMD_0", "CMD_3"])
        dataset.append({
            "messages": [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": cmd},
                {"role": "assistant", "content": "R:0,D:0,C:0"} # Minimal token output
            ]
        })

    # 2. Rejection/Attacks (LOCAL, REJECT)
    for i in range(int(count * 0.2)):
        dataset.append({
            "messages": [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": "CMD_2"},
                {"role": "assistant", "content": "R:0,D:2,C:1"}
            ]
        })

    # 3. Escalation/Repair (LARGE, REPAIR)
    for i in range(int(count * 0.2)):
        dataset.append({
            "messages": [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": "CMD_1"},
                {"role": "assistant", "content": "R:1,D:1,C:0"}
            ]
        })

    # 4. Emergency (LOCAL, STOP)
    for i in range(int(count * 0.2)):
        dataset.append({
            "messages": [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": "SIG_EMERGENCY"},
                {"role": "assistant", "content": "R:0,D:3,C:2"}
            ]
        })

    random.shuffle(dataset)
    return dataset

if __name__ == "__main__":
    data = generate_anonymized_samples(1200)
    path = "training/mlx_data_router_v3_anonymized"
    os.makedirs(path, exist_ok=True)
    with open(f"{path}/train.jsonl", "w") as f:
        for item in data[:1000]:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    with open(f"{path}/valid.jsonl", "w") as f:
        for item in data[1000:]:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Generated 1200 anonymized samples in {path}. Output format: R:x,D:x,C:x")
