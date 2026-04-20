from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import json
import os
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
    task_id: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FindingsCard":
        return cls(**data)

    @classmethod
    def from_lesson_event(cls, event: Any) -> "FindingsCard":
        """Compatibility factory: convert LessonEvent payload to FindingsCard."""
        return cls(
            id=str(getattr(event, "lesson_id", ""))[:8] or str(uuid.uuid4())[:8],
            kind="episodes",
            title=f"Lesson: {getattr(event, 'task_id', 'unknown')}",
            task_id=str(getattr(event, "task_id", "")),
            body=(
                f"Root Cause: {getattr(event, 'root_cause', '')}\n"
                f"Corrective Action: {getattr(event, 'corrective_action', '')}"
            ),
            confidence=str(getattr(event, "confidence", "medium")),
            tags=[str(getattr(event, "category", "")), str(getattr(event, "source_phase", ""))],
            evidence_paths=list(getattr(event, "evidence", []) or []),
            extra={
                "trace_id": getattr(event, "trace_id", ""),
                "decision_id": getattr(event, "decision_id", ""),
                "outcome": getattr(event, "outcome", ""),
            },
        )

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
        """
        🛡️ 硬化路徑: 加入 task_id 避免併發覆蓋。
        """
        safe_task_id = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (card.task_id or ""))
        filename = f"{safe_task_id}_{card.id}.json" if safe_task_id else f"{card.id}.json"
        return self.base_path / card.scope / card.kind / filename

    def _atomic_write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    @classmethod
    def from_lesson_event(cls, event: Any) -> "FindingsCard":
        """🛡️ MUSE-TRANSFORM (v24.0 Hardened): Convert LessonEvent to FindingsCard."""
        return cls(
            id=event.lesson_id[:8],
            kind="episodes",
            title=f"Lesson: {event.task_id}",
            task_id=event.task_id,
            body=f"Root Cause: {event.root_cause}\nCorrective Action: {event.corrective_action}",
            confidence=event.confidence,
            tags=[event.category, event.source_phase],
            evidence_paths=event.evidence,
            extra={
                "trace_id": event.trace_id,
                "decision_id": event.decision_id,
                "outcome": event.outcome
            }
        )

    def write(self, card: FindingsCard) -> str:
        """寫入記憶卡 (v24.0 Atomic: Filesystem + Vector Sync)。"""
        card.updated_at = datetime.now().isoformat()
        path = self._get_card_path(card)
        payload = card.to_dict()
        self._atomic_write_json(path, payload)

        # 🚀 [v24.0 Evolution] Trigger Vector Indexing if repository is available
        lancedb_synced = False
        try:
            from nexus.services.memory_repository import MemoryRepository
            repo = MemoryRepository(self.project_root / ".nexus" / "memory" / "memory_index.lancedb")
            repo.semantic_dedup_ingest("findings_cards", payload)
            lancedb_synced = True
        except Exception:
            pass
        
        card.extra["lancedb_synced"] = lancedb_synced
        payload["extra"]["lancedb_synced"] = lancedb_synced
        self._atomic_write_json(path, payload) # re-write with sync status if needed that's fine, but at least card object has it


        return str(path)

    def read(self, card_id: str, scope: str = "task", kind: str = "knowledge", task_id: Optional[str] = None) -> Optional[FindingsCard]:
        """讀取記憶卡。"""
        if task_id:
            safe_task_id = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in task_id)
            filename = f"{safe_task_id}_{card_id}.json"
        else:
            # 相容舊版或全局搜尋
            filename = f"{card_id}.json"
            
        path = self.base_path / scope / kind / filename
        
        if not path.exists():
            # 嘗試找尋所有以 card_id 結尾或特定的檔案
            potential_files = list((self.base_path / scope / kind).glob(f"*_{card_id}.json"))
            if potential_files:
                path = potential_files[0]
            else:
                if scope == "task":
                    return self.read(card_id, scope="global", kind=kind, task_id=task_id)
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
