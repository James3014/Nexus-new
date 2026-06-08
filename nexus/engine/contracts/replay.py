import json
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional

@dataclass
class ReplayArtifact:
    """
    🛡️ ReplayArtifact: 可重放證據契約
    封裝一次決策的所有關鍵變因，確保機器可證的一致性。
    """
    input_digest: str  # Task + Code Snapshot Hash
    slice_spec: Dict[str, Any]
    context_digest: str  # Final Context Hash
    candidate_hash: str  # Patch Hash
    verifier_verdicts: Dict[str, str]  # Verifier Type -> Verdict
    memory_trace_ids: List[str]
    final_action: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReplayArtifact":
        # 嚴格校驗必要欄位 (Fail-closed)
        required = {
            "input_digest", "slice_spec", "context_digest", 
            "candidate_hash", "verifier_verdicts", 
            "memory_trace_ids", "final_action"
        }
        for field_name in required:
            if field_name not in data:
                raise KeyError(f"REPLAY_CONTRACT_VIOLATION: Missing required field '{field_name}'")
        
        return cls(**data)

    def compute_replay_signature(self) -> str:
        """計算決策簽名，用於一致性比對。"""
        # 排除 metadata 等非決策因子
        decision_bundle = {
            "input": self.input_digest,
            "context": self.context_digest,
            "patch": self.candidate_hash,
            "verdicts": self.verifier_verdicts
        }
        return hashlib.sha256(json.dumps(decision_bundle, sort_keys=True).encode()).hexdigest()
