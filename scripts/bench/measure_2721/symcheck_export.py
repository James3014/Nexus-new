"""Export each arm's captured inputs as the JSONL ``lab symcheck`` compares.

Reads ``<run-root>/inputs/*.json`` (written by every arm before its model
call) and writes ``<out>/<ARM>.jsonl``, one object per (task, repeat) keyed
``task_id = "<task>#r<repeat>"``.  Fields that are arm-specific by design
are dropped: the run id (it names the arm), the NEXUS-only Gateway call
arguments, and the arm label itself.  Then::

    lab symcheck --arm BARE=<out>/BARE.jsonl --arm NEXUS=<out>/NEXUS.jsonl --mask BARE --mask NEXUS
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

ARM_SPECIFIC = frozenset({"run_id", "arm", "gateway_worker_args"})
# What the model is given, the projection every arm shares (the dry run's
# local P1 chain records only these for NEXUS).
TASK_FIELDS = ("what", "why", "allowed_files", "verifier_commands", "base_prompt")


def export(run_root: Path, out: Path, *, task_fields_only: bool = False) -> dict[str, int]:
    """``task_fields_only`` keeps just ``TASK_FIELDS`` (to compare with the dry
    run's NEXUS chain records, ``<run-root>/nexus/*.json``, also exported)."""
    per_arm: dict[str, list[dict]] = {}
    for path in sorted((Path(run_root) / "inputs").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        arm = str(record.get("arm"))
        neutral = {k: v for k, v in record.items() if k not in ARM_SPECIFIC}
        if task_fields_only:
            neutral = {k: neutral.get(k) for k in TASK_FIELDS}
        neutral["task_id"] = f"{record['task_id']}#r{record.get('repeat')}"
        per_arm.setdefault(arm, []).append(neutral)
    for path in sorted((Path(run_root) / "nexus").glob("*.json")) if task_fields_only else []:
        if path.name.endswith(".spec.json"):
            continue
        chain = json.loads(path.read_text(encoding="utf-8"))
        spec = json.loads(path.with_name(path.name[:-5] + ".spec.json").read_text(encoding="utf-8"))
        args = chain.get("worker_args") or {}
        record = {k: args.get(k) for k in TASK_FIELDS if k != "base_prompt"}
        record["base_prompt"] = chain.get("base_prompt")
        record["task_id"] = f"{spec['task']['task_id']}#r1"
        per_arm.setdefault("NEXUS", []).append(record)
    out.mkdir(parents=True, exist_ok=True)
    for arm, records in per_arm.items():
        records.sort(key=lambda r: r["task_id"])
        (out / f"{arm}.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records))
    return {arm: len(records) for arm, records in per_arm.items()}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--task-fields-only", action="store_true",
                        help="export only the model-facing task fields, NEXUS from the dry run's chain records")
    args = parser.parse_args(argv)
    print(json.dumps(export(Path(args.run_root), Path(args.out), task_fields_only=args.task_fields_only)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
