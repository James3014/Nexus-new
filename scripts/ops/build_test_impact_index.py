#!/usr/bin/env python3
"""Build a lightweight import-based test impact index for Nexus."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_SOURCE_ROOTS = ("nexus", "scripts")
DEFAULT_TEST_ROOTS = ("tests",)
DEFAULT_OUTPUT = ".nexus/test_impact_index.json"


def _normalize_path(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _module_name(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _iter_python_files(root: Path, roots: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for rel_root in roots:
        base = root / rel_root
        if not base.exists():
            continue
        files.extend(
            path
            for path in base.rglob("*.py")
            if "__pycache__" not in path.parts and path.name != "__init__.py"
        )
    return sorted(files)


def _imports_for(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
            for alias in node.names:
                if alias.name != "*":
                    imports.add(f"{node.module}.{alias.name}")
    return imports


def build_index(
    *,
    root: Path,
    source_roots: tuple[str, ...] = DEFAULT_SOURCE_ROOTS,
    test_roots: tuple[str, ...] = DEFAULT_TEST_ROOTS,
) -> dict:
    root = root.resolve()
    source_files = _iter_python_files(root, source_roots)
    test_files = _iter_python_files(root, test_roots)
    modules = {
        module: _normalize_path(path, root)
        for path in source_files
        if (module := _module_name(path, root))
    }
    mappings: dict[str, list[str]] = {}

    for test_file in test_files:
        test_rel = _normalize_path(test_file, root)
        matched_sources: set[str] = set()
        for imported in _imports_for(test_file):
            candidates = [imported]
            parts = imported.split(".")
            candidates.extend(".".join(parts[:idx]) for idx in range(len(parts) - 1, 0, -1))
            for candidate in candidates:
                source_rel = modules.get(candidate)
                if source_rel:
                    matched_sources.add(source_rel)
        for source_rel in sorted(matched_sources):
            mappings.setdefault(source_rel, [])
            if test_rel not in mappings[source_rel]:
                mappings[source_rel].append(test_rel)

    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_roots": list(source_roots),
        "test_roots": list(test_roots),
        "modules": modules,
        "mappings": {key: sorted(value) for key, value in sorted(mappings.items())},
        "stats": {
            "source_files": len(source_files),
            "test_files": len(test_files),
            "mapped_source_files": len(mappings),
        },
    }


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip().strip("/") for part in value.split(",") if part.strip())


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build .nexus/test_impact_index.json from Python imports.")
    parser.add_argument("--root", default=".", help="Project root.")
    parser.add_argument("--source-roots", default=",".join(DEFAULT_SOURCE_ROOTS))
    parser.add_argument("--test-roots", default=",".join(DEFAULT_TEST_ROOTS))
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true", help="Print the generated index.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    root = Path(args.root).resolve()
    payload = build_index(
        root=root,
        source_roots=_split_csv(args.source_roots),
        test_roots=_split_csv(args.test_roots),
    )
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(
            f"Wrote {output} "
            f"({payload['stats']['mapped_source_files']} mapped source files, {payload['stats']['test_files']} tests)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
