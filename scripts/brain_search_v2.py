#!/usr/bin/env python3
# 🛡️ Codex-Verified: Codex-Auth-Lvl13-Final (2026-03-03)
import os
import lancedb
import requests
import json
import argparse
import re
from dotenv import load_dotenv

# 載入環境變數
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
load_dotenv(os.path.expanduser("~/.openclaw/.env"))

JINA_KEY = os.environ.get("JINA_API_KEY", "MISSING_KEY")
DB_PATH = os.path.expanduser("~/.openclaw/memory/lancedb-pro")
PRIMARY_TABLE = os.environ.get("MUSE_SEARCH_TABLE", "agent_main")
TABLE_FALLBACKS = ["agent_main", "memories_v2", "memories"]


def _table_names(db):
    """Normalize table names across LanceDB client versions."""
    tables = db.list_tables()
    if isinstance(tables, (list, tuple)):
        names = list(tables)
    elif hasattr(tables, "tables"):
        names = list(getattr(tables, "tables"))
    else:
        names = []
    normalized = []
    for t in names:
        normalized.append(t[0] if isinstance(t, tuple) else t)
    return normalized


def get_embedding(text):
    if JINA_KEY == "MISSING_KEY":
        print("❌ 錯誤：未設定環境變數 JINA_API_KEY")
        return None

    url = "https://api.jina.ai/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {JINA_KEY}",
        "Content-Type": "application/json",
    }
    data = {"model": "jina-embeddings-v3", "input": [text], "task": "retrieval.query"}
    try:
        res = requests.post(url, headers=headers, json=data).json()
        return res["data"][0]["embedding"]
    except Exception as e:
        print(f"❌ Embedding Error: {e}")
        return None


def _pick_table(db):
    names = _table_names(db)
    if PRIMARY_TABLE in names:
        return PRIMARY_TABLE
    for t in TABLE_FALLBACKS:
        if t in names:
            return t
    return None


def _normalize(s):
    return re.sub(r"[^a-z0-9_]+", "", (s or "").lower())


def _metadata_of(row):
    meta = row.get("metadata", {})
    if isinstance(meta, str):
        try:
            return json.loads(meta)
        except Exception:
            return {}
    return meta if isinstance(meta, dict) else {}


def _rerank(results, query):
    q = _normalize(query)
    reranked = []
    for row in results:
        meta = _metadata_of(row)
        source = str(meta.get("source", ""))
        basename = source.split("/")[-1]
        title = str(row.get("note_id", ""))
        # LanceDB distance: lower is better, so we subtract bonus.
        bonus = 0.0
        n_source = _normalize(source)
        n_base = _normalize(basename)
        n_title = _normalize(title)
        if q and n_base == f"{q}md":
            bonus += 0.9
        if q and q in n_base:
            bonus += 0.5
        if q and q in n_source:
            bonus += 0.25
        if q and q in n_title:
            bonus += 0.15
        score = float(row.get("_distance", 9999.0)) - bonus
        reranked.append((score, row))
    reranked.sort(key=lambda x: x[0])
    return [r for _, r in reranked]


def _strip_heavy_fields(results):
    cleaned = []
    for row in results:
        item = dict(row)
        item.pop("vector", None)
        cleaned.append(item)
    return cleaned


def search_brain(query, limit=3):
    if not os.path.exists(DB_PATH):
        print(f"❌ 找不到資料庫：{DB_PATH}")
        return []

    db = lancedb.connect(DB_PATH)
    table_name = _pick_table(db)
    if not table_name:
        print(f"❌ 找不到可用資料表：{TABLE_FALLBACKS}")
        return []

    table = db.open_table(table_name)
    vector = get_embedding(query)

    if vector:
        results = table.search(vector).limit(limit).to_list()
        results = _rerank(results, query)
        return _strip_heavy_fields(results)
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
            print(f"[{i + 1}] {source} (更新於: {updated})")
            print(f"    SCORE: {res.get('_distance', 'N/A')}")
            text = res.get("text", "")
            summary = "N/A"
            if "SUMMARY:" in text:
                summary = text.split("SUMMARY:")[1].split("CONTENT:")[0].strip()
            print(f"    SUMMARY: {summary}")
            print("-" * 20)


if __name__ == "__main__":
    main()
