#!/usr/bin/env python3
"""CLI for the #1216 post-hoc real-outcome scorer.

Implements docs/research/REAL_OUTCOME_SCORER_SPEC.md. Reads a hybrid
replication store read-only and writes create-only receipts to a separate
outcome store. Scores one task at a time and waits while M5 free memory is
below the threshold (Splash is resident on this host).

Examples:
  score_real_outcome.py --store <copy>/store --out <outcome> --work <scratch>
  score_real_outcome.py --store ... --out ... --work ... --task KEY --candidate-override gold
  score_real_outcome.py --out <outcome> --summarize
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

from nexus.research import real_outcome_scorer as ros  # noqa: E402


def free_memory_percent() -> int | None:
    try:
        out = subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"free percentage:\s*(\d+)%", out)
    return int(m.group(1)) if m else None


def wait_for_memory(min_free: int, log) -> float:
    waited = 0.0
    while True:
        free = free_memory_percent()
        if free is None or free >= min_free:
            log(f"memory_pressure free={free}%")
            return waited
        log(f"memory_pressure free={free}% < {min_free}%: pausing 60s")
        time.sleep(60)
        waited += 60


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--store", type=Path, help="store dir containing tasks/ (read only)")
    p.add_argument("--out", type=Path, required=True, help="outcome store (create-only)")
    p.add_argument("--work", type=Path, help="scorer scratch: repos, trees, envs, cache")
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
    p.add_argument("--keep-trees", action="store_true")
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
        env_provider=ros.UvEnvProvider(args.work / "envs", log=log),
        runner=ros.PytestRunner(args.work / "scratch", log=log),
        repo_sources=sources,
        spec_sha256=_spec_sha256(),
        leakage_flags=leakage,
        log=log,
        keep_trees=args.keep_trees,
    )
    rc = 0
    for key in keys:
        if (args.out / "tasks" / key / "real_outcome.json").exists():
            log(f"{key}: receipt exists, skipped")
            continue
        waited = wait_for_memory(args.min_free_percent, log)
        try:
            result = ros.score_task(
                tasks_dir / key, ctx, candidate_override=args.candidate_override
            )
        except ros.SealRefused as exc:
            log(f"{key}: REFUSED_SEAL {exc}")
            rc = 3
            continue
        result["timing"]["memory_wait_seconds"] = waited
        ros.write_receipt(args.out, result)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
