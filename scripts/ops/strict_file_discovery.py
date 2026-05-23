from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def strict_glob(root: Path, pattern: str, *, label: str = "file discovery") -> list[Path]:
    matches = sorted(root.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"{label}: glob matched no files: {pattern}")
    return matches


def read_nonempty_json(path: Path, *, label: str = "json manifest") -> dict[str, Any] | list[Any]:
    if not path.exists():
        raise FileNotFoundError(f"{label}: file not found: {path}")
    if path.stat().st_size == 0:
        raise ValueError(f"{label}: empty JSON file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def strict_json_glob(root: Path, pattern: str, *, label: str = "json manifest") -> list[dict[str, Any] | list[Any]]:
    return [read_nonempty_json(path, label=label) for path in strict_glob(root, pattern, label=label)]
