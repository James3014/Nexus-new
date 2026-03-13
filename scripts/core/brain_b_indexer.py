#!/usr/bin/env -S uv run --with requests
# 🛡️ Brain-B 索引維護器 V2.0 (2026-03-10) - Final Human Centric Polish
import os
import re
import json
from datetime import datetime
from pathlib import Path

# --- 配置 ---
LAB_DIR = Path("/Users/jameschen/Downloads/Brain_B_Lab")
INSIGHTS_DIR = LAB_DIR / "Insights"
REALITY_DIR = LAB_DIR / "Reality_Reports"
INDEX_PATH = LAB_DIR / "events_index.json"
ACTION_PATH = LAB_DIR / "next_action.json"
LOG_PATH = LAB_DIR / "EVOLUTION_LOG.md"

def clean_noise(text):
    """徹底掃除所有 raw UI tokens 與工程雜訊"""
    if not text: return ""
    noise = ["keyboard_arrow_right", "CONTENT & ACTIONS", "System Insight ID", "🌀", "🔬", "keyboard_arrow_down", "DREAM_", "REALITY_CHECK_", "TG_B_THINK_"]
    for n in noise:
        text = text.replace(n, "")
    # 移除日期與時間戳模式
    text = re.sub(r'\d{8}_\d{6}', '', text)
    text = re.sub(r'\d{4}-\d{2}-\d{2}', '', text)
    return text.strip()

def get_standardized_summary(content, file_name, meta_type):
    """產出 判斷｜影響｜建議 的標準化駕駛艙摘要"""
    text = clean_noise(content)
    judgment, impact, action = "分析中", "涉及演化路徑", "建議查閱詳情"

    if meta_type == "Reality Check":
        score_match = re.search(r'現實信號.*?(\d+)/100', content)
        score = int(score_match.group(1)) if score_match else 50
        judgment = f"原創度 {score}/100"
        if score < 70:
            impact, action = "市場已有類似方案", "建議作為內部工具或調整切入點"
        else:
            impact, action = "高價值藍海點子", "建議優先啟動 MVP 驗證"
        pivot = re.search(r'## 3\. 轉型建議.*?\n(.*?)\n', content, re.DOTALL)
        if pivot: action = f"建議：{pivot.group(1).strip()[:60]}..."

    elif meta_type == "Dream":
        div_match = re.search(r'(?:分歧係數|Divergence)[:：\*]*\s*(\d+\.\d+)', content, re.IGNORECASE)
        div = float(div_match.group(1)) if div_match else 0.5
        judgment = f"分歧度 {div:.2f}"
        if div > 0.8:
            impact, action = "觸發激進架構進化", "需介入審核以防邏輯漂移"
        else:
            impact, action = "知識合成平穩", "已自動納入大腦背景"
        trunk = re.search(r'## 🦾 核心樹幹.*?：(.*?)\n', content)
        if trunk: impact = trunk.group(1).strip()[:60] + "..."

    return f"{judgment} ｜ {impact} ｜ {action}"

def parse_evolution_log():
    """將演化日誌轉為 100% 人類語意標題"""
    if not LOG_PATH.exists(): return []
    raw_log = LOG_PATH.read_text(encoding="utf-8")
    lines = [l for l in raw_log.strip().split("\n") if l.strip()]
    processed = []
    for line in lines:
        match = re.search(r'- \[(.*?)\] \*\*(.*?)\*\*\s*➜\s*(.*)', line)
        if match:
            ts_raw, title, msg = match.groups()
            try:
                time_str = datetime.strptime(ts_raw, "%Y%m%d_%H%M%S").strftime("%H:%M")
            except:
                time_str = ts_raw[-5:] if "-" in ts_raw else ts_raw
            
            # 處理「EVOLUTION_LOG: 2026-03-10」這類 meta 標題
            if "EVOLUTION_LOG" in title:
                clean_title = "系統自我進化紀錄"
            else:
                clean_title = clean_noise(title).split(".md")[0].strip()
            
            # 處理訊息
            msg_clean = msg.split("➜")[0].split(".md")[0].strip()
            if "已同步" in msg_clean or "同步至主 Inbox" in msg_clean:
                status_text = "已同步至大腦"
            elif "產出分歧點" in msg_clean or "演化突破" in msg_clean:
                status_text = "完成演化突破"
            else:
                status_text = msg_clean[:30]

            if clean_title:
                processed.append({"time": time_str, "title": clean_title, "msg": status_text})
    return processed

def parse_md_metadata(file_path):
    try:
        content = file_path.read_text(encoding="utf-8")
        meta = {
            "file_path": str(file_path),
            "title": file_path.name,
            "summary": "",
            "risk": "Low",
            "divergence": 0.0,
            "type": "Unknown",
            "mtime": os.path.getmtime(file_path),
            "domains": []
        }
        
        name_upper = file_path.name.upper()
        if "DREAM" in name_upper or "【重力熔爐】" in content: meta["type"] = "Dream"
        elif "REALITY" in name_upper or "現實檢查" in content: meta["type"] = "Reality Check"
        elif "THINK" in name_upper or "覺醒洞察" in content: meta["type"] = "Think"
        elif "INGEST" in name_upper: meta["type"] = "Ingest"

        title_match = re.search(r'^# (.*)\n', content, re.MULTILINE)
        if title_match: 
            meta["title"] = clean_noise(title_match.group(1))
        
        div_match = re.search(r'(?:分歧係數|Divergence)[:：\*]*\s*(\d+\.\d+)', content, re.IGNORECASE)
        if div_match: 
            meta["divergence"] = round(float(div_match.group(1)), 2)
        else:
            meta["divergence"] = 0.50
        
        if meta["divergence"] > 0.8: meta["risk"] = "High"
        elif meta["divergence"] > 0.6: meta["risk"] = "Medium"

        meta["summary"] = get_standardized_summary(content, file_path.name, meta["type"])
        
        kw_map = {"Skiing": ["滑雪", "Ski", "刻滑"], "SKIDIY": ["SKIDIY", "教練"], "Philosophy": ["楊定一", "全部生命", "臣服"], "AI_Ops": ["AI", "Agent", "自動化"]}
        for dom, kws in kw_map.items():
            if any(k.lower() in content.lower() for k in kws): meta["domains"].append(dom)

        return meta
    except: return None

def update_index():
    print("🔄 正在執行數據終極精煉 (V2.0 Final Polish)...")
    all_events = []
    for folder in [INSIGHTS_DIR, REALITY_DIR]:
        if folder.exists():
            for f in folder.glob("*.md"):
                meta = parse_md_metadata(f)
                if meta: all_events.append(meta)
    
    all_events.sort(key=lambda x: x["mtime"], reverse=True)
    seen = set()
    unique_events = [e for e in all_events if not (e["title"], e["type"]) in seen and not seen.add((e["title"], e["type"]))]
    
    logs = parse_evolution_log()
    index_data = {"events": unique_events, "human_logs": logs}
    
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    
    # --- NBA Sync ---
    nba = {"recommendation": "演化環境平穩", "reason": "等待新事件觸發。", "target_file": "", "divergence": 0.0}
    if unique_events:
        top = max(unique_events, key=lambda x: x["divergence"])
        if top["divergence"] > 0.8:
            nba = {"recommendation": f"P1 決策：{top['title']}", "reason": f"判斷：檢測到 D{top['divergence']} 極高分歧 ｜ 下一步：對位核心架構。", "target_file": top["file_path"], "divergence": top["divergence"]}
        else:
            latest_r = next((e for e in unique_events if e["type"] == "Reality Check"), None)
            if latest_r:
                nba = {"recommendation": f"商業點子：{latest_r['title']}", "reason": "判斷：全球現實檢查完成 ｜ 下一步：評估轉型空間。", "target_file": latest_r["file_path"], "divergence": latest_r["divergence"]}

    with open(ACTION_PATH, "w", encoding="utf-8") as f:
        json.dump(nba, f, ensure_ascii=False, indent=2)
    print(f"✅ 數據精煉完成 (V2.0)。")

if __name__ == "__main__":
    update_index()
