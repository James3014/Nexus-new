from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


RETRIEVAL_QUERY_SCHEMA = "nexus.retrieval_query.v1"


@dataclass(frozen=True)
class RetrievalQuery:
    raw_text: str
    normalized_text: str
    source_scope: str
    max_chars: int
    unsafe_flags: tuple[str, ...]

    @property
    def allowed(self) -> bool:
        return not self.unsafe_flags

    def receipt(self) -> dict[str, Any]:
        return {
            "schema": RETRIEVAL_QUERY_SCHEMA,
            "status": "PASS" if self.allowed else "RETURN",
            "source_scope": self.source_scope,
            "raw_length": len(self.raw_text),
            "normalized_length": len(self.normalized_text),
            "max_chars": self.max_chars,
            "unsafe_flags": list(self.unsafe_flags),
            "query_allowed": self.allowed,
            "claim_boundary": [
                "Retrieval query receipts validate query shape only.",
                "They do not imply retrieval relevance, source verification, or public readiness.",
            ],
        }


def build_retrieval_query(
    query: str,
    *,
    source_scope: str = "local_docs",
    max_chars: int = 500,
) -> RetrievalQuery:
    raw_text = str(query or "")
    normalized = " ".join(raw_text.split())[: max(1, int(max_chars or 500))]
    flags: list[str] = []
    if _has_control_chars(raw_text):
        flags.append("control_chars")
    if len(raw_text) > max_chars:
        flags.append("query_truncated")
    if not normalized:
        flags.append("empty_query")
    return RetrievalQuery(
        raw_text=raw_text,
        normalized_text=normalized,
        source_scope=source_scope,
        max_chars=max_chars,
        unsafe_flags=tuple(flags),
    )


def _has_control_chars(text: str) -> bool:
    return bool(re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text or ""))
