"""Bounded swarm / multi-agent run: lock -> worktrees -> worker step -> verify -> integrate.

One call does, in the caller's git workspace:

1. claim the target file in the cross-task ``FileLockRegistry`` (a file held by another task
   blocks the run before anything is created);
2. fork ``BattleSwarm`` worktrees, one per strategy, on ``battle_<task>_*`` branches;
3. run one worker step per worktree: a candidate from the Workforce-admitted local worker through
   the armored local lane (``LocalArmorCandidateGenerator``; model calls are serialized), written
   into the worktree and committed;
4. verify each worktree with the request's verify script inside the shared OS sandbox
   (``nexus.engine.sandboxed_lane``: trusted interpreter with ``-I``, scrubbed env, HOME/TMPDIR
   in a per-worker sandbox dir, no network, writes only in the worktree and that dir); without
   an OS barrier the script is not run and the worker is unverified;
5. offer the winning commit to the canonical Candidate integration facade
   (``SelfHostedTaskService.integrate_approved``, which delegates to
   ``ControlledIntegrationManager``); this module never calls the Git-apply sink itself (#947).

Integration needs a persisted, APPROVED lifecycle task (external acceptance bound to the
candidate, a consumed Owner approval grant, a verified receipt). An approval binds an exact
candidate commit, which only exists after the run, so a run can never integrate by itself: it
reports the facade's refusal verbatim plus ``pending_owner_approval``; once an Owner approved
that winner, ``integrate_swarm_winner`` offers it to the same facade again. Worktrees and battle
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

from nexus.core.hardened_git import repository_config_can_start_a_program, run_hardened_git

SCHEMA = "nexus.swarm_run.v1"
NOT_EXECUTED_NO_BARRIER = "not_executed:no_os_barrier"
VERIFY_TIMEOUT_SEC = 60
MAX_WORKERS = 4
AUTHORITY = (
    "nexus.orchestrator.self_hosted_task_service.SelfHostedTaskService.integrate_approved"
    " -> ControlledIntegrationManager.integrate_authorized_task_state"
)


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """``git <args>`` in ``cwd`` (the workspace root or a worker worktree) through the shared
    hardened runner: no hooks, fsmonitor, signing or external diff program the repository
    names."""
    return run_hardened_git(cwd, *args, timeout=60)


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or ""))[:48] or "task"


def _unsafe_relpath(value: str) -> bool:
    """A request path that could become a flag, escape the worktree or name its git dir."""

    path = Path(str(value or ""))
    return (
        not str(value or "").strip()
        or str(value).startswith("-")
        or "\x00" in str(value)
        or path.is_absolute()
        or ".." in path.parts
        or any(part.lower() == ".git" for part in path.parts)
    )


def _scoped_file(worktree: Path, rel: str) -> Path | None:
    """``worktree/rel`` when it is a regular file inside the worktree with no symlink on the way."""

    from nexus.engine.sandboxed_lane import scoped_path

    target = scoped_path(worktree, rel)
    if target is None or target.is_symlink() or not target.is_file():
        return None
    return target


def run_bounded_swarm(
    *,
    workspace_root: Path,
    task_id: str,
    task: str,
    target_file: str,
    verify_script: str,
    workers: int = 2,
) -> dict[str, Any]:
    from nexus.engine import sandboxed_lane as lane
    from nexus.engine.battle_swarm import BattleSwarm
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
    for field, value in (("target_file", target_file), ("verify_script", verify_script)):
        if _unsafe_relpath(value):
            report.update(status="BLOCKED", reason=f"UNSAFE_PATH:{field}")
            return report
    head = _git(["rev-parse", "HEAD"], root)
    if head.returncode != 0:
        report.update(status="BLOCKED", reason="WORKSPACE_NOT_GIT_REPOSITORY")
        return report
    report["base_commit"] = head.stdout.strip()
    if repository_config_can_start_a_program(root):
        report.update(status="BLOCKED", reason="WORKSPACE_GIT_CONFIG_NAMES_A_PROGRAM")
        return report

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
        target = _scoped_file(wt, target_file)
        script = _scoped_file(wt, verify_script)
        if target is None or script is None:
            record.update(worker_status="unsafe_path", verify_result="not_executed:unsafe_path")
            return {**record, "passed": False, "score": 0.0}
        source = target.read_text(encoding="utf-8")
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
        # Model output: never written through a symlink (O_NOFOLLOW, re-checked containment).
        target = _scoped_file(wt, target_file)
        if target is None:
            record.update(worker_status="unsafe_path", verify_result="not_executed:unsafe_path")
            return {**record, "passed": False, "score": 0.0}
        lane.write_no_follow(target, code.encode("utf-8"))
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
        script = _scoped_file(wt, verify_script)
        if script is None:
            record.update(verify_result="not_executed:unsafe_path")
            return {**record, "passed": False, "score": 0.0}
        all_passed = False
        record["verify_exit_codes"] = []
        if not lane.os_sandbox_available():
            # The verify script imports and runs model-written code: without an OS barrier it
            # does not run at all and the worker stays unverified (it cannot win).
            record["verify_result"] = NOT_EXECUTED_NO_BARRIER
            return {**record, "passed": False, "score": 0.0}
        try:
            confined = lane.confinement(
                sandbox=wt.parent / f"sandbox_{_safe(strategy['name'])}",
                extra_writable=(wt,),
                untrusted_roots=(root,),
                extra_forbidden=(root,),
            )
            record["isolation"] = confined.describe()
            run = confined.run(lane.python_script_argv(script), cwd=wt, timeout=VERIFY_TIMEOUT_SEC)
            record["verify_exit_codes"] = [run.returncode]
            all_passed = run.returncode == 0
        except subprocess.TimeoutExpired:
            record["verify_exit_codes"] = [None]
        except lane.SandboxError as exc:
            record.update(verify_result=f"not_executed:sandbox_error:{exc}"[:120])
            return {**record, "passed": False, "score": 0.0}
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
        report["integration"] = integrate_swarm_winner(
            root, safe_task, winner, branch, report["base_commit"]
        )
        if report["integration"].get("merge_performed"):
            report.update(status="SUCCEEDED", reason="")
        else:
            report.update(status="BLOCKED", reason="INTEGRATION_OWNER_AUTHORITY_REQUIRED")
            # What an Owner approves to integrate this exact verified winner later (through
            # the same facade, ``integrate_swarm_winner``); the run itself never approves.
            report["pending_owner_approval"] = {
                "task_id": safe_task,
                "candidate_commit_sha": str(winner.get("commit") or ""),
                "candidate_tree_sha": str(winner.get("tree") or ""),
                "target_base_revision": report["base_commit"],
                "target_file": target_file,
                "verify_script": verify_script,
                "integration_branch": f"nexus/integration/{safe_task}",
            }
        return report
    finally:
        if battle:
            swarm.cleanup(battle)
            report["worktrees_removed"] = [
                str(p) for p in battle.get("worktrees_to_clean", []) if not Path(p).exists()
            ]
        registry.release(safe_task)
        report["lock"]["released"] = not registry.check_access(safe_task, target_file)


def integrate_swarm_winner(
    root: Path, task_id: str, winner: dict[str, Any], branch: str, base: str
) -> dict[str, Any]:
    """Offer the verified winner to the canonical Candidate integration facade.

    Candidate integration has one effect owner: ``SelfHostedTaskService.integrate_approved``
    delegating to ``ControlledIntegrationManager.integrate_authorized_task_state`` (#947). This
    run never calls the physical sink itself. The facade integrates only a persisted, APPROVED
    lifecycle task; a swarm run creates none, so during the run the facade refuses and that
    refusal is the recorded result (``pending_owner_approval`` says what to approve). After an
    Owner approved that exact winner (a lifecycle task whose persisted candidate is the winner
    commit), calling this again integrates it. If a lifecycle task with this id exists, its
    persisted candidate must be the winner commit, otherwise nothing is offered.
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
    record["integration_commit_sha"] = str(
        result.get("integration_commit_sha") or result.get("integration_result_sha") or ""
    )
    record["integration_status"] = str(result.get("status") or "")
    return record


_integrate = integrate_swarm_winner  # backward-compatible private name
