"""Bounded swarm / multi-agent run: lock -> worktrees -> worker step -> verify -> integrate.

One call does, in the caller's git workspace:

1. claim the target file in the cross-task ``FileLockRegistry`` (a file held by another task
   blocks the run before anything is created);
2. fork ``BattleSwarm`` worktrees, one per strategy, on ``battle_<task>_*`` branches;
3. run one worker step per worktree: a candidate from the Workforce-admitted local worker through
   the armored local lane (``LocalArmorCandidateGenerator``; model calls are serialized), written
   into the worktree and committed;
4. verify each worktree with the request's verify script (no-shell CLI pre-gate runner);
5. hand the winning commit to ``ControlledIntegrationManager`` (the live integration authority).

Integration needs persisted lifecycle authority (external acceptance bound to the candidate, a
consumed Owner approval grant, a verified receipt). This module never fabricates those, so
without them the manager refuses and the run reports that refusal verbatim. Worktrees and battle
branches are removed afterwards (``git worktree remove``; never ``git worktree prune``); the
candidate commits stay in the object store as evidence.
"""

from __future__ import annotations

import hashlib
import re
import subprocess  # nosec B404 - fixed git argv only
import sys
import threading
from pathlib import Path
from typing import Any

SCHEMA = "nexus.swarm_run.v1"
MAX_WORKERS = 4


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 B607 - fixed git argv
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=60, check=False
    )


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or ""))[:48] or "task"


def run_bounded_swarm(
    *,
    workspace_root: Path,
    task_id: str,
    task: str,
    target_file: str,
    verify_script: str,
    workers: int = 2,
) -> dict[str, Any]:
    from nexus.engine.battle_swarm import BattleSwarm
    from nexus.engine.cli_pregate import run_cli_pregate
    from nexus.orchestrator.file_lock_registry import FileLockRegistry
    from nexus.research.sprint_service import LocalArmorCandidateGenerator

    root = Path(workspace_root).resolve()
    safe_task = _safe(task_id)
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "task_id": safe_task,
        "workspace_root": str(root),
        "target_file": target_file,
        "verify_script": verify_script,
        "lock": {},
        "workers": [],
        "winner": {},
        "integration": {},
        "status": "",
        "reason": "",
    }
    head = _git(["rev-parse", "HEAD"], root)
    if head.returncode != 0:
        report.update(status="BLOCKED", reason="WORKSPACE_NOT_GIT_REPOSITORY")
        return report
    report["base_commit"] = head.stdout.strip()

    lock_file = root / ".nexus" / "multi_agent" / "locks" / "file_locks.json"
    registry = FileLockRegistry(lock_file=str(lock_file))
    conflicts = registry.acquire(safe_task, [target_file])
    report["lock"] = {
        "lock_file": str(lock_file),
        "files": [target_file],
        "conflicts": list(conflicts),
        "held_by_this_task": registry.check_access(safe_task, target_file),
    }
    if conflicts:
        report.update(status="BLOCKED", reason="FILE_LOCK_CONFLICT")
        return report

    model_lock = threading.Lock()

    def execute(
        strategy: dict[str, Any], worktree: str, _tid: str, desc: str, _ctx: dict[str, Any]
    ) -> dict[str, Any]:
        wt = Path(worktree)
        record: dict[str, Any] = {"strategy": strategy["name"], "worktree": str(wt)}
        source = (wt / target_file).read_text(encoding="utf-8")
        generator = LocalArmorCandidateGenerator(
            wt,
            target_file=target_file,
            test_file=None,
            verifier_command=(sys.executable, verify_script),
        )
        try:
            with model_lock:
                code, meta = generator.generate(
                    source_code=source,
                    task=desc,
                    mutation_hint=str(strategy["params"].get("prompt_modifier") or ""),
                    seed=len(strategy["name"]),
                )
        except Exception as exc:  # noqa: BLE001 - the worker failure is the evidence
            meta = dict(getattr(exc, "metadata", {}) or {})
            record.update(
                worker_status="no_candidate",
                worker_error=str(exc)[:200],
                model_calls=int(meta.get("model_calls", 0) or 0),
            )
            return {**record, "passed": False, "score": 0.0}
        record.update(
            worker_status="candidate_written",
            model_calls=int(meta.get("model_calls", 0) or 0),
            model_name=str(meta.get("model_name") or ""),
            local_candidate_hash=str(meta.get("local_candidate_hash") or ""),
        )
        (wt / target_file).write_text(code, encoding="utf-8")
        _git(["add", target_file], wt)
        commit = _git(
            [
                "-c",
                "user.name=nexus-swarm",
                "-c",
                "user.email=nexus-swarm@invalid",
                "commit",
                "-q",
                "--no-verify",
                "-m",
                f"swarm {safe_task} {strategy['name']}",
            ],
            wt,
        )
        if commit.returncode != 0:
            record.update(worker_status="commit_failed", worker_error=(commit.stderr or "")[-200:])
            return {**record, "passed": False, "score": 0.0}
        record["commit"] = _git(["rev-parse", "HEAD"], wt).stdout.strip()
        record["tree"] = _git(["rev-parse", "HEAD^{tree}"], wt).stdout.strip()
        all_passed, runs = run_cli_pregate(wt, [f"python3 {verify_script}"], timeout_per_cmd=60)
        record["verify_exit_codes"] = [run.get("exit_code") for run in runs]
        record["verify_result"] = "pass" if all_passed else "fail"
        return {
            **record,
            "passed": bool(all_passed),
            "score": 1.0 if all_passed else 0.0,
            "candidate_state_hash": record["commit"],
        }

    swarm = BattleSwarm(
        project_root=str(root),
        default_workers=max(1, min(MAX_WORKERS, int(workers or 2))),
        run_dir=str(root / ".nexus" / "runs" / "battle_swarm" / safe_task),
    )
    battle: dict[str, Any] = {}
    worker_records: list[dict[str, Any]] = []

    def capture(
        strategy: dict[str, Any], worktree: str, tid: str, desc: str, ctx: dict[str, Any]
    ) -> dict[str, Any]:
        result = execute(strategy, worktree, tid, desc, ctx)
        worker_records.append(dict(result))
        return result

    try:
        battle = swarm.trigger_battle(safe_task, task, {}, capture)
        report["worktrees"] = [str(p) for p in battle.get("worktrees_to_clean", [])]
        report["branches"] = list(battle.get("branches_to_clean", []))
        report["workers"] = [
            {key: value for key, value in rec.items() if key not in {"passed", "score"}}
            for rec in sorted(worker_records, key=lambda r: str(r.get("strategy")))
        ]
        if battle.get("status") == "aborted":
            report.update(status="BLOCKED", reason="WORKTREE_CREATION_FAILED")
            return report
        winner_name = str((battle.get("winner") or {}).get("strategy") or "")
        winner = next((r for r in worker_records if r.get("strategy") == winner_name), {})
        if battle.get("status") != "winner_found" or not winner.get("passed"):
            report.update(status="FAILED", reason="NO_VERIFIED_WORKER")
            return report
        report["winner"] = {
            key: winner.get(key)
            for key in ("strategy", "worktree", "commit", "tree", "verify_result")
        }
        branch = next(
            (b for b in report["branches"] if b.startswith(f"battle_{safe_task}_{winner_name}_")),
            "",
        )
        report["integration"] = _integrate(root, safe_task, winner, branch, report["base_commit"])
        if report["integration"].get("merge_performed"):
            report.update(status="SUCCEEDED", reason="")
        else:
            report.update(status="BLOCKED", reason="INTEGRATION_OWNER_AUTHORITY_REQUIRED")
        return report
    finally:
        if battle:
            swarm.cleanup(battle)
            report["worktrees_removed"] = [
                str(p) for p in battle.get("worktrees_to_clean", []) if not Path(p).exists()
            ]
        registry.release(safe_task)
        report["lock"]["released"] = not registry.check_access(safe_task, target_file)


def _integrate(
    root: Path, task_id: str, winner: dict[str, Any], branch: str, base: str
) -> dict[str, Any]:
    """Offer the verified winner to the live integration authority with what this run holds.

    The state carries only facts this run produced (candidate commit/tree, source branch, base).
    It has no external acceptance, approval grant or verified lifecycle receipt, so the manager is
    expected to refuse; that refusal is the recorded result.
    """
    from nexus.orchestrator.governed_integration import ControlledIntegrationManager

    state = {
        "task_id": task_id,
        "status": "CANDIDATE_COMMITTED",
        "contract": {
            "task_id": task_id,
            "controller_repo_root": str(root),
            "target_base_revision": base,
        },
        "lease": {"target_branch": branch},
        "promotion_packet": {
            "candidate_commit_sha": str(winner.get("commit") or ""),
            "candidate_tree_sha": str(winner.get("tree") or ""),
            "candidate_state_hash": hashlib.sha256(
                str(winner.get("commit") or "").encode("utf-8")
            ).hexdigest(),
        },
    }
    manager = ControlledIntegrationManager(integration_root=root / ".nexus" / "integration")
    try:
        receipt = manager.integrate_task_state(
            state, integration_branch=f"nexus/integration/{task_id}"
        )
    except Exception as exc:  # noqa: BLE001 - the refusal is the evidence
        return {
            "authority": "nexus.orchestrator.governed_integration.ControlledIntegrationManager.integrate_task_state",
            "attempted": True,
            "merge_performed": False,
            "refusal": str(exc)[:300],
        }
    return {
        "authority": "nexus.orchestrator.governed_integration.ControlledIntegrationManager.integrate_task_state",
        "attempted": True,
        "merge_performed": bool(receipt.merge_performed),
        "integration_commit_sha": receipt.integration_commit_sha,
    }
