from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass(frozen=True)
class EvidenceBundle:
    ticket_id: str
    verdicts: List[Dict[str, Any]]
    integrity_hash: str
    metadata: Dict[str, Any] = field(default_factory=dict)
