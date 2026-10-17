"""Symbol-bounded excerpts of large Python contract sources for EIA context packs (#2357).

When a mutation-path source does not fit the EIA context budget, the semantic
stage may receive an explicit excerpt instead of the whole file: the module's
import block, an index of its top-level symbols (and class methods) with line
ranges, and the full source of the symbols the issue contract names.  Every
other body is omitted and the excerpt says so in its own text; nothing is cut
mid-symbol.  The caller keeps the whole-file sha256 as the evidence anchor.

Fail-closed: non-``.py`` refs, unparsable source, an empty symbol scope or a
named symbol that does not exist raise ``ExcerptError`` with a reason code.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any, Sequence

EXCERPT_SCHEMA = "eia_source_excerpt.v1"
MAX_EXCERPT_SYMBOLS = 64
SYMBOL_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}(\.[A-Za-z_][A-Za-z0-9_]{0,127})?")


class ExcerptError(ValueError):
    """Excerpt refused; the message is a stable reason code."""


@dataclass(frozen=True)
class _Symbol:
    name: str
    kind: str
    start_line: int
    end_line: int


def _symbol_kind(node: ast.AST) -> str | None:
    if isinstance(node, ast.ClassDef):
        return "class"
    if isinstance(node, ast.AsyncFunctionDef):
        return "async def"
    if isinstance(node, ast.FunctionDef):
        return "def"
    return None


def _assigned_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def _span(node: ast.AST) -> tuple[int, int]:
    start = int(getattr(node, "lineno"))
    for decorator in getattr(node, "decorator_list", []) or []:
        start = min(start, int(decorator.lineno))
    end = int(getattr(node, "end_lineno", None) or getattr(node, "lineno"))
    return start, end


def _index(tree: ast.Module) -> list[_Symbol]:
    symbols: list[_Symbol] = []
    for node in tree.body:
        kind = _symbol_kind(node)
        start, end = _span(node)
        if kind is not None:
            name = getattr(node, "name")
            symbols.append(_Symbol(name, kind, start, end))
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    child_kind = _symbol_kind(child)
                    if child_kind is None:
                        continue
                    c_start, c_end = _span(child)
                    symbols.append(
                        _Symbol(f"{name}.{getattr(child, 'name')}", child_kind, c_start, c_end)
                    )
            continue
        for assigned in _assigned_names(node):
            symbols.append(_Symbol(assigned, "assign", start, end))
    return symbols


def validate_symbol_names(names: Any) -> list[str]:
    """Return the sorted, de-duplicated symbol scope or raise ``ExcerptError``."""
    if not isinstance(names, (list, tuple)) or not names or len(names) > MAX_EXCERPT_SYMBOLS:
        raise ExcerptError("CONTRACT_EXCERPT_SYMBOLS_INVALID")
    result: set[str] = set()
    for name in names:
        if not isinstance(name, str) or not SYMBOL_NAME_RE.fullmatch(name):
            raise ExcerptError("CONTRACT_EXCERPT_SYMBOLS_INVALID")
        result.add(name)
    return sorted(result)


def build_python_excerpt(
    ref: str,
    content: str,
    symbols: Sequence[str],
    *,
    full_file_sha256: str,
) -> tuple[str, dict[str, Any]]:
    """Build the excerpt text and its metadata for one Python source.

    Returns ``(text, metadata)``.  ``metadata`` lists the included slices so a
    reader (or validator) knows exactly which line ranges are present.
    """
    if not ref.endswith(".py"):
        raise ExcerptError("CONTRACT_EXCERPT_UNSUPPORTED_SOURCE")
    if not symbols:
        raise ExcerptError("CONTRACT_EXCERPT_NO_SYMBOL_SCOPE")
    names = validate_symbol_names(list(symbols))
    try:
        tree = ast.parse(content, filename=ref)
    except (SyntaxError, ValueError) as exc:
        raise ExcerptError("CONTRACT_EXCERPT_PARSE_FAILED") from exc
    lines = content.splitlines(keepends=True)
    index = _index(tree)
    by_name: dict[str, _Symbol] = {}
    for symbol in index:
        # A later top-level redefinition wins, as at import time.
        by_name[symbol.name] = symbol
    missing = [name for name in names if name not in by_name]
    if missing:
        raise ExcerptError("CONTRACT_EXCERPT_SYMBOL_NOT_FOUND")

    def _text(start: int, end: int) -> str:
        return "".join(lines[start - 1 : end])

    import_spans = [
        _span(node) for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    selected = sorted({by_name[name] for name in names}, key=lambda s: (s.start_line, s.name))

    parts = [
        "# NEXUS SOURCE EXCERPT — NOT THE WHOLE FILE\n",
        f"# path: {ref}\n",
        f"# full_file_sha256: {full_file_sha256}\n",
        f"# full_file_bytes: {len(content.encode('utf-8'))}\n",
        f"# full_file_lines: {len(lines)}\n",
        "# Included: the import block, the symbol index, and the full source of the\n",
        "# SLICE sections below. Every other body is omitted from this excerpt.\n",
        "## IMPORTS\n",
    ]
    for start, end in import_spans:
        parts.append(f"# lines {start}-{end}\n")
        parts.append(_text(start, end))
    parts.append("## SYMBOL INDEX (name, kind, start-end line)\n")
    for symbol in index:
        parts.append(f"- {symbol.name} | {symbol.kind} | {symbol.start_line}-{symbol.end_line}\n")
    for symbol in selected:
        parts.append(
            f"## SLICE {symbol.name} ({symbol.kind}) lines {symbol.start_line}-{symbol.end_line}\n"
        )
        body = _text(symbol.start_line, symbol.end_line)
        parts.append(body if body.endswith("\n") else body + "\n")
        parts.append(f"## END SLICE {symbol.name}\n")
    metadata = {
        "schema": EXCERPT_SCHEMA,
        "symbols": names,
        "slices": [
            {
                "name": s.name,
                "kind": s.kind,
                "start_line": s.start_line,
                "end_line": s.end_line,
            }
            for s in selected
        ],
        "index_count": len(index),
        "import_spans": [[start, end] for start, end in import_spans],
    }
    return "".join(parts), metadata


__all__ = [
    "EXCERPT_SCHEMA",
    "ExcerptError",
    "MAX_EXCERPT_SYMBOLS",
    "build_python_excerpt",
    "validate_symbol_names",
]
