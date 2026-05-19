from __future__ import annotations

from pathlib import Path


def resolve_report_output(default_output: Path, *, output: Path | None = None, output_dir: Path | None = None) -> Path:
    if output is not None:
        return output
    if output_dir is not None:
        return output_dir / default_output.name
    return default_output
