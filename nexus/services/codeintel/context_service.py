from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nexus.services.codeintel.graph_builder import build_graph
from nexus.services.codeintel.models import CodeContextResult


def _load_graph(root: Path, index_path: str | Path | None = None) -> dict[str, Any]:
    if index_path:
        path = Path(index_path)
        path = path if path.is_absolute() else root / path
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
    return build_graph(root)


def context_for_symbol(
    root: str | Path,
    symbol: str,
    *,
    index_path: str | Path | None = None,
) -> CodeContextResult:
    project_root = Path(root).resolve()
    target = symbol.strip()
    graph = _load_graph(project_root, index_path)
    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    matched_nodes = [
        node
        for node in nodes
        if str(node.get("id", "")) == target or str(node.get("id", "")).endswith(f".{target}")
    ]
    if not target:
        return CodeContextResult(symbol=symbol, found=False, reason="empty_symbol")
    if not matched_nodes:
        return CodeContextResult(symbol=target, found=False, reason="symbol_not_found")

    matched_ids = {str(node.get("id")) for node in matched_nodes}
    callers = sorted({str(edge.get("from")) for edge in edges if str(edge.get("to")) in matched_ids})
    callees = sorted({str(edge.get("to")) for edge in edges if str(edge.get("from")) in matched_ids})
    files = sorted({str(node.get("path")) for node in matched_nodes if node.get("path")})
    related_tests = sorted(
        {
            str(node.get("path"))
            for node in nodes
            if str(node.get("path", "")).startswith("tests/")
            and (
                str(node.get("id")) in callers
                or str(node.get("id")) in callees
                or any(str(node.get("id", "")).endswith(f".test_{part.split('.')[-1]}") for part in matched_ids)
            )
        }
    )
    return CodeContextResult(
        symbol=target,
        callers=callers,
        callees=callees,
        files=files,
        related_tests=related_tests,
        found=True,
    )
