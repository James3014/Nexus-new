"""Shared runner plumbing and the interleaved schedule for #2721.

* ``add_common_args`` / ``prepare``: what every runner (BARE, NOOP, NEXUS)
  takes and does before the first row: the Gateway env (whitelisted), the
  READ_ROOTS check, and the pre-run task exclusions (``preflight``), written
  to ``<run-root>/preflight.json`` so every arm excludes the same tasks.
* ``build_schedule``: block randomization (``block_randomized_v1``).  Every
  (task, repeat) is one block in which all arms run back to back in a seeded
  random order, and the blocks themselves are shuffled with the same seeded
  RNG (default seed 20261020).  Every arm thus gets one slot in every block,
  so no arm runs in a systematically earlier or later slot (time of day, API
  load, cache warmth): the per-arm mean slots differ by less than one block.
  A single global shuffle (the earlier scheme) let BARE take 20 of the first
  36 slots and NEXUS 10.  Seed, scheme and order are recorded in
  ``<run-root>/schedule.json``.
* Formal runs go through ``main`` here only; the single-arm entrypoints
  (``arms.main``, ``nexus_driver.main``) refuse a paid run unless
  ``--single-arm-debug`` is given.
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
from typing import Any, Mapping, Optional, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.bench.measure_2721.common import write_json

DEFAULT_SEED = 20261020
SCHEDULE_SCHEMA = "nexus.measure_2721.schedule.v1"
SCHEDULE_SCHEME = "block_randomized_v1"
ARMS = ("BARE", "NEXUS", "NOOP")
SINGLE_ARM_FLAG = "--single-arm-debug"
SINGLE_ARM_REFUSED = "SINGLE_ARM_FORMAL_RUN_REFUSED"


def add_single_arm_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        SINGLE_ARM_FLAG,
        dest="single_arm_debug",
        action="store_true",
        help="allow a paid single-arm run outside the block-randomized schedule (debug only; "
        "formal #2721 runs go through runner.py)",
    )


def single_arm_refusal(args: argparse.Namespace, *, paid: bool) -> Optional[dict[str, Any]]:
    """The stop payload when a single-arm entrypoint would make a paid (formal) run, else None.

    Formal rows must come from ``runner.main`` (one block-randomized schedule
    for every arm); a single-arm runner would put all of one arm's rows in one
    stretch of time.  With the explicit debug flag it runs, and says so.
    """
    if not paid:
        return None
    if getattr(args, "single_arm_debug", False):
        print(
            f"WARNING: single-arm paid run ({SINGLE_ARM_FLAG}); its rows are not a formal #2721 schedule",
            file=sys.stderr,
        )
        return None
    return {
        "stopped": SINGLE_ARM_REFUSED,
        "detail": f"formal runs go through scripts/bench/measure_2721/runner.py; pass {SINGLE_ARM_FLAG} "
        "to run one arm on its own for debugging",
    }


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
    """Block-randomized order (``block_randomized_v1``): one block per (task, repeat).

    One ``random.Random(seed)`` first shuffles the blocks, then the arm order
    inside each block (in block order), so the schedule is a pure function of
    the inputs and the seed.
    """
    rng = random.Random(seed)
    blocks = [(task_id, repeat) for task_id in task_ids for repeat in repeats]
    rng.shuffle(blocks)
    entries = []
    for block, (task_id, repeat) in enumerate(blocks):
        order = list(arms)
        rng.shuffle(order)
        entries.extend(
            {"block": block, "arm": arm, "task_id": task_id, "repeat": repeat} for arm in order
        )
    return [{"slot": index, **entry} for index, entry in enumerate(entries)]


def schedule_stats(schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Mean slot per arm and per-arm counts in the first third of the slots."""
    arms = sorted({str(e["arm"]) for e in schedule})
    third = len(schedule) // 3
    return {
        "mean_slot": {
            arm: round(
                sum(e["slot"] for e in schedule if e["arm"] == arm)
                / max(1, sum(1 for e in schedule if e["arm"] == arm)),
                3,
            )
            for arm in arms
        },
        "first_third": {arm: sum(1 for e in schedule[:third] if e["arm"] == arm) for arm in arms},
    }


def write_schedule(run_root: Path, schedule: Sequence[Mapping[str, Any]], seed: int) -> dict[str, Any]:
    body = json.dumps(list(schedule), sort_keys=True)
    block_size = len({str(e["arm"]) for e in schedule})
    record = {
        "schema": SCHEDULE_SCHEMA,
        "scheme": SCHEDULE_SCHEME,
        "seed": seed,
        "block_size": block_size,
        "stats": schedule_stats(schedule),
        "entries": list(schedule),
        "order_sha256": hashlib.sha256(body.encode()).hexdigest(),
    }
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
    except nexus_driver.state_phase.PhaseMarkerMismatch as exc:
        print(
            json.dumps({
                "stopped": "STATE_PHASE_MARKER_MISMATCH",
                "detail": str(exc),
                "rows": len(rows),
            })
        )
        return 2
    write_json(run_root / "schedule_done.json", {"seed": args.seed, "rows": rows})
    print(json.dumps({"rows": len(rows), "seed": args.seed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
