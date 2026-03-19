#!/usr/bin/env python3
import json
import time
import logging
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
from nexus.services.reviewer import CodexLoopV2
from nexus.services.reporter import Reporter
from nexus.engine.phases.planner import PlannerPhaseHandler
from nexus.engine.phases.research import ResearchPhaseHandler
from nexus.engine.phases.repair import RepairPhaseHandler
from nexus.engine.metrics.token_accumulator import TokenAccumulator
from nexus.engine.health.evaluator import HealthEvaluator
from nexus.core.review_status import ReviewStatusNormalizer
from nexus.engine.policies.research_policy import ResearchPolicy
from nexus.engine.pipeline import NexusPipeline


logger = logging.getLogger(__name__)


class NexusEngine:
    """
    ⚙️ Nexus v9 Core Engine
    負責執行 P-D-R-A-C 生命週期循環與業務邏輯調度。
    """

    def __init__(
        self,
        project_root: Path,
        run_dir: Optional[Path] = None,
        silent: bool = False,
        fast_mode: bool = False,
        audit_level: str = "standard",  # bypass, standard, strict
        state_io=None,
        commander=None,
        router=None,
        reporter=None,
        phases: Optional[Dict[str, Any]] = None,
    ):
        self.project_root = project_root
        self.fast_mode = fast_mode
        self.audit_level = audit_level
        self.run_dir = (
            Path(run_dir)
            if run_dir
            else (project_root / ".nexus" / "runs" / f"task-{int(time.time())}")
        )
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self.silent = silent
        self.accumulator = TokenAccumulator()
        self.health_evaluator = HealthEvaluator()
        self.research_policy = ResearchPolicy(fast_mode=fast_mode)
        self.pipeline = NexusPipeline(self)
        self.max_retries = 3
        self.ReviewStatusNormalizer = ReviewStatusNormalizer # Export for pipeline access

        # 🛡️ v9 Hardening: 自動初始化核心組件
        self.state_io = state_io or StateIO(
            str(project_root), run_dir=str(self.run_dir)
        )
        self.router = router or SkillsRouter(project_root, run_dir=str(self.run_dir))
        self.reporter = reporter or Reporter(
            str(project_root), silent=silent, run_dir=str(self.run_dir)
        )
        self.commander = commander or Commander(
            str(self.run_dir), self.state_io, self.router
        )
        self.tracelog_path = self.run_dir / "tracelog.jsonl"
        self.phases = phases or {}

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

    def _voice_notify(self, message: str):
        self.reporter.voice_notify(message)

    def _log_trace(
        self, command: str, task: str, status: str, tokens: int = 0, score: float = 0.0
    ):
        self.reporter.log_trace(command, task, status, tokens, score)

    def _add_step_to_history(
        self,
        state: NexusState,
        phase: str,
        status: str = "completed",
        metadata: Dict[str, Any] = None,
        summary: str = None,
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
        self._voice_notify(f"Nexus 啟動：偵測到 Bug {bug_id}")
        desc_resolved = desc or bug_id
        
        self.reporter.log_trace("run_bug", bug_id, "START", 0, 0.0)
        res = self._run_task_pipeline(
            task_id=bug_id,
            task_desc=desc_resolved,
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
        logger.info(
            "[Nexus:Benchmark] Initializing real-world benchmark run for %s", framework
        )
        self._voice_notify(f"開始執行 {framework} 真實基準測試")
        catalog_path = self.project_root / "cases" / "catalog.json"
        if not catalog_path.exists():
            logger.error("❌ Benchmark catalog not found!")
            return []

        catalog = json.loads(catalog_path.read_text())
        cases_to_run = catalog["cases"][:task_count]

        results = []
        import csv

        for case in cases_to_run:
            case_id = case["id"]
            case_type = case["type"]
            case_file_path = self.project_root / "cases" / case["file"]

            if not case_file_path.exists():
                logger.warning("⚠️ Case file %s missing, skipping.", case["file"])
                continue

            case_data = json.loads(case_file_path.read_text())
            logger.info("🚀 [Benchmark] Running Case: %s", case_id)

            # 🛡️ Force a dummy diff for OFF-001 to ensure LLM is invoked and raw tokens are captured
            dummy_file = self.project_root / "dummy_benchmark_trigger.py"
            if case_id == "OFF-001":
                dummy_file.write_text("# Force diff")
                import subprocess
                subprocess.run(["git", "add", str(dummy_file)], cwd=self.project_root)

            # 建立子任務隔離目錄
            case_run_dir = self.run_dir / case_id
            case_run_dir.mkdir(parents=True, exist_ok=True)

            # 建立局部 Engine 以保持狀態潔淨
            from nexus.containers import NexusContainer

            container = NexusContainer()
            container.project_root.from_value(str(self.project_root))
            container.run_dir.from_value(
                str(case_run_dir)
            )  # 🛡️ FIX: Pass as string to avoid DI dict wrapping

            sub_engine = container.engine_factory(
                silent=True, fast_mode=self.fast_mode, audit_level=self.audit_level
            )

            start_time = time.time()
            success = False
            try:
                if case_type == "bug":
                    success = sub_engine.run_bug(
                        case_id, desc=case_data.get("goal"), context=case_data
                    )
                else:
                    success = sub_engine.run_feature(
                        case_data.get("goal"), context=case_data
                    )
            except Exception as e:
                logger.error("💥 [Benchmark] Case %s crashed: %s", case_id, e)

            duration = time.time() - start_time
            
            # Clean up dummy diff if created
            if dummy_file.exists():
                subprocess.run(["git", "reset", "HEAD", str(dummy_file)], cwd=self.project_root)
                dummy_file.unlink()

            final_state = sub_engine.state_io.load_global_state()

            # Calculate lowest_phase_health for this run
            phase_healths = [m.health for m in final_state.phase_metrics.values() if m.health > 0]
            lowest_ph = min(phase_healths) if phase_healths else 0.0

            # 🧬 統一 Schema 數據採集 (VAR-002)
            res = {
                "task_id": case_id,
                "status": "PASS" if success else "FAIL",
                "tokens": final_state.total_token_usage,
                "token_raw_model": final_state.token_raw_model,
                "token_fallback_est": final_state.token_fallback_est,
                "token_system_overhead": final_state.token_system_overhead,
                "token_source_x": final_state.phase_tokens.get("X", 0),
                "token_source_r": final_state.phase_tokens.get("R", 0),
                "token_capture_status": final_state.token_capture_status,
                "phase_path": " -> ".join([h.phase for h in final_state.steps_history]),
                "review_status": final_state.metadata.get(
                    "last_review_status", "UNKNOWN"
                ),
                "duration": round(duration, 2),
                "health": final_state.health_score,
                "drift": final_state.health_metrics.drift_index,
                "lowest_phase_health": lowest_ph,
                "policy_hit": ",".join(final_state.policy_hit_ids),
                "learning_velocity": final_state.learning_velocity,
            }
            results.append(res)
            logger.info(
                "🏁 [Benchmark] Case %s: %s (Tokens: %d, ph_min: %.1f, v: %.2f)",
                case_id,
                res["status"],
                res["tokens"],
                res["lowest_phase_health"],
                res["learning_velocity"],
            )

        # 輸出 CSV
        if results:
            fieldnames = [
                "task_id",
                "status",
                "tokens",
                "token_raw_model",
                "token_fallback_est",
                "token_system_overhead",
                "token_source_x",
                "token_source_r",
                "token_capture_status",
                "phase_path",
                "review_status",
                "duration",
                "health",
                "drift",
                "lowest_phase_health",
                "policy_hit",
                "learning_velocity",
            ]
            with open(output_csv, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for r in results:
                    writer.writerow(r)
            logger.info("💾 [Benchmark] Results saved to %s", output_csv)

        return results
