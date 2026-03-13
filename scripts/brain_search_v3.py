#!/usr/bin/env python3
# 🛡️ Codex-Verified: Muse-Core-Brain-V3.1 (2026-03-09)
# 🧠 整合 Idea-Reality 概念：混合檢索 + 時間衰減 + MMR + 信號強度診斷
import os
import lancedb
import requests
import json
import argparse
import datetime
import math

# 核心配置
JINA_KEY = os.environ.get("JINA_API_KEY", "MISSING_KEY")
DB_PATH = os.path.expanduser("~/.openclaw/memory/lancedb-pro")
TABLE_NAME = "agent_main"

def get_embedding(text):
    if JINA_KEY == "MISSING_KEY": return None
    url = "https://api.jina.ai/v1/embeddings"
    headers = {"Authorization": f"Bearer {JINA_KEY}", "Content-Type": "application/json"}
    data = {"model": "jina-embeddings-v3", "input": [text], "task": "retrieval.query"}
    try:
        res = requests.post(url, headers=headers, json=data).json()
        return res["data"][0]["embedding"]
    except: return None

def calculate_recency_score(updated_at, half_life_days=30):
    try:
        dt = datetime.datetime.strptime(updated_at, "%Y-%m-%d")
        days_diff = (datetime.datetime.now() - dt).days
        return math.pow(0.5, max(0, days_diff) / half_life_days)
    except: return 0.5

def mmr_rerank(results, top_k=3, lambda_param=0.7):
    if not results: return []
    selected = [results.pop(0)]
    while len(selected) < top_k and results:
        best_score, best_idx = -float('inf'), -1
        for i, cand in enumerate(results):
            sim_to_query = 1.0 - cand.get("_distance", 1.0)
            redundancy_penalty = 0
            cand_source = json.loads(cand.get("metadata", "{}")).get("source")
            for sel in selected:
                if json.loads(sel.get("metadata", "{}")).get("source") == cand_source:
                    redundancy_penalty = 0.8
                    break
            score = lambda_param * sim_to_query - (1 - lambda_param) * redundancy_penalty
            if score > best_score:
                best_score, best_idx = score, i
        if best_idx != -1: selected.append(results.pop(best_idx))
        else: break
    return selected

def search_brain(query, limit=3, half_life=30):
    if not os.path.exists(DB_PATH): return []
    db = lancedb.connect(DB_PATH)
    if TABLE_NAME not in db.table_names(): return []
    table = db.open_table(TABLE_NAME)
    vector = get_embedding(query)
    if not vector: return []

    raw_results = table.search(vector).limit(20).to_list()
    processed_results = []
    for res in raw_results:
        meta = json.loads(res.get("metadata", "{}"))
        recency = calculate_recency_score(meta.get("updated_at", "2024-01-01"), half_life)
        # 調整 _distance 以反映新鮮度權重
        res["_distance"] = res["_distance"] / (recency + 0.1)
        res["recency_score"] = round(recency, 4)
        processed_results.append(res)
    
    return mmr_rerank(processed_results, top_k=limit)

def main():
    parser = argparse.ArgumentParser(description="Muse-Core 大腦現實偵測儀 V3.1 (Signal Integrated)")
    parser.add_argument("query", help="搜尋關鍵字")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = search_brain(args.query, args.limit)
    if not results:
        print("❌ 未發現相關記憶信號。")
        return

    # 計算整體信號強度 (Signal Strength)
    top_sim = 1.0 - results[0].get("_distance", 1.0)
    top_rec = results[0].get("recency_score", 0.5)
    signal_strength = round((top_sim * 0.6 + top_rec * 0.4) * 100, 1)

    output_data = {
        "brain_reality_signal": signal_strength,
        "query": args.query,
        "status": "High" if signal_strength > 70 else "Medium" if signal_strength > 40 else "Low/Stale",
        "evidence_sources": list(set([json.loads(r.get("metadata", "{}")).get("source", "Unknown") for r in results])),
        "top_memories": []
    }

    for res in results:
        meta = json.loads(res.get("metadata", "{}"))
        text = res.get("text", "")
        summary = text.split("SUMMARY:")[1].split("CONTENT:")[0].strip() if "SUMMARY:" in text else "N/A"
        output_data["top_memories"].append({
            "source": meta.get("source", "Unknown"),
            "updated_at": meta.get("updated_at", "Unknown"),
            "signal": round((1.0 - res.get("_distance", 1.0)) * 100, 1),
            "summary": summary,
            "text": text[:300] + "..."
        })

    if args.json:
        print(json.dumps(output_data, ensure_ascii=False, indent=2))
    else:
        print(f"📡 大腦現實信號強度: {output_data['brain_reality_signal']} ({output_data['status']})")
        print(f"🧩 來源分布: {', '.join(output_data['evidence_sources'])}")
        print("-" * 30)
        for i, m in enumerate(output_data["top_memories"]):
            print(f"[{i+1}] {m['source']} ({m['updated_at']}) - 信號: {m['signal']}%")
            print(f"    摘要: {m['summary']}\n")

if __name__ == "__main__":
    main()
