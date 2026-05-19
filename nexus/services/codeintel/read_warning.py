from __future__ import annotations

from pathlib import Path
from typing import Any


DEFAULT_LARGE_READ_LINE_THRESHOLD = 400


def build_large_read_warning_receipt(
    *,
    file_path: str | Path,
    skeleton_lookup_receipt: dict[str, Any] | None = None,
    line_threshold: int = DEFAULT_LARGE_READ_LINE_THRESHOLD,
) -> dict[str, Any]:
    path = Path(file_path)
    line_count = _line_count(path)
    skeleton_found = bool((skeleton_lookup_receipt or {}).get("found", False))
    warning = bool(line_count > line_threshold and not skeleton_found)
    return {
        "schema": "nexus.codeintel.large_read_warning.v1",
        "status": "WARN" if warning else "PASS",
        "file_path": str(path),
        "line_count": line_count,
        "line_threshold": int(line_threshold),
        "skeleton_lookup_present": bool(skeleton_lookup_receipt),
        "skeleton_lookup_found": skeleton_found,
        "observation_only": True,
        "warning_code": "large_read_without_skeleton_lookup" if warning else "",
        "claim_boundary": [
            "This receipt is observation-only.",
            "It must not block small-file reads or normal development flow.",
            "It only flags large direct reads that lack a prior skeleton lookup receipt.",
        ],
    }


def _line_count(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0
