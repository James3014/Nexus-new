from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from scripts.engine.commands.exception_translation import NexusCliActionError


class LearnModeServiceLike(Protocol):
    def read_phase_slo_summary(self) -> dict[str, Any]:
        ...


class PhaseActionsLike(Protocol):
    allow_research: bool
    force_baseline: bool
    require_writeback: bool
    audit_strictness: Any
    reasoning: str


LearnModeServiceFactory = Callable[[Path], LearnModeServiceLike]
DerivePhaseActions = Callable[[dict[str, Any], str, str], PhaseActionsLike]
EvidenceWriter = Callable[[Path | None, str, dict[str, Any]], Path | None]
HallucinationGate = Callable[[str, dict[str, Any]], None]
CompletionVerifier = Callable[..., None]
CommandRunner = Callable[[list[str]], None]


@dataclass(frozen=True)
class LearnConvergeResult:
    topic: str
    payload: dict[str, Any]
    report_path: Path
    evidence_path: Path | None


@dataclass(frozen=True)
class LearnAskResult:
    topic: str
    question: str
    payload: dict[str, Any]
    evidence_path: Path | None


@dataclass(frozen=True)
class LearnSourceLifecycleResult:
    command_name: str
    payload: dict[str, Any]
    report_path: Path


@dataclass(frozen=True)
class LearnReportResult:
    topic: str
    payload: dict[str, Any]
    report_path: Path
    markdown_path: Path


@dataclass(frozen=True)
class LearnIngestResult:
    source: str
    payload: dict[str, Any]
    report_path: Path
    markdown_path: Path
    evidence_path: Path | None


@dataclass(frozen=True)
class LearnGateResult:
    payload: dict[str, Any]
    report_path: Path
    evidence_path: Path | None


@dataclass(frozen=True)
class LearnPhaseReportResult:
    command_name: str
    payload: dict[str, Any]
    report_path: Path


def _default_learn_mode_service_factory(repo_root: Path) -> LearnModeServiceLike:
    from nexus.research.learn_mode import LearnModeService

    return LearnModeService(repo_root)


def _default_command_runner(command: list[str]) -> None:
    import subprocess

    subprocess.run(command, check=True)


def _default_derive_phase_actions(slo_summary: dict[str, Any], task_type: str, risk: str) -> PhaseActionsLike:
    from nexus.research.learn.phase_policy import derive_phase_actions

    return derive_phase_actions(slo_summary, task_type, risk)


def _resolve_report_path(repo_root: Path, path: str | Path | None) -> Path | None:
    if path is None or str(path) == "":
        return None
    out = Path(path)
    return out if out.is_absolute() else (repo_root / out).resolve()


def _write_json_report(repo_root: Path, path: str | Path, payload: dict[str, Any]) -> Path:
    out = _resolve_report_path(repo_root, path)
    if out is None:
        raise NexusCliActionError("learn report_file is required", exit_code=1)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _identity_vault_status(root: Path) -> tuple[bool, list[str]]:
    candidate_paths = (
        root / "nexus_wiki_vault" / "01_System" / "Identity_Vault.md",
        Path(__file__).resolve().parents[3] / "nexus_wiki_vault" / "01_System" / "Identity_Vault.md",
    )
    identity_path = next((path for path in candidate_paths if path.exists()), None)
    if identity_path is None:
        return False, ["missing_identity_vault"]
    text = identity_path.read_text(encoding="utf-8")
    failures: list[str] = []
    for identity in ("learn_mode_agent", "codex_supervisor", "gemini_router"):
        if identity not in text:
            failures.append(f"missing_identity:{identity}")
    if text.count("Init/Active/Archive") < 3:
        failures.append("identity_lifecycle_incomplete")
    return not failures, failures


def _write_dual_gate_markdown(base_root: Path, path: Path, task: str, data: dict, evidence: str, debt: str) -> Path:
    from nexus.research.learn.dual_gate_protocol import DualGateProtocol

    out = path if path.is_absolute() else (base_root / path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(DualGateProtocol.render(task=task, data=data, evidence=evidence, debt=debt), encoding="utf-8")
    return out


def _evaluate_learn_semantic_contract(
    *,
    root: Path,
    payload: dict,
    command_name: str,
    markdown_report_written: bool,
) -> dict:
    failures: list[str] = []
    if command_name == "learn:ingest":
        channel_counts = payload.get("channel_counts")
        if not isinstance(channel_counts, dict):
            failures.append("missing_dual_channel_fields")
        else:
            for key in ("tactical_data", "governance_principles"):
                if key not in channel_counts:
                    failures.append(f"missing_channel_count:{key}")
    identity_ok, identity_failures = _identity_vault_status(root)
    if not identity_ok:
        failures.extend(identity_failures)
    if not markdown_report_written:
        failures.append("dual_gate_markdown_not_written")
    semantic_status = "VERIFIED" if not failures else "UNVERIFIED"
    return {
        "semantic_status": semantic_status,
        "semantic_failures": failures,
    }


def _format_unresolved_question_item(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()

    if isinstance(item, dict):
        question = item.get("question")
        reason = item.get("reason")
        if isinstance(question, str):
            question_parts = [part.strip() for part in question.splitlines() if part.strip()]
        elif isinstance(question, list):
            question_parts = [str(part).strip() for part in question if str(part).strip()]
        else:
            question_parts = [str(question).strip()] if question is not None else []
        rendered = "; ".join(question_parts)
        if reason:
            rendered = f"{rendered} - {reason}" if rendered else str(reason).strip()
        return rendered.strip()

    return str(item).strip()


def _format_unresolved_questions_for_debt(unresolved_questions: Any) -> str:
    rendered: list[str] = []
    for item in unresolved_questions or []:
        value = _format_unresolved_question_item(item)
        if value:
            rendered.append(value)
    return "; ".join(rendered)


def _merge_completion_payload(base_payload: dict[str, Any], completion_payload: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base_payload)
    for key, value in completion_payload.items():
        if key == "status" and "status" in merged:
            merged["runtime_status"] = value
            continue
        merged[key] = value
    merged["semantic_status"] = merged.get("semantic_status", "UNVERIFIED")
    return merged


def _finalize_learn_semantic_payload(
    payload: dict[str, Any],
    *,
    command_name: str,
    task_name: str,
    runtime_ok: bool,
    execution_path: str,
) -> dict[str, Any]:
    from nexus.engine.completion_contract import build_completion_envelope

    completion_payload = build_completion_envelope(
        command_name=command_name,
        task_name=task_name,
        runtime_ok=runtime_ok,
        execution_path=execution_path,
    )
    return _merge_completion_payload(payload, completion_payload)


def _write_learn_hallucination_evidence(
    path: Path | None,
    final_response: str,
    evidence_bundle: dict[str, Any],
) -> Path | None:
    if path is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"final_response": final_response, "evidence_bundle": evidence_bundle},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _enforce_learn_hallucination_gate(final_response: str, evidence_bundle: dict[str, Any]) -> None:
    from nexus.core.hallucination_guard import HallucinationGuard

    guard = HallucinationGuard()
    analysis = guard.analyze(final_response, evidence_bundle)
    if analysis["status"] == "REJECTED":
        raise NexusCliActionError(
            f"Hallucination gate rejected response. score={analysis['score']} triggers={analysis['triggers']}",
            exit_code=1,
        )


def get_learn_phase_policy(
    repo_root: str | Path,
    *,
    task_type: str,
    risk: str,
    service_factory: LearnModeServiceFactory | None = None,
    derive_actions: DerivePhaseActions | None = None,
) -> dict[str, Any]:
    root = Path(repo_root)
    service = (service_factory or _default_learn_mode_service_factory)(root)
    slo_summary = service.read_phase_slo_summary()
    actions = (derive_actions or _default_derive_phase_actions)(slo_summary, task_type, risk)
    return {
        "task_type": task_type,
        "risk": risk,
        "slo_readiness": slo_summary.get("overall_pass_rate", 0.0),
        "policy": {
            "allow_research": actions.allow_research,
            "force_baseline": actions.force_baseline,
            "require_writeback": actions.require_writeback,
            "audit_strictness": actions.audit_strictness.value,
            "reasoning": actions.reasoning,
        },
    }


def render_learn_phase_policy(payload: dict[str, Any]) -> list[str]:
    policy = payload["policy"]
    return [
        f"SLO Readiness: {float(payload['slo_readiness']):.1%}",
        f"Allow Research: {policy['allow_research']}",
        f"Force Baseline: {policy['force_baseline']}",
        f"Reasoning: {policy['reasoning']}",
    ]


def get_learn_scheduler_status(repo_root: str | Path) -> dict[str, Any] | None:
    root = Path(repo_root)
    report_path = root / ".nexus/reports/learn/scheduler_last_run.json"
    alert_dir = root / ".nexus/reports/alerts"
    if not report_path.exists():
        return None

    data = json.loads(report_path.read_text(encoding="utf-8"))
    alerts = sorted(alert_dir.glob("*.json")) if alert_dir.exists() else []
    return {
        "last_run": data.get("timestamp"),
        "last_exit_code": data.get("exit_code"),
        "slo_readiness": data.get("slo_readiness"),
        "alert_count": len(alerts),
        "alert_paths": [str(path.name) for path in alerts[-3:]],
    }


def render_learn_scheduler_status(payload: dict[str, Any]) -> list[str]:
    exit_code = payload["last_exit_code"]
    status = "OK" if exit_code == 0 else "DEGRADED" if exit_code == 2 else "FAILED"
    return [
        f"Last Run: {payload['last_run']}",
        f"Status: {status}",
        f"Alerts Found: {payload['alert_count']}",
    ]


def run_learn_register_source(
    repo_root: str | Path,
    *,
    topic: str,
    source: str,
    source_file: str | Path | None,
    refresh_after_days: int,
    priority: str,
    report_file: str | Path,
    service_factory: LearnModeServiceFactory | None = None,
) -> LearnSourceLifecycleResult:
    root = Path(repo_root)
    service = (service_factory or _default_learn_mode_service_factory)(root)
    payload = service.register_source(
        topic=topic,
        source=source,
        source_file=source_file,
        refresh_after_days=refresh_after_days,
        priority=priority,
    )
    report_path = _write_json_report(root, report_file, payload)
    finalized_payload = _finalize_learn_semantic_payload(
        payload,
        command_name="learn:register-source",
        task_name=f"register source topic={topic}",
        runtime_ok=(str(payload.get("status", "")).upper() == "SUCCESS"),
        execution_path="cli->learn_mode_service",
    )
    return LearnSourceLifecycleResult("learn:register-source", finalized_payload, report_path)


def run_learn_refresh(
    repo_root: str | Path,
    *,
    topic: str,
    due_only: bool,
    pass_threshold: float,
    question_count: int,
    report_file: str | Path,
    service_factory: LearnModeServiceFactory | None = None,
) -> LearnSourceLifecycleResult:
    root = Path(repo_root)
    service = (service_factory or _default_learn_mode_service_factory)(root)
    payload = service.refresh_sources(
        topic=topic,
        due_only=due_only,
        pass_threshold=pass_threshold,
        question_count=question_count,
    )
    report_path = _write_json_report(root, report_file, payload)
    finalized_payload = _finalize_learn_semantic_payload(
        payload,
        command_name="learn:refresh",
        task_name=f"refresh sources topic={topic or 'all'}",
        runtime_ok=(str(payload.get("status", "")).upper() == "SUCCESS"),
        execution_path="cli->learn_mode_service",
    )
    return LearnSourceLifecycleResult("learn:refresh", finalized_payload, report_path)


def run_learn_refresh_plan(
    repo_root: str | Path,
    *,
    topic: str,
    due_within_days: int,
    report_file: str | Path,
    service_factory: LearnModeServiceFactory | None = None,
) -> LearnSourceLifecycleResult:
    root = Path(repo_root)
    service = (service_factory or _default_learn_mode_service_factory)(root)
    payload = service.build_refresh_plan(
        topic=topic,
        due_within_days=due_within_days,
    )
    report_path = _write_json_report(root, report_file, payload)
    finalized_payload = _finalize_learn_semantic_payload(
        payload,
        command_name="learn:refresh-plan",
        task_name=f"build refresh plan topic={topic or 'all'}",
        runtime_ok=(str(payload.get("status", "")).upper() == "SUCCESS"),
        execution_path="cli->learn_mode_service",
    )
    return LearnSourceLifecycleResult("learn:refresh-plan", finalized_payload, report_path)


def render_learn_register_source_complete(
    result: LearnSourceLifecycleResult,
    *,
    topic: str,
    source: str,
) -> list[str]:
    return [
        f"✅ Learn source registered: topic={topic} source={source}",
        f"Report: {result.report_path}",
    ]


def render_learn_refresh_complete(result: LearnSourceLifecycleResult) -> list[str]:
    return [
        (
            "✅ Learn refresh complete: "
            f"refreshed={result.payload['refreshed_count']} skipped={result.payload['skipped_count']}"
        ),
        f"Report: {result.report_path}",
    ]


def render_learn_refresh_plan_complete(result: LearnSourceLifecycleResult) -> list[str]:
    return [
        (
            "✅ Learn refresh plan generated: "
            f"due={result.payload['due_count']} total={result.payload['sources_total']}"
        ),
        f"Report: {result.report_path}",
    ]


def verify_learn_source_lifecycle_completion(
    result: LearnSourceLifecycleResult,
    *,
    completion_verifier: CompletionVerifier | None = None,
) -> None:
    if completion_verifier is None:
        from nexus.engine.completion_contract import ensure_verified_completion

        completion_verifier = ensure_verified_completion
    completion_verifier(result.payload, context=result.command_name)


def run_learn_phase_slo(
    repo_root: str | Path,
    *,
    window: int,
    report_file: str | Path,
    service_factory: LearnModeServiceFactory | None = None,
) -> LearnPhaseReportResult:
    root = Path(repo_root)
    service = (service_factory or _default_learn_mode_service_factory)(root)
    payload = service.build_phase_slo_report(window=window)
    report_path = _write_json_report(root, report_file, payload)
    finalized_payload = _finalize_learn_semantic_payload(
        payload,
        command_name="learn:phase-slo",
        task_name=f"build learn phase slo window={window}",
        runtime_ok=True,
        execution_path="cli->learn_mode_service",
    )
    return LearnPhaseReportResult("learn:phase-slo", finalized_payload, report_path)


def run_learn_phase_kpi(
    repo_root: str | Path,
    *,
    window: int,
    report_file: str | Path,
    service_factory: LearnModeServiceFactory | None = None,
) -> LearnPhaseReportResult:
    root = Path(repo_root)
    service = (service_factory or _default_learn_mode_service_factory)(root)
    payload = service.build_phase_kpi_report(window=window)
    report_path = _write_json_report(root, report_file, payload)
    finalized_payload = _finalize_learn_semantic_payload(
        payload,
        command_name="learn:phase-kpi",
        task_name=f"build learn phase kpi window={window}",
        runtime_ok=True,
        execution_path="cli->learn_mode_service",
    )
    return LearnPhaseReportResult("learn:phase-kpi", finalized_payload, report_path)


def render_learn_phase_slo_complete(result: LearnPhaseReportResult) -> list[str]:
    return [
        "✅ Learn phase SLO summary generated",
        (
            f"phase_slo_pass={result.payload.get('phase_slo_pass')} "
            f"required_done_ratio={result.payload.get('global', {}).get('required_done_ratio', 0.0)}"
        ),
        f"Report: {result.report_path}",
    ]


def render_learn_phase_kpi_complete(result: LearnPhaseReportResult) -> list[str]:
    return [
        "✅ Learn phase KPI report generated",
        (
            f"total_records={result.payload.get('total_records', 0)} "
            f"success_ratio={result.payload.get('global', {}).get('success_ratio', 0.0)} "
            f"required_done_ratio={result.payload.get('global', {}).get('required_done_ratio', 0.0)}"
        ),
        f"Report: {result.report_path}",
    ]


def verify_learn_phase_report_completion(
    result: LearnPhaseReportResult,
    *,
    completion_verifier: CompletionVerifier | None = None,
) -> None:
    if completion_verifier is None:
        from nexus.engine.completion_contract import ensure_verified_completion

        completion_verifier = ensure_verified_completion
    completion_verifier(result.payload, context=result.command_name)


def run_learn_report(
    repo_root: str | Path,
    *,
    topic: str,
    question_count: int,
    pass_threshold: float,
    report_file: str | Path,
    markdown_report_file: str | Path,
    service_factory: LearnModeServiceFactory | None = None,
    markdown_writer: Callable[[Path, Path, str, dict, str, str], Path] | None = None,
    semantic_evaluator: Callable[..., dict[str, Any]] | None = None,
) -> LearnReportResult:
    root = Path(repo_root)
    service = (service_factory or _default_learn_mode_service_factory)(root)
    payload = service.build_report(
        topic=topic,
        question_count=question_count,
        pass_threshold=pass_threshold,
    )
    markdown_path = (markdown_writer or _write_dual_gate_markdown)(
        root,
        Path(markdown_report_file),
        f"learn:report topic={topic or 'all'}",
        payload,
        (
            f"claims_count={payload.get('claims_count', 0)} "
            f"converged={payload.get('converged')} "
            f"citation_valid_ratio={payload.get('citation_valid_ratio', 0.0)}"
        ),
        _format_unresolved_questions_for_debt(payload.get("unresolved_questions")) or "None",
    )
    semantic_contract = (semantic_evaluator or _evaluate_learn_semantic_contract)(
        root=root,
        payload=payload,
        command_name="learn:report",
        markdown_report_written=markdown_path.exists(),
    )
    payload.update(semantic_contract)
    report_path = _write_json_report(root, report_file, payload)
    return LearnReportResult(
        topic=topic,
        payload=payload,
        report_path=report_path,
        markdown_path=markdown_path,
    )


def render_learn_report_complete(result: LearnReportResult) -> list[str]:
    return [
        "✅ Learn report generated",
        (
            f"sources={result.payload['sources_count']} claims={result.payload['claims_count']} "
            f"coverage={result.payload['coverage']} converged={result.payload['converged']}"
        ),
        f"Report: {result.report_path}",
        f"Markdown: {result.markdown_path}",
    ]


def enforce_learn_report_semantic_contract(result: LearnReportResult) -> None:
    if result.payload["semantic_status"] != "VERIFIED":
        raise NexusCliActionError(
            "Learn report semantic contract failed: " + ", ".join(result.payload["semantic_failures"]),
            exit_code=1,
        )


def run_learn_ingest(
    repo_root: str | Path,
    *,
    source: str,
    source_file: str | Path | None,
    topic: str,
    report_file: str | Path,
    markdown_report_file: str | Path,
    evidence_file: str | Path | None,
    service_factory: LearnModeServiceFactory | None = None,
    evidence_writer: EvidenceWriter | None = None,
    hallucination_gate: HallucinationGate | None = None,
    markdown_writer: Callable[[Path, Path, str, dict, str, str], Path] | None = None,
    semantic_evaluator: Callable[..., dict[str, Any]] | None = None,
) -> LearnIngestResult:
    root = Path(repo_root)
    service = (service_factory or _default_learn_mode_service_factory)(root)
    payload = service.ingest(source=source, source_file=source_file, topic=topic)

    final_response = f"Learn ingest finished for source: {source}."
    evidence_bundle = {
        "code_artifacts": ["nexus/research/learn_mode.py"],
        "test_artifacts": [f"claims_count={payload.get('claims_count', 0)}"],
        "command_artifacts": [f"source={source}", f"source_ref={payload.get('source_ref', '')}"],
    }
    evidence_path = _resolve_report_path(root, evidence_file)
    (evidence_writer or _write_learn_hallucination_evidence)(
        evidence_path,
        final_response,
        evidence_bundle,
    )
    (hallucination_gate or _enforce_learn_hallucination_gate)(final_response, evidence_bundle)

    markdown_path = (markdown_writer or _write_dual_gate_markdown)(
        root,
        Path(markdown_report_file),
        f"learn:ingest source={source}",
        payload,
        f"claims_count={payload.get('claims_count', 0)} source_ref={payload.get('source_ref', '')}",
        "None" if payload.get("claims_count", 0) > 0 else "No claims ingested",
    )
    semantic_contract = (semantic_evaluator or _evaluate_learn_semantic_contract)(
        root=root,
        payload=payload,
        command_name="learn:ingest",
        markdown_report_written=markdown_path.exists(),
    )
    payload.update(semantic_contract)
    report_path = _write_json_report(root, report_file, payload)
    return LearnIngestResult(
        source=source,
        payload=payload,
        report_path=report_path,
        markdown_path=markdown_path,
        evidence_path=evidence_path,
    )


def render_learn_ingest_complete(result: LearnIngestResult) -> list[str]:
    return [
        f"✅ Learn ingest complete: {result.source}",
        f"Claims: {result.payload['claims_count']}, Verified: {result.payload['verified_claims_count']}",
        f"Report: {result.report_path}",
        f"Markdown: {result.markdown_path}",
        f"Evidence: {result.evidence_path if result.evidence_path else 'N/A'}",
    ]


def enforce_learn_ingest_semantic_contract(result: LearnIngestResult) -> None:
    if result.payload["semantic_status"] != "VERIFIED":
        raise NexusCliActionError(
            "Learn ingest semantic contract failed: " + ", ".join(result.payload["semantic_failures"]),
            exit_code=1,
        )


def run_learn_gate(
    repo_root: str | Path,
    *,
    topic: str,
    pass_threshold: float,
    citation_valid_min: float,
    claims_min: int,
    report_file: str | Path,
    evidence_file: str | Path | None,
    contract_file: str | Path,
    skip_contract: bool,
    skip_ci: bool,
    service_factory: LearnModeServiceFactory | None = None,
    evidence_writer: EvidenceWriter | None = None,
    hallucination_gate: HallucinationGate | None = None,
    command_runner: CommandRunner | None = None,
    python_executable: str | None = None,
) -> LearnGateResult:
    import sys

    root = Path(repo_root)
    service = (service_factory or _default_learn_mode_service_factory)(root)
    payload = service.build_report(topic=topic)
    report_path = _write_json_report(root, report_file, payload)

    final_response = (
        f"Validated learn gate. topic={topic}, coverage={payload.get('coverage', 0.0)}, "
        f"self_question_pass_rate={payload.get('self_question_pass_rate', 0.0)}."
    )
    evidence_bundle = {
        "code_artifacts": ["nexus/research/learn_mode.py", "scripts/engine/nexus_cli.py"],
        "test_artifacts": [
            f"claims_count={payload.get('claims_count', 0)}",
            f"coverage={payload.get('coverage', 0.0)}",
            f"self_question_pass_rate={payload.get('self_question_pass_rate', 0.0)}",
        ],
        "command_artifacts": [f"topic={topic}", f"report={report_path}"],
        "benchmark_metrics": {
            "success_rate": payload.get("self_question_pass_rate", 0.0),
            "success_threshold": pass_threshold,
        },
    }
    evidence_path = _resolve_report_path(root, evidence_file)
    (evidence_writer or _write_learn_hallucination_evidence)(evidence_path, final_response, evidence_bundle)
    (hallucination_gate or _enforce_learn_hallucination_gate)(final_response, evidence_bundle)

    gate_failures = []
    if float(payload.get("self_question_pass_rate", 0.0)) < pass_threshold:
        gate_failures.append("self_question_pass_rate_below_threshold")
    if float(payload.get("citation_valid_ratio", 0.0)) < citation_valid_min:
        gate_failures.append("citation_valid_ratio_below_threshold")
    if int(payload.get("claims_count", 0)) < claims_min:
        gate_failures.append("claims_count_below_threshold")
    if gate_failures:
        raise NexusCliActionError(f"Learn gate blocked: {', '.join(gate_failures)}", exit_code=1)

    runner = command_runner or _default_command_runner
    executable = python_executable or sys.executable
    cli_path = str(root / "scripts/engine/nexus_cli.py")
    evidence_arg = str(evidence_path)
    runner([executable, cli_path, "nexus", "acceptance-check", "--evidence", evidence_arg])
    runner([executable, cli_path, "nexus", "acceptance-check", "--json", "--evidence", evidence_arg])

    if not skip_contract:
        runner([executable, cli_path, "nexus", "contract-check", "--contract-file", str(contract_file)])

    if not skip_ci:
        runner(
            [
                executable,
                str(root / "scripts/ops/ci_gate.py"),
                "--dry-run",
                "--wiki-drift-enforce-level",
                "p0",
                "--require-closeout-contract",
                "--closeout-contract-path",
                str(contract_file),
                "--learn-mode",
                "smoke",
                "--learn-topic",
                topic,
            ]
        )

    return LearnGateResult(payload=payload, report_path=report_path, evidence_path=evidence_path)


def render_learn_gate_complete(result: LearnGateResult) -> list[str]:
    return [
        "✅ Learn gate PASSED",
        f"Report: {result.report_path}",
        f"Evidence: {result.evidence_path}",
    ]


def run_learn_converge(
    repo_root: str | Path,
    *,
    topic: str,
    max_rounds: int,
    pass_threshold: float,
    question_count: int,
    auto_research: bool,
    max_sources_per_round: int,
    swarm_mode: bool,
    swarm_max_parallel: int,
    per_source_timeout_sec: int,
    report_file: str | Path,
    evidence_file: str | Path | None,
    service_factory: LearnModeServiceFactory | None = None,
    evidence_writer: EvidenceWriter | None = None,
    hallucination_gate: HallucinationGate | None = None,
) -> LearnConvergeResult:
    root = Path(repo_root)
    service = (service_factory or _default_learn_mode_service_factory)(root)
    payload = service.converge(
        topic=topic,
        max_rounds=max_rounds,
        pass_threshold=pass_threshold,
        question_count=question_count,
        auto_research=auto_research,
        max_sources_per_round=max_sources_per_round,
        swarm_mode=swarm_mode,
        swarm_max_parallel=swarm_max_parallel,
        per_source_timeout_sec=per_source_timeout_sec,
    )

    final_response = (
        f"Converge status for topic {topic}: converged={payload.get('converged')}, "
        f"pass_rate={payload.get('self_question_pass_rate')}."
    )
    evidence_bundle = {
        "code_artifacts": ["nexus/research/learn_mode.py"],
        "test_artifacts": [
            f"claims_matched={payload.get('claims_matched', 0)}",
            f"self_question_pass_rate={payload.get('self_question_pass_rate', 0.0)}",
        ],
        "command_artifacts": [f"topic={topic}"],
        "benchmark_metrics": {
            "success_rate": payload.get("self_question_pass_rate", 0.0),
            "success_threshold": pass_threshold,
        },
    }
    evidence_path = _resolve_report_path(root, evidence_file)
    (evidence_writer or _write_learn_hallucination_evidence)(
        evidence_path,
        final_response,
        evidence_bundle,
    )
    (hallucination_gate or _enforce_learn_hallucination_gate)(final_response, evidence_bundle)

    report_path = _resolve_report_path(root, report_file)
    if report_path is None:
        raise NexusCliActionError("learn converge report_file is required", exit_code=1)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return LearnConvergeResult(
        topic=topic,
        payload=payload,
        report_path=report_path,
        evidence_path=evidence_path,
    )


def render_learn_converge_complete(result: LearnConvergeResult) -> list[str]:
    return [
        f"✅ Learn converge complete: topic={result.topic}",
        (
            f"Converged={result.payload['converged']} | "
            f"pass_rate={result.payload['self_question_pass_rate']} | "
            f"coverage={result.payload['coverage']}"
        ),
        f"Report: {result.report_path}",
        f"Evidence: {result.evidence_path if result.evidence_path else 'N/A'}",
    ]


def run_learn_ask(
    repo_root: str | Path,
    *,
    topic: str,
    question: str,
    top_k: int,
    min_evidence: int,
    min_token_coverage: float | None,
    max_staleness_days: int,
    allow_cross_pack: bool,
    evidence_file: str | Path | None,
    service_factory: LearnModeServiceFactory | None = None,
    evidence_writer: EvidenceWriter | None = None,
    hallucination_gate: HallucinationGate | None = None,
) -> LearnAskResult:
    root = Path(repo_root)
    service = (service_factory or _default_learn_mode_service_factory)(root)
    payload = service.ask(
        topic=topic,
        question=question,
        top_k=top_k,
        min_evidence=min_evidence,
        min_token_coverage=min_token_coverage,
        max_staleness_days=max_staleness_days,
        allow_cross_pack=allow_cross_pack,
    )

    final_response = str(payload.get("answer", "UNKNOWN"))
    evidence_bundle = {
        "code_artifacts": ["nexus/research/learn_mode.py"],
        "test_artifacts": [f"claims_used={payload.get('claims_used', 0)}"],
        "command_artifacts": [f"topic={topic}", f"question={question}"],
    }
    evidence_path = _resolve_report_path(root, evidence_file)
    (evidence_writer or _write_learn_hallucination_evidence)(
        evidence_path,
        final_response,
        evidence_bundle,
    )
    (hallucination_gate or _enforce_learn_hallucination_gate)(final_response, evidence_bundle)
    return LearnAskResult(
        topic=topic,
        question=question,
        payload=payload,
        evidence_path=evidence_path,
    )


def render_learn_ask_response(result: LearnAskResult) -> list[str]:
    status = result.payload["status"]
    if status == "UNKNOWN":
        return ["UNKNOWN"]
    if status == "CONFLICT":
        return ["CONFLICT"]
    return [str(result.payload.get("answer", "UNKNOWN"))]


def run_learn_precision_benchmark(
    repo_root: str | Path,
    *,
    manifest_file: str | Path,
    topic: str,
    service_factory: LearnModeServiceFactory | None = None,
) -> dict[str, Any]:
    root = Path(repo_root)
    manifest_data = json.loads(Path(manifest_file).read_text(encoding="utf-8"))
    cases = manifest_data.get("cases") or manifest_data.get("questions", [])
    service = (service_factory or _default_learn_mode_service_factory)(root)
    results = []

    for case in cases:
        question = case.get("q") or case.get("question")
        expected = case.get("expected") or case.get("expected_status")
        if expected == "ANSWERED":
            expected = "ANSWER"

        answer = service.ask(topic=topic, question=question)
        actual = "UNKNOWN" if answer["status"] == "UNKNOWN" else "ANSWER"
        results.append(
            {
                "q": question,
                "expected": expected,
                "actual": actual,
                "is_correct": expected == actual,
                "citations": len(answer.get("citations", [])),
                "noise_filtered": answer.get("filtered_out_count", 0),
            }
        )

    correct = sum(1 for row in results if row["is_correct"])
    precision = sum(1 for row in results if row["expected"] == "ANSWER" and row["actual"] == "ANSWER") / max(
        1,
        sum(1 for row in results if row["actual"] == "ANSWER"),
    )
    unknown_correct_rate = sum(
        1 for row in results if row["expected"] == "UNKNOWN" and row["actual"] == "UNKNOWN"
    ) / max(1, sum(1 for row in results if row["expected"] == "UNKNOWN"))

    return {
        "topic": topic,
        "total": len(results),
        "correct": correct,
        "precision": round(precision, 4),
        "unknown_correct_rate": round(unknown_correct_rate, 4),
        "status": "SUCCESS",
        "baseline": {
            "success_rate": round(precision, 4),
            "answer_precision": round(precision, 4),
            "unknown_accuracy": round(unknown_correct_rate, 4),
            "avg_token_coverage": 0.0,
            "total_questions": len(results),
        },
        "best": {
            "success_rate": round(precision, 4),
            "answer_precision": round(precision, 4),
            "unknown_accuracy": round(unknown_correct_rate, 4),
            "avg_token_coverage": 0.0,
        },
        "results": results,
    }


def write_learn_precision_benchmark_output(summary: dict[str, Any], output: str | Path) -> Path:
    output_path = Path(output)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return output_path


def render_learn_precision_benchmark_complete(summary: dict[str, Any]) -> str:
    return (
        f"✅ Benchmark complete. Precision: {float(summary['precision']):.2%}, "
        f"Unknown Correct: {float(summary['unknown_correct_rate']):.2%}"
    )
