#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from nexus.contracts.learning_experience import learning_experience_from_dict
from nexus.contracts.s2t_export import export_agent_lightning_preferences, export_model_training_v2, export_model_training_v3, redact_s2t_event
from nexus.contracts.s2t_trace import S2TTraceEvent


def _load_events(path: Path) -> list[S2TTraceEvent]:
    events: list[S2TTraceEvent] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(S2TTraceEvent.from_dict(json.loads(line)))
        except Exception as exc:  # noqa: BLE001 - CLI should preserve source line context.
            raise ValueError(f"invalid S2T trace row {line_number}: {exc}") from exc
    return events


def _load_json_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        raise ValueError(f"manifest_missing:{path}")
    if path.suffix == ".jsonl":
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"invalid manifest row {line_number}: expected object")
            rows.append(row)
        return rows
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "experiences", "quality_rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return [payload]
    return []


def export_s2t_trace_file(
    input_path: Path,
    output_path: Path,
    *,
    dry_run: bool = False,
    export_format: str = "v1",
    experience_manifest: Path | None = None,
    autodata_manifest: Path | None = None,
) -> dict[str, Any]:
    if not input_path.exists():
        return {
            "passed": False,
            "dry_run": dry_run,
            "source": str(input_path),
            "output": str(output_path),
            "error": "input_missing",
            "source_rows": 0,
            "preference_pairs": 0,
        }

    events = _load_events(input_path)
    if export_format in {"v2", "v3"}:
        experiences = (
            [learning_experience_from_dict(row) for row in _load_json_rows(experience_manifest)]
            if experience_manifest
            else None
        )
        quality_rows = _load_json_rows(autodata_manifest) if autodata_manifest else None
        export = (
            export_model_training_v3(events, experiences=experiences, quality_rows=quality_rows)
            if export_format == "v3"
            else export_model_training_v2(events, experiences=experiences, quality_rows=quality_rows)
        )
        payload = {**export, "source": str(input_path)}
        if export_format == "v3":
            preference_pairs = export["summary"]["preference_pair_count"]
        else:
            preference_pairs = export["compat"]["agent_lightning_preferences_v1"]["pair_count"]
    else:
        export = export_agent_lightning_preferences(events)
        redacted_rows = [redact_s2t_event(event) for event in events]
        payload = {
            **export,
            "source": str(input_path),
            "redacted_source_rows": redacted_rows,
        }
        preference_pairs = export["pair_count"]
    summary = {
        "passed": True,
        "dry_run": dry_run,
        "source": str(input_path),
        "output": str(output_path),
        "source_rows": len(events),
        "preference_pairs": preference_pairs,
        "format": export_format,
        "experience_rows": len(payload.get("experience_rows", [])) if export_format == "v2" else len(payload.get("compat", {}).get("v2", {}).get("experience_rows", [])) if export_format == "v3" else 0,
        "autodata_attached": bool(payload.get("quality_gate", {}).get("autodata_attached", False)) if export_format == "v2" else bool(payload.get("compat", {}).get("v2", {}).get("quality_gate", {}).get("autodata_attached", False)) if export_format == "v3" else False,
    }
    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export S2T trace JSONL to Agent Lightning preference JSON.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--format", choices=("v1", "v2", "v3"), default="v1")
    parser.add_argument("--experience-manifest", type=Path)
    parser.add_argument("--autodata-manifest", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        summary = export_s2t_trace_file(
            args.input,
            args.output,
            dry_run=args.dry_run,
            export_format=args.format,
            experience_manifest=args.experience_manifest,
            autodata_manifest=args.autodata_manifest,
        )
    except Exception as exc:  # noqa: BLE001 - command boundary returns structured failure.
        summary = {
            "passed": False,
            "dry_run": args.dry_run,
            "source": str(args.input),
            "output": str(args.output),
            "error": str(exc),
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
