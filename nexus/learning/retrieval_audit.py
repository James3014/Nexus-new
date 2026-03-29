import json
import logging
from pathlib import Path
from typing import List, Tuple, Optional, Any, Dict
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class RetrievalAuditLogger:
    """
    Appends structured retrieval events to .nexus/audit/retrieval_log.jsonl
    """
    def __init__(self, project_root: Path):
        self.log_dir = project_root / ".nexus" / "audit"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "retrieval_log.jsonl"
        
    def log(
        self,
        query: str,
        threshold: float,
        top_k: int,
        embedding_version: str,
        hits: List[Tuple[str, float]],
        task_type: str = "",
        task_id: str = "",
        trace_id: str = "",
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log a single retrieval event."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": task_id,
            "trace_id": trace_id,
            "query": query,
            "task_type": task_type,
            "threshold": threshold,
            "top_k": top_k,
            "embedding_version": embedding_version,
            "hits": [{"skill_id": sid, "score": score} for sid, score in hits],
            "context": context or {}
        }
        
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception as e:
            logger.warning("retrieval_audit_logger_failed task_id=%s trace_id=%s: %s", task_id, trace_id, e)

_global_auditor = None

def log_retrieval_audit(
    project_root: Path,
    query: str,
    threshold: float,
    top_k: int,
    embedding_version: str,
    hits: List[Tuple[str, float]],
    task_type: str = "",
    task_id: str = "",
    trace_id: str = "",
    context: Optional[Dict[str, Any]] = None
) -> None:
    """Helper for easy global logging"""
    global _global_auditor
    if not _global_auditor or _global_auditor.log_dir.parent != project_root / ".nexus":
        _global_auditor = RetrievalAuditLogger(Path(project_root))
        
    _global_auditor.log(
        query=query,
        threshold=threshold,
        top_k=top_k,
        embedding_version=embedding_version,
        hits=hits,
        task_type=task_type,
        task_id=task_id,
        trace_id=trace_id,
        context=context
    )
