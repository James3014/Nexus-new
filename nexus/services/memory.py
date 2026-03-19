import lancedb
import pandas as pd
import json
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
        self.db_path = self.project_root / ".nexus" / "knowledge" / "lancedb"
        self._db = None
        try:
            import redis
            self.redis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            self.redis.ping()
            self.redis_available = True
        except Exception:
            self.redis_available = False

    def _get_db(self):
        if self._db is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(self.db_path)
            
            # 🛡️ Auto-Init: 如果 policy 表不存在，從 JSONL 匯入
            table_names = self._db.table_names() if self._db else []
            if "policy" not in table_names:
                policy_jsonl = self.project_root / ".nexus" / "knowledge" / "policy_memory.jsonl"
                if policy_jsonl.exists():
                    try:
                        data = []
                        with open(policy_jsonl, "r", encoding="utf-8") as f:
                            for line in f:
                                if line.strip():
                                    data.append(json.loads(line.strip()))
                        if data:
                            tbl = self._db.create_table("policy", data=data)
                            # 🧪 v9 M2: 建立 FTS 索引 (限制: 單一欄位)
                            tbl.create_fts_index("condition", replace=True)
                            print(f"✅ [MemoryService] Initialized 'policy' table with FTS index on 'condition'")
                    except Exception as e:
                        print(f"⚠️ [MemoryService] Auto-init failed: {e}")
        return self._db

    def semantic_search(self, query: str, table_name: str = "policy", limit: int = 3) -> List[Dict]:
        """🧬 語義檢索實作 (M2-Active)"""
        try:
            db = self._get_db()
            if table_name not in db.table_names():
                return []
            
            table = db.open_table(table_name)
            try:
                # 💡 v9: 優先使用 FTS (Full Text Search)
                results = table.search(query, query_type="fts").limit(limit).to_pandas()
            except Exception as e:
                # 🛡️ Fallback: 如果 FTS 索引尚未就緒或失敗，使用 Pandas 關鍵字過濾
                print(f"⚠️ [MemorySearch] FTS failed, using pandas fallback: {e}")
                df = table.to_pandas()
                # 簡單關鍵字過濾
                q = str(query).lower()
                results = df[
                    df['condition'].str.contains(q, case=False, na=False) | 
                    df['action'].str.contains(q, case=False, na=False)
                ].head(limit)

            # 轉換為 Nexus 格式
            reminders = []
            for _, row in results.iterrows():
                # FTS 下使用得分 (_score) 作為相關性參考
                score = float(getattr(row, "_score", 1.0))
                confidence = min(1.0, score / 1.0) # Fallback 情況下設較高 confidence 
                reminders.append({
                    "id": str(row.get("rule_id", "unknown")),
                    "content": str(row.get("action", row.get("condition", "No Content"))),
                    "relevance": round(confidence, 2),
                    "source": "lancedb-fts" if "_score" in row.index else "lancedb-fallback"
                })
            return []
        except Exception as e:
            print(f"⚠️ [MemorySearch] Critical failure: {e}")
            return []

    def ingest_episode(self, episode: Dict[str, Any]):
        """🧪 Phase M3: 學習閉環入口。根據任務結果更新 Policy 權重。"""
        try:
            db = self._get_db()
            if not db:
                return
            
            success = episode.get("success", False)
            policy_ids = episode.get("policy_hit_ids", [])
            
            if not policy_ids:
                return
                
            # 更新 Policy Confidence
            if "policy" in db.table_names():
                table = db.open_table("policy")
                df = table.to_pandas()
                
                # 簡單權重更新：成功 +0.05, 失敗 -0.15 (挫折偏好)
                penalty = 0.05 if success else -0.15
                
                updated = False
                for pid in policy_ids:
                    if pid in df['rule_id'].values:
                        idx = df[df['rule_id'] == pid].index
                        df.loc[idx, 'confidence'] = (df.loc[idx, 'confidence'] + penalty).clip(0.0, 1.0)
                        updated = True
                
                if updated:
                    # 覆寫表格 (M3 規模較小，全量覆寫可接受)
                    db.create_table("policy", data=df, mode="overwrite")
                    print(f"🧠 [MemoryService] M3 Learning applied: {len(policy_ids)} policies updated. (Success: {success})")
                    
                    # 🛡️ 汰弱留強: 如果信心度低於 0.3，標註為 deprecated
                    deprecated_count = len(df[df['confidence'] < 0.3])
                    if deprecated_count > 0:
                        print(f"⚠️ [MemoryService] {deprecated_count} policies are now deprecated due to poor performance.")
        except Exception as e:
            print(f"⚠️ [MemoryService] M3 Ingestion failed: {e}")

    def aggregate_memory(self, query: Optional[str] = None) -> Dict[str, Any]:
        """聚合全域與專案級記憶來源。"""
        # 🧪 v9 M2: 優先使用語義檢索
        if query:
            reminders = self.semantic_search(query)
        else:
            # Fallback to random/recent if no query provided
            reminders = self.semantic_search("general_nexus_task")[:3]

        result = {
            'reminders': reminders, 
            'total_sources': 3, # LanceDB + Global
            'timestamp': datetime.now().isoformat()
        }
        
        # 持久化 reminders.json 以供其他工具/Shell 讀取 (後向相容)
        if self.run_dir:
            dest_path = self.run_dir / 'reminders.json'
        else:
            dest_path = self.project_root / 'reminders.json'
        
        with open(dest_path, 'w', encoding='utf-8') as f:
            import json
            json.dump(result, f, ensure_ascii=False, indent=2)
            
        import gc
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
