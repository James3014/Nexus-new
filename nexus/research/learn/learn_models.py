from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, List, Optional

@dataclass(frozen=True)
class LearnClaim:
    claim: str
    source_url: str
    citation_span: list[int]
    topic_tags: list[str]
    created_at: str
    topic_pack: str = ""
    evidence_strength: str = "medium"
    metadata: dict[str, Any] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
