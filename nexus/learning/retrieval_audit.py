from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from dataclasses import dataclass

@dataclass
class AuditEntry:
    """R1.4: RetrievalAuditLogger 的參數物件。"""
    query: str
    threshold: float
    top_k: int
    embedding_version: str
    hits: List[Tuple[str, float]]
    task_type: str = ""
    task_id: str = ""
    trace_id: str = ""
    context: Optional[Dict[str, Any]] = None


class RetrievalAuditLogger:
    """
    Appends structured retrieval events to .nexus/audit/retrieval_log.jsonl
    """
    def __init__(self, project_root: Path):
        self.log_dir = project_root / ".nexus" / "audit"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "retrieval_log.jsonl"
        
    def log(self, entry: AuditEntry) -> None:
        """Log a single retrieval event."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": entry.task_id,
            "trace_id": entry.trace_id,
            "query": entry.query,
            "task_type": entry.task_type,
            "threshold": entry.threshold,
            "top_k": entry.top_k,
            "embedding_version": entry.embedding_version,
            "hits": [{"skill_id": sid, "score": score} for sid, score in entry.hits],
            "context": entry.context or {}
        }
        
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception as e:
            logger.warning("retrieval_audit_logger_failed task_id=%s trace_id=%s: %s", task_id, trace_id, e)

_global_auditor = None

def log_retrieval_audit(entry: AuditEntry, project_root: Path) -> None:
    """Helper for easy global logging"""
    global _global_auditor
    if not _global_auditor or _global_auditor.log_dir.parent != project_root / ".nexus":
        _global_auditor = RetrievalAuditLogger(Path(project_root))
        
    _global_auditor.log(entry)
