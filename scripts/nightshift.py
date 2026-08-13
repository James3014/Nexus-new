#!/usr/bin/env python3
import argparse
from pathlib import Path

from nexus.app.nightshift_runner_service import (
    AutoResearchNightShift,
    _cleanup_stale_swarm_locks,
)


def main():
    parser = argparse.ArgumentParser(description="Nexus Night Shift: Local Autonomous Convergence")
    parser.add_argument(
        "--task", required=True, help="Task description or specific file to optimize"
    )
    parser.add_argument(
        "--target-file", default="", help="Specific file to edit (if different from task name)"
    )
    parser.add_argument(
        "--test-file", default="", help="Specific test file or directory for targeted validation"
    )
    parser.add_argument("--max-rounds", type=int, default=50)
    parser.add_argument("--budget-min", type=int, default=5, help="Time budget in minutes")
    parser.add_argument(
        "--convergence-patience", type=int, default=5, help="Stop if no improvement for N rounds"
    )
    parser.add_argument("--model", default="gemini-3.1-pro-preview")
    parser.add_argument("--fallback-model", default="gemini-3-flash-preview")
    parser.add_argument(
        "--keep-worktree", action="store_true", help="Keep the leased worktree for review"
    )
    parser.add_argument(
        "--cleanup-only", action="store_true", help="Only run janitor to clear stale locks"
    )
    parser.add_argument(
        "--cleanup-ttl", type=int, default=120, help="TTL for swarm locks in minutes"
    )
    parser.add_argument(
        "--project-root",
        default="",
        help="Override project root (used by isolated benchmark fixtures)",
    )

    args = parser.parse_args()
    project_root = (
        Path(args.project_root).resolve()
        if args.project_root
        else Path(__file__).resolve().parent.parent
    )

    if args.cleanup_only:
        _cleanup_stale_swarm_locks(project_root, args.cleanup_ttl)
        return

    runner = AutoResearchNightShift(
        project_root=project_root,
        task=args.task,
        max_rounds=args.max_rounds,
        budget_min=args.budget_min,
        target_file=args.target_file,
        test_file=args.test_file or None,
        convergence_patience=args.convergence_patience,
        model_name=args.model,
        fallback_model_name=args.fallback_model,
        keep_worktree=args.keep_worktree,
        queue_dispatcher=None,
    )
    runner.run()


if __name__ == "__main__":
    main()
