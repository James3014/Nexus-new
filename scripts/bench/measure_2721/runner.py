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
import shlex
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
ALL_ARMS = ("BARE", "NEXUS", "NOOP", "NEXUS_NOOP")
# Arms whose rows are charged to the ledger (block admission, PREREG v0.9).
CHARGED_ARMS = frozenset({"BARE", "NEXUS", "NEXUS_NOOP"})
# A block with an infra row in any arm is re-run whole up to this many times, then excluded.
MAX_INFRA_RERUNS = 2
RESOLVED = frozenset({"COMPLETE", "EXCLUDED_AFTER_RERUNS"})
PROGRESS_FILE = "progress.jsonl"
BLOCKS_FILE = "blocks.jsonl"
STOP_FILE = "stop.json"
LEDGER_BINDING_FILE = "ledger_binding.json"
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
    parser.add_argument("--budget-usd", "--cap-usd", dest="budget_usd", type=float, default=100.0,
                        help="hard stop for the whole measurement (PREREG v0.9: US$100 actual API spend)")
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
        gate6_switches,
        require_read_roots,
        use_gateway_env,
    )

    gate6_warnings: list[str] = []
    gate6 = gate6_switches(args.gateway_env, warnings=gate6_warnings)
    for name in gate6_warnings:
        print(f"WARNING: GATE 6: {name} is enabled on the measurement Gateway (pending decision)", file=sys.stderr)
    if gate6:
        # GATE 6: no external/local model, judge or committee on the measurement Gateway.
        payload = {"stopped": "GATE6_EXTRA_MODEL_SWITCH", "switches": gate6, "gateway_env": str(args.gateway_env)}
        write_json(Path(args.run_root) / "gate6_refused.json", payload)
        raise PrepareStop(2, payload)
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


def _blocks(schedule: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The schedule as blocks: index, task, repeat and the arm order inside the block."""
    blocks: dict[int, dict[str, Any]] = {}
    for entry in schedule:
        block = blocks.setdefault(int(entry["block"]), {"block": int(entry["block"]), "task_id": entry["task_id"],
                                                         "repeat": entry["repeat"], "arms": [], "slots": []})
        block["arms"].append(entry["arm"])
        block["slots"].append(entry["slot"])
    return [blocks[key] for key in sorted(blocks)]


def _records(path: Path) -> list[dict[str, Any]]:
    """Complete JSON lines.  A torn last line (no newline: a crash mid-write) is ignored --
    that row then counts as missing and its block re-runs whole; a bad complete line
    fails closed."""
    if not path.is_file():
        return []
    complete = path.read_text(encoding="utf-8").split("\n")[:-1]
    return [json.loads(line) for line in complete if line.strip()]


def _finished_row(row: Mapping[str, Any]) -> bool:
    """A row recover() may take as this arm's result: common.classify_row on its facts says
    not infra and not interrupted (re-review #6).  A BARE/NOOP row (no facts): an outcome
    other than INTERRUPTED and ``infra`` false."""
    from scripts.bench.measure_2721.common import classify_row

    if isinstance(row.get("facts"), Mapping):
        verdict = classify_row(row["facts"])
        return not verdict["infra"] and not row["facts"].get("interrupted")
    outcome = row.get("outcome")
    return isinstance(outcome, str) and bool(outcome) and outcome != "INTERRUPTED" and row.get("infra") is False


def _drop_torn_tail(path: Path) -> None:
    """Cut a torn last line before appending again (so it never ends up mid-file)."""
    if path.is_file():
        data = path.read_bytes()
        if data and not data.endswith(b"\n"):
            path.write_bytes(data[: data.rfind(b"\n") + 1])


def _append(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(record), sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def block_outcomes(run_root: Path) -> Optional[dict[str, Any]]:
    """Which rows of a runner run root count (None: not a runner run root).

    Only the final attempt of a resolved block counts (``COMPLETE`` or
    ``EXCLUDED_AFTER_RERUNS``); rows of earlier attempts are ``RERUN_SUPERSEDED``,
    rows of a block that never finished are ``INCOMPLETE_BLOCK`` (blind.py
    drops both, so only complete blocks reach the scorer).
    """
    run_root = Path(run_root)
    progress = [p for p in _records(run_root / PROGRESS_FILE) if "event" not in p]  # done rows only
    if not progress and not (run_root / BLOCKS_FILE).is_file():
        return None
    final: dict[int, dict[str, Any]] = {}
    for record in _records(run_root / BLOCKS_FILE):
        final[int(record["block"])] = record
    counted: set[str] = set()
    dropped: dict[str, str] = {}
    for entry in progress:
        block = final.get(int(entry["block"]))
        if block is not None and block["status"] in RESOLVED and int(entry["attempt"]) == int(block["attempt"]):
            counted.add(entry["run_id"])
        elif block is not None and int(entry["attempt"]) <= int(block["attempt"]):
            dropped[entry["run_id"]] = "RERUN_SUPERSEDED"
        else:
            dropped[entry["run_id"]] = "INCOMPLETE_BLOCK"
    return {"counted": counted, "dropped": dropped}


def _noop_driver(args: argparse.Namespace, nexus_driver: Any) -> Any:
    """The NEXUS_NOOP driver: P1 on a second measurement Gateway whose claude binary is
    the no-model fake (``fake_claude.py`` mode ``noop``), from ``--noop-gateway-args``."""
    from scripts.bench.measure_2721.gateway_env import gate6_switches

    sub = argparse.ArgumentParser(prog="--noop-gateway-args")
    nexus_driver.add_gateway_args(sub)
    sub.add_argument("--gateway-env", required=True)
    noop = sub.parse_args(shlex.split(args.noop_gateway_args or ""))
    if getattr(args, "gateway_url", None) and noop.gateway_url.rstrip("/") == args.gateway_url.rstrip("/"):
        raise nexus_driver.DriverStartRefused("NOOP_GATEWAY_IS_THE_NEXUS_GATEWAY")
    switches = gate6_switches(noop.gateway_env)
    if switches:
        raise nexus_driver.DriverStartRefused(f"GATE6_EXTRA_MODEL_SWITCH (NEXUS_NOOP Gateway): {switches}")
    noop.arm_label = "NEXUS_NOOP"
    noop.key_file = args.key_file
    return nexus_driver.build_driver(noop, sub)


def main(argv: Sequence[str] | None = None) -> int:
    from scripts.bench.measure_2721 import arms as arms_module
    from scripts.bench.measure_2721 import nexus_driver
    from scripts.bench.measure_2721.budget import BudgetExhausted, SpendLedger

    parser = argparse.ArgumentParser(description="Run the #2721 arms in one block-randomized order")
    add_common_args(parser)
    nexus_driver.add_gateway_args(parser)
    parser.add_argument("--arms", nargs="+", choices=list(ALL_ARMS), default=list(ARMS),
                        help="arms in every block; NOOP = no P1 (empty), NEXUS_NOOP = P1 with the fake claude "
                        "on a second Gateway (--noop-gateway-args); which count is PREREG's decision")
    parser.add_argument("--noop-gateway-args",
                        help="NEXUS_NOOP Gateway arguments, e.g. '--gateway-url http://127.0.0.1:18767 "
                        "--token-file F --scope-id S --trace-dir D --gateway-env E ...'")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--provider", choices=["claude", "fake"], default="fake")
    parser.add_argument("--claude-bin")
    args = parser.parse_args(argv)
    if "NEXUS_NOOP" in args.arms and not args.noop_gateway_args:
        parser.error("--arms NEXUS_NOOP needs --noop-gateway-args")
    try:
        tasks = prepare(args, need_read_roots=args.provider == "claude" or "NEXUS" in args.arms
                        or "NEXUS_NOOP" in args.arms)
    except PrepareStop as stop:
        print(json.dumps(stop.payload))
        return stop.code
    run_root = Path(args.run_root)
    by_id = {task["task_id"]: task for task in tasks}
    schedule = build_schedule(list(by_id), args.repeats, args.arms, args.seed)
    previous = run_root / "schedule.json"
    resume = previous.is_file()
    binding_path = run_root / LEDGER_BINDING_FILE
    if resume:
        # The spend ledger is bound to the run: a resume with a new (or missing) ledger
        # would start the US$100 cap from 0 again.
        binding = json.loads(binding_path.read_text(encoding="utf-8")) if binding_path.is_file() else {}
        if not Path(args.spend_ledger).is_file() or \
                binding.get("path") != os.path.realpath(args.spend_ledger):
            print(json.dumps({"stopped": "LEDGER_CHANGED_ON_RESUME", "bound": binding.get("path")}))
            return 2
    if previous.is_file():
        # Exit 75 is resumable only with the same seed, arms and task set (same order).
        old = json.loads(previous.read_text(encoding="utf-8"))
        if old.get("seed") != args.seed or old.get("order_sha256") != hashlib.sha256(json.dumps(schedule, sort_keys=True).encode()).hexdigest():
            print(json.dumps({"stopped": "SCHEDULE_CHANGED_ON_RESUME", "seed": args.seed}))
            return 2
    ledger = SpendLedger(Path(args.spend_ledger), args.budget_usd, args.max_row_usd)
    if resume:
        if binding.get("ledger_id") != ledger.identity():
            print(json.dumps({"stopped": "LEDGER_CHANGED_ON_RESUME", "bound": binding.get("path")}))
            return 2
    else:
        write_schedule(run_root, schedule, args.seed)
        write_json(binding_path, {"path": os.path.realpath(args.spend_ledger), "ledger_id": ledger.identity()})
    provider = arms_module.build_provider(args.provider, claude_bin=args.claude_bin,
                                          trace_dir=run_root / "traces", key_file=args.key_file) \
        if "BARE" in args.arms else None
    drivers: dict[str, Any] = {}
    try:
        if "NEXUS" in args.arms:
            drivers["NEXUS"] = nexus_driver.build_driver(args, parser)
        if "NEXUS_NOOP" in args.arms:
            drivers["NEXUS_NOOP"] = _noop_driver(args, nexus_driver)
    except nexus_driver.DriverStartRefused as exc:
        print(json.dumps({"stopped": "DRIVER_REFUSED", "detail": str(exc)}))
        return 2
    progress, blocks_path = run_root / PROGRESS_FILE, run_root / BLOCKS_FILE
    for path in (progress, blocks_path):
        _drop_torn_tail(path)
    started = [p for p in _records(progress) if p.get("event") == "start"]
    done_progress = [p for p in _records(progress) if "event" not in p]
    last_status = {int(r["block"]): r for r in _records(blocks_path)}
    rows: list[dict[str, Any]] = []
    last_completed = max((b for b, r in last_status.items() if r["status"] in RESOLVED), default=None)

    def stop(code: int, reason: str, **extra: Any) -> int:
        record = {"reason": reason, "last_completed_block": last_completed, "rows_this_session": len(rows),
                  "seed": args.seed, "ledger": {k: v for k, v in ledger.state().items()
                                                if k in ("cap_usd", "spent_usd", "worst_row_usd", "rows")},
                  **extra}
        write_json(run_root / STOP_FILE, record)
        print(json.dumps({"stopped": reason, **{k: v for k, v in record.items() if k != "ledger"}}))
        return code

    from scripts.bench.measure_2721 import watchdog

    def recover(block: Mapping[str, Any], attempt: int) -> None:
        """A started arm without a completion record whose row IS in rows.jsonl (written
        by the row's own ``finally`` before the runner died) is completed from that row
        (re-review #4): only an arm with no row at all is CRASHED."""
        done_arms = {p["arm"] for p in done_progress if int(p["block"]) == block["block"]
                     and int(p["attempt"]) == attempt}
        rows_file = run_root / "rows.jsonl"
        consumed = {p.get("run_id") for p in done_progress}
        for start in [p for p in started if int(p["block"]) == block["block"] and int(p["attempt"]) == attempt
                      and p["arm"] not in done_arms]:
            if not rows_file.is_file() or "rows_offset" not in start:
                continue  # no offset recorded: the row cannot be tied to this start -> CRASHED
            with rows_file.open("rb") as handle:
                handle.seek(int(start.get("rows_offset") or 0))
                tail = handle.read().decode("utf-8", errors="replace")
            for line in tail.split("\n")[:-1]:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("arm") == start["arm"] and row.get("task_id") == block["task_id"] \
                        and row.get("repeat") == block["repeat"] and row.get("run_id") \
                        and row["run_id"] not in consumed and _finished_row(row):
                    entry = {"block": block["block"], "attempt": attempt, "slot": start["slot"], "arm": start["arm"],
                             "run_id": row["run_id"], "infra": bool(row.get("infra")), "recovered_from_rows": True}
                    _append(progress, entry)
                    done_progress.append(entry)
                    break

    def evaluate(block: Mapping[str, Any], attempt: int) -> tuple[list[str], dict[str, Any]]:
        """Arms of this attempt that are infra: an infra row, a row missing from progress
        or rows.jsonl (a crash, a lost Gateway), or one the watchdog listed (re-review B2).
        A block is COMPLETE only when every arm has a written, non-infra row."""
        entries = {p["arm"]: p for p in done_progress if int(p["block"]) == block["block"]
                   and int(p["attempt"]) == attempt}
        written = {r.get("run_id") for r in _records(run_root / "rows.jsonl")}
        why: dict[str, str] = {}
        begun = {p["arm"] for p in started if int(p["block"]) == block["block"] and int(p["attempt"]) == attempt}
        for arm in block["arms"]:
            entry = entries.get(arm)
            if entry is None and arm in begun:
                why[arm] = "CRASHED"  # started, never finished: infra
            elif entry is None or entry.get("run_id") not in written:
                why[arm] = "MISSING"
            elif entry["infra"]:
                why[arm] = "INFRA"
            elif watchdog.infra_event_for(run_root, entry["run_id"]) is not None:
                why[arm] = "WATCHDOG_EVENT"
        run_ids = {arm: entries[arm]["run_id"] for arm in block["arms"] if arm in entries}
        return sorted(why), {"why": why, "run_ids": run_ids}

    def record_attempt(block: Mapping[str, Any], attempt: int) -> str:
        infra_arms, detail = evaluate(block, attempt)
        status = "COMPLETE" if not infra_arms else (
            "RERUN" if attempt < MAX_INFRA_RERUNS else "EXCLUDED_AFTER_RERUNS")
        record = {"block": block["block"], "task_id": block["task_id"], "repeat": block["repeat"],
                  "attempt": attempt, "status": status, "arm_order": block["arms"], "infra_arms": infra_arms,
                  "infra_why": detail["why"], "run_ids": detail["run_ids"]}
        _append(blocks_path, record)
        last_status[block["block"]] = record
        return status

    for block in _blocks(schedule):
        state = last_status.get(block["block"])
        if state is not None and state["status"] == "COMPLETE" and evaluate(block, int(state["attempt"]))[0]:
            # A late watchdog event (or a lost row) on a block recorded COMPLETE: re-run it
            # whole -- or, with no re-run left, exclude it (re-review #3: max 2 re-runs).
            late = evaluate(block, int(state["attempt"]))[1]["why"]
            state = dict(state, status="RERUN" if int(state["attempt"]) < MAX_INFRA_RERUNS
                         else "EXCLUDED_AFTER_RERUNS", late_infra=late)
            _append(blocks_path, state)
            last_status[block["block"]] = state
        if state is not None and state["status"] in RESOLVED:
            continue  # resumed: completed rows are never re-run
        attempt = int(state["attempt"]) + 1 if state is not None else 0
        begun = {p["arm"] for p in started if int(p["block"]) == block["block"] and int(p["attempt"]) == attempt}
        if begun:
            recover(block, attempt)
            # Resume of an interrupted attempt.  An arm that started and never finished
            # (a crash), an infra row or a watchdog event re-runs the WHOLE block, every
            # arm.  Arms never started (the runner stopped on purpose after a non-infra
            # row, e.g. a lost Gateway without a watchdog event) simply run now.
            infra_now = [arm for arm in evaluate(block, attempt)[0] if arm in begun]
            if infra_now:
                if record_attempt(block, attempt) != "RERUN":
                    last_completed = block["block"]
                    continue
                attempt += 1
        task = by_id[block["task_id"]]
        while True:
            done_arms = {p["arm"] for p in done_progress if int(p["block"]) == block["block"]
                         and int(p["attempt"]) == attempt}
            remaining = [arm for arm in block["arms"] if arm not in done_arms]
            try:
                # PREREG v0.9: admit the whole (rest of the) block or start nothing.
                ledger.begin_block(sum(arm in CHARGED_ARMS for arm in remaining))
            except BudgetExhausted as exc:
                return stop(75, "BUDGET_CAP", detail=str(exc), next_block=block["block"])
            admitted = ledger.admitted()
            for arm in remaining:
                slot = block["slots"][block["arms"].index(arm)]
                rows_file = run_root / "rows.jsonl"
                start = {"event": "start", "block": block["block"], "attempt": attempt, "arm": arm, "slot": slot,
                         "rows_offset": rows_file.stat().st_size if rows_file.is_file() else 0}
                _append(progress, start)
                started.append(start)
                try:
                    if arm == "BARE":
                        row = arms_module.run_bare(task, block["repeat"], run_root, provider,
                                                   timeout_seconds=args.timeout, ledger=admitted)
                    elif arm in drivers:
                        row = drivers[arm].run(task, block["repeat"], run_root, timeout_seconds=args.timeout,
                                               ledger=admitted)
                    else:
                        row = arms_module.run_noop(task, block["repeat"], run_root)
                except nexus_driver.GatewayStuck as exc:
                    run_id = drivers[arm]._run_id
                    written = [r for r in _records(run_root / "rows.jsonl") if r.get("run_id") == run_id]
                    entry = {"block": block["block"], "attempt": attempt, "slot": slot, "arm": arm, "run_id": run_id,
                             "infra": bool(written and written[-1].get("infra")), "gateway_stuck": True}
                    _append(progress, entry)
                    return stop(75, "GATEWAY_STUCK", detail=str(exc), block=block["block"])
                except nexus_driver.state_phase.PhaseMarkerMismatch as exc:
                    return stop(2, "STATE_PHASE_MARKER_MISMATCH", detail=str(exc))
                except Exception as exc:  # noqa: BLE001 - any row crash: stop resumable, block re-runs whole
                    return stop(75, "ROW_EXCEPTION", detail=f"{type(exc).__name__}: {str(exc)[:300]}",
                                block=block["block"], arm=arm)
                entry = {"block": block["block"], "attempt": attempt, "slot": slot, "arm": arm,
                         "run_id": row.get("run_id"), "infra": bool(row.get("infra"))}
                _append(progress, entry)
                done_progress.append(entry)
                if arm in drivers and nexus_driver.instance_busy(row):
                    # Busy to the end: stop (resumable) instead of spending on the other arms.
                    return stop(75, "INSTANCE_BUSY", detail=row.get("void_reason"), block=block["block"])
                rows.append({"slot": slot, "arm": arm, "run_id": row.get("run_id"), "attempt": attempt})
            if record_attempt(block, attempt) != "RERUN":
                break
            attempt += 1  # an infra row in any arm: the whole block again, same arm order
        last_completed = block["block"]
    write_json(run_root / "schedule_done.json", {"seed": args.seed, "rows": rows})
    stop(0, "DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
