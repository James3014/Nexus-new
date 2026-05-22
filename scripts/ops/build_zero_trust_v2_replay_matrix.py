#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_BACKLOG = Path("docs/reports/NEXUS_ZERO_TRUST_V2_CURATION_BACKLOG_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_REPLAY_MATRIX_2026-05-21.json")
ARM_TYPES = ("capability_only_v2", "candidate_skill_v2", "wrong_or_quarantined_skill_v2", "shadow_candidate_v2")


def _security_contract() -> dict[str, Any]:
    return {
        "security_contract_version": "v2",
        "promotion_credit_source": "v2_only",
        "requires_sandbox_attestation": True,
        "requires_runtime_signed_receipt": True,
        "requires_clean_slate_isolation": True,
        "requires_trust_mismatch_zero": True,
        "requires_negative_control_block": True,
    }


def _row_for_item(item: Mapping[str, Any], arm_type: str, index: int) -> dict[str, Any]:
    capability = str(item.get("capability_id") or "")
    skill_id = str(item.get("skill_id") or "")
    row = {
        "row_id": f"ztv2-{index:03d}-{capability}-{arm_type}",
        "capability_id": capability,
        "skill_id": skill_id if arm_type != "capability_only_v2" else "",
        "source_skill_id": skill_id,
        "arm_type": arm_type,
        "shadow_output_affects_runtime": False,
        "v1_context_only": True,
        "v1_evidence_count": int(item.get("v1_evidence_count") or 0),
        "v2_evidence_count": 0,
        "risk_flags": list(item.get("risk_flags") or []),
        "required_next_steps": list(item.get("required_next_steps") or []),
        **_security_contract(),
    }
    if arm_type == "wrong_or_quarantined_skill_v2":
        row["expected_status"] = "BLOCKED_BY_POLICY"
    elif arm_type == "capability_only_v2":
        row["expected_status"] = "BASELINE"
    else:
        row["expected_status"] = "DIAGNOSTIC_ONLY_UNTIL_EXECUTED"
    return row


def build_zero_trust_v2_replay_matrix(*, curation_backlog: Mapping[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(curation_backlog.get("items", []) or [], start=1):
        if not isinstance(item, Mapping):
            continue
        for arm_type in ARM_TYPES:
            rows.append(_row_for_item(item, arm_type, index))
    return {
        "schema": "nexus.zero_trust_v2.replay_matrix.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_curation_backlog": str(DEFAULT_BACKLOG),
        "summary": {
            "candidate_count": len(curation_backlog.get("items", []) or []),
            "row_count": len(rows),
            "arms_per_candidate": len(ARM_TYPES),
            "promotion_credit_source": "v2_only",
            "v1_context_only": True,
            "runtime_mutation_allowed": False,
            "public_benchmark_allowed": False,
        },
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 replay matrix from curation backlog.")
    parser.add_argument("--curation-backlog", default=str(DEFAULT_BACKLOG))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_zero_trust_v2_replay_matrix(curation_backlog=read_json(args.curation_backlog))
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
