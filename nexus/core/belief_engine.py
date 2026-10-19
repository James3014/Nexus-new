import posixpath
import re
from pathlib import Path
from typing import Any, Dict

from nexus.core.belief_contracts import AuditOutcome
from nexus.core.state_root import rebase_state_path
from nexus.infrastructure.state_json_store import StateJsonStore
from nexus.telemetry.tracer import NexusTracer


def blend_semantic_confidence(audit_confidence: float, semantic_confidence: float, *, semantic_weight: float = 0.3) -> float:
    """Blend audit confidence with semantic-search evidence without letting retrieval dominate."""
    audit = max(0.0, min(1.0, float(audit_confidence)))
    semantic = max(0.0, min(1.0, float(semantic_confidence)))
    weight = max(0.0, min(1.0, float(semantic_weight)))
    return round((audit * (1.0 - weight)) + (semantic * weight), 4)

def repair_target_key(target_file: str) -> str:
    """Shared belief key for repair outcomes on one target file (#2688).

    Writers keyed outcomes by ``local_heal:<task>:repair_outcome``; readers ask with
    free task text, so they never found them.  A key derived from the target file is
    stable across tasks and known to both sides.  Only a normalized repo-relative path
    gets a key; empty, absolute or ``..`` paths get "" (no cross-project influence).
    """
    text = str(target_file or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        return ""
    text = posixpath.normpath(text)
    if text in ("", ".") or text == ".." or text.startswith("../"):
        return ""
    return f"repair_outcome:file:{text}"


class BeliefEngine:
    """維護當前的邏輯假設與信心度 (Subjective Trust)。"""

    def __init__(self, state_file: Path | None = None, state_store: StateJsonStore | None = None):
        if state_file is None:
            state_file = Path(".nexus/belief_state.json")
        # <deploy root>/.nexus/belief_state.json follows NEXUS_STATE_ROOT; unset or any
        # other root keeps the given path (#2688).
        self.state_file = rebase_state_path(state_file)
        self.state_store = state_store or StateJsonStore()
        self.beliefs: Dict[str, Any] = {}
        self._load()

    def _load(self):
        self.beliefs = self.state_store.read_dict(self.state_file)

    def _persist(self, key: str | None = None) -> None:
        merge = getattr(self.state_store, "merge_dict", None)
        if key is None or merge is None:
            self.state_store.write_dict(self.state_file, self.beliefs)
            return
        # Merge only the key we changed, under the file lock, so a concurrent engine's
        # keys are not lost (#2688 review).
        self.beliefs = merge(self.state_file, {key: self.beliefs[key]})

    def assess_confidence(self, task_id: str, assumption: str = "", target_file: str = "") -> float:
        """根據歷史證據評估信心。

        Lookup order: the exact ``assumption or task_id`` key, then the shared
        ``repair_target_key(target_file)`` written by the repair path; else 0.7.
        """
        # 簡單模型：若有歷史相同假設則提高，否則基準為 0.7
        key = assumption or task_id
        target_key = repair_target_key(target_file)
        if target_key and key not in self.beliefs and target_key in self.beliefs:
            key = target_key
        return self.beliefs.get(key, {}).get("confidence", 0.7)

    def get_confidence(self, task_id: str, assumption: str = "", target_file: str = "") -> float:
        return self.assess_confidence(task_id, assumption, target_file)

    def update_belief(self, task_id: str, assumption: str, confidence: float, evidence_id: str):
        self.beliefs[assumption] = {
            "confidence": confidence,
            "evidence": evidence_id,
            "task_id": task_id
        }
        self._persist(assumption)

    def process_audit_outcome(self, outcome: AuditOutcome) -> dict[str, Any]:
        """Process a structured audit outcome without leaking confidence policy."""
        old_confidence = self.assess_confidence(outcome.task_id, outcome.assumption)
        confidence = outcome.confidence
        if confidence is None:
            confidence = 0.9 if outcome.passed else 0.1
        confidence = max(0.0, min(1.0, float(confidence)))
        semantic_raw = outcome.metadata.get("semantic_searcher_confidence")
        semantic_confidence = None
        if semantic_raw is not None:
            semantic_confidence = max(0.0, min(1.0, float(semantic_raw)))
            confidence = blend_semantic_confidence(confidence, semantic_confidence)
        self.update_belief(
            task_id=outcome.task_id,
            assumption=outcome.assumption,
            confidence=confidence,
            evidence_id=outcome.evidence_id,
        )
        self.beliefs[outcome.assumption]["last_audit_passed"] = bool(outcome.passed)
        self.beliefs[outcome.assumption]["reason"] = outcome.reason
        self.beliefs[outcome.assumption]["metadata"] = dict(outcome.metadata)
        semantic_refs = list(outcome.metadata.get("semantic_searcher_refs", []) or [])
        if semantic_refs:
            self.beliefs[outcome.assumption]["semantic_evidence_refs"] = [str(item) for item in semantic_refs if str(item).strip()]
        confidence_source = str(outcome.metadata.get("semantic_searcher_confidence_source") or "").strip()
        if confidence_source:
            self.beliefs[outcome.assumption]["semantic_confidence_source"] = confidence_source
        if semantic_confidence is not None:
            self.beliefs[outcome.assumption]["semantic_searcher_confidence"] = semantic_confidence
            self.beliefs[outcome.assumption]["confidence_policy"] = "audit_semantic_weighted"
        self._persist(outcome.assumption)
        NexusTracer.record_belief_shift(outcome.task_id, old_confidence, confidence)
        return {
            "task_id": outcome.task_id,
            "assumption": outcome.assumption,
            "confidence": confidence,
            "evidence_id": outcome.evidence_id,
            "accepted": bool(outcome.passed),
        }
