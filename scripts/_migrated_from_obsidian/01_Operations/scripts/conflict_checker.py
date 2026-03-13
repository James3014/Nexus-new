#!/usr/bin/env python3
# 🛡️ Codex-Verified: Codex-Auth-Lvl13-Final (2026-03-03)
import os
import sys
import subprocess
import json
import argparse

SEARCH_BIN = "/Users/jameschen/Downloads/obsidian/知識庫/01_Operations/scripts/brain_search_v2.py"
REPORT_FILE = "/Users/jameschen/Downloads/obsidian/知識庫/01_Operations/CONTRADICTIONS.md"

def check_conflict(new_summary, source_file):
    print(f"🔍 執行衝突偵測：{source_file}")
    try:
        jina_key = os.environ.get("JINA_API_KEY", "MISSING_KEY")
        env = os.environ.copy()
        env["JINA_API_KEY"] = jina_key
        cmd = ["/Users/jameschen/.local/bin/uv", "run", "--with", "lancedb", "--with", "pandas", "--with", "requests", SEARCH_BIN, new_summary, "--limit", "3", "--json"]
        res = subprocess.run(cmd, capture_output=True, text=True, env=env)
        results = json.loads(res.stdout)
    except Exception as e:
        print(f"❌ 搜尋失敗: {e}")
        return None
    if not results: return None
    report_content = f"### ⚠️ 知識衝突預警：{source_file}\n"
    report_content += f"**新摘要**: {new_summary}\n\n"
    report_content += "| 來源檔案 | 相似分數 | 舊摘要 | 更新時間 |\n"
    report_content += "| --- | --- | --- | --- |\n"
    potential_conflict = False
    for res in results:
        meta = json.loads(res.get("metadata", "{}"))
        source = meta.get("source", "Unknown")
        updated = meta.get("updated_at", "Unknown")
        score = res.get("_distance", 1.0)
        if score < 0.3: potential_conflict = True
        text = res.get("text", "")
        old_summary = text.split("SUMMARY:")[1].split("CONTENT:")[0].strip() if "SUMMARY:" in text else "N/A"
        report_content += f"| {source} | {score:.4f} | {old_summary} | {updated} |\n"
    if potential_conflict:
        os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
        with open(REPORT_FILE, "a", encoding="utf-8") as f: f.write(f"\n---\n{report_content}\n")
        print(f"🚨 偵測到高度疑似衝突！報告已寫入：{REPORT_FILE}")
        return report_content
    return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("summary")
    parser.add_argument("source")
    args = parser.parse_args()
    check_conflict(args.summary, args.source)
