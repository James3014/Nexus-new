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

# 定義知識領域
DOMAINS = [
    "滑雪技術與重心控制",
    "AI代理與系統架構",
    "投資交易與風險管理",
    "裝修設計與空間規劃",
    "教育心理學與教案設計"
]

def get_domain_knowledge(domain):
    print(f"🔍 檢索領域知識：{domain}")
    try:
        cmd = [
            "/Users/jameschen/.local/bin/uv", "run", "--with", "lancedb", "--with", "pandas", "--with", "requests",
            SEARCH_BIN, domain, "--limit", "3", "--json"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        results = json.loads(res.stdout)
        
        context = ""
        for res in results:
            text = res.get("text", "")
            if text:
                context += f"- {text}\n"
        return context
    except Exception as e:
        print(f"❌ 檢索失敗 ({domain}): {e}")
        return ""

def synthesize():
    print("🧬 啟動 Muse-Core 背景合成者模式...")
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
    # 隨機挑選兩個不重複的領域
    domain_a, domain_b = random.sample(DOMAINS, 2)
    print(f"🧪 今日雜交主題：【{domain_a}】 ✕ 【{domain_b}】")
    
    knowledge_a = get_domain_knowledge(domain_a)
    knowledge_b = get_domain_knowledge(domain_b)
    
    if not knowledge_a or not knowledge_b:
        print("⚠️ 知識萃取不足，無法進行合成。")
        return

    prompt = f"""
你是一位名為「合成者 (The Synthesizer)」的頂級思想家。你的任務是將看似不相關的領域知識進行「高維度雜交」，找出底層邏輯的共通點。

### 領域 A：{domain_a}
{knowledge_a}

### 領域 B：{domain_b}
{knowledge_b}

請執行以下合成任務：
1. 找出這兩個領域在「底層邏輯、系統運作或人類行為」上的 1-2 個核心共通點。
2. 撰寫一篇具啟發性的「合成筆記」，說明如何將領域 A 的思維應用於領域 B，或是兩者如何結合成一個更高維度的哲學。
3. 為這篇文章下一個極具洞見的標題（例如：《滑雪邊刃控制對分散式系統壓力測試的啟發》）。

請嚴格依照以下 Markdown 格式輸出（不要包含 Markdown 程式碼區塊的三引號，直接輸出文字）：

TITLE: 你的標題
CONTENT:
---
title: "你的標題"
date: {datetime.now().strftime("%Y-%m-%d")}
tags: [System/Synthesis, {domain_a.split('與')[0]}, {domain_b.split('與')[0]}]
type: synthesized-insight
---

# 你的標題

> **合成者洞察**：(一句話總結底層共通點)

## 🌌 高維度共通點
(描述底層邏輯)

## 💡 交叉啟發 (Cross-Pollination)
(詳細闡述如何互相應用)

---
%% 
由 Muse-Core 合成者引擎自動生成
基於：{domain_a} ✕ {domain_b}
%%
"""

    print("🧠 正在呼叫 LLM 進行大腦蒸餾與雜交...")
    try:
        cmd = [OPENCLAW_BIN, 'agent', '--agent', 'main', '--message', prompt, '--json']
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        
        match = re.search(r'\{.*\}', process.stdout, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            output_text = (data.get('result', {}).get('payloads') or data.get('payloads', []))[0].get('text', '')
            
            if "TITLE:" in output_text and "CONTENT:" in output_text:
                parts = output_text.split("CONTENT:", 1)
                title = parts[0].replace("TITLE:", "").strip()
                # 清理標題不能當作檔名的字元
                safe_title = re.sub(r'[\/*?:"<>|]', "", title)
                content = parts[1].strip()
                
                # 寫入檔案
                filepath = os.path.join(OUTPUT_DIR, f"{datetime.now().strftime('%Y-%m-%d')}_{safe_title}.md")
                
                # 確保我們寫入的是當前執行環境下的相對路徑 (相容分身與主幹)
                local_output_dir = os.path.join(os.getcwd(), "06_Synthesized_Insights")
                if os.path.exists(os.path.join(os.getcwd(), "01_Operations")):
                     os.makedirs(local_output_dir, exist_ok=True)
                     filepath = os.path.join(local_output_dir, f"{datetime.now().strftime('%Y-%m-%d')}_{safe_title}.md")
                else:
                     os.makedirs(OUTPUT_DIR, exist_ok=True)

                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                    
                print(f"✨ 合成筆記已產出：{filepath}")
            else:
                print("⚠️ LLM 回應格式錯誤，未能解析出 TITLE 與 CONTENT。")
                print(output_text)
        else:
            print("⚠️ 無法解析 LLM 結構化輸出。")
            
    except Exception as e:
        print(f"❌ 合成過程崩潰: {e}")

if __name__ == "__main__":
    synthesize()
