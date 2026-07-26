"""Detached worker entrypoint for one durable self-hosted task attempt."""

from __future__ import annotations

import argparse

from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--attempt-id", required=True)
    args = parser.parse_args()
    service = SelfHostedTaskService(
        state_dir=args.state_dir,
        auto_reconcile=False,
    )
    if not service._wait_for_owner(args.task_id, args.attempt_id, __import__("os").getpid()):
        return 2
    service._run_owned_task(args.task_id, args.attempt_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
