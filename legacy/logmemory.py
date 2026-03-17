#!/usr/bin/env python3
import json
import argparse
import random  # Mock, 換 Jina/Lance
from pathlib import Path
import hashlib
import time
import gc  # Cleanup
import redis

BASE_PATH = Path('/Users/jameschen/Downloads/Muse-Nexus')  # 調整你的路徑

# Redis Config
try:
    r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    r.ping()
    REDIS_AVAILABLE = True
except Exception:
    REDIS_AVAILABLE = False

def aggregate_memory():
    sources = {}
    # 1. Global Lessons
    codex = Path('/Users/jameschen/Downloads/.codex_lessons.md')
    sources['codex'] = codex.read_text(encoding='utf-8') if codex.exists() else ''
    # 2. Crystal
    crystal = []
    c_path = BASE_PATH / 'obsidian/crystal_lessons.jsonl'
    if c_path.exists():
        for line in c_path.open():
            crystal.append(json.loads(line.strip()))
    sources['crystal'] = crystal
    # 3. Tracelog (tail 100)
    trace = []
    t_path = BASE_PATH / 'tracelog.jsonl'
    if t_path.exists():
        for line in t_path.open().readlines()[-100:]:
            trace.append(json.loads(line.strip()))
    sources['trace'] = trace
    # 4. Patterns
    pats = []
    p_dir = BASE_PATH / 'obsidian/patterns'
    if p_dir.exists():
        for md in p_dir.glob('*.md'):
            pats.append(md.read_text())
    sources['patterns'] = pats

    unified = []
    for name, content in sources.items():
        if isinstance(content, list):
            for item in content[-10:]:  # Recent
                unified.append({'source': name, 'content': item, 'type': 'jsonl'})
        else:
            unified.append({'source': name, 'content': content.strip()[:1000], 'type': 'text'})

    # LanceDB sim (未來真 embed)
    reminders = unified[:3]
    for r_item in reminders:
        r_item['relevance'] = round(random.uniform(0.7, 1.0), 2)
        r_item['id'] = hashlib.md5(str(r_item['content']).encode()).hexdigest()[:8]

    result = {'reminders': reminders, 'total_sources': len(sources), 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S')}
    (BASE_PATH / 'reminders.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    gc.collect()  # Memory clean
    return result

def cached_search(key, ttl=3600):
    """雙層快取實作：短期 Redis (熱 lessons) + 長期 LanceDB (冷數據)"""
    if REDIS_AVAILABLE:
        # 1. 熱快取搜尋 (Hot Lessons)
        hot_key = f"hot:{hashlib.md5(key.encode()).hexdigest()}"
        cached = r.get(hot_key)
        if cached:
            print(f"⚡ [DualCache: HOT] Retrieval for {key} successful.")
            return json.loads(cached)
    
    # 2. 冷數據聚合 (Cold Data / LanceDB Fallback)
    result = aggregate_memory()
    
    if REDIS_AVAILABLE:
        # 存入熱快取，TTL 為 1800 秒 (30 分鐘)
        r.setex(f"hot:{hashlib.md5(key.encode()).hexdigest()}", 1800, json.dumps(result))
    return result

def cleanup_memory():
    if REDIS_AVAILABLE:
        r.flushdb()
    gc.collect()
    print("🧹 [Cleanup] Redis flushed + GC done")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='LogMemory Agent')
    parser.add_argument('--test', action='store_true', help='Run test aggregation')
    parser.add_argument('--cache', action='store_true', help='Test with Redis cache')
    parser.add_argument('--phase', help='Inject for phase')
    args = parser.parse_args()

    if args.test or args.cache or args.phase:
        key = f"memory_v7_{args.phase or 'test'}"
        if args.cache:
            result = cached_search(key)
        else:
            result = aggregate_memory()
            
        print(f"✅ reminders.json generated: {result['total_sources']} sources, {len(result['reminders'])} reminders")
        print(f"Avg relevance: {round(sum(r['relevance'] for r in result['reminders'])/len(result['reminders']), 2)}")
        print(f"Ready for {args.phase or 'all phases'}")
    else:
        print("Use --test, --cache or --phase D")
