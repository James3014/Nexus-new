from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from nexus.services.codeintel.models import CodeSkeletonLookupResult
from nexus.services.codeintel.skeleton_provider import PythonCodeSkeletonProvider


FAULT_TOLERANT_AST_SNAPSHOT_SCHEMA = "nexus.fault_tolerant_ast_snapshot.v1"


@dataclass
class FaultTolerantASTSnapshot:
    root: Path | str
    search_paths: Iterable[str | Path] = ()

    def __post_init__(self) -> None:
        self.provider = PythonCodeSkeletonProvider(self.root, search_paths=self.search_paths)
        self.last_receipt: dict[str, Any] | None = None

    def lookup(self, symbol_name: str) -> CodeSkeletonLookupResult:
        result = self.provider.lookup_implementation(symbol_name)
        self.last_receipt = build_fault_tolerant_ast_snapshot_receipt(result)
        return result

    def export_compact_snapshot(self) -> dict[str, object]:
        snapshot = self.provider.export_symbol_snapshot()
        return {
            "schema": "nexus.fault_tolerant_ast_compact_snapshot.v1",
            "root": snapshot["root"],
            "symbol_count": snapshot["symbol_count"],
            "snapshot_hash": snapshot["snapshot_hash"],
            "symbols": snapshot["symbols"],
            "stores_source_text": False,
        }

    def load_compact_snapshot(self, payload: dict[str, object]) -> None:
        if payload.get("schema") != "nexus.fault_tolerant_ast_compact_snapshot.v1":
            raise ValueError("invalid_fault_tolerant_ast_snapshot_schema")
        self.provider.load_symbol_snapshot(
            {
                "schema": "nexus.code_skeleton_snapshot.v1",
                "root": payload.get("root", ""),
                "symbol_count": payload.get("symbol_count", 0),
                "snapshot_hash": payload.get("snapshot_hash", ""),
                "symbols": payload.get("symbols", []),
            }
        )


def build_fault_tolerant_ast_snapshot_receipt(result: CodeSkeletonLookupResult) -> dict[str, Any]:
    ast_statuses = sorted({match.ast_status for match in result.matches})
    blockers: list[str] = []
    if not result.found:
        blockers.append("UNPARSABLE_HOTSPOT" if result.reason == "symbol_not_found" else result.reason or "symbol_missing")
    return {
        "schema": FAULT_TOLERANT_AST_SNAPSHOT_SCHEMA,
        "status": "PASS" if result.found else "RETURN",
        "symbol": result.symbol,
        "found": result.found,
        "match_count": len(result.matches),
        "ast_statuses": ast_statuses,
        "used_last_known_good": "LAST_KNOWN_GOOD" in ast_statuses,
        "stores_source_text": False,
        "generated_or_boilerplate_promoted": False,
        "blockers": blockers,
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }
