from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from nexus.services.codeintel.skeleton_provider import lookup_implementation


CODE_SKELETON_CONTEXT_SCHEMA = "nexus.code_skeleton_context.v1"


def build_code_skeleton_context(
    root: str | Path,
    symbols: Iterable[str],
    *,
    search_paths: Iterable[str | Path] = (),
    max_matches: int = 20,
) -> dict[str, Any]:
    lookups = [
        lookup_implementation(root, symbol, search_paths=search_paths).to_dict()
        for symbol in symbols
        if str(symbol).strip()
    ]
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for lookup in lookups:
        matches = list(lookup.get("matches", []) or [])
        for match in matches:
            if len(kept) < max_matches:
                kept.append(match)
            else:
                dropped.append({"symbol": match.get("symbol"), "reason": "max_matches_exceeded"})
    ast_statuses = {str(item.get("ast_status") or "UNKNOWN") for item in kept}
    blockers = _context_blockers(lookups, kept, max_matches=max_matches)
    return {
        "schema": CODE_SKELETON_CONTEXT_SCHEMA,
        "status": "PASS" if not blockers else "RETURN",
        "lookup_count": len(lookups),
        "kept_symbol_count": len(kept),
        "dropped_symbol_count": len(dropped),
        "ast_graph_freshness_status": "STALE_FALLBACK" if "LAST_KNOWN_GOOD" in ast_statuses else "FRESH",
        "estimated_tokens": _estimate_tokens(kept),
        "kept_symbols": kept,
        "dropped_symbols": dropped,
        "lookup_receipts": lookups,
        "blockers": blockers,
        "claim_boundary": [
            "Skeleton context is a bounded context source, not a delivery or claim verdict.",
            "Direct full-file reads should be justified by this context seam when possible.",
        ],
    }


def _context_blockers(lookups: list[dict[str, Any]], kept: list[dict[str, Any]], *, max_matches: int) -> list[str]:
    blockers: list[str] = []
    if max_matches <= 0:
        blockers.append("invalid_max_matches")
    if lookups and not kept:
        blockers.append("no_symbols_found")
    return sorted(set(blockers))


def _estimate_tokens(symbols: list[dict[str, Any]]) -> int:
    total = 0
    for symbol in symbols:
        text = " ".join(
            [
                str(symbol.get("symbol") or ""),
                str(symbol.get("signature") or ""),
                " ".join(str(item) for item in symbol.get("rationale_context", []) or []),
            ]
        )
        total += max(1, len(text.split()))
    return total
