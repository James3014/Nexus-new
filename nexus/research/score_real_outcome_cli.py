#!/usr/bin/env python3
"""CLI for the #1216 post-hoc real-outcome scorer.

Implements docs/research/REAL_OUTCOME_SCORER_SPEC.md. Reads a hybrid
replication store read-only and writes create-only receipts to a separate
outcome store. Scores one task at a time and waits while M5 free memory is
below the threshold (Splash is resident on this host).

Examples:
  python -m nexus.research.score_real_outcome_cli --store <copy>/store --out <outcome> --work <scratch>
  python -m nexus.research.score_real_outcome_cli --store ... --out ... --work ... --task KEY --candidate-override gold
  python -m nexus.research.score_real_outcome_cli --out <outcome> --summarize
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nexus.engine.sandboxed_lane import (  # noqa: E402
    DISABLE_OS_SANDBOX_ENVS,
    os_sandbox_available,
)
from nexus.research import real_outcome_scorer as ros  # noqa: E402


def free_memory_percent() -> int | None:
    try:
        out = subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"free percentage:\s*(\d+)%", out)
    return int(m.group(1)) if m else None


class MemoryCheckUnavailable(RuntimeError):
    """memory_pressure kept returning nothing usable; the batch stops instead of scoring
    without the spec §8 free-memory check."""


UNKNOWN_BACKOFF_SECONDS = (60, 120, 240, 300, 300)


def wait_for_memory(
    min_free: int,
    log,
    *,
    probe=None,
    sleep=time.sleep,
    backoff: tuple[int, ...] = UNKNOWN_BACKOFF_SECONDS,
) -> float:
    """Spec §8: wait while free memory < ``min_free`` %, re-checking every 60 s.

    An empty or unparseable ``memory_pressure`` result is treated as low memory, never as
    "enough": the runner waits with a bounded backoff and raises MemoryCheckUnavailable
    after ``len(backoff)`` consecutive unknown readings. ``min_free <= 0`` disables the check.
    """
    if min_free <= 0:
        log("memory_pressure check disabled (--min-free-percent <= 0)")
        return 0.0
    probe = probe or free_memory_percent
    waited = 0.0
    unknown = 0
    while True:
        free = probe()
        if free is None:
            if unknown >= len(backoff):
                log(f"memory_pressure unknown {unknown}x: giving up")
                raise MemoryCheckUnavailable(f"memory_pressure unknown after {waited:.0f}s")
            delay = backoff[unknown]
            unknown += 1
            log(f"memory_pressure free=unknown, treated as low: pausing {delay}s ({unknown})")
            sleep(delay)
            waited += delay
            continue
        unknown = 0
        if free >= min_free:
            log(f"memory_pressure free={free}%")
            return waited
        log(f"memory_pressure free={free}% < {min_free}%: pausing 60s")
        sleep(60)
        waited += 60


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--store", type=Path, help="store dir containing tasks/ (read only)")
    p.add_argument("--out", type=Path, required=True, help="outcome store (create-only)")
    p.add_argument(
        "--work",
        type=Path,
        help=(
            "scorer scratch: repos, trees, envs, cache. One scorer per --work: each task"
            " holds <work>/.scorer.lock, and a second scorer on the same dir stops at once"
            " (exit 6)"
        ),
    )
    p.add_argument("--task", action="append", default=[], help="task key (repeatable)")
    p.add_argument(
        "--candidate-override", default=None, help="self-check only: gold | empty | broken[:path]"
    )
    p.add_argument("--leakage-flags", type=Path, help="JSON {task_key: reason}")
    p.add_argument(
        "--repo-source",
        action="append",
        default=[],
        help="REPO=PATH_OR_URL extra git source (repeatable)",
    )
    p.add_argument("--min-free-percent", type=int, default=20)
    p.add_argument(
        "--min-free-disk-gib",
        type=float,
        default=ros.SCRATCH_MIN_FREE_BYTES / 1024**3,
        help=(
            "--sandbox os only (A11): free GiB the scratch filesystem must keep before"
            " every pytest run, else the batch stops with exit 8 and no receipt"
            " (default: 2x the per-run cap)"
        ),
    )
    p.add_argument("--keep-trees", action="store_true")
    p.add_argument(
        "--sandbox",
        choices=ros.RUNNER_SANDBOX_MODES,
        default=ros.SANDBOX_NONE,
        help=(
            "pytest confinement (amendment A9). none (default): v1 §8 as pre-registered."
            " os: macOS sandbox-exec, no network, writes only to the tree and scratch;"
            " refused (exit 7) when no OS sandbox is available, never run unconfined."
            " Before every os run the scratch disk must keep --min-free-disk-gib free,"
            " else the batch stops with exit 8 and no receipt (infra, A11)"
        ),
    )
    p.add_argument(
        "--spec-version",
        choices=ros.SCORING_SPEC_VERSIONS,
        default=ros.SPEC_V1,
        help=(
            "scoring rules. v1 (default): the pre-registered v1, with the v2 GOLD port"
            " fallback (A5), exactly as before. v3 (opt-in, #2709): adds a metadata-only"
            " dist-info stub for the BASE project to the env (REAL_OUTCOME_SCORER_SPEC.v3.md)"
        ),
    )
    p.add_argument("--dry-run", action="store_true", help="verify seals and list labels only")
    p.add_argument("--summarize", action="store_true", help="print summary of --out receipts")
    return p.parse_args(argv)


def _spec_sha256() -> str:
    return ros.sha256_bytes((ROOT / ros.SPEC_RELATIVE_PATH).read_bytes())


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log = lambda msg: print(msg, flush=True)  # noqa: E731
    if args.summarize:
        receipts = [
            json.loads(p.read_text()) for p in sorted(args.out.glob("tasks/*/real_outcome.json"))
        ]
        print(json.dumps(ros.summarize(receipts), indent=1, sort_keys=True))
        return 0
    if not args.store or not args.work:
        print("--store and --work are required", file=sys.stderr)
        return 2
    if args.sandbox == ros.SANDBOX_OS and not os_sandbox_available():
        print(
            "--sandbox os: no OS sandbox available (macOS sandbox-exec missing, or disabled by"
            f" {' / '.join(DISABLE_OS_SANDBOX_ENVS)}); refusing to score unconfined",
            file=sys.stderr,
        )
        return 7
    tasks_dir = args.store / "tasks"
    keys = args.task or sorted(d.name for d in tasks_dir.iterdir() if (d / "raw.json").exists())
    if args.dry_run:
        rc = 0
        for key in keys:
            try:
                inputs = ros.load_sealed_task(tasks_dir / key)
                gt = ros.load_ground_truth(inputs)
                print(
                    f"{key}: seal OK, candidate_empty={inputs.candidate.empty}, "
                    f"terminal={gt.get('terminal_state') if gt else None}"
                )
            except ros.SealRefused as exc:
                print(f"{key}: REFUSED_SEAL {exc}")
                rc = 3
        return rc
    sources: dict[str, list[str]] = {}
    for item in args.repo_source:
        repo, src = item.split("=", 1)
        sources.setdefault(repo, []).append(src)
    for key in keys:
        owner, repo, _ = ros.parse_task_key(key)
        defaults = [str(Path.home() / "workspace" / repo), f"https://github.com/{owner}/{repo}.git"]
        sources.setdefault(repo, [])
        sources[repo] = sources[repo] + [d for d in defaults if d not in sources[repo]]
    leakage = json.loads(args.leakage_flags.read_text()) if args.leakage_flags else {}
    ctx = ros.ScoreContext(
        work=args.work,
        env_provider=ros.UvEnvProvider(args.work / "envs", log=log, spec_version=args.spec_version),
        runner=ros.PytestRunner(
            args.work / "scratch",
            log=log,
            sandbox=args.sandbox,
            store=args.store,
            min_free_disk_bytes=int(args.min_free_disk_gib * 1024**3),
        ),
        repo_sources=sources,
        spec_sha256=_spec_sha256(),
        spec_v2_sha256=ros.sha256_bytes((ROOT / ros.SPEC_V2_RELATIVE_PATH).read_bytes()),
        leakage_flags=leakage,
        log=log,
        keep_trees=args.keep_trees,
        spec_version=args.spec_version,
        spec_v3_sha256=ros.sha256_bytes((ROOT / ros.SPEC_V3_RELATIVE_PATH).read_bytes())
        if args.spec_version == ros.SPEC_V3
        else None,
    )
    rc = 0
    for key in keys:
        if (args.out / "tasks" / key / "real_outcome.json").exists():
            log(f"{key}: receipt exists, skipped")
            continue
        try:
            waited = wait_for_memory(args.min_free_percent, log)
        except MemoryCheckUnavailable as exc:
            log(f"{key}: MEMORY_CHECK_UNAVAILABLE {exc}; stopping before scoring")
            return 5
        try:
            result = ros.score_task(
                tasks_dir / key, ctx, candidate_override=args.candidate_override
            )
        except ros.SealRefused as exc:
            log(f"{key}: REFUSED_SEAL {exc}")
            rc = 3
            continue
        except ros.ScorerBusy as exc:
            log(f"{key}: SCORER_BUSY {exc}; stopping")
            return 6
        except ros.ScratchInfraAbort as exc:
            # A11: infra, not a label: no receipt; the driver reruns the task.
            log(f"{key}: INFRA_ABORT {exc}; stopping, no receipt written")
            return ros.INFRA_ABORT_EXIT_CODE
        except Exception as exc:  # noqa: BLE001 - one task must not stop the batch
            log(f"{key}: SCORER_ERROR {type(exc).__name__}: {exc}")
            rc = 4
            continue
        result["timing"]["memory_wait_seconds"] = waited
        ros.write_receipt(args.out, result)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
