from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class ResearchPlannerLike(Protocol):
    def plan(self, **kwargs: Any) -> Any:
        ...


RouteBuilder = Callable[..., dict[str, Any]]
PlannerFactory = Callable[[], ResearchPlannerLike]
LearningPolicyLoader = Callable[[Path], Any]
DecisionBuilder = Callable[..., Any]
ReportWriter = Callable[[Path, Any], Path]
TimestampProvider = Callable[[], int]
JsonReader = Callable[[Path, str | Path | None], dict[str, Any] | None]
AutoFlowRunner = Callable[..., tuple[dict[str, Any], Path]]
ResearchPreflight = Callable[..., dict[str, Any]]
ResearchBlockPayloadBuilder = Callable[..., dict[str, Any]]
ResearchSessionAttacher = Callable[..., dict[str, Any]]
CompletionVerifier = Callable[..., None]
CompletionHandoffWriter = Callable[..., Path]


@dataclass(frozen=True)
class ResearchRouteResult:
    payload: dict[str, Any]
    route_report_path: Path | None


@dataclass(frozen=True)
class ResearchSessionActionResult:
    command_name: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ResearchHumanReportResult:
    report: str
    output_path: Path | None


@dataclass(frozen=True)
class ResearchAutoFlowResult:
    payload: dict[str, Any]
    report_path: Path
    exit_code: int = 0
    blocked: bool = False
    completion_handoff_path: Path | None = None
    completion_error: str | None = None


@dataclass(frozen=True)
class ResearchAutoFlowRouteResult:
    payload: dict[str, Any]


@dataclass(frozen=True)
class ResearchRunResult:
    output_payload: dict[str, Any]
    report_payload: dict[str, Any]
    report_path: Path
    exit_code: int = 0
    continuation_stdout: str | None = None


def _default_session_service_factory(repo_root: Path) -> Any:
    from nexus.research.session_loop_service import ResearchSessionLoopService

    return ResearchSessionLoopService(repo_root)


def _default_route_builder(**kwargs: Any) -> dict[str, Any]:
    from nexus.app import research_flow_service

    return research_flow_service.build_route(**kwargs)


def _default_planner_factory() -> ResearchPlannerLike:
    from nexus.engine.capability_planner import CapabilityPlanner

    return CapabilityPlanner()


def _default_learning_policy_loader(repo_root: Path) -> Any:
    from nexus.engine.learning_policy_loader import merge_runtime_learning_policy

    return merge_runtime_learning_policy(repo_root)


def _default_decision_builder(**kwargs: Any) -> Any:
    from nexus.engine.route_decision_adapter import build_route_decision

    return build_route_decision(**kwargs)


def _default_report_writer(path: Path, decision: Any) -> Path:
    from nexus.engine.route_decision_adapter import write_route_decision_report

    return write_route_decision_report(path, decision)


def _default_json_reader(repo_root: Path, path: str | Path | None) -> dict[str, Any] | None:
    from scripts.engine.commands.research_support import read_json_file

    return read_json_file(repo_root, path)


def _default_auto_flow_runner(**kwargs: Any) -> tuple[dict[str, Any], Path]:
    from nexus.app import research_flow_service

    return research_flow_service.run_auto_flow(**kwargs)


def _default_research_preflight(**kwargs: Any) -> dict[str, Any]:
    from scripts.engine.commands.research_support import research_session_preflight

    return research_session_preflight(**kwargs)


def _default_research_block_payload(**kwargs: Any) -> dict[str, Any]:
    from scripts.engine.commands.research_support import research_preflight_block_payload

    return research_preflight_block_payload(**kwargs)


def _default_research_session_attacher(**kwargs: Any) -> dict[str, Any]:
    from scripts.engine.commands.research_support import attach_research_session_result

    return attach_research_session_result(**kwargs)


def _default_completion_verifier(payload: dict[str, Any], *, context: str) -> None:
    from nexus.engine.completion_contract import ensure_verified_completion

    ensure_verified_completion(payload, context=context)


def _default_completion_handoff_writer(
    *,
    repo_root: Path,
    payload: dict[str, Any],
    context: str,
    report_file: Path,
) -> Path:
    from nexus.engine.completion_enforcer import write_completion_handoff

    handoff_path = write_completion_handoff(
        project_root=repo_root,
        payload=payload,
        context=context,
        report_file=report_file,
    )
    payload["next_action_file"] = str(handoff_path)
    return handoff_path


def _resolve_report_path(repo_root: Path, path: str | Path | None) -> Path | None:
    if path is None or str(path) == "":
        return None
    out = Path(path)
    return out if out.is_absolute() else (repo_root / out).resolve()


def _merge_completion_payload(base_payload: dict[str, Any], completion_payload: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base_payload)
    for key, value in completion_payload.items():
        if key == "status" and "status" in merged:
            merged["runtime_status"] = value
            continue
        merged[key] = value
    return merged


def run_research_auto_flow_route_explanation(
    repo_root: str | Path,
    *,
    task_desc: str,
    task_type: str,
    candidate_count: int,
    root_cause_confidence: float,
    findings_query: str | None,
    target_file: str,
    route_builder: RouteBuilder | None = None,
) -> ResearchAutoFlowRouteResult:
    root = Path(repo_root)
    payload = (route_builder or _default_route_builder)(
        repo_root=root,
        task_desc=task_desc,
        task_type=task_type,
        candidate_count=candidate_count,
        root_cause_confidence=root_cause_confidence,
        findings_query=findings_query,
        target_file=target_file,
    )
    return ResearchAutoFlowRouteResult(payload=payload)


def render_research_auto_flow_route_explanation(result: ResearchAutoFlowRouteResult) -> list[str]:
    return [
        "--- ROUTE EXPLANATION ---",
        json.dumps(result.payload["explain_payload"], indent=2),
    ]


def run_research_auto_flow(
    repo_root: str | Path,
    *,
    task_desc: str,
    target_file: str,
    test_file: str,
    task_type: str,
    success_criteria: str,
    candidate_count: int,
    root_cause_confidence: float,
    findings_query: str | None,
    llm_mode: bool,
    llm_baseline: bool,
    llm_baseline_required: bool,
    timeout_sec: int,
    stage1_timeout_sec: int,
    max_time_ratio_guard: float,
    baseline_fast_sec: float,
    history_window: int,
    history_fail_threshold: int,
    dynamic_timeout_multiplier: float,
    min_dynamic_stage1_timeout: int,
    force_flow: str | None,
    report_file: str | Path,
    output_file: str | Path | None,
    task_id: str | None,
    research_session_id: str,
    research_gate: bool,
    auto_flow_runner: AutoFlowRunner | None = None,
    research_preflight: ResearchPreflight | None = None,
    block_payload_builder: ResearchBlockPayloadBuilder | None = None,
    session_result_attacher: ResearchSessionAttacher | None = None,
    completion_verifier: CompletionVerifier | None = None,
    completion_handoff_writer: CompletionHandoffWriter | None = None,
) -> ResearchAutoFlowResult:
    from nexus.engine.completion_contract import build_completion_envelope
    from nexus.engine.completion_enforcer import CompletionEnforcementError

    root = Path(repo_root)
    preflight: dict[str, Any] | None = None
    report_path = _resolve_report_path(root, report_file)
    if report_path is None:
        raise ValueError("report_file is required for research:auto-flow")

    if research_session_id:
        preflight = (research_preflight or _default_research_preflight)(
            repo_root=root,
            session_id=research_session_id,
            task_desc=task_desc,
            task_type=task_type,
            candidate_count=candidate_count,
            root_cause_confidence=root_cause_confidence,
            findings_query=findings_query,
            target_file=target_file,
            scope=[target_file],
            enforce_gate=research_gate,
        )
        if preflight["blocked"]:
            block_payload = (block_payload_builder or _default_research_block_payload)(
                command_name="research:auto-flow",
                task_name=task_desc,
                preflight=preflight,
            )
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(block_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            return ResearchAutoFlowResult(
                payload=block_payload,
                report_path=report_path,
                exit_code=1,
                blocked=True,
            )

    payload, out_path = (auto_flow_runner or _default_auto_flow_runner)(
        repo_root=root,
        task_desc=task_desc,
        target_file=target_file,
        test_file=test_file,
        task_type=task_type,
        success_criteria=success_criteria,
        candidate_count=candidate_count,
        root_cause_confidence=root_cause_confidence,
        findings_query=findings_query,
        llm_mode=llm_mode,
        llm_baseline=llm_baseline,
        llm_baseline_required=llm_baseline_required,
        timeout_sec=timeout_sec,
        stage1_timeout_sec=stage1_timeout_sec,
        max_time_ratio_guard=max_time_ratio_guard,
        baseline_fast_sec=baseline_fast_sec,
        history_window=history_window,
        history_fail_threshold=history_fail_threshold,
        dynamic_timeout_multiplier=dynamic_timeout_multiplier,
        min_dynamic_stage1_timeout=min_dynamic_stage1_timeout,
        force_flow=force_flow,
        report_file=report_file,
        output_file=output_file,
        task_id=task_id,
    )
    result_payload = payload.get("result", {})
    io_payload = payload.get("io", {})
    artifact_paths = [str(out_path)]
    output_path = io_payload.get("output_path")
    if output_path:
        artifact_paths.append(str(output_path))
    semantic_failures: list[str] = []
    if output_file and not io_payload.get("output_written", False):
        semantic_failures.append("requested_output_not_written")
    completion_payload = build_completion_envelope(
        command_name="research:auto-flow",
        task_name=task_desc,
        runtime_ok=(result_payload.get("status") == "SUCCESS"),
        execution_path="cli->research_flow_service",
        artifact_paths=artifact_paths,
        semantic_failures=semantic_failures,
    )
    response_payload = _merge_completion_payload(payload, completion_payload)
    if research_session_id:
        response_payload["research_preflight"] = preflight
        response_payload["research_session"] = (session_result_attacher or _default_research_session_attacher)(
            repo_root=root,
            session_id=research_session_id,
            report_payload={**response_payload, "status": result_payload.get("status"), "report_file": str(out_path)},
            preflight=preflight,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(response_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    completion_handoff_path: Path | None = None
    completion_error: str | None = None
    exit_code = 0
    try:
        (completion_verifier or _default_completion_verifier)(response_payload, context="research:auto-flow")
    except CompletionEnforcementError as exc:
        completion_handoff_path = (completion_handoff_writer or _default_completion_handoff_writer)(
            repo_root=root,
            payload=response_payload,
            context="research:auto-flow",
            report_file=out_path,
        )
        out_path.write_text(json.dumps(response_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        completion_error = str(exc)
        exit_code = 1

    return ResearchAutoFlowResult(
        payload=response_payload,
        report_path=out_path,
        exit_code=exit_code,
        blocked=False,
        completion_handoff_path=completion_handoff_path,
        completion_error=completion_error,
    )


def render_research_auto_flow_result(result: ResearchAutoFlowResult) -> list[str]:
    payload = result.payload
    result_payload = payload.get("result", {})
    io_payload = payload.get("io", {})
    lines = [
        f"Chosen Flow: {payload['chosen_flow']}",
        f"Status: {result_payload['status']}",
        f"Elapsed: {result_payload['elapsed_sec']} sec",
        f"Report: {result.report_path}",
        f"Output Written: {io_payload.get('output_written', False)}",
        f"Output Path: {io_payload.get('output_path') or 'N/A'}",
        f"Semantic Status: {payload['semantic_status']}",
    ]
    if result.completion_handoff_path is not None:
        lines.append(f"Next Action: {result.completion_handoff_path}")
    if result.completion_error:
        lines.append(result.completion_error)
    return lines


def run_research_run(
    repo_root: str | Path,
    *,
    run_id: str,
    candidate_id: str,
    candidate_count: int,
    hypothesis: str,
    scope: tuple[str, ...] | list[str],
    candidate_src_root: Path,
    budget_limit: float,
    min_score_threshold: float,
    estimated_cost_per_round: float,
    dry_run: bool,
    report_file: Path,
    max_parallel: int,
    max_retries: int,
    continuation_attempts: int,
    timeout_sec: int,
    retain_last_n: int,
    disk_watermark_gb: float,
    research_session_id: str,
    research_gate: bool,
    task_type: str,
    root_cause_confidence: float,
    findings_query: str | None,
    disk_usage: Callable[[Path], tuple[int, int, int]] | None = None,
    research_preflight: ResearchPreflight | None = None,
    block_payload_builder: ResearchBlockPayloadBuilder | None = None,
    session_result_attacher: ResearchSessionAttacher | None = None,
    scheduler_factory: Callable[[Path], Any] | None = None,
    evaluator_factory: Callable[..., Any] | None = None,
    selector_factory: Callable[[Path], Any] | None = None,
    completion_verifier: CompletionVerifier | None = None,
    completion_handoff_writer: CompletionHandoffWriter | None = None,
    subprocess_runner: Callable[..., Any] | None = None,
) -> ResearchRunResult:
    from datetime import datetime, timezone
    import shutil
    import subprocess
    import sys

    from nexus.engine.completion_contract import build_completion_envelope
    from nexus.engine.completion_enforcer import CompletionEnforcementError

    root = Path(repo_root)
    start_ts = datetime.now(timezone.utc).isoformat()
    actual_run_id = run_id or f"research-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    scope_list = list(scope) if scope else ["nexus/research", "tests/research", "docs/research"]
    report_path = _resolve_report_path(root, report_file)
    if report_path is None:
        raise ValueError("report_file is required for research:run")

    preflight: dict[str, Any] | None = None
    if research_session_id:
        preflight = (research_preflight or _default_research_preflight)(
            repo_root=root,
            session_id=research_session_id,
            task_desc=hypothesis,
            task_type=task_type,
            candidate_count=candidate_count,
            root_cause_confidence=root_cause_confidence,
            findings_query=findings_query,
            scope=scope_list,
            enforce_gate=research_gate,
        )
        if preflight["blocked"]:
            block_payload = (block_payload_builder or _default_research_block_payload)(
                command_name="research:run",
                task_name=hypothesis,
                preflight=preflight,
            )
            block_payload.update({"run_id": actual_run_id, "report_file": str(report_path)})
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(block_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            return ResearchRunResult(
                output_payload=block_payload,
                report_payload=block_payload,
                report_path=report_path,
                exit_code=1,
            )

    rollback_trace: list[str] = []
    elimination_matrix: list[dict[str, Any]] = []
    rejected_reasons: list[str] = []
    decision_log: list[str] = []
    status = "success"
    winner = None
    promoted = False
    file_scope: list[str] = []
    retention_summary = {"retain_last_n": retain_last_n, "cleaned": {"reports": 0, "experiments": 0, "backups": 0}}
    scheduler = None
    evaluator = None
    selector = None
    store = None

    decision_log.append("governance: start")
    _, _, free = (disk_usage or shutil.disk_usage)(root)
    free_gb = free / (1024**3)
    if free_gb < disk_watermark_gb:
        status = "failed"
        rejected_reasons.append("low_disk_space")
        decision_log.append("governance: low_disk_space")
    if candidate_count <= 0:
        status = "failed"
        rejected_reasons.append("invalid_candidate_count")
        decision_log.append("governance: invalid_candidate_count")
    if max_parallel <= 0:
        status = "failed"
        rejected_reasons.append("invalid_parallelism")
        decision_log.append("governance: invalid_parallelism")
    if max_retries < 0:
        status = "failed"
        rejected_reasons.append("invalid_retries")
        decision_log.append("governance: invalid_retries")
    if continuation_attempts < 0:
        status = "failed"
        rejected_reasons.append("invalid_continuation_attempts")
        decision_log.append("governance: invalid_continuation_attempts")
    if timeout_sec <= 0:
        status = "failed"
        rejected_reasons.append("invalid_timeout")
        decision_log.append("governance: invalid_timeout")
    if retain_last_n <= 0:
        status = "failed"
        rejected_reasons.append("invalid_retain_n")
        decision_log.append("governance: invalid_retain_n")

    if status == "failed":
        elimination_matrix.append({"candidate_id": candidate_id, "reason_codes": rejected_reasons})

    candidate_root = (root / candidate_src_root).resolve()
    if status == "success":
        from nexus.engine.policies.research_policy import ResearchPolicy
        from nexus.research.experiment_scheduler import ExperimentScheduler
        from nexus.research.findings_memory import FindingsMemoryStore
        from nexus.research.selector_rollback import SelectorRollback
        from nexus.research.unified_evaluator import UnifiedEvaluator

        scheduler = (scheduler_factory or ExperimentScheduler)(root)
        evaluator = (evaluator_factory or UnifiedEvaluator)(
            budget_limit=budget_limit,
            min_score_threshold=min_score_threshold,
        )
        selector = (selector_factory or SelectorRollback)(root)
        policy = ResearchPolicy()
        store = FindingsMemoryStore(root)

        historical_hints = []
        hits = store.search(hypothesis)
        for hit in hits:
            historical_hints.extend(hit.retrieval_hints)
        historical_hints = list(dict.fromkeys(historical_hints))[:3]

        def collect_workspace_files(paths: list[str]) -> list[str]:
            file_paths: list[str] = []
            for item in paths:
                target = (root / item).resolve()
                try:
                    if not target.is_relative_to(root):
                        continue
                except Exception:
                    continue
                if target.is_file():
                    file_paths.append(str(target.relative_to(root)))
                    continue
                if target.is_dir():
                    for path in sorted(target.rglob("*")):
                        if path.is_file():
                            file_paths.append(str(path.relative_to(root)))
            return list(dict.fromkeys(file_paths))

        file_scope = collect_workspace_files(scope_list)
        candidates = [candidate_id]
        if candidate_count > 1:
            candidates = [candidate_id] + [f"candidate-{i}" for i in range(2, candidate_count + 1)]

        for idx, current_cid in enumerate(candidates):
            mutation_hint = policy.get_mutation_hint(idx, task_desc=hypothesis, historical_hints=historical_hints)
            decision_log.append(f"candidate:{current_cid}:start:mutation:{mutation_hint}")
            decision_log.append("schedule: start")
            scheduler.create_candidate(current_cid, hypothesis, scope_list, mutation_hint=mutation_hint)
            scheduler.start_experiment(current_cid)
            if file_scope:
                selector.backup_scope(current_cid, file_scope)

            decision_log.append("evaluate: start")

            def seed_eval(seed: int, cid: str = current_cid) -> dict[str, Any]:
                if "sleep" in hypothesis.lower():
                    time.sleep(timeout_sec + 1.0)
                    return {"seed": seed, "score": 0.0, "cost": estimated_cost_per_round}

                if "real-run" in hypothesis.lower():
                    try:
                        from nexus.research.swarm_broker import SwarmBroker

                        broker = SwarmBroker(root)
                        swarm_dir = broker.acquire(timeout_sec=timeout_sec)
                        if not swarm_dir:
                            return {
                                "seed": seed,
                                "score": 0.0,
                                "cost": estimated_cost_per_round,
                                "error": "broker_timeout",
                            }

                        try:
                            broker.sync_scope(swarm_dir, scope_files=scope_list)
                            res = (subprocess_runner or subprocess.run)(
                                [sys.executable, "-m", "pytest", "-q", "--maxfail=1"],
                                capture_output=True,
                                text=True,
                                timeout=timeout_sec,
                                cwd=swarm_dir,
                            )
                            score = 1.0 if res.returncode == 0 else 0.4
                            return {
                                "seed": seed,
                                "score": score,
                                "cost": estimated_cost_per_round,
                                "stdout": res.stdout,
                            }
                        finally:
                            broker.release(swarm_dir)
                    except subprocess.TimeoutExpired:
                        return {"seed": seed, "score": 0.0, "cost": estimated_cost_per_round, "error": "timeout"}
                    except Exception as exc:  # noqa: BLE001
                        return {"seed": seed, "score": 0.0, "cost": estimated_cost_per_round, "error": str(exc)}

                valid_scope_count = sum(1 for path in scope_list if scheduler.validate_write(cid, path))
                total_scope = len(scope_list) or 1
                valid_ratio = valid_scope_count / total_scope
                src_exists_count = sum(1 for path in scope_list if (candidate_root / path).exists())
                coverage_ratio = src_exists_count / total_scope
                score = round((0.2 + 0.8 * valid_ratio * coverage_ratio), 4)
                return {"seed": seed, "score": score, "cost": estimated_cost_per_round}

            eval_report = evaluator.evaluate(
                candidate_id=current_cid,
                test_fn=seed_eval,
                estimated_cost_per_round=estimated_cost_per_round,
                max_parallel=max_parallel,
                max_retries=max_retries,
                timeout_sec=timeout_sec,
            )
            scheduler.finish_evaluation(current_cid, eval_report)

            if not eval_report.get("passed_gate"):
                elimination_matrix.append(
                    {
                        "candidate_id": current_cid,
                        "reason_codes": ["below_threshold"],
                        "score": eval_report.get("average_score", 0.0),
                    }
                )
                rejected_reasons.append("below_threshold")
                decision_log.append(f"candidate:{current_cid}:gate_failed")
                if not dry_run:
                    decision_log.append(f"candidate:{current_cid}:rolling_back")
                    if selector.restore_scope(current_cid, file_scope):
                        rollback_trace.append(f"below_threshold:{current_cid} -> restore_scope_success")
                    else:
                        rollback_trace.append(f"below_threshold:{current_cid} -> restore_scope_failed")

        decision_log.append("select: start")
        passed_reports = [item for item in evaluator.scoreboard.values() if item.get("passed_gate")]
        if passed_reports:
            best_report = max(passed_reports, key=lambda item: item.get("average_score", 0.0))
            winner = best_report["candidate_id"]
            decision_log.append(f"select: winner={winner}")

            if dry_run:
                rollback_trace.append("dry_run=true; promotion skipped")
                promoted = True
                decision_log.append("promote: skipped")
            else:
                decision_log.append(f"promote: start winner={winner}")
                no_op_promotion = bool(file_scope) and all(
                    (candidate_root / file_path).resolve() == (root / file_path).resolve()
                    for file_path in file_scope
                    if (candidate_root / file_path).exists()
                )
                if no_op_promotion:
                    promoted = True
                    rollback_trace.append("promotion_noop_same_source_target")
                else:
                    promoted = selector.promote_candidate(winner, candidate_root, file_scope)

                if not promoted:
                    status = "failed"
                    rejected_reasons.append("promotion_failed")
                    decision_log.append("promote: failed")
                    if selector.restore_scope(winner, file_scope):
                        rollback_trace.append(f"promotion_failed:{winner} -> restore_scope_success")
                    else:
                        rollback_trace.append(f"promotion_failed:{winner} -> restore_scope_failed")
        else:
            status = "failed"
            decision_log.append("select: no_candidates_passed")

    def apply_retention_policy() -> dict[str, Any]:
        summary = {"retain_last_n": retain_last_n, "cleaned": {"reports": 0, "experiments": 0, "backups": 0}}
        targets = [
            ("reports", root / ".nexus" / "reports" / "research", lambda p: p.is_file() and p.suffix == ".json"),
            ("experiments", root / ".nexus" / "experiments", lambda p: p.is_dir()),
            ("backups", root / ".nexus" / "backups", lambda p: p.is_dir()),
        ]
        for key, target_root, predicate in targets:
            if not target_root.exists():
                continue
            entries = [path for path in target_root.iterdir() if predicate(path)]
            keep_count = retain_last_n
            if key == "reports":
                entries = [path for path in entries if path.resolve() != report_path]
                keep_count = max(0, retain_last_n - 1)
            entries.sort(key=lambda path: path.stat().st_mtime, reverse=True)
            for stale in entries[keep_count:]:
                try:
                    if not stale.resolve().is_relative_to(target_root.resolve()):
                        continue
                    if stale.is_dir():
                        shutil.rmtree(stale)
                    else:
                        stale.unlink()
                    summary["cleaned"][key] += 1
                except Exception:
                    continue
        return summary

    scoreboard = evaluator.scoreboard if evaluator is not None else {}
    top_k = [
        {
            "candidate_id": cid,
            "average_score": float(detail.get("average_score", 0.0)),
            "passed_gate": bool(detail.get("passed_gate", False)),
        }
        for cid, detail in sorted(
            scoreboard.items(),
            key=lambda item: item[1].get("average_score", 0.0),
            reverse=True,
        )
    ]

    total_cost = sum(item.get("total_cost", 0.0) for item in scoreboard.values())
    last_eval_report = scoreboard.get(winner or candidate_id, {})

    arweave_tx_id = None
    if status == "success" and winner and store is not None:
        try:
            from nexus.research.findings_memory import FindingsCard
            from nexus.services.mem_palace import MemPalace

            palace = MemPalace(str(root))
            seed_details = last_eval_report.get("seed_details", [])
            hint = seed_details[0].get("hint", "") if seed_details else ""
            card = FindingsCard(
                kind="episodes",
                title=f"Gladiator Win: {hypothesis[:30]}",
                task_id=actual_run_id,
                body=f"Hypothesis: {hypothesis}\nScope: {scope_list}\nWinner: {winner}",
                confidence="high" if promoted else "medium",
                tags=["gladiator", "research_run"],
                retrieval_hints=[hint] if hint else [],
            )
            clean_cards = palace.verify([card.to_dict()])
            if clean_cards:
                store.write(FindingsCard.from_dict(clean_cards[0]))
                arweave_tx_id = palace.trigger_arweave_distillation(clean_cards[0])
                decision_log.append(f"metabolism: arweave_tx_id={arweave_tx_id}")
            else:
                decision_log.append("metabolism: rejected_by_aaak_judge")
        except Exception as exc:  # noqa: BLE001
            decision_log.append(f"metabolism_error: {exc}")

    report_payload: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": actual_run_id,
        "status": status,
        "winner": winner,
        "arweave_tx_id": arweave_tx_id,
        "top_k": top_k,
        "elimination_matrix": elimination_matrix,
        "decision_log": decision_log,
        "rejected_reasons": rejected_reasons,
        "rollback_trace": rollback_trace,
        "cost_curve": {
            "estimated_cost_per_round": float(estimated_cost_per_round),
            "total_cost": total_cost,
            "budget_limit": float(budget_limit),
            "budget_remaining": max(0.0, float(budget_limit) - total_cost),
        },
        "budget_summary": {
            "limit": budget_limit,
            "used": total_cost,
            "remaining": max(0.0, budget_limit - total_cost),
        },
        "timestamps": {"start": start_ts, "end": datetime.now(timezone.utc).isoformat()},
        "execution": {
            "max_parallel": max_parallel,
            "max_retries": max_retries,
            "timeout_sec": timeout_sec,
            "candidate_count": candidate_count,
        },
        "retention": apply_retention_policy() if status != "failed" or retain_last_n > 0 else retention_summary,
        "candidate": {
            "id": winner or candidate_id,
            "hypothesis": hypothesis,
            "scope": scope_list,
            "file_scope_count": len(file_scope),
            "candidate_src_root": str(candidate_root),
            "promoted": promoted,
            "seed_details": last_eval_report.get("seed_details", []),
        },
    }

    governance_failure_reasons = {
        "low_disk_space",
        "invalid_candidate_count",
        "invalid_parallelism",
        "invalid_retries",
        "invalid_timeout",
        "invalid_retain_n",
    }
    blocker_type = "none"
    semantic_status = "VERIFIED"
    retryable = False
    next_action = "none"
    if status != "success":
        if any(reason in governance_failure_reasons for reason in rejected_reasons):
            blocker_type = "governance"
            semantic_status = "BLOCKED"
            next_action = "stop"
        else:
            blocker_type = "semantic_incomplete"
            semantic_status = "UNVERIFIED"
            retryable = True
            next_action = "retry_repair"
    completion_payload = build_completion_envelope(
        command_name="research:run",
        task_name=hypothesis,
        runtime_ok=(status == "success"),
        execution_path="cli->research_control_plane",
        artifact_paths=[str(report_path)],
        semantic_failures=rejected_reasons,
        blocker_type=blocker_type,
        semantic_status=semantic_status,
        retryable=retryable,
        next_action=next_action,
    )
    report_payload = _merge_completion_payload(report_payload, completion_payload)
    if research_session_id:
        report_payload["research_preflight"] = preflight
        report_payload["research_session"] = (session_result_attacher or _default_research_session_attacher)(
            repo_root=root,
            session_id=research_session_id,
            report_payload={**report_payload, "status": status, "report_file": str(report_path)},
            preflight=preflight,
        )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    summary_payload: dict[str, Any] = {
        "status": status,
        "winner": winner,
        "report_file": str(report_path),
        "semantic_status": report_payload["semantic_status"],
        "retryable": report_payload["retryable"],
        "blocker_type": report_payload["blocker_type"],
        "next_action": report_payload["next_action"],
        "next_action_file": report_payload.get("next_action_file"),
    }

    try:
        (completion_verifier or _default_completion_verifier)(report_payload, context="research:run")
    except CompletionEnforcementError:
        if report_payload.get("retryable") and int(continuation_attempts) > 0:
            continuation_report = report_path.parent / f"{report_path.stem}.retry{continuation_attempts}{report_path.suffix}"
            continuation_cmd = [
                "uv",
                "run",
                "scripts/engine/nexus_cli.py",
                "nexus",
                "research:run",
                "--run-id",
                f"{actual_run_id}-retry{continuation_attempts}",
                "--candidate-id",
                candidate_id,
                "--candidate-count",
                str(candidate_count),
                "--hypothesis",
                hypothesis,
                "--candidate-src-root",
                str(candidate_root),
                "--budget-limit",
                str(budget_limit),
                "--min-score-threshold",
                str(min_score_threshold),
                "--estimated-cost-per-round",
                str(estimated_cost_per_round),
                "--report-file",
                str(continuation_report),
                "--max-parallel",
                str(max_parallel),
                "--max-retries",
                str(max_retries),
                "--continuation-attempts",
                str(continuation_attempts - 1),
                "--timeout-sec",
                str(timeout_sec),
                "--retain-last-n",
                str(retain_last_n),
                "--disk-watermark-gb",
                str(disk_watermark_gb),
            ]
            if dry_run:
                continuation_cmd.append("--dry-run")
            for one_scope in scope_list:
                continuation_cmd.extend(["--scope", str(one_scope)])
            if research_session_id:
                continuation_cmd.extend(["--research-session-id", research_session_id])
            if research_gate:
                continuation_cmd.append("--research-gate")
            continuation_cmd.extend(["--task-type", task_type])
            continuation_cmd.extend(["--root-cause-confidence", str(root_cause_confidence)])
            if findings_query:
                continuation_cmd.extend(["--findings-query", findings_query])

            continuation_proc = (subprocess_runner or subprocess.run)(
                continuation_cmd,
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            summary_payload["continuation"] = {
                "attempted": True,
                "attempts_left_after_call": continuation_attempts - 1,
                "exit_code": continuation_proc.returncode,
                "report_file": str(continuation_report),
            }
            if continuation_proc.returncode == 0:
                return ResearchRunResult(
                    output_payload=summary_payload,
                    report_payload=report_payload,
                    report_path=report_path,
                    exit_code=0,
                    continuation_stdout=str(continuation_proc.stdout).strip(),
                )

        handoff = (completion_handoff_writer or _default_completion_handoff_writer)(
            repo_root=root,
            payload=report_payload,
            context="research:run",
            report_file=report_path,
        )
        report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
        summary_payload["next_action_file"] = str(handoff)
        return ResearchRunResult(
            output_payload=summary_payload,
            report_payload=report_payload,
            report_path=report_path,
            exit_code=1,
        )

    return ResearchRunResult(
        output_payload=summary_payload,
        report_payload=report_payload,
        report_path=report_path,
        exit_code=0,
    )


def render_research_run_result(result: ResearchRunResult) -> list[str]:
    if result.continuation_stdout:
        return [result.continuation_stdout]
    return [json.dumps(result.output_payload, indent=2)]


def run_research_route(
    repo_root: str | Path,
    *,
    task_desc: str,
    task_type: str,
    candidate_count: int,
    root_cause_confidence: float,
    findings_query: str | None,
    task_id: str | None,
    route_decision_report: str | Path | None = None,
    route_builder: RouteBuilder | None = None,
    planner_factory: PlannerFactory | None = None,
    learning_policy_loader: LearningPolicyLoader | None = None,
    decision_builder: DecisionBuilder | None = None,
    report_writer: ReportWriter | None = None,
    timestamp_provider: TimestampProvider | None = None,
) -> ResearchRouteResult:
    root = Path(repo_root)
    payload = (route_builder or _default_route_builder)(
        repo_root=root,
        task_desc=task_desc,
        task_type=task_type,
        candidate_count=candidate_count,
        root_cause_confidence=root_cause_confidence,
        findings_query=findings_query,
        task_id=task_id,
    )

    route_report_path = _resolve_report_path(root, route_decision_report)
    if route_report_path is not None:
        planner = (planner_factory or _default_planner_factory)()
        budget = (learning_policy_loader or _default_learning_policy_loader)(root)
        plan = planner.plan(
            task_desc=task_desc,
            task_type=task_type,
            route=dict(payload),
            budget=budget,
        )
        timestamp = (timestamp_provider or (lambda: int(time.time())))()
        decision = (decision_builder or _default_decision_builder)(
            task_id=f"research-route-{timestamp}",
            task_desc=task_desc,
            task_type=task_type,
            recommended_flow=payload["recommended_flow"],
            plan=plan,
        )
        written = (report_writer or _default_report_writer)(route_report_path, decision)
        payload["route_decision_report"] = str(written)
        route_report_path = written

    return ResearchRouteResult(payload=payload, route_report_path=route_report_path)


def render_research_route_explanation(result: ResearchRouteResult) -> list[str]:
    lines = [
        "--- ROUTE EXPLANATION ---",
        json.dumps(result.payload["explain_payload"], indent=2),
    ]
    if result.route_report_path is not None:
        lines.append(f"Route Decision Report: {result.payload['route_decision_report']}")
    return lines


def render_research_route_summary(result: ResearchRouteResult) -> list[str]:
    payload = result.payload
    lines = [
        f"Should Research: {payload['should_research']}",
        f"Mode: {payload['mode']}",
        f"Reason: {payload['reason']}",
        f"Recommended Flow: {payload['recommended_flow']} ({payload['recommended_reason']})",
        f"Findings Hits: {payload['findings_hits']}",
        f"Adjusted RC Confidence: {payload['adjusted_root_cause_confidence']}",
    ]
    if payload["historical_hints"]:
        lines.append(f"Historical Hints: {payload['historical_hints']}")
    if payload["require_codex_audit"]:
        lines.append("ADVISOR: Low confidence detected. Codex Audit recommended.")
    return lines


def run_research_onboarding(
    repo_root: str | Path,
    *,
    session_id: str,
    goal: str,
    benchmark: str,
    metric: str,
    scope: tuple[str, ...] | list[str],
    service_factory: Callable[[Path], Any] | None = None,
) -> ResearchSessionActionResult:
    root = Path(repo_root)
    payload = (service_factory or _default_session_service_factory)(root).onboarding(
        session_id=session_id,
        goal=goal,
        benchmark=benchmark,
        metric=metric,
        scope=list(scope),
    )
    return ResearchSessionActionResult("research:onboarding", payload)


def run_research_recommend_next(
    repo_root: str | Path,
    *,
    session_id: str,
    task_desc: str,
    task_type: str,
    candidate_count: int,
    root_cause_confidence: float,
    findings_query: str | None,
    route_builder: RouteBuilder | None = None,
    service_factory: Callable[[Path], Any] | None = None,
) -> ResearchSessionActionResult:
    root = Path(repo_root)
    route = (route_builder or _default_route_builder)(
        repo_root=root,
        task_desc=task_desc,
        task_type=task_type,
        candidate_count=candidate_count,
        root_cause_confidence=root_cause_confidence,
        findings_query=findings_query,
    )
    payload = (service_factory or _default_session_service_factory)(root).recommend_next(
        session_id=session_id,
        route=route,
    )
    return ResearchSessionActionResult("research:recommend-next", payload)


def run_research_packet(
    repo_root: str | Path,
    *,
    session_id: str,
    report_file: str | Path | None,
    route_file: str | Path | None,
    json_reader: JsonReader | None = None,
    service_factory: Callable[[Path], Any] | None = None,
) -> ResearchSessionActionResult:
    root = Path(repo_root)
    reader = json_reader or _default_json_reader
    payload = (service_factory or _default_session_service_factory)(root).packet(
        session_id=session_id,
        report=reader(root, report_file),
        route=reader(root, route_file),
    )
    return ResearchSessionActionResult("research:packet", payload)


def run_research_log_from_last(
    repo_root: str | Path,
    *,
    session_id: str,
    status: str,
    description: str,
    asi_file: str | Path | None,
    json_reader: JsonReader | None = None,
    service_factory: Callable[[Path], Any] | None = None,
) -> ResearchSessionActionResult:
    root = Path(repo_root)
    reader = json_reader or _default_json_reader
    payload = (service_factory or _default_session_service_factory)(root).log_from_last(
        session_id=session_id,
        status=status,
        description=description,
        asi=reader(root, asi_file),
    )
    return ResearchSessionActionResult("research:log-from-last", payload)


def run_research_finalize_preview(
    repo_root: str | Path,
    *,
    session_id: str,
    service_factory: Callable[[Path], Any] | None = None,
) -> ResearchSessionActionResult:
    root = Path(repo_root)
    payload = (service_factory or _default_session_service_factory)(root).finalize_preview(session_id=session_id)
    return ResearchSessionActionResult("research:finalize-preview", payload)


def run_research_writeback_lessons(
    repo_root: str | Path,
    *,
    session_id: str,
    service_factory: Callable[[Path], Any] | None = None,
) -> ResearchSessionActionResult:
    root = Path(repo_root)
    payload = (service_factory or _default_session_service_factory)(root).writeback_pending_lessons(session_id=session_id)
    return ResearchSessionActionResult("research:writeback-lessons", payload)


def run_research_human_report(
    repo_root: str | Path,
    *,
    session_id: str,
    output: str | Path | None,
    service_factory: Callable[[Path], Any] | None = None,
) -> ResearchHumanReportResult:
    root = Path(repo_root)
    report = (service_factory or _default_session_service_factory)(root).human_report(session_id=session_id)
    output_path = _resolve_report_path(root, output)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
    return ResearchHumanReportResult(report=report, output_path=output_path)


def render_research_session_action(result: ResearchSessionActionResult) -> list[str]:
    payload = result.payload
    if result.command_name == "research:onboarding":
        return [f"Research session: {payload['session_id']}", f"Ledger: {payload['ledger_path']}"]
    if result.command_name == "research:recommend-next":
        next_action = payload["nextStep"]["nextAction"]
        return [
            f"Next: {next_action['stage']}",
            f"Flow: {next_action['recommended_flow']}",
            f"Reason: {next_action['reason']}",
        ]
    if result.command_name == "research:packet":
        return [f"Research packet: {payload['packet_id']}"]
    if result.command_name == "research:log-from-last":
        if payload["logged"]:
            return [f"Logged: {payload['entry']['packet_id']}"]
        return [f"Not logged: {payload['reason']}"]
    if result.command_name == "research:finalize-preview":
        return [
            f"Ready: {payload['ready']}",
            f"Entries: {payload['entry_count']}",
            f"Keeps: {payload['keep_count']}",
        ]
    if result.command_name == "research:writeback-lessons":
        return [f"Lessons written: {payload['written_count']}"]
    raise ValueError(f"unsupported research session action: {result.command_name}")


def render_research_human_report(result: ResearchHumanReportResult) -> list[str]:
    if result.output_path is not None:
        return [f"Human report: {result.output_path}"]
    return [result.report]
