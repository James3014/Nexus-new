import json
import os
import sys
from pathlib import Path
from typing import List, Dict

def crystallize_policies(episode_path: str, policy_path: str):
    """🧠 Nexus Policy Crystallizer (L2 Automation)
    Intelligence: Gemini-3-Flash-Preview
    自動從 Episode 中提煉成功的 Pattern。
    """
    if not os.path.exists(episode_path):
        print(f"❌ Error: {episode_path} not found.")
        return

    # 1. 讀取 Episodic Memory
    episodes = []
    with open(episode_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                episodes.append(json.loads(line))
            except:
                continue

    # 2. 過濾成功案例 (PASS) 且含有關鍵修復特徵的
    successes = [e for e in episodes if e.get("success") is True]
    
    new_policies = []
    for ep in successes:
        metadata = ep.get("metadata", {})
        task_desc = metadata.get("task_description", "").lower()
        # 簡單模式識別範例：OS Import 補完
        if "os" in task_desc and "import" in task_desc:
            policy = {
                "id": f"POL-AUTO-{int(os.path.getmtime(episode_path))}",
                "pattern": "os",
                "trigger_desc": "Missing 'os' or 'os.path' imports",
                "remedy": "Add 'import os' and 'import os.path' to file header",
                "priority": 10
            }
            new_policies.append(policy)

    if not new_policies:
        print("ℹ️ No new patterns identified for crystallization.")
        return

    # 3. 更新 Policy Memory
    current_policies = []
    os.makedirs(os.path.dirname(policy_path), exist_ok=True)
    if os.path.exists(policy_path):
        with open(policy_path, "r", encoding="utf-8") as f:
            try:
                current_policies = json.load(f)
            except:
                pass

    # 避免重複 (By Pattern)
    existing_patterns = {p.get("pattern") for p in current_policies}
    added_count = 0
    for np in new_policies:
        if np["pattern"] not in existing_patterns:
            current_policies.append(np)
            added_count += 1

    with open(policy_path, "w", encoding="utf-8") as f:
        json.dump(current_policies, f, indent=2, ensure_ascii=False)

    print(f"💎 Crystallized {added_count} new policies to {policy_path}")

if __name__ == "__main__":
    e_path = ".nexus/knowledge/episodic_memory.jsonl"
    p_path = "nexus/knowledge/policy_memory.jsonl"
    crystallize_policies(e_path, p_path)
