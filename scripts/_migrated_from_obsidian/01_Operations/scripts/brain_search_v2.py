#!/usr/bin/env python3
# 🛡️ Codex-Verified: Codex-Auth-Lvl13-Final (2026-03-03)
import os
import lancedb
import requests
import json
import argparse
from datetime import datetime

# 核心配置 - 從環境變數讀取以確保安全性
JINA_KEY = os.environ.get("JINA_API_KEY", "MISSING_KEY")
DB_PATH = os.path.expanduser("~/.openclaw/memory/lancedb-pro")
TABLE_NAME = "agent_main"

def get_embedding(text):
    if JINA_KEY == "MISSING_KEY":
        print("❌ 錯誤：未設定環境變數 JINA_API_KEY")
        return None
        
    url = "https://api.jina.ai/v1/embeddings"
    headers = {"Authorization": f"Bearer {JINA_KEY}", "Content-Type": "application/json"}
    data = {"model": "jina-embeddings-v3", "input": [text], "task": "retrieval.query"}
    try:
        res = requests.post(url, headers=headers, json=data).json()
        return res["data"][0]["embedding"]
    except Exception as e:
        print(f"❌ Embedding Error: {e}")
        return None

def search_brain(query, limit=3):
    if not os.path.exists(DB_PATH):
        print(f"❌ 找不到資料庫：{DB_PATH}")
        return []

    db = lancedb.connect(DB_PATH)
    if TABLE_NAME not in db.table_names():
        print(f"❌ 找不到資料表：{TABLE_NAME}")
        return []

    table = db.open_table(TABLE_NAME)
    vector = get_embedding(query)
    
    if vector:
        results = table.search(vector).limit(limit).to_list()
        return results
    return []

def main():
    parser = argparse.ArgumentParser(description="Muse-Core 大腦語義檢索工具 v2")
    parser.add_argument("query", help="搜尋關鍵字或摘要")
    parser.add_argument("--limit", type=int, default=3, help="返回結果數量")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式輸出")
    
    args = parser.parse_args()
    results = search_brain(args.query, args.limit)
    
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for i, res in enumerate(results):
            meta = json.loads(res.get("metadata", "{}"))
            source = meta.get("source", "Unknown")
            updated = meta.get("updated_at", "Unknown")
            print(f"[{i+1}] {source} (更新於: {updated})")
            print(f"    SCORE: {res.get('_distance', 'N/A')}")
            text = res.get("text", "")
            summary = "N/A"
            if "SUMMARY:" in text:
                summary = text.split("SUMMARY:")[1].split("CONTENT:")[0].strip()
            print(f"    SUMMARY: {summary}")
            print("-" * 20)

if __name__ == "__main__":
    main()
