from __future__ import annotations

import ast
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nexus.services.codeintel.models import CodeScanResult


IGNORED_DIRS = {
    ".codex",
    ".git",
    ".mypy_cache",
    ".nexus",
    ".pytest_cache",
    ".venv",
    "__pycache__",
}


def iter_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.py"):
        rel_parts = path.relative_to(root).parts
        if IGNORED_DIRS.intersection(rel_parts):
            continue
        files.append(path)
    return sorted(files)


def module_name(root: Path, path: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def imports_for(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def build_graph(root: str | Path) -> dict[str, Any]:
    project_root = Path(root).resolve()
    python_files = iter_python_files(project_root)
    modules = {module_name(project_root, path): str(path.relative_to(project_root)) for path in python_files}
    nodes = [
        {"id": module, "type": "python_module", "path": path}
        for module, path in sorted(modules.items())
    ]
    edges: list[dict[str, str]] = []
    module_names = set(modules)
    for path in python_files:
        source = module_name(project_root, path)
        for imported in sorted(imports_for(path)):
            matched = [
                module
                for module in module_names
                if module == imported or module.startswith(f"{imported}.") or imported.startswith(f"{module}.")
            ]
            if len(matched) > 1:
                max_depth = max(module.count(".") for module in matched)
                matched = [module for module in matched if module.count(".") == max_depth]
            for target in sorted(matched):
                if target != source:
                    edges.append({"from": source, "to": target, "type": "imports"})
    return {"nodes": nodes, "edges": edges}


def scan_codebase(root: str | Path, *, index_path: str | Path | None = None) -> CodeScanResult:
    project_root = Path(root).resolve()
    out_path = Path(index_path) if index_path else project_root / ".nexus" / "reports" / "codeintel" / "code_graph.json"
    out_path = out_path if out_path.is_absolute() else project_root / out_path
    graph = build_graph(project_root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return CodeScanResult(
        nodes_count=len(graph["nodes"]),
        edges_count=len(graph["edges"]),
        languages=["python"] if graph["nodes"] else [],
        index_path=str(out_path),
        generated_at=datetime.now(UTC).isoformat(),
    )
