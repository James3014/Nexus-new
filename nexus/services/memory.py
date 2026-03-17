import json
import random
import hashlib
import gc
import redis
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

class MemoryService:
    """
    🧠 Nexus Memory Service
    負責聚合與快取跨階段的背景知識與歷史記錄。
    已從 legacy scripts/logmemory.py 重構為原生物件。
    """
    def __init__(self, project_root: str, run_dir: Optional[str] = None):
        self.project_root = Path(project_root)
        self.run_dir = Path(run_dir) if run_dir else None
        try:
            self.redis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            self.redis.ping()
            self.redis_available = True
        except Exception:
            self.redis_available = False

    def aggregate_memory(self) -> Dict[str, Any]:
        """聚合全域與專案級記憶來源。"""
        sources = {}
        # 1. Global Lessons
        codex = Path('/Users/jameschen/Downloads/.codex_lessons.md')
        sources['codex'] = codex.read_text(encoding='utf-8') if codex.exists() else ''
        
        # 2. Crystal Lessons
        crystal = []
        c_path = self.project_root / 'obsidian/crystal_lessons.jsonl'
        if c_path.exists():
            with open(c_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        try:
                            crystal.append(json.loads(line.strip()))
                        except Exception:
                            continue
        sources['crystal'] = crystal
        
        # 3. Tracelog (tail 100)
        trace = []
        t_path = self.project_root / 'tracelog.jsonl'
        if t_path.exists():
            with open(t_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()[-100:]
                for line in lines:
                    if line.strip():
                        try:
                            trace.append(json.loads(line.strip()))
                        except Exception:
                            continue
        sources['trace'] = trace
        
        # 4. Patterns
        pats = []
        p_dir = self.project_root / 'obsidian/patterns'
        if p_dir.exists():
            for md in p_dir.glob('*.md'):
                try:
                    pats.append(md.read_text(encoding='utf-8'))
                except Exception:
                    continue
        sources['patterns'] = pats

        unified = []
        for name, content in sources.items():
            if isinstance(content, list):
                for item in content[-10:]:  # Recent
                    unified.append({'source': name, 'content': item, 'type': 'jsonl'})
            else:
                unified.append({'source': name, 'content': content.strip()[:1000], 'type': 'text'})

        # 模擬相似度檢索 (未來可擴展為真 Embeddings)
        reminders = unified[:3]
        for r_item in reminders:
            r_item['relevance'] = round(random.uniform(0.7, 1.0), 2)
            r_item['id'] = hashlib.md5(str(r_item['content']).encode()).hexdigest()[:8]

        result = {
            'reminders': reminders, 
            'total_sources': len(sources), 
            'timestamp': datetime.now().isoformat()
        }
        
        # 持久化 reminders.json 以供其他工具/Shell 讀取 (後向相容)
        # Phase C: 產物收斂，優先使用 run_dir
        if self.run_dir:
            dest_path = self.run_dir / 'reminders.json'
        else:
            dest_path = self.project_root / 'reminders.json'
        dest_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), 
            encoding='utf-8'
        )
        gc.collect()
        return result

    def cached_search(self, key: str, ttl: int = 1800) -> Dict[str, Any]:
        """雙層快取搜尋。"""
        if self.redis_available:
            hot_key = f"hot:{hashlib.md5(key.encode()).hexdigest()}"
            try:
                cached = self.redis.get(hot_key)
                if cached:
                    return json.loads(cached)
            except Exception:
                pass
        
        result = self.aggregate_memory()
        
        if self.redis_available:
            try:
                self.redis.setex(f"hot:{hashlib.md5(key.encode()).hexdigest()}", ttl, json.dumps(result))
            except Exception:
                pass
        return result
