from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

@dataclass(frozen=True)
class SelectionVerdict:
    """[T5] 選優決策的輸出契約"""
    winner_id: Optional[str]
    confidence: float
    gap: float
    abstained: bool
    reason: str
    failure_bucket: Optional[str] = None
