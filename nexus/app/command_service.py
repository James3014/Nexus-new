from pathlib import Path
from typing import Optional

class NexusCommandService:
    """🧬 v9 Command Service: CLI 授權的業務邏輯層"""
    def __init__(self, engine):
        self.engine = engine
        
    def execute_bug(self, task: str, plan_only: bool = False):
        import time
        return self.engine.run_bug(
            bug_id=f"bug-{int(time.time())}",
            desc=task,
            plan_only=plan_only
        )
        
    def execute_feature(self, task: str, domain: Optional[str] = None, dry_run: bool = False, skill: Optional[str] = None):
        return self.engine.run_feature(
            task=task,
            domain=domain,
            dry_run=dry_run,
            skill=skill
        )
        
    def execute_benchmark(self, framework: str, tasks: int, output: str, model: Optional[str] = None, target: Optional[str] = None):
        return self.engine.run_benchmark(
            framework=framework,
            task_count=tasks,
            output_csv=output,
            model=model,
            target=target
        )
