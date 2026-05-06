#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from nexus.contracts.s2t_export import export_agent_lightning_preferences, redact_s2t_event
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


def export_s2t_trace_file(input_path: Path, output_path: Path, *, dry_run: bool = False) -> dict[str, Any]:
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
    export = export_agent_lightning_preferences(events)
    redacted_rows = [redact_s2t_event(event) for event in events]
    payload = {
        **export,
        "source": str(input_path),
        "redacted_source_rows": redacted_rows,
    }
    summary = {
        "passed": True,
        "dry_run": dry_run,
        "source": str(input_path),
        "output": str(output_path),
        "source_rows": len(events),
        "preference_pairs": export["pair_count"],
    }
    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export S2T trace JSONL to Agent Lightning preference JSON.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        summary = export_s2t_trace_file(args.input, args.output, dry_run=args.dry_run)
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
