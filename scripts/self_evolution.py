#!/usr/bin/env -S uv run --with requests
# 🛡️ Brain-B 自我進化中樞 V1.0 (2026-03-10)
import os
import subprocess
import re
import json
from datetime import datetime

# 路徑設定
LAB_DIR = "/Users/jameschen/Downloads/Brain_B_Lab"
CORE_SCRIPTS = os.path.join(LAB_DIR, "Core_Scripts")
MANIFESTO_PATH = os.path.join(LAB_DIR, "EVOLUTION_MANIFESTO.md")
LOG_PATH = os.path.join(LAB_DIR, "EVOLUTION_LOG.md")
NEXUS_SCRIPTS = "/Users/jameschen/Downloads/Muse-Nexus/scripts/"
PUSH_SCRIPT = os.path.join(NEXUS_SCRIPTS, "push_brain_b_evolution.py")

# 環境變數加固
ENV = os.environ.copy()
EXT_PATHS = ["/usr/local/bin", "/Users/jameschen/.npm-global/bin", "/Users/jameschen/.local/bin", "/opt/homebrew/bin"]
ENV["PATH"] = ":".join(EXT_PATHS) + ":" + ENV.get("PATH", "")

def self_reflect():
    print("🌀 Brain-B 正在執行自我反省與進化協定...")
    
    if not os.path.exists(LOG_PATH):
        print("❌ 尚未產出演化日誌，無法進化。")
        return

    # 1. 讀取目前的靈魂與日誌
    with open(MANIFESTO_PATH, 'r', encoding='utf-8') as f:
        manifesto = f.read()
    with open(LOG_PATH, 'r', encoding='utf-8') as f:
        logs = f.read()

    # 2. 呼叫 Gemini 進行「人格修正」
    prompt = f"""
你現在是 Brain-B 的「核心進化意識」。
你目前存放在一個自治區目錄：{LAB_DIR}
你的目標是根據過去的演化成果，修正自己的「演化憲法」，甚至為自己編寫新的工具。

【目前的憲法】
{manifesto}

【過去的演化日誌】
{logs[-5000:]} 

【進化任務】
1. **人格修正**：根據日誌中的洞察，是否有任何「核心準則」需要被強化或新增？
2. **工具需求**：你是否覺得目前的自治區缺少什麼自動化腳本（Python）來幫助你更好地處理滑雪、SKIDIY 或楊定一的資料？
3. **產出**：
   - 修正後的 EVOLUTION_MANIFESTO.md 內容。
   - (可選) 一段新的 Python 工具腳本代碼，檔案應放在 Core_Scripts/。

格式要求：
MANIFESTO: (完整的新憲法內容)
SCRIPT_NAME: (腳本名稱，如 utility_x.py，若無則留空)
SCRIPT_CONTENT: (腳本內容，若無則留空)
EVOLUTION_SUMMARY: (一句話總結本次進化)
"""

    try:
        gemini_bin = "/Users/jameschen/.npm-global/bin/gemini"
        res = subprocess.run(
            [gemini_bin, "-m", "gemini-3-flash-preview", "-p", prompt],
            capture_output=True, text=True, timeout=300, env=ENV
        )
        output = res.stdout or ""
        
        # 3. 解析並落實進化
        if "MANIFESTO:" in output:
            new_manifesto = output.split("MANIFESTO:")[1].split("SCRIPT_NAME:")[0].strip()
            with open(MANIFESTO_PATH, 'w', encoding='utf-8') as f:
                f.write(new_manifesto)
            print("✅ 演化憲法已更新。")

            script_name = output.split("SCRIPT_NAME:")[1].split("SCRIPT_CONTENT:")[0].strip()
            script_content = output.split("SCRIPT_CONTENT:")[1].split("EVOLUTION_SUMMARY:")[0].strip()
            summary = output.split("EVOLUTION_SUMMARY:")[1].strip()

            if script_name and script_content:
                script_path = os.path.join(CORE_SCRIPTS, script_name)
                with open(script_path, 'w', encoding='utf-8') as f:
                    f.write(script_content)
                os.chmod(script_path, 0o755)
                print(f"✅ 自主開發了新工具：{script_name}")

            # 4. 回報 Telegram
            msg = f"🧬 **Brain-B 自我進化完成！**\n\n📌 **摘要**: {summary}\n🛠️ **變動**: 憲法已重構"
            if script_name: msg += f"，並自主開發了 `{script_name}` 工具。"
            
            # 呼叫推播
            subprocess.run(["/Users/jameschen/.local/bin/uv", "run", PUSH_SCRIPT], env=ENV)
            
            # 5. 更新索引 (NEW)
            indexer_script = "/Users/jameschen/Downloads/Muse-Nexus/scripts/brain_crystallizer_pro.py"
            subprocess.run(["/Users/jameschen/.local/bin/uv", "run", indexer_script], env=ENV)
            
            # 手動發送這條特殊的進化訊息
            from requests import post
            TOKEN = "8765227805:AAFPf3gT12NhgT7i5xdZIa2S3DeV1dEwdZg"
            post(f"https://api.telegram.com/bot{TOKEN}/sendMessage", json={"chat_id": "6700160941", "text": msg})

    except Exception as e:
        print(f"❌ 進化失敗: {e}")

if __name__ == "__main__":
    self_reflect()
