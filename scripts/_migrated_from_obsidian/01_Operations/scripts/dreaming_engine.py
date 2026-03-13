#!/usr/bin/env python3
# 🛡️ Codex-Verified: Codex-Auth-Lvl13-Final (2026-03-03)
import sys
import json
import subprocess
import re
import os
import random
from datetime import datetime

SEARCH_BIN = "/Users/jameschen/Downloads/obsidian/知識庫/01_Operations/scripts/brain_search_v2.py"
OPENCLAW_BIN = "/Users/jameschen/.npm-global/bin/openclaw"
OUTPUT_DIR = "/Users/jameschen/Downloads/obsidian/知識庫/06_Synthesized_Insights"
DREAM_LOG = "/Users/jameschen/Downloads/obsidian/知識庫/01_Operations/LAST_DREAM.json"

def get_random_seeds():
    """隨機選取兩個不同類別的檢索種子"""
    categories = ["滑雪技術物理學", "商業戰略與資本管理", "教育心理學", "AI系統架構", "理財與風險控制"]
    return random.sample(categories, 2)

def fetch_isomorphic_nodes(seed):
    """檢索具有結構相似性的知識點"""
    try:
        cmd = ["/Users/jameschen/.local/bin/uv", "run", "--with", "lancedb", "--with", "pandas", "--with", "requests", SEARCH_BIN, seed, "--limit", "5", "--json"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        return json.loads(res.stdout)
    except:
        return []

def play_glass_bead_game():
    print("🌌 [Dreaming Engine] 正在進入深層睡眠模式，啟動 Glass Bead Game...")
    
    seeds = get_random_seeds()
    print(f"🔮 夢境連結：{seeds[0]} <---> {seeds[1]}")
    
    nodes_a = fetch_isomorphic_nodes(seeds[0])
    nodes_b = fetch_isomorphic_nodes(seeds[1])
    
    if not nodes_a or not nodes_b:
        print("⚠️ 知識點不足，夢境崩塌。")
        return

    context_a = "\n".join([f"- {n.get('text', '')}" for n in nodes_a])
    context_b = "\n".join([f"- {n.get('text', '')}" for n in nodes_b])

    prompt = f"""
你是一位掌握了「玻璃球遊戲 (The Glass Bead Game)」精髓的跨維度合成者。
你的目標是找出以下兩個領域之間的「同構性 (Isomorphism)」，並產出一個激進的跨維度戰略提案。

### 領域 A: {seeds[0]}
{context_a}

### 領域 B: {seeds[1]}
{context_b}

請執行以下「夢境合成」：
1. **結構映射**：找出領域 A 的某個核心機制（如：換刃控制）與領域 B 某個隱藏邏輯（如：現金流燒錢率）之間的結構性相似。
2. **雜交提案**：撰寫一份標題極具洞見的文章，說明領域 A 的規律如何能直接「診斷」或「優化」領域 B。
3. **戰略處方箋**：給出 3 個具體的行動建議。

格式：
TITLE: 標題
CONTENT:
---
title: "標題"
type: dream-insight
---
# 標題
> **夢境洞察**：(一句話總結同構性)
## 🌌 同構性分析
## 🚀 跨維度戰略提案
"""

    try:
        print("🧠 正在進行高維度語義對撞...")
        cmd = [OPENCLAW_BIN, 'agent', '--agent', 'main', '--message', prompt, '--json']
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=200)
        
        match = re.search(r'\{.*\}', process.stdout, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            payloads = data.get('result', {}).get('payloads') or data.get('payloads', [])
            output = payloads[0].get('text', '') if payloads else ''
            
            if "TITLE:" in output and "CONTENT:" in output:
                title = output.split("CONTENT:")[0].replace("TITLE:", "").strip()
                content = output.split("CONTENT:")[1].strip()
                
                safe_title = re.sub(r'[\/*?:"<>|]', "", title)
                filename = f"DREAM_{datetime.now().strftime('%Y-%m-%d')}_{safe_title}.md"
                
                # 確保寫入當前目錄
                os.makedirs(OUTPUT_DIR, exist_ok=True)
                filepath = os.path.join(OUTPUT_DIR, filename)
                
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                
                # 更新最後一次夢境摘要供晨報使用
                with open(DREAM_LOG, "w", encoding="utf-8") as f:
                    json.dump({"title": title, "summary": "已產出同構性合成筆記"}, f)
                    
                print(f"✨ 夢境結晶完成：{filepath}")
            else:
                print("⚠️ 解析失敗。")
    except Exception as e:
        print(f"❌ 夢境執行崩潰: {e}")

if __name__ == "__main__":
    play_glass_bead_game()
