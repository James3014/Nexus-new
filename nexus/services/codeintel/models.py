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
    report_path: str = ""
    schema_version: str = CODEINTEL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CodeScanResult:
    nodes_count: int
    edges_count: int
    languages: list[str] = field(default_factory=list)
    index_path: str = ""
    generated_at: str = ""
    schema_version: str = CODEINTEL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CodeContextResult:
    symbol: str
    callers: list[str] = field(default_factory=list)
    callees: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    related_tests: list[str] = field(default_factory=list)
    found: bool = False
    reason: str = ""
    schema_version: str = CODEINTEL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CodeSkeletonSymbol:
    symbol: str
    file_path: str
    start_line: int
    end_line: int
    kind: str
    signature: str
    docstring_present: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CodeSkeletonLookupResult:
    symbol: str
    found: bool
    matches: list[CodeSkeletonSymbol] = field(default_factory=list)
    reason: str = ""
    schema_version: str = CODEINTEL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["matches"] = [match.to_dict() for match in self.matches]
        return payload
