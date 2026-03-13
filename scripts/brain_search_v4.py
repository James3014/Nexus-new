import os
import lancedb
import requests
import json
import argparse
import time
import sqlite3
import hashlib
from dotenv import load_dotenv

# 核心配置
load_dotenv(os.path.expanduser("~/.openclaw/.env"))
JINA_KEY = os.environ.get("JINA_API_KEY", "MISSING_KEY")
DB_PATH = os.path.expanduser("~/.openclaw/memory/lancedb-pro")
CACHE_DB = os.path.expanduser("~/.openclaw/memory/embeddings_cache.sqlite")
TABLE_NAME = "memories"


def get_cache_db():
    conn = sqlite3.connect(CACHE_DB)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache (hash TEXT PRIMARY KEY, embedding TEXT)"
    )
    return conn


def get_cached_embedding(text_hash):
    conn = get_cache_db()
    res = conn.execute(
        "SELECT embedding FROM cache WHERE hash = ?", (text_hash,)
    ).fetchone()
    conn.close()
    return json.loads(res[0]) if res else None


def set_cached_embedding(text_hash, embedding):
    conn = get_cache_db()
    conn.execute(
        "INSERT OR REPLACE INTO cache (hash, embedding) VALUES (?, ?)",
        (text_hash, json.dumps(embedding)),
    )
    conn.commit()
    conn.close()


def get_embedding(text):
    text_hash = hashlib.md5(text.encode()).hexdigest()
    cached = get_cached_embedding(text_hash)
    if cached:
        return cached, "L1-Cache"

    if JINA_KEY == "MISSING_KEY":
        return None, "FAILED"

    # 這裡實作超時降級，若 API 慢過 800ms
    url = "https://api.jina.ai/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {JINA_KEY}",
        "Content-Type": "application/json",
    }
    data = {"model": "jina-embeddings-v3", "input": [text], "task": "retrieval.query"}

    try:
        start_api = time.perf_counter()
        res = requests.post(url, headers=headers, json=data, timeout=1.5).json()
        embedding = res["data"][0]["embedding"]
        set_cached_embedding(text_hash, embedding)
        return embedding, "Jina-API"
    except Exception as e:
        return None, f"TIMEOUT/FAILED ({e})"


def set_cached_results(text_hash, results):
    conn = get_cache_db()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS results_cache (hash TEXT PRIMARY KEY, results TEXT, timestamp REAL)"
    )
    conn.execute(
        "INSERT OR REPLACE INTO results_cache (hash, results, timestamp) VALUES (?, ?, ?)",
        (text_hash, json.dumps(results), time.time()),
    )
    conn.commit()
    conn.close()


def get_cached_results(text_hash, ttl=3600):
    try:
        conn = get_cache_db()
        res = conn.execute(
            "SELECT results, timestamp FROM results_cache WHERE hash = ?", (text_hash,)
        ).fetchone()
        conn.close()
        if res and (time.time() - res[1]) < ttl:
            return json.loads(res[0])
    except:
        pass
    return None


def search_brain_v4(query, limit=3):
    start_total = time.perf_counter()
    text_hash = hashlib.md5(query.encode()).hexdigest()

    # L0: 檢查結果快取
    cached_results = get_cached_results(text_hash)
    if cached_results:
        return {
            "latency_ms": round((time.perf_counter() - start_total) * 1000, 2),
            "mode": "L0-Results-Cache",
            "results": cached_results,
        }

    if not os.path.exists(DB_PATH):
        return {"status": "error", "message": "DB not found"}
    db = lancedb.connect(DB_PATH)
    table = db.open_table(TABLE_NAME)

    embedding, source_type = get_embedding(query)

    results = []
    if embedding:
        results = table.search(embedding).limit(limit).to_list()
        mode = f"Vector ({source_type})"
    else:
        try:
            results = table.search(query).limit(limit).to_list()
            mode = "FTS-Fallback"
        except:
            mode = "FAILED"

    # 寫入結果快取
    if results:
        set_cached_results(text_hash, results)

    end_total = time.perf_counter()
    latency_ms = (end_total - start_total) * 1000

    return {"latency_ms": round(latency_ms, 2), "mode": mode, "results": results}


def main():
    parser = argparse.ArgumentParser(description="Muse-Core 極速檢索引擎 v4")
    parser.add_argument("query", help="搜尋關鍵字")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    data = search_brain_v4(args.query, args.limit)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"🚀 檢索模式: {data['mode']} | 延遲: {data['latency_ms']}ms")
        for i, res in enumerate(data["results"]):
            meta = json.loads(res.get("metadata", "{}"))
            print(
                f"[{i + 1}] {meta.get('source', 'Unknown')} (Dist: {res.get('_distance', 'N/A')})"
            )


if __name__ == "__main__":
    main()
