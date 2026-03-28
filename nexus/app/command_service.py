from pathlib import Path
from pathlib import Path
from typing import Optional

from nexus.delivery.gate import evaluate_completion
from nexus.delivery.models import CompletionRequest
from nexus.delivery.models import CompletionResult
from nexus.delivery.models import TaskLevel
from nexus.delivery.report import write_report_bundle
from nexus.delivery.suggestions import suggest_verification_commands
from nexus.health.ops import run_self_check
from nexus.health.ops import run_health_explain
from nexus.health.ops import run_self_heal

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
        
    def execute_bug(
        self,
        task: str,
        plan_only: bool = False,
        delivery_mode: str = "standard",
        verify_commands: Optional[list[str]] = None,
        artifact_paths: Optional[list[str]] = None,
        bug_id: Optional[str] = None,
        execution_context: Optional[dict] = None,
    ):
        """Execute a bug task through the sole delivery-aware service boundary."""
        import time
        bug_id = bug_id or f"bug-{int(time.time())}"
        merged_context = dict(execution_context or {})
        if plan_only:
            # Dry-run should be deterministic and fast:
            # skip self-heal/task-runner side loops by marking benchmark_run.
            merged_context.setdefault("benchmark_run", True)
            merged_context.setdefault("auto_repair_enabled", False)
        success = self.engine.run_bug(
            bug_id=bug_id,
            desc=task,
            plan_only=plan_only,
            context={"delivery_mode": delivery_mode, **merged_context},
        )
        if not success:
            return False
        return self._run_completion_gate(
            task_name=bug_id,
            task_level=TaskLevel.SMALL_FIX,
            delivery_mode=delivery_mode,
            verify_commands=verify_commands,
            artifact_paths=artifact_paths,
        )
        
    def execute_feature(
        self,
        task: str,
        domain: Optional[str] = None,
        dry_run: bool = False,
        skill: Optional[str] = None,
        delivery_mode: str = "standard",
        verify_commands: Optional[list[str]] = None,
        artifact_paths: Optional[list[str]] = None,
        execution_context: Optional[dict] = None,
    ):
        """Execute a feature task through the sole delivery-aware service boundary."""
        success = self.engine.run_feature(
            task=task,
            context={"delivery_mode": delivery_mode, **(execution_context or {})},
            domain=domain,
            dry_run=dry_run,
            skill=skill
        )
        if not success:
            return False
        return self._run_completion_gate(
            task_name=task,
            task_level=TaskLevel.FEATURE,
            delivery_mode=delivery_mode,
            verify_commands=verify_commands,
            artifact_paths=artifact_paths,
        )
        
    def execute_benchmark(self, framework: str, tasks: int, output: str, model: Optional[str] = None, target: Optional[str] = None):
        return self.engine.run_benchmark(
            framework=framework,
            task_count=tasks,
            output_csv=output,
            model=model,
            target=target
        )

    def execute_self_check(self, level: str = "standard"):
        self.last_self_check_result = run_self_check(self.engine, level=level)
        return self.last_self_check_result

    def execute_self_heal(self, mode: str = "standard"):
        self.last_self_heal_result = run_self_heal(self.engine, mode=mode)
        return self.last_self_heal_result

    def execute_health_explain(self):
        self.last_health_explain_result = run_health_explain(self.engine)
        return self.last_health_explain_result
