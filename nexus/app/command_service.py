from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from nexus.delivery.gate import evaluate_completion
from nexus.delivery.models import CompletionRequest
from nexus.delivery.models import CompletionResult
from nexus.delivery.models import TaskLevel
from nexus.delivery.report import write_report_bundle
from nexus.delivery.suggestions import suggest_verification_commands
from nexus.health.ops import run_self_check
from nexus.health.ops import run_health_explain
from nexus.health.ops import run_self_heal

@dataclass
class TaskRequest:
    """任務下發的參數封裝。"""
    task: str
    task_id: Optional[str] = None
    plan_only: bool = False
    delivery_mode: str = "standard"
    verify_commands: Optional[List[str]] = None
    artifact_paths: Optional[List[str]] = None
    domain: Optional[str] = None
    skill: Optional[str] = None
    execution_context: Optional[Dict[str, Any]] = None
    # 🧬 進化戰術參數
    swarm_mode: bool = False
    use_sota_cache: bool = False

class NexusCommandService:
    """🧬 v9 Command Service: CLI 授權的業務邏輯層。

    This service is the canonical execution seam for task-style bug/feature work.
    Direct ``engine.run_bug`` / ``engine.run_feature`` calls should be routed here
    so delivery mode, suggested verification, report emission, and completion gate
    behavior stay centralized.
    """
    def __init__(self, engine):
        self.engine = engine
        self.last_completion_result: Optional[CompletionResult] = None
        self.last_completion_report_paths: tuple[Path, Path] | None = None
        self.last_completion_error: Optional[str] = None
        self.last_effective_verify_commands: list[str] = []
        self.last_self_check_result = None
        self.last_self_heal_result = None
        self.last_health_explain_result = None

    def _run_completion_gate(
        self,
        *,
        task_name: str,
        task_level: TaskLevel,
        delivery_mode: str,
        verify_commands: Optional[list[str]] = None,
        artifact_paths: Optional[list[str]] = None,
    ) -> bool:
        self.last_completion_result = None
        self.last_completion_report_paths = None
        self.last_completion_error = None
        self.last_effective_verify_commands = []
        if delivery_mode != "high":
            return True

        commands = list(verify_commands or [])
        if not commands:
            commands = suggest_verification_commands(self.engine.project_root, task_name)
        if not commands:
            self.last_completion_error = "high_delivery_requires_verify_commands"
            return False
        self.last_effective_verify_commands = commands[:]

        request = CompletionRequest(
            task_name=task_name,
            task_level=task_level,
            verification_commands=commands,
            artifact_paths=[Path(path) for path in (artifact_paths or [])],
            cwd=self.engine.project_root,
        )
        result = evaluate_completion(request)
        output_dir = self.engine.run_dir / "delivery"
        self.last_completion_report_paths = write_report_bundle(result, output_dir)
        self.last_completion_result = result
        if not result.gate_passed:
            self.last_completion_error = result.status.value
        return result.gate_passed
        
    def execute_bug(self, request: TaskRequest):
        """Execute a bug task through the sole delivery-aware service boundary."""
        import time
        bug_id = request.task_id or f"bug-{int(time.time())}"
        merged_context = dict(request.execution_context or {})
        if request.plan_only:
            # Dry-run should be deterministic and fast
            merged_context.setdefault("benchmark_run", True)
            merged_context.setdefault("auto_repair_enabled", False)
        
        success = self.engine.run_bug(
            bug_id=bug_id,
            desc=request.task,
            plan_only=request.plan_only,
            context={
                "delivery_mode": request.delivery_mode, 
                "swarm_mode": request.swarm_mode,
                "use_sota_cache": request.use_sota_cache,
                **merged_context
            },
        )
        if not success:
            return False
        return self._run_completion_gate(
            task_name=bug_id,
            task_level=TaskLevel.SMALL_FIX,
            delivery_mode=request.delivery_mode,
            verify_commands=request.verify_commands,
            artifact_paths=request.artifact_paths,
        )

    def execute_feature(self, request: TaskRequest):
        """Execute a feature task through the sole delivery-aware service boundary."""
        import time
        success = self.engine.run_feature(
            task=request.task,
            context={
                "delivery_mode": request.delivery_mode, 
                "swarm_mode": request.swarm_mode,
                "use_sota_cache": request.use_sota_cache,
                **(request.execution_context or {})
            },
            domain=request.domain,
            dry_run=request.plan_only,
            skill=request.skill
        )
        if not success:
            return False
        return self._run_completion_gate(
            task_name=request.task_id or f"feat-{int(time.time())}",
            task_level=TaskLevel.FEATURE,
            delivery_mode=request.delivery_mode,
            verify_commands=request.verify_commands,
            artifact_paths=request.artifact_paths,
        )

    def execute_refactor(self, request: TaskRequest):
        """🛰️ v22-Linus Phase 2: 執行漸進式重構指令"""
        from nexus.services.refactor_engine import RefactorEngine
        import time
        refactor = RefactorEngine(self.engine.project_root)
        
        # 1. 物理生成重構 DAG 計畫
        plan = refactor.generate_plan(request.task)
        
        # 2. 彙整計畫摘要
        summary_lines = ["Progressive Refactor DAG Generated:"]
        for node in plan:
            summary_lines.append(f"- [{node['priority']}] {node['file']} -> {node['task']} (|linus-mode|)")
            
        return {
            "task_id": f"refactor_dag_{int(time.time())}",
            "summary": "\n".join(summary_lines),
            "plan": plan
        }
        
    def execute_research(self, request: TaskRequest):
        """執行 SOTA 學術錨定搜尋任務。"""
        return self.engine.run_research(
            query=request.task,
            use_cache=request.use_sota_cache,
            context=request.execution_context
        )
        
    def execute_benchmark(self, framework: str, tasks: int, output: str, model: Optional[str] = None, target: Optional[str] = None, swarm_mode: bool = False):
        """🛰️ v22-ARC Phase 3: 執行基準測試並產出價值對比報表"""
        result = self.engine.run_benchmark(
            framework=framework,
            task_count=tasks,
            output_csv=output,
            model=model,
            target=target,
            swarm_mode=swarm_mode
        )
        
        # 🧪 物理導通：針對 ARC-AGI 輸出專屬結論
        if framework == "arc-agi":
            # 聚合結果 (如果是列表)
            if isinstance(result, list) and len(result) > 0:
                # 取最後一個點的聚合數據，或者從列表中提取
                main_res = result[-1] if isinstance(result[-1], dict) else {}
            else:
                main_res = result if isinstance(result, dict) else {}
                
            score = main_res.get("score_pct", 0.0)
            conclusion = main_res.get("conclusion", "N/A")
            print(f"\n📊 [Benchmark] ARC-AGI Vision Stress Test Result")
            print("-" * 50)
            print(f"Score: {score:.2f}% (Human: 85%)")
            print(f"Conclusion: {conclusion}")
            print("-" * 50)
            
        return result

    def execute_self_check(self, level: str = "standard"):
        self.last_self_check_result = run_self_check(self.engine, level=level)
        return self.last_self_check_result

    def execute_self_heal(self, mode: str = "standard"):
        self.last_self_heal_result = run_self_heal(self.engine, mode=mode)
        return self.last_self_heal_result

    def execute_autopilot_accelerate(self, samples: int = 28, mode: str = "spst"):
        """⚡ Phase 2.4 主動衝刺接口"""
        return self.engine.run_autopilot_accelerate(samples=samples, mode=mode)

    def execute_health_explain(self):
        self.last_health_explain_result = run_health_explain(self.engine)
        return self.last_health_explain_result
