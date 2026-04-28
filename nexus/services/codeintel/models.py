from __future__ import annotations

from dataclasses import asdict, dataclass, field


CODEINTEL_SCHEMA_VERSION = "codeintel-v1"


@dataclass(frozen=True)
class CodeImpactResult:
    changed_files: list[str]
    impacted_symbols: list[str] = field(default_factory=list)
    impacted_files: list[str] = field(default_factory=list)
    risk_score: int = 0
    risk_reason: list[str] = field(default_factory=list)
    evidence_paths: list[str] = field(default_factory=list)
    schema_version: str = CODEINTEL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
