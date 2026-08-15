#!/usr/bin/env python3
"""Nexus cumulative model-calibration plan CLI.

Read-only calibration tooling.  This script derives minimum-requalification
plans (or reads calibration evidence) from
``nexus/config/model_capability_lineage.yaml``.  It never:

* calls a provider;
* writes files or runtime state;
* grants Workforce Admission;
* selects a route or changes model_workforce.yaml.

The three-arm benchmark (``scripts/bench/experimental/model_workforce_three_arm.py``)
remains the baseline/comparative diagnostic instrument.  This planner is the
cumulative requalification path: still-valid lower-tier semantic evidence is
reused instead of restarting from L1.  Individual physical model trials keep
using ``nexus_model_probe`` / ``nexus_model_probe_result`` or existing bounded
execution paths.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.services.model_capability_lineage import (  # noqa: E402
    CHANGE_KIND_VALUES,
    CalibrationPlanner,
    LineageResolutionError,
    LineageValidationError,
    ModelCapabilityLineageRegistry,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Nexus cumulative model-calibration planner (read-only)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="derive a minimum-requalification plan")
    plan.add_argument("--provider", default="")
    plan.add_argument("--model", default="")
    plan.add_argument("--lineage-id", default="")
    plan.add_argument("--target-role", required=True)
    plan.add_argument("--change-kind", choices=CHANGE_KIND_VALUES, default=None)
    plan.add_argument("--description", default="")
    plan.add_argument(
        "--registry", default=str(REPO_ROOT / "nexus/config/model_capability_lineage.yaml")
    )

    evidence = subparsers.add_parser("evidence", help="read calibration evidence for one lineage")
    evidence.add_argument("--provider", default="")
    evidence.add_argument("--model", default="")
    evidence.add_argument("--lineage-id", default="")
    evidence.add_argument(
        "--registry", default=str(REPO_ROOT / "nexus/config/model_capability_lineage.yaml")
    )
    return parser


def _validate_identity(args: argparse.Namespace) -> tuple[str, str]:
    provider = str(args.provider or "").strip()
    model = str(args.model or "").strip()
    if provider and model:
        return provider, model
    if getattr(args, "lineage_id", None):
        return "", ""
    raise SystemExit(
        "error: --provider and --model are required (exact registered identity) or --lineage-id"
    )


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    registry = ModelCapabilityLineageRegistry(args.registry)
    planner = CalibrationPlanner(registry)

    try:
        if args.command == "evidence":
            if getattr(args, "lineage_id", None):
                bundle = planner.evidence_bundle(lineage_id=args.lineage_id)
            else:
                provider, model = _validate_identity(args)
                bundle = planner.evidence_bundle(provider=provider, model=model)
            _emit(bundle)
            return 0

        if getattr(args, "lineage_id", None):
            lineage = registry.resolve_by_lineage_id(args.lineage_id)
            plan = planner.build_calibration_plan(
                provider=lineage.execution_identities[0].provider,
                model=lineage.execution_identities[0].model,
                target_role=args.target_role,
                change_kind=args.change_kind,
                description=args.description,
            )
        else:
            provider, model = _validate_identity(args)
            plan = planner.build_calibration_plan(
                provider=provider,
                model=model,
                target_role=args.target_role,
                change_kind=args.change_kind,
                description=args.description,
            )
        _emit(plan.to_dict())
        return 0
    except (LineageResolutionError, LineageValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _emit(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, sort_keys=True, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
