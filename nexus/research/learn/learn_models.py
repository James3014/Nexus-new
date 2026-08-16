from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class LearnClaim:
    claim: str
    source_url: str
    citation_span: list[int]
    topic_tags: list[str]
    created_at: str
    topic_pack: str = ""
    evidence_strength: str = "medium"
    freshness_days: float = 0.0
    freshness_score: float = 1.0
    metadata: dict[str, Any] | None = None
    admission_status: str = "UNVERIFIED"
    admission_verifier: str = ""
    source_snapshot_sha256: str = ""
    admission_claim_key: str = ""
    admission_proof: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
