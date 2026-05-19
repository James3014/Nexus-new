#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_inventory_roots import apply_cleanup_plan, build_cleanup_apply_plan


DEFAULT_INVENTORY = Path("docs/reports/NEXUS_SF_FULL_SKILL_INVENTORY_2026-05-18.json")
DEFAULT_DEDUP = Path("docs/reports/NEXUS_SF_SKILL_IDENTITY_DEDUP_2026-05-18.json")
DEFAULT_PLAN = Path("docs/reports/NEXUS_SF_SKILL_CLEANUP_APPLY_PLAN_2026-05-18.json")
DEFAULT_RESULT = Path("docs/reports/NEXUS_SF_SKILL_CLEANUP_APPLY_RESULT_2026-05-18.json")
DEFAULT_QUARANTINE_ROOT = Path(".agents/skills/.duplicates-quarantine")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply SF safe duplicate cleanup plan.")
    parser.add_argument("--inventory", default=str(DEFAULT_INVENTORY))
    parser.add_argument("--dedup", default=str(DEFAULT_DEDUP))
    parser.add_argument("--plan-output", default=str(DEFAULT_PLAN))
    parser.add_argument("--result-output", default=str(DEFAULT_RESULT))
    parser.add_argument("--quarantine-root", default=str(DEFAULT_QUARANTINE_ROOT))
    parser.add_argument("--mode", choices=("dry-run", "quarantine"), default="dry-run")
    args = parser.parse_args(argv)

    inventory = _read(Path(args.inventory))
    dedup = _read(Path(args.dedup))
    plan = build_cleanup_apply_plan(
        inventory=inventory,
        dedup_report=dedup,
        quarantine_root=args.quarantine_root,
    )
    result = apply_cleanup_plan(plan, mode=args.mode)

    _write(Path(args.plan_output), plan)
    _write(Path(args.result_output), result)

    print(
        json.dumps(
            {
                "status": result["status"],
                "mode": result["summary"]["mode"],
                "planned_quarantine_count": plan["summary"]["planned_quarantine_count"],
                "result_count": result["summary"]["result_count"],
                "status_counts": result["summary"]["status_counts"],
                "blocker_count": result["summary"]["blocker_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

