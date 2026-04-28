from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nexus.services.codeintel.graph_builder import imports_for, iter_python_files, module_name
from nexus.services.codeintel.models import CodeImpactResult


def _module_name(root: Path, path: Path) -> str:
    return module_name(root, path)


def _imports_for(path: Path) -> set[str]:
    return imports_for(path)


def _iter_python_files(root: Path) -> list[Path]:
    return iter_python_files(root)


def _load_graph(root: Path, index_path: str | Path | None) -> dict[str, Any] | None:
    if not index_path:
        return None
    path = Path(index_path)
    path = path if path.is_absolute() else root / path
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return None
    return payload


def _impact_from_graph(root: Path, graph: dict[str, Any], changed_modules: set[str]) -> tuple[set[str], set[str]]:
    module_paths = {
        str(node.get("id")): str(node.get("path"))
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and node.get("id") and node.get("path")
    }
    impacted_symbols = set(changed_modules)
    impacted_files = {module_paths[module] for module in changed_modules if module in module_paths}
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if target in changed_modules and source in module_paths:
            impacted_symbols.add(source)
            impacted_files.add(module_paths[source])
    return impacted_files, impacted_symbols


def analyze_impact(root: str | Path, changed_files: list[str], *, index_path: str | Path | None = None) -> CodeImpactResult:
    project_root = Path(root).resolve()
    normalized_changed = [str(Path(item)) for item in changed_files if str(item).strip()]
    missing = [item for item in normalized_changed if not (project_root / item).exists()]
    existing = [
        item
        for item in normalized_changed
        if (project_root / item).exists() and not set(Path(item).parts).intersection({".nexus", ".git", ".venv", ".codex"})
    ]

    changed_modules = {
        _module_name(project_root, project_root / item)
        for item in existing
        if item.endswith(".py")
    }
    impacted: set[str] = set(existing)
    impacted_symbols: set[str] = set(changed_modules)
    graph = _load_graph(project_root, index_path)
    if graph and changed_modules:
        graph_impacted, graph_symbols = _impact_from_graph(project_root, graph, changed_modules)
        impacted.update(graph_impacted)
        impacted_symbols.update(graph_symbols)
    else:
        for py_file in _iter_python_files(project_root):
            rel = str(py_file.relative_to(project_root))
            if rel in existing:
                continue
            imports = _imports_for(py_file)
            if any(module == imported or module.startswith(f"{imported}.") or imported.startswith(f"{module}.") for module in imports for imported in changed_modules):
                impacted.add(rel)
                impacted_symbols.add(_module_name(project_root, py_file))

    risk_reason: list[str] = []
    if missing:
        risk_reason.append("missing_changed_files")
    if index_path and graph:
        risk_reason.append("scan_index_used")
    elif index_path:
        risk_reason.append("scan_index_unavailable")
    if len(impacted) > len(existing):
        risk_reason.append("reverse_import_impact")
    if any(item.startswith(("nexus/orchestrator/", "nexus/delivery/", "nexus/contracts/")) for item in impacted):
        risk_reason.append("governance_or_delivery_contract")
    risk_score = min(100, len(impacted) * 10 + len(risk_reason) * 15)

    return CodeImpactResult(
        changed_files=normalized_changed,
        impacted_symbols=sorted(impacted_symbols),
        impacted_files=sorted(impacted),
        risk_score=risk_score,
        risk_reason=risk_reason,
        evidence_paths=[*existing, *([str(Path(index_path))] if index_path and graph else [])],
    )
