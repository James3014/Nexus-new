"""Shared runner plumbing and the interleaved schedule for #2721.

* ``add_common_args`` / ``prepare``: what every runner (BARE, NOOP, NEXUS)
  takes and does before the first row: the Gateway env (whitelisted), the
  READ_ROOTS check, and the pre-run task exclusions (``preflight``), written
  to ``<run-root>/preflight.json`` so every arm excludes the same tasks.
* ``build_schedule``: the three arms (BARE, NEXUS, NOOP) x tasks x repeats in
  ONE seeded random order (default seed 20261020), so neither arm runs in a
  systematically earlier or later slot (time of day, API load, cache warmth).
  The seed and the order are recorded in ``<run-root>/schedule.json``.
* ``main``: runs a schedule in-process with the BARE provider and the NEXUS
  driver built from the same arguments as the single-arm runners.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.bench.measure_2721.common import write_json

DEFAULT_SEED = 20261020
SCHEDULE_SCHEMA = "nexus.measure_2721.schedule.v1"
ARMS = ("BARE", "NEXUS", "NOOP")


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--repeats", type=int, nargs="+", default=[1])
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--key-file", default=os.path.expanduser("~/.config/nexus-measure-2721/anthropic.env"),
                        help="0600 KEY=value file with ANTHROPIC_API_KEY (read only by the adapter)")
    parser.add_argument("--budget-usd", type=float, default=60.0, help="hard stop for the whole measurement")
    parser.add_argument("--max-row-usd", type=float, default=3.0,
                        help="conservative charge per attempt whose cost was never reported (stored in the ledger)")
    parser.add_argument("--spend-ledger", required=True,
                        help="the ONE ledger file every arm of the measurement shares (cap stored in it)")
    parser.add_argument("--gateway-env", required=True,
                        help="the Gateway's env file (assignments only, never executed); required for every arm")


class PrepareStop(RuntimeError):
    def __init__(self, code: int, payload: Mapping[str, Any]):
        super().__init__(json.dumps(payload))
        self.code = code
        self.payload = dict(payload)


def prepare(args: argparse.Namespace, *, need_read_roots: bool) -> list[dict[str, Any]]:
    """Load the Gateway env, check READ_ROOTS and return the tasks every arm measures."""
    from scripts.bench.measure_2721 import preflight
    from scripts.bench.measure_2721.arms import load_manifest
    from scripts.bench.measure_2721.gateway_env import (
        GatewayEnvError,
        require_read_roots,
        use_gateway_env,
    )

    try:
        use_gateway_env(args.gateway_env)
    except GatewayEnvError as exc:
        raise PrepareStop(2, {"stopped": "GATEWAY_ENV_REFUSED", "detail": str(exc)}) from exc
    if need_read_roots:
        try:
            require_read_roots()
        except GatewayEnvError as exc:
            raise PrepareStop(2, {"stopped": "READ_ROOTS_EMPTY", "detail": str(exc)}) from exc
    measured, excluded = preflight.split(load_manifest(args.manifest, args.ids))
    run_root = Path(args.run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    # The exclusion is a pure function of the manifest, identical for every arm.
    write_json(run_root / "preflight.json", {"manifest": str(args.manifest),
                                             "measured": [t["task_id"] for t in measured], "excluded": excluded})
    return measured


def build_schedule(task_ids: Sequence[str], repeats: Sequence[int], arms: Sequence[str] = ARMS,
                   seed: int = DEFAULT_SEED) -> list[dict[str, Any]]:
    entries = [{"arm": arm, "task_id": task_id, "repeat": repeat}
               for task_id in task_ids for repeat in repeats for arm in arms]
    random.Random(seed).shuffle(entries)
    return [{"slot": index, **entry} for index, entry in enumerate(entries)]


def write_schedule(run_root: Path, schedule: Sequence[Mapping[str, Any]], seed: int) -> dict[str, Any]:
    body = json.dumps(list(schedule), sort_keys=True)
    record = {"schema": SCHEDULE_SCHEMA, "seed": seed, "entries": list(schedule),
              "order_sha256": hashlib.sha256(body.encode()).hexdigest()}
    write_json(Path(run_root) / "schedule.json", record)
    return record


def main(argv: Sequence[str] | None = None) -> int:
    from scripts.bench.measure_2721 import arms as arms_module
    from scripts.bench.measure_2721 import nexus_driver
    from scripts.bench.measure_2721.budget import BudgetExhausted, SpendLedger

    parser = argparse.ArgumentParser(description="Run BARE, NEXUS and NOOP rows of #2721 in one seeded order")
    add_common_args(parser)
    nexus_driver.add_gateway_args(parser)
    parser.add_argument("--arms", nargs="+", choices=list(ARMS), default=list(ARMS))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--provider", choices=["claude", "fake"], default="fake")
    parser.add_argument("--claude-bin")
    args = parser.parse_args(argv)
    try:
        tasks = prepare(args, need_read_roots=args.provider == "claude" or "NEXUS" in args.arms)
    except PrepareStop as stop:
        print(json.dumps(stop.payload))
        return stop.code
    run_root = Path(args.run_root)
    by_id = {task["task_id"]: task for task in tasks}
    schedule = build_schedule(list(by_id), args.repeats, args.arms, args.seed)
    write_schedule(run_root, schedule, args.seed)
    ledger = SpendLedger(Path(args.spend_ledger), args.budget_usd, args.max_row_usd)
    provider = arms_module.build_provider(args.provider, claude_bin=args.claude_bin,
                                          trace_dir=run_root / "traces", key_file=args.key_file) \
        if "BARE" in args.arms else None
    driver = None
    if "NEXUS" in args.arms:
        try:
            driver = nexus_driver.build_driver(args, parser)
        except nexus_driver.DriverStartRefused as exc:
            print(json.dumps({"stopped": "DRIVER_REFUSED", "detail": str(exc)}))
            return 2
    rows = []
    try:
        for entry in schedule:
            task = by_id[entry["task_id"]]
            if entry["arm"] == "BARE":
                row = arms_module.run_bare(task, entry["repeat"], run_root, provider, timeout_seconds=args.timeout,
                                           ledger=ledger)
            elif entry["arm"] == "NEXUS":
                row = driver.run(task, entry["repeat"], run_root, timeout_seconds=args.timeout, ledger=ledger)
            else:
                row = arms_module.run_noop(task, entry["repeat"], run_root)
            rows.append({"slot": entry["slot"], "arm": entry["arm"], "run_id": row.get("run_id")})
    except BudgetExhausted as exc:
        print(json.dumps({"stopped": str(exc), "rows": len(rows)}))
        return 75
    except nexus_driver.GatewayStuck as exc:
        print(json.dumps({"stopped": "GATEWAY_STUCK", "detail": str(exc), "rows": len(rows)}))
        return 75
    write_json(run_root / "schedule_done.json", {"seed": args.seed, "rows": rows})
    print(json.dumps({"rows": len(rows), "seed": args.seed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
