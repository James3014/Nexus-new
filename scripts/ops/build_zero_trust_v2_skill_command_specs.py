#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json
from nexus.learning.zero_trust_v2_skill_gate import build_skill_command_spec


DEFAULT_BACKLOG = Path("docs/reports/NEXUS_ZERO_TRUST_V2_CURATION_BACKLOG_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_SKILL_COMMAND_SPECS_2026-05-21.json")


def build_zero_trust_v2_skill_command_specs(*, backlog: dict, priority: str = "P0") -> dict:
    source_items = [item for item in backlog.get("items", []) or [] if isinstance(item, dict)]
    items = [item for item in source_items if not priority or item.get("priority") == priority]
    specs = [build_skill_command_spec(item) for item in items]
    status_counts = Counter(spec["source_review"]["status"] for spec in specs)
    return {
        "schema": "nexus.zero_trust_v2.skill_command_specs.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_backlog": str(DEFAULT_BACKLOG),
        "summary": {
            "source_candidate_count": len(source_items),
            "selected_priority": priority or "ALL",
            "selected_candidate_count": len(items),
            "command_ready_count": sum(1 for spec in specs if spec["command"]),
            "blocked_count": sum(1 for spec in specs if not spec["command"]),
            "source_review_status_counts": dict(sorted(status_counts.items())),
            "runtime_mutation_allowed": False,
            "public_benchmark_allowed": False,
        },
        "specs": specs,
        "claim_boundary": [
            "Command specs materialize SKILL.md into a per-arm sandbox workspace.",
            "Source review pass permits sandbox inspection only; behavior promotion still requires physical V2 evidence.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 skill command specs.")
    parser.add_argument("--backlog", default=str(DEFAULT_BACKLOG))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--priority", default="P0")
    args = parser.parse_args(argv)
    result = build_zero_trust_v2_skill_command_specs(backlog=read_json(args.backlog), priority=args.priority)
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
