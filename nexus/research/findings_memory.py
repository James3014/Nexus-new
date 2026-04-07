from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import json
import uuid

@dataclass
class FindingsCard:
    """
    🧬 Research Memory Card (DeepScientist Spec v1.5)
    用於持久化、檢索與跨任務學習的核心數據模型。
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    kind: str = "knowledge"          # papers | knowledge | episodes | decisions | ideas
    title: str = "Untitled Finding"
    scope: str = "task"              # task | global
    tags: List[str] = field(default_factory=list)
    stage: str = "unknown"           # scout | baseline | idea | experiment | analysis | decision
    confidence: str = "medium"       # high | medium | low
    evidence_paths: List[str] = field(default_factory=list)
    retrieval_hints: List[str] = field(default_factory=list)
    body: str = ""                   # 內容 (Context/Observation/Interpretation)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    recall_accuracy: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FindingsCard":
        return cls(**data)

class FindingsMemoryStore:
    """
    🏗️ 記憶儲存引擎
    職責: 管理 .nexus/memory/ 下的結構化記憶分佈。
    """
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.base_path = project_root / ".nexus" / "memory"
        self._ensure_dirs()

    def _ensure_dirs(self):
        for scope in ["task", "global"]:
            for kind in ["papers", "knowledge", "episodes", "decisions", "ideas"]:
                (self.base_path / scope / kind).mkdir(parents=True, exist_ok=True)

    def _get_card_path(self, card: FindingsCard) -> Path:
        return self.base_path / card.scope / card.kind / f"{card.id}.json"

    def write(self, card: FindingsCard) -> str:
        """寫入記憶卡。"""
        card.updated_at = datetime.now().isoformat()
        path = self._get_card_path(card)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(card.to_dict(), f, indent=4, ensure_ascii=False)
        return str(path)

    def read(self, card_id: str, scope: str = "task", kind: str = "knowledge") -> Optional[FindingsCard]:
        """讀取記憶卡。"""
        path = self.base_path / scope / kind / f"{card_id}.json"
        if not path.exists():
            # 嘗試全局搜索 (如果 scope 是 task)
            if scope == "task":
                return self.read(card_id, scope="global", kind=kind)
            return None
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return FindingsCard.from_dict(data)

    def list_recent(self, scope: str = "task", kind: Optional[str] = None, limit: int = 10) -> List[FindingsCard]:
        """按時間倒序列出最近記憶。"""
        results = []
        search_path = self.base_path / scope
        
        target_kinds = [kind] if kind else ["papers", "knowledge", "episodes", "decisions", "ideas"]
        
        for k in target_kinds:
            dir_path = search_path / k
            for p in dir_path.glob("*.json"):
                with open(p, "r", encoding="utf-8") as f:
                    results.append(FindingsCard.from_dict(json.load(f)))
        
        # 按更新時間排序
        results.sort(key=lambda x: x.updated_at, reverse=True)
        return results[:limit]

    def promote_to_global(self, card_id: str, kind: str) -> bool:
        """將任務級記憶提升到全域。"""
        card = self.read(card_id, scope="task", kind=kind)
        if not card:
            return False
        
        # 刪除舊的 task 檔案
        old_path = self._get_card_path(card)
        if old_path.exists():
            old_path.unlink()
            
        # 更改 scope 並重新寫入
        card.scope = "global"
        self.write(card)
        return True

    def list_cards(self, scope: str = "task", kind: Optional[str] = None) -> List[FindingsCard]:
        """
        📋 CLI 對位介面：列出所有結構化記憶卡。
        基於 list_recent 但範圍更廣。
        """
        return self.list_recent(scope=scope, kind=kind, limit=1000)
    
    def search(self, query: str, kind: Optional[str] = None, scope: str = "both") -> List[FindingsCard]:
        """
        🔍 語義檢索關鍵字 (此處先實現關鍵字匹配，待對接 Embedding Service)
        """
        all_cards = []
        scopes = ["task", "global"] if scope == "both" else [scope]
        
        for s in scopes:
            all_cards.extend(self.list_recent(scope=s, kind=kind, limit=100))
            
        # 簡易關鍵字過濾 (Title & Tags & Retrieval Hints)
        query = query.lower()
        matched = [
            c for c in all_cards 
            if query in c.title.lower() or 
               any(query in t.lower() for t in c.tags) or
               any(query in h.lower() for h in c.retrieval_hints)
        ]
        return matched
