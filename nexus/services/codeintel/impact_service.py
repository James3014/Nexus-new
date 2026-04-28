from __future__ import annotations

import ast
from pathlib import Path

from nexus.services.codeintel.models import CodeImpactResult


def _module_name(root: Path, path: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imports_for(path: Path) -> set[str]:
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


def _iter_python_files(root: Path) -> list[Path]:
    ignored = {
        ".codex",
        ".git",
        ".mypy_cache",
        ".nexus",
        ".pytest_cache",
        ".venv",
        "__pycache__",
    }
    files: list[Path] = []
    for path in root.rglob("*.py"):
        if ignored.intersection(path.relative_to(root).parts):
            continue
        files.append(path)
    return files


def analyze_impact(root: str | Path, changed_files: list[str]) -> CodeImpactResult:
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
        evidence_paths=existing,
    )
