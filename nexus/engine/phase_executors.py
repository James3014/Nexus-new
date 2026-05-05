from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexus.engine.phase_plugin import PhaseExecutor, PhaseResult


@dataclass
class HandlerPhaseExecutor:
    """Composition adapter around legacy BasePhaseHandler implementations."""

    handler: Any

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
            return execute(pipeline, ctx)
        result = self.handler.run(ctx.state, ctx.pack)
        return PhaseResult(status="success", mutations=dict(result or {}), events=[])


def build_plan_executor(project_root: Any, run_dir: Any, **kwargs: Any) -> PhaseExecutor:
    from nexus.engine.phases.planner import PlannerPhaseHandler

    return HandlerPhaseExecutor(PlannerPhaseHandler(project_root, run_dir, **kwargs))


def build_research_executor(project_root: Any, run_dir: Any) -> PhaseExecutor:
    from nexus.engine.phases.research import ResearchPhaseHandler

    return HandlerPhaseExecutor(ResearchPhaseHandler(project_root, run_dir))


def build_diagnose_executor(project_root: Any, run_dir: Any, hub: Any) -> PhaseExecutor:
    from nexus.engine.phases.diagnose import DiagnosticPhaseHandler

    return HandlerPhaseExecutor(DiagnosticPhaseHandler(project_root, run_dir, hub=hub))


def build_repair_executor(project_root: Any, run_dir: Any, **kwargs: Any) -> PhaseExecutor:
    from nexus.engine.phases.repair import RepairPhaseHandler

    return HandlerPhaseExecutor(RepairPhaseHandler(project_root, run_dir, **kwargs))
