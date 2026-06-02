import uuid
from typing import Dict, Any
from nexus.committee.models import ProposalCandidate
from nexus.engine.semantic_adapter import SemanticAdapter

class ProposerAdapter:
    """
    🔌 Task T3: Proposer Adapter
    職責: 將 7B/14B 標籤輸出接成標準 ProposalCandidate。
    """
    def __init__(self):
        self.semantic_adapter = SemanticAdapter()

    def create_candidate(self, task_id: str, model: str, attempt: int, raw_output: str, artifacts: list) -> ProposalCandidate:
        route, decision, phase, conf = self.semantic_adapter.process_model_output(raw_output)
        
        return ProposalCandidate(
            candidate_id=f"{task_id}-{model}-{attempt}-{uuid.uuid4().hex[:4]}",
            source_model=model,
            attempt_id=attempt,
            raw_label=raw_output,
            normalized_phase=str(phase),
            artifact_refs=artifacts
        )
