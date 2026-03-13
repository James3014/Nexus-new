#!/usr/bin/env -S uv run --with requests
# 🛡️ Brain-B Reality Check Engine V1.2 (2026-03-10) - Mirror & Noise-Fix Edition
import os
import subprocess
import json
import re
import sys
from datetime import datetime

# 核心設定
TOKEN = "8765227805:AAFPf3gT12NhgT7i5xdZIa2S3DeV1dEwdZg"
CHAT_ID = "6700160941"
LAB_DIR = "/Users/jameschen/Downloads/Brain_B_Lab"
REPORTS_DIR = os.path.join(LAB_DIR, "Reality_Reports")
MAIN_INBOX = "/Users/jameschen/Downloads/obsidian/知識庫/01_Operations/Inbox"

# 環境變數加固
ENV = os.environ.copy()
EXT_PATHS = ["/usr/local/bin", "/Users/jameschen/.npm-global/bin", "/Users/jameschen/.local/bin", "/opt/homebrew/bin"]
ENV["PATH"] = ":".join(EXT_PATHS) + ":" + ENV.get("PATH", "")

def clean_noise(text):
    """深度清理 gemini CLI 的系統噪音"""
    # 移除同步宣告
    text = re.sub(r'--- /.*? ---.*?已同步完畢。', '', text, flags=re.DOTALL)
    text = re.sub(r'Sir，大腦內容已同步完畢.*?\n', '', text)
    # 移除語音指令
    text = re.sub(r'`?/usr/bin/python3.*?notify\.py.*?任務完成`?', '', text)
    # 移除載入訊息
    lines = text.split('\n')
    clean_lines = [l for l in lines if not any(x in l for x in ['Warning:', 'Error executing', 'Loaded cached', 'Loading extension', 'Server', 'Done in'])]
    return "\n".join(clean_lines).strip()

def google_search_proxy(query):
    prompt = f"請使用 google_search 搜尋與 '{query}' 相關的現有 GitHub 專案、NPM 套件或產品。請條列出最相似的 3-5 個結果，並說明它們的功能。"
    try:
        gemini_bin = "/Users/jameschen/.npm-global/bin/gemini"
        res = subprocess.run([gemini_bin, "-m", "gemini-3-flash-preview", "-p", prompt], capture_output=True, text=True, timeout=120, env=ENV)
        return clean_noise((res.stdout or "") + (res.stderr or ""))
    except Exception as e:
        return f"搜尋失敗: {e}"

def analyze_reality(idea, search_results):
    prompt = f"""
你現在是 Brain-B 的「現實審查官」。
針對以下點子與搜尋到的現實資料，請進行殘酷的競爭力分析。

【點子】
{idea}

【現實檢索結果】
{search_results}

【要求】
1. **現實信號 (0-100)**：評分。
2. **撞車分析**：對手分析。
3. **轉型建議 (Pivot)**：差異化。
4. **格式**：Markdown。禁止包含語音指令或同步宣告。
"""
    try:
        gemini_bin = "/Users/jameschen/.npm-global/bin/gemini"
        res = subprocess.run([gemini_bin, "-m", "gemini-3-flash-preview", "-p", prompt], capture_output=True, text=True, timeout=120, env=ENV)
        return clean_noise(res.stdout or "")
    except Exception as e:
        return f"分析崩潰: {e}"

def perform_check(idea):
    print(f"📡 正在對點子 '{idea}' 進行現實檢查...")
    search_results = google_search_proxy(idea)
    analysis = analyze_reality(idea, search_results)
    
    if not analysis:
        print("❌ 分析失敗：內容為空")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(MAIN_INBOX, exist_ok=True)
    
    filename = f"REALITY_CHECK_{ts}.md"
    lab_path = os.path.join(REPORTS_DIR, filename)
    mirror_path = os.path.join(MAIN_INBOX, f"[Brain-B]_{filename}")
    
    report_content = f"# 🔬 Brain-B 現實檢查報告: {idea}\n\n{analysis}"
    
    # 1. 寫入實驗室
    with open(lab_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    
    # 2. 鏡像到主 Inbox
    with open(mirror_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    
    print(f"✅ 報告已產出並鏡像至: {mirror_path}")
    
    # 3. 推送到 Telegram
    safe_analysis = analysis.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`")
    msg = f"🔬 **Brain-B 現實檢查完成！**\n\n📌 **點子**: {idea}\n\n{safe_analysis[:3500]}"
    
    import requests
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                      json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    except: pass
    
    # 4. 更新索引 (NEW)
    indexer_script = "/Users/jameschen/Downloads/Brain_B_Lab/Core_Scripts/brain_b_indexer.py"
    subprocess.run(["/Users/jameschen/.local/bin/uv", "run", indexer_script], env=ENV)
    
    return mirror_path

if __name__ == "__main__":
    if len(sys.argv) > 1:
        perform_check(sys.argv[1])
    else:
        print("Usage: brain_b_reality_check.py <idea>")
