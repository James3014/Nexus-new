from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus.contracts.s2t_export import write_model_training_export_v3
from nexus.contracts.s2t_trace import S2TTraceEvent


def write_auto_flow_model_training_export(
    *,
    repo_root: Path,
    receipt_slug: str,
    s2t_trace: dict[str, Any],
    experiences: list[Any],
    quality_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    event = s2t_trace.get("event") if isinstance(s2t_trace, dict) else None
    if not event:
        return {}
    training_export_path = Path(".nexus") / "exports" / "model_training" / f"{receipt_slug}.json"
    training_export = write_model_training_export_v3(
        repo_root / training_export_path,
        [S2TTraceEvent.from_dict(event)],
        experiences=experiences,
        quality_rows=quality_rows,
    )
    return {
        "schema_version": training_export["schema_version"],
        "path": str(training_export_path),
        **training_export["summary"],
    }
