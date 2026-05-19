from __future__ import annotations

from pathlib import Path
from re import sub


def resolve_report_output(default_output: Path, *, output: Path | None = None, output_dir: Path | None = None) -> Path:
    if output is not None:
        return output
    if output_dir is not None:
        return output_dir / default_output.name
    return default_output


def resolve_run_report_output(
    default_output: Path,
    *,
    output: Path | None = None,
    output_dir: Path | None = None,
    run_id: str | None = None,
) -> Path:
    if output is not None:
        return output
    if output_dir is None:
        return default_output
    if not run_id:
        return output_dir / default_output.name
    return output_dir / _safe_run_id(run_id) / default_output.name


def _safe_run_id(value: str) -> str:
    safe = sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip(".-")
    return safe or "run"
