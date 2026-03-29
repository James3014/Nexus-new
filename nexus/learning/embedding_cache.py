import json
from pathlib import Path
from typing import Dict, Any, List

class EmbeddingCache:
    """Store and retrieve embeddings globally to avoid re-computation."""
    
    def __init__(self, cache_file: Path):
        self.cache_file = cache_file
        self.data: Dict[str, List[float]] = {}
        self._load()
        
    def _load(self):
        if self.cache_file.exists():
            try:
                content = self.cache_file.read_text(encoding="utf-8")
                self.data = json.loads(content)
            except Exception:
                self.data = {}
                
    def _save(self):
        try:
            self.cache_file.write_text(json.dumps(self.data), encoding="utf-8")
        except Exception:
            pass
            
    def get_or_compute(self, skill_id: str, text: str, model: Any) -> List[float]:
        """Get embedding from cache, or compute and save it."""
        if skill_id in self.data:
            return self.data[skill_id]
            
        emb = model.encode(text).tolist()
        self.data[skill_id] = emb
        self._save()
        return emb
