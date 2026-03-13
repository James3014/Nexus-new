#!/usr/bin/env python3
# 🛡️ Codex-Verified: Codex-Auth-Lvl13-Final (2026-03-03)
import os
import lancedb
import requests
import json
import argparse
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# 載入環境變數
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
load_dotenv(os.path.expanduser("~/.openclaw/.env"))

JINA_KEY = os.environ.get("JINA_API_KEY", "MISSING_KEY")
DB_PATH = os.path.expanduser("~/.openclaw/memory/lancedb-pro")
PRIMARY_TABLE = os.environ.get("MUSE_SEARCH_TABLE", "agent_main")
TABLE_FALLBACKS = ["agent_main", "memories_v2", "memories"]
HOT_TABLE_NAME = os.environ.get("MUSE_HOT_TABLE", "agent_hot")
HOT_DISTANCE_THRESHOLD = float(os.environ.get("MUSE_HOT_MAX_DISTANCE", "1.5"))
ENABLE_CACHE = os.environ.get("MUSE_SEARCH_ENABLE_CACHE", "1") == "1"
CACHE_TTL_SEC = int(os.environ.get("MUSE_SEARCH_CACHE_TTL_SEC", "180"))
CACHE_PATH = Path.home() / ".muse_logs" / "brain_search_cache_v2.json"
USAGE_LOG_PATH = Path.home() / ".muse_logs" / "brain_search_usage.jsonl"
USAGE_LOG_ENABLED = os.environ.get("MUSE_SEARCH_LOG", "1") == "1"


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


def _append_usage_log(query, table_name, results, elapsed_ms, status):
    if not USAGE_LOG_ENABLED:
        return
    try:
        USAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        sources = []
        for r in results[:5]:
            meta = _metadata_of(r)
            src = meta.get("source")
            if src:
                sources.append(src)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "table": table_name,
            "elapsed_ms": round(elapsed_ms, 2),
            "result_count": len(results),
            "top_sources": sources,
            "status": status,
        }
        with USAGE_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # logging failure must never break search flow
        pass


def _cache_key(query, limit):
    return f"{_normalize(query)}|{limit}"


def _load_cache():
    if not ENABLE_CACHE or not CACHE_PATH.exists():
        return {}
    try:
        with CACHE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cache(cache):
    if not ENABLE_CACHE:
        return
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CACHE_PATH.open("w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass


def _get_cached(query, limit):
    cache = _load_cache()
    item = cache.get(_cache_key(query, limit))
    if not item:
        return None
    ts = item.get("ts", 0)
    if not isinstance(ts, (int, float)):
        return None
    if time.time() - ts > CACHE_TTL_SEC:
        return None
    return item.get("results")


def _put_cache(query, limit, results):
    cache = _load_cache()
    cache[_cache_key(query, limit)] = {"ts": time.time(), "results": results}
    _save_cache(cache)


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
    started = time.perf_counter()
    if ENABLE_CACHE:
        cached = _get_cached(query, limit)
        if cached is not None:
            _append_usage_log(
                query,
                "cache",
                cached,
                (time.perf_counter() - started) * 1000,
                "cache_hit",
            )
            return cached

    if not os.path.exists(DB_PATH):
        print(f"❌ 找不到資料庫：{DB_PATH}")
        _append_usage_log(query, "", [], (time.perf_counter() - started) * 1000, "db_missing")
        return []

    db = lancedb.connect(DB_PATH)
    table_name = _pick_table(db)
    if not table_name:
        print(f"❌ 找不到可用資料表：{TABLE_FALLBACKS}")
        _append_usage_log(query, "", [], (time.perf_counter() - started) * 1000, "table_missing")
        return []

    vector = get_embedding(query)

    if vector:
        table_names = _table_names(db)
        if HOT_TABLE_NAME in table_names:
            hot_table = db.open_table(HOT_TABLE_NAME)
            hot_results = hot_table.search(vector).limit(limit).to_list()
            hot_results = _rerank(hot_results, query)
            if hot_results and float(hot_results[0].get("_distance", 9999.0)) <= HOT_DISTANCE_THRESHOLD:
                hot_cleaned = _strip_heavy_fields(hot_results)
                _put_cache(query, limit, hot_cleaned)
                _append_usage_log(
                    query,
                    HOT_TABLE_NAME,
                    hot_cleaned,
                    (time.perf_counter() - started) * 1000,
                    "ok_hot",
                )
                return hot_cleaned

        table = db.open_table(table_name)
        results = table.search(vector).limit(limit).to_list()
        results = _rerank(results, query)
        cleaned = _strip_heavy_fields(results)
        _put_cache(query, limit, cleaned)
        _append_usage_log(
            query,
            table_name,
            cleaned,
            (time.perf_counter() - started) * 1000,
            "ok",
        )
        return cleaned
    _append_usage_log(query, table_name, [], (time.perf_counter() - started) * 1000, "embedding_failed")
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
