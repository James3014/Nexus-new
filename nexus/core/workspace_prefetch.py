from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import os
import time
import logging

logger = logging.getLogger(__name__)

class Prefetcher:
    """
    ⚡ Nexus 工作空間預取器 (Claw-30P2)
    負責大規模專案的物理檔案樹構建與熱點緩衝，消除 I/O 延遲。
    """
    
    def __init__(self, workspace_root: str):
        self.root = Path(workspace_root).resolve()
        self.file_tree: List[str] = []
        self.hot_cache: Dict[str, str] = {}
        self.last_sync = 0.0

    def bootstrap(self, hot_files: List[str] = ["package.json", "main.py", "pyproject.toml"]):
        """🎯 啟動預取程序：構建索引與預加載"""
        start_time = time.time()
        logger.info(f"⚡ [Prefetch:Start] Indexing substrate at {self.root}...")
        
        count = 0
        for dirpath, dirnames, filenames in os.walk(self.root):
            # 排除隱藏目錄與常用忽略項
            if any(p in dirpath for p in [".git", "node_modules", ".venv", "__pycache__"]):
                continue
                
            for f in filenames:
                rel_path = os.path.relpath(os.path.join(dirpath, f), self.root)
                self.file_tree.append(rel_path)
                count += 1
                
                # 熱點預加載
                if f in hot_files:
                    try:
                        self.hot_cache[rel_path] = Path(os.path.join(dirpath, f)).read_text(encoding="utf-8")
                    except Exception:
                        pass
                        
            if count >= 5000: # 規模上限保護
                 break
        
        self.last_sync = time.time()
        duration = self.last_sync - start_time
        logger.info(f"✅ [Prefetch:DONE] Indexed {count} files in {duration:.2f}s. Cache Hit: {len(self.hot_cache)}")
        return count

    def get_file_list(self) -> List[str]:
        return self.file_tree

    def get_from_cache(self, rel_path: str) -> Optional[str]:
        return self.hot_cache.get(rel_path)
