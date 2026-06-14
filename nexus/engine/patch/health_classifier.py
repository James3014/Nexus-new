from enum import Enum
from typing import List, Any

class PatchHealth(str, Enum):
    HEALTHY = "HEALTHY"
    UNHEALTHY_EMPTY = "UNHEALTHY_EMPTY"
    UNHEALTHY_CONFLICT = "UNHEALTHY_CONFLICT"

class PatchEnvelopeHealthClassifier:
    """
    🛡️ PatchEnvelopeHealthClassifier: 補丁健康度分類器
    """
    def classify(self, raw_patch: str, blocks: List[Any]) -> PatchHealth:
        if not raw_patch or not raw_patch.strip():
            return PatchHealth.UNHEALTHY_EMPTY
        # Search/Replace blocks use conflict-like markers as delimiters, which is healthy
        if blocks:
            return PatchHealth.HEALTHY
        # Only flag as conflict if markers exist but no valid blocks were parsed
        if "<<<<<<<" in raw_patch or "=======" in raw_patch or ">>>>>>>" in raw_patch:
            return PatchHealth.UNHEALTHY_CONFLICT
        return PatchHealth.HEALTHY
