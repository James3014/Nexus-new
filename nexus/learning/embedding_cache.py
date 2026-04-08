from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import time
import hashlib
import logging
from nexus.learning.disk_policy import DiskPolicy

class EmbeddingCache:
    """Simple file-based JSON cache for storing embeddings."""
    CURRENT_MODEL_VERSION = "all-MiniLM-L6-v2"

    def __init__(self, cache_file: Path):
        self.cache_file = cache_file
        self.data: Dict[str, Dict[str, Any]] = {}
        self.config = DiskPolicy.from_env()
        self._load()
        
    def _load(self):
        if self.cache_file.exists():
            try:
                content = self.cache_file.read_text(encoding="utf-8")
                raw = json.loads(content)
                if raw.get("_model_version") != self.CURRENT_MODEL_VERSION:
                    logging.getLogger(__name__).info("🔄 Embedding model version changed, rebuilding cache")
                    self.data = {"_model_version": self.CURRENT_MODEL_VERSION}
                else:
                    self.data = raw
            except Exception as exc:
                logging.getLogger(__name__).warning("embedding_cache_load_failed: %s", exc)
                self.data = {"_model_version": self.CURRENT_MODEL_VERSION}
        else:
            self.data = {"_model_version": self.CURRENT_MODEL_VERSION}

    def save(self) -> None:
        """Persist cache with atomic write and LRU eviction."""
        if not self.data:
            return
            
        # --- LRU Eviction ---
        if len(self.data) > self.config.max_cache_entries:
            # Sort by last_accessed descending, keep first max_cache_entries
            sorted_items = sorted(
                self.data.items(), 
                key=lambda item: item[1].get("last_accessed", 0) if isinstance(item[1], dict) else 0, 
                reverse=True
            )
            self.data = dict(sorted_items[:self.config.max_cache_entries])

        # --- Atomic Write ---
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.cache_file.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(self.data), encoding="utf-8")
            tmp_path.rename(self.cache_file)
        except OSError as exc:
            logging.getLogger(__name__).warning("embedding_cache_save_failed: %s", exc)

    def get_or_compute(self, key_id: str, text: str, model: Any) -> List[float]:
        # Use ID if provided, otherwise MD5 hash of text
        key = key_id if key_id else hashlib.md5(text.encode("utf-8")).hexdigest()

        if key in self.data:
            # For backward compatibility with old cache format [List[float]]
            if isinstance(self.data[key], list):
                self.data[key] = {"vector": self.data[key], "last_accessed": time.time()}
            else:
                # Ensure the entry is a dict
                if not isinstance(self.data[key], dict):
                    self.data[key] = {"vector": self.data[key], "last_accessed": time.time()}
                self.data[key]["last_accessed"] = time.time()
                
            return self.data[key]["vector"]

        # Compute
        vector = model.encode(text).tolist()
        self.data[key] = {"vector": vector, "last_accessed": time.time()}
        
        self.save()
        return vector

    @property
    def model_version(self) -> str:
        return self.data.get("_model_version", "unknown")
