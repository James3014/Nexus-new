from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from nexus.engine.phase_plugin import PhaseExecutor, PhaseResult

FAIL_STATUSES = frozenset({"FAIL", "FAILED", "REJECTED", "REJECTED_NO_RED_TEST"})


@dataclass
class HandlerPhaseExecutor:
    """Composition adapter around legacy BasePhaseHandler implementations."""

    handler: Any
    result_binder: Callable[[Any, dict[str, Any]], None] | None = None

    @property
    def name(self) -> str:
        return str(getattr(self.handler, "name", ""))

    @property
    def priority(self) -> int:
        return int(getattr(self.handler, "priority", 100) or 100)

    def should_run(self, ctx: Any) -> bool:
        should = getattr(self.handler, "should_run", None)
        return bool(should(ctx)) if callable(should) else True

    def execute(self, pipeline: Any, ctx: Any) -> PhaseResult:
        execute = getattr(self.handler, "execute", None)
        if callable(execute):
            result = execute(pipeline, ctx)
            mutations = dict(result.mutations or {})
            if self.result_binder is not None:
                self.result_binder(ctx, mutations)
            return PhaseResult(status=result.status, mutations=mutations, events=result.events or [])
        result = self.handler.run(ctx.state, ctx.pack)
        mutations = dict(result or {})
        if self.result_binder is not None:
            self.result_binder(ctx, mutations)
        status_text = str(mutations.get("status") or "").strip().upper()
        status = "fail" if mutations.get("fail") or status_text in FAIL_STATUSES else "success"
        return PhaseResult(status=status, mutations=mutations, events=[])


@dataclass
class PipelineMethodPhaseExecutor:
    """Composition seam for rich pipeline methods that are not safe to replace yet."""

    name: str
    priority: int
    method_name: str

    def should_run(self, ctx: Any) -> bool:
        return self.name not in set(ctx.kwargs.get("skip_phases", [])) if hasattr(ctx, "kwargs") else True

    def execute(self, pipeline: Any, ctx: Any) -> PhaseResult:
        method = getattr(pipeline, self.method_name)
        success = bool(getattr(ctx, "state").metadata.get("pipeline_success", False))
        method(ctx, success, getattr(ctx, "tracer", None))
        mutations = {"status": "COMPLETED", "pipeline_success": success}
        ctx.pack["crystallize"] = mutations
        return PhaseResult(status="success", mutations=mutations, events=[])


def _bind_plan(ctx: Any, mutations: dict[str, Any]) -> None:
    ctx.prediction = mutations
    ctx.pack["prediction"] = mutations


def _bind_research(ctx: Any, mutations: dict[str, Any]) -> None:
    ctx.research_pack = mutations
    ctx.pack["research_pack"] = mutations


def _bind_diagnose(ctx: Any, mutations: dict[str, Any]) -> None:
    ctx.pack = mutations


def build_plan_executor(project_root: Any, run_dir: Any, **kwargs: Any) -> PhaseExecutor:
    from nexus.engine.phases.planner import PlannerPhaseHandler

    return HandlerPhaseExecutor(
        PlannerPhaseHandler(project_root, run_dir, **kwargs),
        result_binder=_bind_plan,
    )


def build_research_executor(project_root: Any, run_dir: Any) -> PhaseExecutor:
    from nexus.engine.phases.research import ResearchPhaseHandler

    return HandlerPhaseExecutor(
        ResearchPhaseHandler(project_root, run_dir),
        result_binder=_bind_research,
    )


def build_diagnose_executor(project_root: Any, run_dir: Any, hub: Any) -> PhaseExecutor:
    from nexus.engine.phases.diagnose import DiagnosticPhaseHandler

    return HandlerPhaseExecutor(
        DiagnosticPhaseHandler(project_root, run_dir, hub=hub),
        result_binder=_bind_diagnose,
    )


def build_repair_executor(project_root: Any, run_dir: Any, **kwargs: Any) -> PhaseExecutor:
    from nexus.engine.phases.repair import RepairPhaseHandler

    return HandlerPhaseExecutor(RepairPhaseHandler(project_root, run_dir, **kwargs))


def build_audit_executor(project_root: Any, run_dir: Any) -> PhaseExecutor:
    from nexus.engine.phases.audit import AuditPhaseHandler

    return HandlerPhaseExecutor(AuditPhaseHandler(project_root, run_dir, name="A", priority=40))


def build_crystallize_executor(project_root: Any, run_dir: Any) -> PhaseExecutor:
    return PipelineMethodPhaseExecutor(name="C", priority=50, method_name="_stage_crystallize")
