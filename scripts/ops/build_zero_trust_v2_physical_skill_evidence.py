#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json
from nexus.learning.zero_trust_v2_physical_runner import run_zero_trust_v2_physical_rows


DEFAULT_REPLAY_MATRIX = Path("docs/reports/NEXUS_ZERO_TRUST_V2_REPLAY_MATRIX_2026-05-21.json")
DEFAULT_COMMAND_SPECS = Path("docs/reports/NEXUS_ZERO_TRUST_V2_SKILL_COMMAND_SPECS_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_PHYSICAL_SKILL_EVIDENCE_2026-05-21.json")


def _key(capability_id: str, skill_id: str) -> tuple[str, str]:
    return (capability_id, skill_id)


def _baseline_command() -> list[str]:
    return ["python3", "-c", "print('nexus-zero-trust-v2-clean-baseline')"]


def build_zero_trust_v2_physical_skill_evidence(
    *,
    replay_matrix: dict,
    command_specs: dict,
    signing_secret: str,
    allow_promotion_credit: bool = False,
) -> dict:
    specs_by_key = {
        _key(str(spec.get("capability_id") or ""), str(spec.get("skill_id") or "")): spec
        for spec in command_specs.get("specs", []) or []
        if isinstance(spec, dict) and spec.get("command")
    }
    selected_rows = [
        row
        for row in replay_matrix.get("rows", []) or []
        if isinstance(row, dict)
        and row.get("arm_type") in {"capability_only_v2", "candidate_skill_v2", "wrong_or_quarantined_skill_v2", "shadow_candidate_v2"}
        and _key(str(row.get("capability_id") or ""), str(row.get("source_skill_id") or row.get("skill_id") or "")) in specs_by_key
    ]
    workspace_files_by_key: dict[tuple[str, str], dict[str, str]] = {}
    command_by_key: dict[tuple[str, str], list[str]] = {}
    for key, spec in specs_by_key.items():
        source_path = Path(spec["source_review"]["skill_path"])
        workspace_files_by_key[key] = {"SKILL.md": source_path.read_text(encoding="utf-8", errors="replace")}
        command_by_key[key] = list(spec["command"])

    executed_rows = []
    run_id = f"ztv2-skill-evidence-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    for key, command in command_by_key.items():
        rows_for_skill = [row for row in selected_rows if _key(str(row.get("capability_id") or ""), str(row.get("source_skill_id") or row.get("skill_id") or "")) == key]
        executed_rows.extend(
            run_zero_trust_v2_physical_rows(
                rows_for_skill,
                command=command,
                signing_secret=signing_secret,
                run_id=run_id,
                promotion_credit_allowed=allow_promotion_credit,
                workspace_files_by_key={key: workspace_files_by_key[key]},
                baseline_command=_baseline_command(),
            )
        )

    execution_counts = Counter(str(row.get("execution_status") or "UNKNOWN") for row in executed_rows)
    ready_count = sum(
        1
        for row in executed_rows
        if isinstance(row.get("promotion_evaluation"), dict)
        and row["promotion_evaluation"].get("status") == "READY_FOR_MANUAL_APPLY"
    )
    return {
        "schema": "nexus.zero_trust_v2.physical_skill_evidence.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_replay_matrix": str(DEFAULT_REPLAY_MATRIX),
        "source_command_specs": str(DEFAULT_COMMAND_SPECS),
        "summary": {
            "command_ready_count": len(specs_by_key),
            "executed_row_count": len(executed_rows),
            "ready_for_manual_apply_count": ready_count,
            "execution_status_counts": dict(sorted(execution_counts.items())),
            "promotion_credit_allowed": allow_promotion_credit,
            "materialization_only": True,
            "runtime_mutation_allowed": False,
            "automatic_apply_allowed": False,
            "public_benchmark_allowed": False,
        },
        "rows": executed_rows,
        "claim_boundary": [
            "This artifact validates physical sandbox execution of materialized SKILL.md assets.",
            "It is materialization-only until a real capability runner executes the skill behavior.",
            "Materialization-only rows must not be used for runtime default promotion.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 physical skill evidence.")
    parser.add_argument("--replay-matrix", default=str(DEFAULT_REPLAY_MATRIX))
    parser.add_argument("--command-specs", default=str(DEFAULT_COMMAND_SPECS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--allow-promotion-credit", action="store_true")
    args = parser.parse_args(argv)
    result = build_zero_trust_v2_physical_skill_evidence(
        replay_matrix=read_json(args.replay_matrix),
        command_specs=read_json(args.command_specs),
        signing_secret=os.environ.get("NEXUS_V2_RUNNER_SIGNING_SECRET", "local-nonproduction-v2-skill-evidence"),
        allow_promotion_credit=args.allow_promotion_credit,
    )
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
