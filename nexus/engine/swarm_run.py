"""Bounded swarm / multi-agent run: lock -> worktrees -> worker step -> verify -> integrate.

One call does, in the caller's git workspace:

1. claim the target file in the cross-task ``FileLockRegistry`` (a file held by another task
   blocks the run before anything is created);
2. fork ``BattleSwarm`` worktrees, one per strategy, on ``battle_<task>_*`` branches;
3. run one worker step per worktree: a candidate from the Workforce-admitted local worker through
   the armored local lane (``LocalArmorCandidateGenerator``; model calls are serialized), written
   into the worktree and committed;
4. verify each worktree with the request's verify script (no-shell CLI pre-gate runner);
5. offer the winning commit to the canonical Candidate integration facade
   (``SelfHostedTaskService.integrate_approved``, which delegates to
   ``ControlledIntegrationManager``); this module never calls the Git-apply sink itself (#947).

Integration needs a persisted, APPROVED lifecycle task (external acceptance bound to the
candidate, a consumed Owner approval grant, a verified receipt). This module never fabricates
those, so without them the facade refuses and the run reports that refusal verbatim. Worktrees and battle
branches are removed afterwards (``git worktree remove``; never ``git worktree prune``); the
candidate commits stay in the object store as evidence.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404 - fixed git argv only
import sys
import threading
from pathlib import Path
from typing import Any

SCHEMA = "nexus.swarm_run.v1"
MAX_WORKERS = 4
AUTHORITY = (
    "nexus.orchestrator.self_hosted_task_service.SelfHostedTaskService.integrate_approved"
    " -> ControlledIntegrationManager.integrate_authorized_task_state"
)


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
    """Offer the verified winner to the canonical Candidate integration facade.

    Candidate integration has one effect owner: ``SelfHostedTaskService.integrate_approved``
    delegating to ``ControlledIntegrationManager.integrate_authorized_task_state`` (#947). This
    run never calls the physical sink itself. The facade integrates only a persisted, APPROVED
    lifecycle task; a swarm run creates none, so the facade is expected to refuse and that
    refusal is the recorded result. If a lifecycle task with this id exists, its persisted
    candidate must be this run's winner commit, otherwise nothing is offered.
    """
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

    record: dict[str, Any] = {
        "authority": AUTHORITY,
        "attempted": False,
        "merge_performed": False,
        "candidate_commit_sha": str(winner.get("commit") or ""),
        "source_branch": branch,
        "target_base_revision": base,
        "workspace_root": str(root),
    }
    try:
        service = SelfHostedTaskService(auto_reconcile=False)
        existing = service.get_task(task_id)
        if existing is not None:
            packet = existing.get("promotion_packet")
            persisted = str(
                existing.get("candidate_commit_sha")
                or (packet.get("candidate_commit_sha") if isinstance(packet, dict) else "")
                or ""
            )
            if persisted != record["candidate_commit_sha"]:
                record["refusal"] = "LIFECYCLE_CANDIDATE_MISMATCH"
                return record
        record["attempted"] = True
        result = service.integrate_approved(
            task_id, integration_branch=f"nexus/integration/{task_id}"
        )
    except KeyError as exc:  # the facade's unknown-task refusal
        record["refusal"] = str(exc.args[0] if exc.args else exc)[:300]
        return record
    except Exception as exc:  # noqa: BLE001 - the refusal is the evidence
        record["refusal"] = str(exc)[:300]
        return record
    record["merge_performed"] = bool(result.get("merge_performed"))
    record["integration_commit_sha"] = str(result.get("integration_commit_sha") or "")
    return record
