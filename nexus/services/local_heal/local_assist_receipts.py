from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, List, Dict, Optional

@dataclass(frozen=True)
class LocalEvidenceCompactionSection:
    compaction_ratio: float = 0.0
    original_size: int = 0
    compacted_size: int = 0
    evidence_keys_processed: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class LocalMemoryRerankSection:
    lessons_count: int = 0
    reranked_keys: List[str] = field(default_factory=list)
    top_lesson_influence_score: float = 0.0

@dataclass(frozen=True)
class LocalPatchPreflightSection:
    preflight_passed: bool = False
    syntax_valid: bool = True
    compilation_error: Optional[str] = None

@dataclass(frozen=True)
class LocalCheapJudgeSection:
    judge_model: str = ""
    winner_confidence: float = 0.0
    abstained: bool = False

@dataclass(frozen=True)
class CandidateIsolationSection:
    candidate_id: str = ""
    isolated_path: str = ""
    sandbox_used: bool = True

@dataclass(frozen=True)
class VerifierSection:
    verifier_passed: bool = False
    verifier_duration_sec: float = 0.0
    test_failures_count: int = 0

@dataclass(frozen=True)
class LearningClosureSection:
    closure_written: bool = False
    learning_closure_path: str = ""
    lessons_learned: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class LocalAssistTelemetryCollection:
    """🛡️ Container for all Assist and Fallback receipt metadata.
    
    This is attached directly to the existing local_model_executor / repair_loop receipts.
    No new capabilities or RouteModes are introduced.
    """
    compaction: Optional[LocalEvidenceCompactionSection] = None
    memory_rerank: Optional[LocalMemoryRerankSection] = None
    preflight: Optional[LocalPatchPreflightSection] = None
    cheap_judge: Optional[LocalCheapJudgeSection] = None
    isolation: Optional[CandidateIsolationSection] = None
    verifier: Optional[VerifierSection] = None
    learning_closure: Optional[LearningClosureSection] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "compaction": asdict(self.compaction) if self.compaction else None,
            "memory_rerank": asdict(self.memory_rerank) if self.memory_rerank else None,
            "preflight": asdict(self.preflight) if self.preflight else None,
            "cheap_judge": asdict(self.cheap_judge) if self.cheap_judge else None,
            "isolation": asdict(self.isolation) if self.isolation else None,
            "verifier": asdict(self.verifier) if self.verifier else None,
            "learning_closure": asdict(self.learning_closure) if self.learning_closure else None,
        }
