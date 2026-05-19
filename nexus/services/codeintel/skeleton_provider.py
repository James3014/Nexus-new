from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable

from nexus.services.codeintel.models import CodeSkeletonLookupResult, CodeSkeletonSymbol


class PythonCodeSkeletonProvider:
    def __init__(self, root: str | Path, search_paths: Iterable[str | Path] = ()) -> None:
        self.root = Path(root).resolve()
        self.search_paths = tuple(Path(path) for path in search_paths)

    def lookup_implementation(self, symbol_name: str) -> CodeSkeletonLookupResult:
        target = symbol_name.strip()
        if not target:
            return CodeSkeletonLookupResult(symbol=symbol_name, found=False, reason="empty_symbol")
        matches = [
            symbol
            for path in self._python_files()
            for symbol in self._symbols_for_file(path)
            if symbol.symbol == target or symbol.symbol.endswith(f".{target}")
        ]
        if not matches:
            return CodeSkeletonLookupResult(symbol=target, found=False, reason="symbol_not_found")
        return CodeSkeletonLookupResult(symbol=target, found=True, matches=matches)

    def _python_files(self) -> Iterable[Path]:
        roots = self.search_paths or (Path("."),)
        for root in roots:
            search_root = root if root.is_absolute() else self.root / root
            paths = [search_root] if search_root.is_file() else sorted(search_root.rglob("*.py"))
            for path in paths:
                if path.suffix != ".py":
                    continue
                if not path.exists() or _skip_path(path):
                    continue
                yield path

    def _symbols_for_file(self, path: Path) -> list[CodeSkeletonSymbol]:
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError, UnicodeDecodeError):
            return []
        relative = path.relative_to(self.root)
        module = _module_name(relative)
        symbols: list[CodeSkeletonSymbol] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(_symbol(module, node, relative))
            elif isinstance(node, ast.ClassDef):
                symbols.append(_symbol(module, node, relative))
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.append(_symbol(f"{module}.{node.name}", child, relative))
        return symbols


def lookup_implementation(
    root: str | Path,
    symbol_name: str,
    *,
    search_paths: Iterable[str | Path] = (),
) -> CodeSkeletonLookupResult:
    return PythonCodeSkeletonProvider(root, search_paths=search_paths).lookup_implementation(symbol_name)


def _symbol(prefix: str, node: ast.AST, relative: Path) -> CodeSkeletonSymbol:
    name = getattr(node, "name", "")
    kind = "class" if isinstance(node, ast.ClassDef) else "function"
    signature = _signature(node)
    return CodeSkeletonSymbol(
        symbol=f"{prefix}.{name}" if prefix else name,
        file_path=str(relative),
        start_line=int(getattr(node, "lineno", 0) or 0),
        end_line=int(getattr(node, "end_lineno", 0) or getattr(node, "lineno", 0) or 0),
        kind=kind,
        signature=signature,
        docstring_present=bool(ast.get_docstring(node)),
    )


def _signature(node: ast.AST) -> str:
    if isinstance(node, ast.ClassDef):
        bases = [ast.unparse(base) for base in node.bases]
        return f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {node.name}({_args(node.args)})"
    return ""


def _args(args: ast.arguments) -> str:
    rendered: list[str] = []
    rendered.extend(arg.arg for arg in args.posonlyargs)
    rendered.extend(arg.arg for arg in args.args)
    if args.vararg:
        rendered.append(f"*{args.vararg.arg}")
    rendered.extend(arg.arg for arg in args.kwonlyargs)
    if args.kwarg:
        rendered.append(f"**{args.kwarg.arg}")
    return ", ".join(rendered)


def _module_name(path: Path) -> str:
    parts = list(path.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _skip_path(path: Path) -> bool:
    return any(part in {".git", ".venv", "__pycache__", ".nexus-swarm-001"} for part in path.parts)
