from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Any, Callable

from nexus.engine.cli_pregate import run_cli_pregate
from nexus.engine.target_env_context import TargetEnvContext
from nexus.learning.lewm_predictor import LeWMPredictor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Trajectory continuity API — loaded at import time so patch paths are stable.
# Any import failure means telemetry is silently unavailable; runtime is
# unaffected in all cases (see _TRAJECTORY_API_AVAILABLE flag below).
# ---------------------------------------------------------------------------
try:
    from nexus.research.clm_system_one.trajectory_continuity import (
        bind_trajectory_step_result,
        resolve_research_evidence_root,
        seal_trajectory_step,
    )

    _TRAJECTORY_API_AVAILABLE = True
except Exception:  # pragma: no cover
    _TRAJECTORY_API_AVAILABLE = False  # type: ignore[assignment]

    def resolve_research_evidence_root(*_a: Any, **_kw: Any) -> Path:  # type: ignore[misc]
        raise RuntimeError("trajectory_continuity unavailable")

    def seal_trajectory_step(**_kw: Any) -> None:  # type: ignore[misc]
        raise RuntimeError("trajectory_continuity unavailable")

    def bind_trajectory_step_result(**_kw: Any) -> None:  # type: ignore[misc]
        raise RuntimeError("trajectory_continuity unavailable")


def _battle_trajectory_id(
    task_id: str, attempt: int, strategy_name: str, source_revision: str
) -> str:
    """Derive a collision-resistant deterministic trajectory_id from the four inputs.

    The result is a hex digest so it is filesystem-safe and globally unique for
    each (task, attempt, strategy, revision) tuple without embedding raw IDs
    (some of which may contain special characters) directly in file paths.
    """
    raw = "\x00".join(
        [
            str(task_id or ""),
            str(attempt),
            str(strategy_name or ""),
            str(source_revision or ""),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class RepairAttemptService:
    """Execute one repair attempt branch (JEPA / battle swarm / pregate)."""

    def __init__(
        self,
        *,
        project_root: Path,
        run_cli_pregate_fn: Callable[..., tuple[bool, list[dict[str, Any]]]] = run_cli_pregate,
        subprocess_run: Callable[..., Any] = subprocess.run,
        lewm_cls: type[LeWMPredictor] = LeWMPredictor,
    ):
        self.project_root = Path(project_root)
        self.run_cli_pregate_fn = run_cli_pregate_fn
        self.subprocess_run = subprocess_run
        self.lewm_cls = lewm_cls

    def execute_attempt(
        self,
        *,
        task_id: str,
        task_desc: str,
        state: Any,
        attempt: int,
        verify_cmds: list[str],
        run_dir: Path,
        skip_pregate_for_isolated_workspace: bool,
        battle_swarm: Any = None,
        reflex_loop: Any = None,
        skill_registry: Any = None,
        wisdom_vault: Any = None,
        target_env: TargetEnvContext | None = None,
    ) -> dict[str, Any]:
        if state.metadata.get("sim_lewm"):
            lewm = self.lewm_cls()
            sim_res = lewm.simulate(state.metadata.get("task_description", ""), None)
            sim_status = sim_res.get("status")
            if sim_status == "REJECTED":
                logger.warning("🚫 [JEPA] Simulator Rejected (Cost: %s)", sim_res.get("cost"))
                state.metadata["lewm_sim_status"] = "REJECTED"
                state.metadata["lewm_rejected_cost"] = sim_res.get("cost")
                return {"status": "abort", "passed": False, "gate_results": []}
            if sim_status == "PASSED":
                state.metadata["lewm_sim_status"] = "PASSED"
                state.metadata["lewm_prediction_cost"] = sim_res.get("cost")
            else:
                logger.info("ℹ️ [JEPA] Simulator %s. Continuing standard flow.", sim_status)
                state.metadata["lewm_sim_status"] = sim_status

        git_exists = (self.project_root / ".git").exists()
        if attempt == 2 and battle_swarm is not None and git_exists:
            workers = 4
            if reflex_loop is not None and hasattr(reflex_loop, "config"):
                workers = int(reflex_loop.config.get("battle_workers", 4) or 4)
            battle_swarm.default_workers = workers
            logger.info(
                "⚔️ [BattleSwarm] Triggering Layer 4 Parallel Repair with %d workers...", workers
            )
            try:
                source_revision_proc = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=str(self.project_root),
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                source_revision = source_revision_proc.stdout.strip()
            except (OSError, subprocess.SubprocessError):
                source_revision = ""

            # Resolve evidence root once so all per-strategy writes share one store.
            # Any failure leaves _evidence_root as None; telemetry is then a no-op.
            _evidence_root: Path | None = None
            if _TRAJECTORY_API_AVAILABLE:
                try:
                    _evidence_root = resolve_research_evidence_root(self.project_root)
                except Exception:
                    _evidence_root = None

            # Verifier-command identities for pre-action state (digests only — no
            # raw output, no future gate results).
            verifier_cmd_identities = [
                hashlib.sha256(str(cmd or "").encode("utf-8")).hexdigest()
                for cmd in (verify_cmds or [])
            ]

            # Per-strategy trajectory step references keyed by strategy name so
            # that post-pregate binding can find the matching ref without any
            # cross-contamination between strategies.
            _strategy_step_refs: dict[str, Any] = {}

            def swarm_worker(_strategy, wt_path, _tid, _desc, _ctx):
                strategy_name = str(_strategy.get("name") or "")
                trajectory_id = _battle_trajectory_id(
                    task_id, attempt, strategy_name, source_revision
                )

                # ------------------------------------------------------------------
                # SEAL pre-action step BEFORE invoking run_cli_pregate_fn.
                # Only then-visible bounded semantic state; no forbidden outcome keys.
                # ------------------------------------------------------------------
                step_ref = None
                if _evidence_root is not None:
                    pre_action_state = {
                        "task_objective": str(task_desc or ""),
                        "strategy_name": strategy_name,
                        "strategy_params": dict(_strategy.get("params") or {}),
                        "attempt": attempt,
                        "verifier_cmd_sha256_list": verifier_cmd_identities,
                        "source_revision": source_revision,
                        "worktree_path_sha256": hashlib.sha256(
                            str(wt_path or "").encode("utf-8")
                        ).hexdigest(),
                    }
                    action_payload = {
                        "action": "cli_pregate",
                        "command_set_sha256_list": verifier_cmd_identities,
                        "worktree_path_sha256": hashlib.sha256(
                            str(wt_path or "").encode("utf-8")
                        ).hexdigest(),
                    }
                    try:
                        step_ref = seal_trajectory_step(
                            evidence_root=_evidence_root,
                            task_id=task_id,
                            trajectory_id=trajectory_id,
                            attempt_id=f"battle-attempt-{attempt}",
                            candidate_id=None,
                            step_index=0,
                            source_revision=source_revision,
                            pre_action_state=pre_action_state,
                            action_type="cli_pregate",
                            action_payload=action_payload,
                        )
                        _strategy_step_refs[strategy_name] = step_ref
                    except Exception as _seal_exc:
                        logger.debug(
                            "[BattleSwarm/trajectory] seal failed for %s: %r",
                            strategy_name,
                            _seal_exc,
                        )

                # ------------------------------------------------------------------
                # Run the per-strategy CLI pregate.
                # Preserve existing exception semantics (any exception propagates).
                # ------------------------------------------------------------------
                if target_env is not None:
                    wt_env = TargetEnvContext(
                        engine_root=target_env.engine_root,
                        target_repo_root=Path(wt_path),
                        target_venv=target_env.target_venv,
                        run_dir=target_env.run_dir,
                    )
                    pregate_root = wt_env
                else:
                    pregate_root = wt_path

                pregate_exc: BaseException | None = None
                wt_passed: bool = False
                wt_gates: list[dict[str, Any]] = []
                try:
                    wt_passed, wt_gates = self.run_cli_pregate_fn(
                        project_root=pregate_root, commands=verify_cmds
                    )
                except Exception as _pregate_exc:
                    pregate_exc = _pregate_exc

                # ------------------------------------------------------------------
                # BIND immediate action result to the sealed step AFTER pregate.
                # Captures passed flag, gate result digests, and exception type.
                # Telemetry failure must not alter pregate/runtime outcome.
                # ------------------------------------------------------------------
                if _evidence_root is not None and step_ref is not None:
                    action_result: dict[str, Any] = {
                        "passed": False if pregate_exc is not None else bool(wt_passed),
                        "exception_type": type(pregate_exc).__name__
                        if pregate_exc is not None
                        else None,
                        "gate_result_digests": [
                            {
                                "cmd_sha256": hashlib.sha256(
                                    str(g.get("cmd") or "").encode("utf-8")
                                ).hexdigest(),
                                "passed": bool(g.get("passed", False)),
                                "exit_code": g.get("exit_code"),
                                "stdout_sha256": hashlib.sha256(
                                    str(g.get("stdout_tail") or "").encode("utf-8")
                                ).hexdigest(),
                                "stderr_sha256": hashlib.sha256(
                                    str(g.get("stderr_tail") or "").encode("utf-8")
                                ).hexdigest(),
                            }
                            for g in wt_gates
                        ],
                    }
                    try:
                        bind_trajectory_step_result(
                            evidence_root=_evidence_root,
                            step_ref=step_ref,
                            action_result=action_result,
                        )
                    except Exception as _bind_exc:
                        logger.debug(
                            "[BattleSwarm/trajectory] bind result failed for %s: %r",
                            strategy_name,
                            _bind_exc,
                        )

                # Re-raise pregate exception to preserve existing runtime semantics.
                if pregate_exc is not None:
                    raise pregate_exc

                score = (sum(1 for g in wt_gates if g["passed"]) / max(len(wt_gates), 1)) * 10.0
                candidate_payload = ""
                if source_revision:
                    try:
                        diff_proc = subprocess.run(
                            ["git", "diff", "--binary", source_revision],
                            cwd=str(wt_path),
                            check=False,
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        candidate_payload = diff_proc.stdout or ""
                    except (OSError, subprocess.SubprocessError):
                        candidate_payload = ""
                gate_evidence = []
                for gate in wt_gates:
                    gate_evidence.append(
                        {
                            "cmd_sha256": hashlib.sha256(
                                str(gate.get("cmd") or "").encode("utf-8")
                            ).hexdigest(),
                            "exit_code": gate.get("exit_code"),
                            "passed": bool(gate.get("passed", False)),
                            "stdout_sha256": hashlib.sha256(
                                str(gate.get("stdout_tail") or "").encode("utf-8")
                            ).hexdigest(),
                            "stderr_sha256": hashlib.sha256(
                                str(gate.get("stderr_tail") or "").encode("utf-8")
                            ).hexdigest(),
                            "reason": str(gate.get("reason") or ""),
                        }
                    )
                return {
                    "passed": wt_passed,
                    "score": score,
                    "verifier_status": "pass" if wt_passed else "fail",
                    "gate_results": gate_evidence,
                    "candidate_payload": candidate_payload,
                    "candidate_payload_sha256": (
                        hashlib.sha256(candidate_payload.encode("utf-8")).hexdigest()
                        if candidate_payload
                        else ""
                    ),
                    "candidate_state_hash": "",
                }

            battle_result = battle_swarm.trigger_battle(
                task_id=task_id,
                desc=task_desc,
                context=state.metadata,
                execute_fn=swarm_worker,
            )
            try:
                from nexus.research.clm_system_one.candidate_evidence_collector import (
                    collect_candidate_group,
                )

                winner_strategy = str((battle_result.get("winner") or {}).get("strategy") or "")
                collection_candidates = []
                for item in battle_result.get("all_results", []) or []:
                    strategy_name = str(item.get("strategy") or "")
                    candidate_payload = str(item.get("candidate_payload") or "")
                    collection_candidates.append(
                        {
                            "candidate_id": f"{task_id}#battle-{strategy_name}",
                            "candidate_model": strategy_name,
                            "candidate_source": "battle_swarm",
                            "candidate_payload": candidate_payload,
                            "candidate_payload_sha256": str(
                                item.get("candidate_payload_sha256") or ""
                            ),
                            "candidate_state_hash": str(item.get("candidate_state_hash") or ""),
                            "verifier_status": str(item.get("verifier_status") or ""),
                            "label_quality": (
                                "MECHANICAL_GATE" if candidate_payload else "TRACE_ONLY"
                            ),
                            "verifier_evidence": {
                                "verifier_kind": "cli_pregate",
                                "gate_results": list(item.get("gate_results", []) or []),
                            },
                            "failure_reason_codes": (
                                [] if item.get("passed") else ["cli_pregate_failed"]
                            ),
                            "selected": strategy_name == winner_strategy,
                        }
                    )
                collection = collect_candidate_group(
                    repo_root=self.project_root,
                    task_id=task_id,
                    attempt_id=f"battle-attempt-{attempt}",
                    collector_source="battle_swarm",
                    source_revision=source_revision,
                    contract_identity={
                        "task_desc": task_desc,
                        "attempt": attempt,
                    },
                    verifier_identity={
                        "kind": "cli_pregate",
                        "commands": list(verify_cmds),
                    },
                    candidates=collection_candidates,
                    winner_id=(f"{task_id}#battle-{winner_strategy}" if winner_strategy else ""),
                )
                state.metadata["candidate_evidence_collection_status"] = collection.status
                state.metadata["candidate_evidence_collection_group_sha256"] = (
                    collection.group_sha256
                )
                state.metadata["candidate_evidence_collection_rows"] = collection.collected_count
                state.metadata["candidate_evidence_collection_eligible_rows"] = (
                    collection.eligible_count
                )

                # BattleSwarm instrumentation is intentionally TRACE_ONLY.
                # The observed action above is the mechanical CLI pregate/verifier,
                # not a repair-generation action.  Do not bind final candidate
                # PASS/FAIL outcomes here: doing so would make verifier execution
                # look like a trainable repair trajectory.
            except Exception as collection_exc:
                state.metadata["candidate_evidence_collection_status"] = "ERROR"
                state.metadata["candidate_evidence_collection_error_type"] = type(
                    collection_exc
                ).__name__
            try:
                if battle_result.get("status") == "winner_found":
                    winner = battle_result["winner"]
                    logger.info("🏆 [BattleSwarm] Winner Strategy %s applied.", winner["strategy"])
                    branches = battle_result.get("branches_to_clean", [])
                    winner_branch = next((b for b in branches if winner["strategy"] in b), None)
                    if winner_branch:
                        self.subprocess_run(
                            ["git", "merge", "--squash", winner_branch],
                            cwd=str(self.project_root),
                            capture_output=True,
                        )
                    if wisdom_vault is not None:
                        from nexus.research.findings_distiller import FindingsDistiller
                        from nexus.research.findings_memory import FindingsMemoryStore

                        distiller = FindingsDistiller(
                            FindingsMemoryStore(self.project_root),
                            skill_registry,
                            wisdom_vault,
                        )
                        distiller.distill_battle_results(battle_result, task_id)
                    return {
                        "status": "ok",
                        "passed": True,
                        "gate_results": [{"status": "PASSED_VIA_SWARM", "passed": True}],
                    }

                effective_project_root = target_env if target_env is not None else run_dir
                passed, gate_results = self.run_cli_pregate_fn(
                    project_root=effective_project_root, commands=verify_cmds
                )
                return {"status": "ok", "passed": bool(passed), "gate_results": gate_results}
            finally:
                battle_swarm.cleanup(battle_result)

        if skip_pregate_for_isolated_workspace:
            return {
                "status": "ok",
                "passed": True,
                "gate_results": [
                    {
                        "cmd": "_NO_VERIFY_COMMANDS",
                        "exit_code": 0,
                        "passed": True,
                        "pregate_skip": True,
                        "reason": "isolated_workspace_without_git",
                    }
                ],
            }

        effective_project_root = target_env if target_env is not None else run_dir
        passed, gate_results = self.run_cli_pregate_fn(
            project_root=effective_project_root, commands=verify_cmds
        )
        return {"status": "ok", "passed": bool(passed), "gate_results": gate_results}
