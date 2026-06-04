from enum import Enum, auto
from typing import List, Dict, Any

class BlockerCode(Enum):
    """
    🛑 [Domain] Standard Blocker Taxonomy (Linus: Good Taste)
    職責: 統一名稱空間，消滅零散的字串判斷。
    """
    SCHEMA_MISMATCH = auto()
    DRIFT_DETECTED = auto()
    EVIDENCE_MISSING = auto()
    BASELINE_REGRESSION = auto()
    REPLAY_INCONSISTENT = auto()
    DOMAIN_UNAUTHORIZED = auto()
    PARTIAL_TELEMETRY = auto()
    ATOMIC_WRITE_FAILURE = auto()

class BlockerRegistry:
    """提供機讀原因與人類可讀描述的映射"""
    _DESCRIPTIONS = {
        BlockerCode.SCHEMA_MISMATCH: "Manifest schema version mismatch with current runtime.",
        BlockerCode.DRIFT_DETECTED: "Task specification hash drifted from sealed receipt.",
        BlockerCode.EVIDENCE_MISSING: "No physical evidence provided for promotion.",
        BlockerCode.BASELINE_REGRESSION: "Loss detected in baseline lane tasks.",
        BlockerCode.REPLAY_INCONSISTENT: "Replay logic produced different verdict than receipt.",
        BlockerCode.DOMAIN_UNAUTHORIZED: "Domain ID not in canary allowlist.",
        BlockerCode.PARTIAL_TELEMETRY: "Incomplete telemetry trace detected.",
        BlockerCode.ATOMIC_WRITE_FAILURE: "Transaction failed during physical state update."
    }

    @classmethod
    def get_description(cls, code: BlockerCode) -> str:
        return cls._DESCRIPTIONS.get(code, "Unknown governance blocker.")
