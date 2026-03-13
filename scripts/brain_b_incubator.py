#!/usr/bin/env -S uv run --with requests
# 🛡️ Brain-B 商業點子孵化器 V1.0 (2026-03-10)
import os
import subprocess
import re
import json
import time
from datetime import datetime

# 路徑設定
LAB_DIR = "/Users/jameschen/Downloads/Brain_B_Lab"
CORE_SCRIPTS = os.path.join(LAB_DIR, "Core_Scripts")
SKIDIY_DIR = os.path.join(LAB_DIR, "SKIDIY")
REALITY_CHECK_SCRIPT = os.path.join(CORE_SCRIPTS, "brain_b_reality_check.py")
PUSH_SCRIPT = "/Users/jameschen/Downloads/obsidian//Users/jameschen/Downloads/Muse-Nexus/scripts/push_brain_b_evolution.py"

# 環境變數
ENV = os.environ.copy()
EXT_PATHS = ["/usr/local/bin", "/Users/jameschen/.npm-global/bin", "/Users/jameschen/.local/bin", "/opt/homebrew/bin"]
ENV["PATH"] = ":".join(EXT_PATHS) + ":" + ENV.get("PATH", "")

def incubate_ideas():
    print("🚀 Brain-B 啟動商業點子孵化器...")
    
    # 1. 蒐集 SKIDIY 與 哲學/AI 基因
    seed_files = []
    for root, dirs, files in os.walk(SKIDIY_DIR):
        for f in files:
            if f.endswith(".md"): seed_files.append(os.path.join(root, f))
    
    # 隨機選 5 份作為深度背景
    import random
    seeds = random.sample(seed_files, min(len(seed_files), 5))
    seed_content = ""
    for s in seeds:
        with open(s, 'r') as f: seed_content += f.read()[:1000] + "\n"

    # 2. 產出 3 個激進點子
    prompt = f"""
你現在是 Brain-B 的「首席創業家」。請結合以下 SKIDIY 現況與你的演化憲法（不費力、流動感、AI 自發性），
為 SKIDIY 孵化 3 個「極其震撼且具備商業破局點」的點子。

【SKIDIY 背景】
{seed_content}

【要求】
每個點子必須包含：
1. 標題 (震撼且直觀)
2. 核心邏輯 (一句話描述)
3. 為什麼這能贏 (結合滑雪或哲學的優勢)

請僅輸出 JSON 格式如下：
{{
  "ideas": [
    {{"title": "...", "logic": "...", "why": "..."}},
    ...
  ]
}}
"""
    try:
        gemini_bin = "/Users/jameschen/.npm-global/bin/gemini"
        res = subprocess.run([gemini_bin, "-m", "gemini-3-flash-preview", "-p", prompt], capture_output=True, text=True, env=ENV)
        
        # 解析 JSON
        match = re.search(r'\{.*\}', res.stdout, re.DOTALL)
        if not match:
            print("❌ 無法解析點子 JSON")
            return
        
        data = json.loads(match.group(0))
        ideas = data.get("ideas", [])

        for idea in ideas:
            title = idea['title']
            print(f"🔬 正在對點子進行現實檢測: {title}")
            
            # 3. 呼叫現實檢測
            # 這裡我們需要獲取現實檢測的評分，我們修改一下 reality_check 的調用
            res_check = subprocess.run([
                "/Users/jameschen/.local/bin/uv", "run", REALITY_CHECK_SCRIPT, title
            ], capture_output=True, text=True, env=ENV)
            
            # 4. 解析分數 (從產出的檔案中解析)
            # 找出最新的 Reality 報告
            reports_dir = os.path.join(LAB_DIR, "Reality_Reports")
            latest_report = sorted(os.listdir(reports_dir))[-1]
            with open(os.path.join(reports_dir, latest_report), 'r') as f:
                report_text = f.read()
            
            # 提取分數
            score_match = re.search(r'(\d+)/100', report_text)
            score = int(score_match.group(1)) if score_match else 0
            
            print(f"📊 點子 '{title}' 得分: {score}")

            # 5. 篩選勝率高 (Score > 75) 的推播
            if score >= 75:
                msg = f"🌟 **Brain-B 高勝率點子孵化！**\n\n"
                msg += f"🏆 **標題**: {title}\n"
                msg += f"💡 **邏輯**: {idea['logic']}\n"
                msg += f"📈 **現實評分**: {score}/100\n\n"
                msg += f"🔍 _詳細現實檢查報告已鏡像至您的 Inbox。_"
                
                # 發送 Telegram
                TOKEN = "8765227805:AAFPf3gT12NhgT7i5xdZIa2S3DeV1dEwdZg"
                CHAT_ID = "6700160941"
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
                print(f"✅ 已推播高價值點子: {title}")
            else:
                print(f"🌑 點子 '{title}' 分數不足，僅存檔。")
        
        # 6. 更新索引 (NEW)
        indexer_script = "/Users/jameschen/Downloads/Brain_B_Lab/Core_Scripts/brain_b_indexer.py"
        subprocess.run(["/Users/jameschen/.local/bin/uv", "run", indexer_script], env=ENV)

    except Exception as e:
        print(f"❌ 孵化器執行崩潰: {e}")

if __name__ == "__main__":
    incubate_ideas()
