#!/usr/bin/env python3
import json
import time
import logging
import subprocess
from enum import Enum
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any


class RepairStrategy(str, Enum):
    L1_QUICK = "L1"  # One-shot, minimal loop
    L2_STANDARD = "L2"  # Standard 5-turn loop
    L3_DEEP = "L3"  # 10-turn, researcher enabled, cost-heavy


from nexus.core.commander import Commander
from nexus.core.state_io import StateIO
from nexus.core.router import SkillsRouter
from nexus.core.state_contracts import NexusState
from nexus.services.reporter import Reporter
from nexus.core.review_status import ReviewStatusNormalizer
from nexus.engine.pipeline import NexusPipeline
from nexus.benchmark.workspace import BenchmarkWorkspace

logger = logging.getLogger(__name__)


from nexus.engine.config import EngineConfig

class NexusEngine:
    """
    ⚙️ Nexus v9 Core Engine
    負責執行 P-D-R-A-C 生命週期循環與業務邏輯調度。
    """

    def __init__(
        self,
        config: EngineConfig,
        state_io=None,
        commander=None,
        router=None,
        reporter=None,
        phases: Optional[Dict[str, Any]] = None,
        accumulator=None,
        health_evaluator=None,
        research_policy=None,
    ):
        self.config = config
        self.project_root = config.project_root
        self.fast_mode = config.fast_mode
        self.audit_level = config.audit_level
        self.silent = config.silent
        
        # 處理 run_dir
        if config.run_dir:
            self.run_dir = Path(config.run_dir)
        else:
            self.run_dir = self.project_root / ".nexus" / "runs" / f"task-{int(time.time())}"
            
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.max_retries = 3
        self.tracelog_path = self.run_dir / "tracelog.jsonl"

        # Dependencies injected or fallback initialized
        from nexus.engine.metrics.token_accumulator import TokenAccumulator
        from nexus.engine.health.evaluator import HealthEvaluator
        from nexus.engine.policies.research_policy import ResearchPolicy
        self.accumulator = accumulator or TokenAccumulator()
        self.health_evaluator = health_evaluator or HealthEvaluator()
        self.research_policy = research_policy or ResearchPolicy(fast_mode=self.fast_mode)
        
        self.state_io = state_io or StateIO(str(self.project_root), run_dir=str(self.run_dir))
        self.router = router or SkillsRouter(self.project_root, run_dir=str(self.run_dir))
        self.reporter = reporter or Reporter(str(self.project_root), silent=self.silent, run_dir=str(self.run_dir))
        self.commander = commander or Commander(str(self.run_dir), self.state_io, self.router)
        self.phases = phases or self._build_default_phases()
        
        self.pipeline = NexusPipeline(self)
        self.ReviewStatusNormalizer = ReviewStatusNormalizer
        self._memory = None
        self._policy_manager = None
        
        # OTel Initialization
        from nexus.telemetry.otel_config import init_otel
        init_otel(project_root=self.project_root)

    def _build_default_phases(self) -> Dict[str, Any]:
        """Lazy load default phases to reduce __init__ complexity and top-level coupling."""
        from nexus.engine.phases.planner import PlannerPhaseHandler
        from nexus.engine.phases.research import ResearchPhaseHandler
        from nexus.engine.phases.repair import RepairPhaseHandler
        from nexus.engine.phases.diagnose import DiagnosticPhaseHandler
        return {
            "P": PlannerPhaseHandler(project_root=self.project_root, run_dir=self.run_dir),
            "X": ResearchPhaseHandler(project_root=self.project_root, run_dir=self.run_dir),
            "D": DiagnosticPhaseHandler(project_root=self.project_root, run_dir=self.run_dir, hub=self.hub),
            "R": RepairPhaseHandler(
                project_root=self.project_root,
                run_dir=self.run_dir,
                router=self.router,
                orchestrator_factory=None,
            ),
        }

    @property
    def hub(self):
        """🛡️ v9.2: Ensure ContextHub availability via Commander"""
        if hasattr(self, "_hub") and self._hub:
            return self._hub
        if self.commander and self.commander.hub:
            return self.commander.hub
        # Last resort fallback if commander fails
        from nexus.core.context_hub import ContextHub

        # 🛡️ v9.2.1 Fix: pass project_root AND run_dir
        self._hub = ContextHub(str(self.project_root), run_dir=str(self.run_dir))
        return self._hub

    @property
    def memory(self):
        """🧠 v9.3: Lazy-loaded MemoryService for semantic learning."""
        if self._memory is None:
            from nexus.services.memory import MemoryService
            self._memory = MemoryService(
                project_root=str(self.project_root),
                run_dir=str(self.run_dir),
                silent=self.silent
            )
        return self._memory

    @property
    def policy_manager(self):
        """📔 Lazy-loaded policy manager used by the pipeline policy phase."""
        if self._policy_manager is None:
            from nexus.core.policy_manager import PolicyManager

            self._policy_manager = PolicyManager(
                project_root=str(self.project_root),
                run_dir=str(self.run_dir),
            )
        return self._policy_manager

    def _voice_notify(self, message: str, urgency: str = "normal"):
        """🧬 Smart-Notify: 分優先級的語音通報"""
        self.reporter.voice_notify(message, urgency=urgency)

    def _log_trace(
        self, command: str, task: str, status: str, tokens: int = 0, score: float = 0.0
    ):
        self.reporter.log_trace(command, task, status, tokens, score)

    def _add_step_to_history(
        self,
        state: NexusState,
        phase: str,
        status: str = "completed",
        metadata: Optional[Dict[str, Any]] = None,
        summary: Optional[str] = None,
    ):
        """🧬 Nexus Soul Protocol: Record step into history for auditability."""
        from nexus.core.state_contracts import StepRecord
        from datetime import datetime

        step = StepRecord(
            phase=phase,
            step_id=f"{phase}-{int(time.time() * 1000)}",
            status=status,
            started_at=datetime.now(),
            ended_at=datetime.now(),
            metadata=metadata or {},
            summary=summary,
        )
        state.steps_history.append(step)
        self.state_io.save_global_state(state)

    # The _normalize_review_status method is removed as per instruction to replace its implementation
    # and use ReviewStatusNormalizer directly.

    def _run_task_pipeline(self, task_desc: str, task_type: str = "bug", context: Optional[Dict] = None, **kwargs) -> bool:
        """🧬 Redirection to modular NexusPipeline."""
        return self.pipeline.run(task_desc, task_type, context, **kwargs)
    def run_bug(
        self,
        bug_id: str,
        desc: str = None,
        manual_files: List[str] = None,
        plan_only: bool = False,
        context: Dict = None,
    ):
        """🕷️ Nexus P-D-X-R-A-C Lifecycle (Unified Redirect)"""
        self._voice_notify(f"Nexus 啟動：偵測到 Bug {bug_id}", urgency="critical")
        logger.info(f"🚀 [Nexus] Starting L2-Repair for {bug_id}")
        desc_resolved = desc or bug_id
        
        self.reporter.log_trace("run_bug", bug_id, "START", 0, 0.0)
        res = self._run_task_pipeline(
            desc_resolved, 
            task_id=bug_id,
            task_type="bug",
            context=context,
            dry_run=plan_only,
            manual_files=manual_files
        )
        status = "SUCCESS" if res else "FAIL"
        self.reporter.log_trace("run_bug", bug_id, status, self.accumulator.total_tokens_used, 0.0)
        return res


    def run_feature(
        self,
        task: str,
        context: Dict = None,
        dry_run: bool = False,
        domain: str = None,
        skill: str = None,
    ):
        """🏗️ Nexus Feature Build (Unified Redirect)"""
        self._voice_notify("開始建置新功能")
        task_id = f"feat-{int(time.time())}"
        
        self.reporter.log_trace("run_feature", task, "START", 0, 0.0)
        res = self._run_task_pipeline(
            task_id=task_id,
            task_desc=task,
            task_type="feature",
            context=context,
            domain=domain,
            skill=skill
        )
        status = "SUCCESS" if res else "FAIL"
        self.reporter.log_trace("run_feature", task, status, self.accumulator.total_tokens_used, 0.0)
        return res

    def run_benchmark(
        self,
        framework: str,
        task_count: int = 10,
        output_csv: str = "nexus_benchmark.csv",
        model: str = None,
        target: str = None,
        dry_run: bool = False,
    ):
        """📊 真實執行基準測試 (IMP-102)"""
        from nexus.benchmark.benchmark_runner import BenchmarkRunner
        runner = BenchmarkRunner(
            self.project_root, 
            self.run_dir, 
            self.reporter, 
            self.fast_mode, 
            self.audit_level
        )
        return runner.run(
            framework=framework,
            task_count=task_count,
            output_csv=output_csv,
            model=model,
            target=target,
            dry_run=dry_run,
        )
