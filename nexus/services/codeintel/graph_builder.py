from __future__ import annotations

import ast
import bisect
import json
import os
import warnings
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
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in IGNORED_DIRS)
        base = Path(dirpath)
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                files.append(base / filename)
    return sorted(files)


def module_name(root: Path, path: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def imports_for(path: Path) -> set[str]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def matching_modules(imported: str, module_names: list[str], module_set: set[str] | None = None) -> list[str]:
    module_set = module_set if module_set is not None else set(module_names)
    matched: set[str] = set()
    if imported in module_set:
        matched.add(imported)

    prefix = f"{imported}."
    start = bisect.bisect_left(module_names, prefix)
    for module in module_names[start:]:
        if not module.startswith(prefix):
            break
        matched.add(module)

    parts = imported.split(".")
    for index in range(len(parts) - 1, 0, -1):
        ancestor = ".".join(parts[:index])
        if ancestor in module_set:
            matched.add(ancestor)

    if len(matched) > 1:
        max_depth = max(module.count(".") for module in matched)
        matched = {module for module in matched if module.count(".") == max_depth}
    return sorted(matched)


def build_graph(root: str | Path, cache_data: dict[str, Any] | None = None) -> dict[str, Any]:
    project_root = Path(root).resolve()
    python_files = iter_python_files(project_root)
    modules = {module_name(project_root, path): str(path.relative_to(project_root)) for path in python_files}
    nodes = [
        {"id": module, "type": "python_module", "path": path}
        for module, path in sorted(modules.items())
    ]
    edges: list[dict[str, str]] = []
    module_names = sorted(modules)
    module_set = set(module_names)
    
    # Incremental AST cache structures
    new_mtimes: dict[str, float] = {}
    new_imports: dict[str, list[str]] = {}
    
    cached_mtimes = (cache_data.get("meta", {}) or {}).get("mtimes", {}) if cache_data else {}
    cached_imports = (cache_data.get("meta", {}) or {}).get("imports", {}) if cache_data else {}
    
    for path in python_files:
        rel_path = str(path.relative_to(project_root))
        source = module_name(project_root, path)
        try:
            current_mtime = path.stat().st_mtime
        except Exception:
            current_mtime = 0.0
            
        new_mtimes[rel_path] = current_mtime
        
        # Check cache hit using mtime and existence in cache
        if rel_path in cached_mtimes and cached_mtimes[rel_path] == current_mtime and rel_path in cached_imports:
            imports = set(cached_imports[rel_path])
        else:
            imports = imports_for(path)
            
        new_imports[rel_path] = sorted(imports)
        
        for imported in sorted(imports):
            for target in matching_modules(imported, module_names, module_set):
                if target != source:
                    edges.append({"from": source, "to": target, "type": "imports"})
                    
    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "mtimes": new_mtimes,
            "imports": new_imports
        }
    }


def scan_codebase(root: str | Path, *, index_path: str | Path | None = None) -> CodeScanResult:
    project_root = Path(root).resolve()
    out_path = Path(index_path) if index_path else project_root / ".nexus" / "reports" / "codeintel" / "code_graph.json"
    out_path = out_path if out_path.is_absolute() else project_root / out_path
    
    cache_data = None
    if out_path.exists():
        try:
            cache_data = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            cache_data = None
            
    graph = build_graph(project_root, cache_data=cache_data)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return CodeScanResult(
        nodes_count=len(graph["nodes"]),
        edges_count=len(graph["edges"]),
        languages=["python"] if graph["nodes"] else [],
        index_path=str(out_path),
        generated_at=datetime.now(UTC).isoformat(),
    )

