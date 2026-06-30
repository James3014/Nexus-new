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


def build_local_assist_telemetry_from_executor_meta(
    raw_meta: Dict[str, Any],
) -> LocalAssistTelemetryCollection:
    """Extract assist telemetry from existing executor raw_model_metadata.
    
    This is observational only — it does not change execution behavior,
    solved outcome, or gate results.
    """
    compaction = None
    if raw_meta.get("compaction_ratio") is not None:
        compaction = LocalEvidenceCompactionSection(
            compaction_ratio=float(raw_meta.get("compaction_ratio", 0.0)),
            original_size=int(raw_meta.get("raw_context_chars", 0)),
            compacted_size=int(raw_meta.get("compact_context_chars", 0)),
            evidence_keys_processed=list(raw_meta.get("evidence_keys_processed", [])),
        )

    memory_rerank = None
    if raw_meta.get("memory_lessons_count") is not None:
        memory_rerank = LocalMemoryRerankSection(
            lessons_count=int(raw_meta.get("memory_lessons_count", 0)),
            reranked_keys=list(raw_meta.get("memory_reranked_keys", [])),
            top_lesson_influence_score=float(raw_meta.get("memory_top_lesson_score", 0.0)),
        )

    preflight = None
    if raw_meta.get("preflight_passed") is not None:
        preflight = LocalPatchPreflightSection(
            preflight_passed=bool(raw_meta.get("preflight_passed", False)),
            syntax_valid=bool(raw_meta.get("syntax_valid", True)),
            compilation_error=raw_meta.get("compilation_error"),
        )

    cheap_judge = None
    if raw_meta.get("judge_model") is not None:
        cheap_judge = LocalCheapJudgeSection(
            judge_model=str(raw_meta.get("judge_model", "")),
            winner_confidence=float(raw_meta.get("judge_winner_confidence", 0.0)),
            abstained=bool(raw_meta.get("judge_abstained", False)),
        )

    isolation = None
    if raw_meta.get("candidate_id") is not None:
        isolation = CandidateIsolationSection(
            candidate_id=str(raw_meta.get("candidate_id", "")),
            isolated_path=str(raw_meta.get("isolated_path", "")),
            sandbox_used=bool(raw_meta.get("sandbox_used", True)),
        )

    verifier = None
    if raw_meta.get("verifier_status") is not None:
        verifier = VerifierSection(
            verifier_passed=raw_meta.get("verifier_status") == "pass",
            verifier_duration_sec=float(raw_meta.get("verifier_duration_sec", 0.0)),
            test_failures_count=int(raw_meta.get("test_failures_count", 0)),
        )

    learning_closure = None
    if raw_meta.get("learning_closure_written") is not None:
        learning_closure = LearningClosureSection(
            closure_written=bool(raw_meta.get("learning_closure_written", False)),
            learning_closure_path=str(raw_meta.get("learning_closure_path", "")),
            lessons_learned=list(raw_meta.get("lessons_learned", [])),
        )

    return LocalAssistTelemetryCollection(
        compaction=compaction,
        memory_rerank=memory_rerank,
        preflight=preflight,
        cheap_judge=cheap_judge,
        isolation=isolation,
        verifier=verifier,
        learning_closure=learning_closure,
    )
