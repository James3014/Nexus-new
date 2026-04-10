import click
from pathlib import Path

class NexusEngineService:
    """
    ⚙️ Nexus Engine Service (Refactored)
    負責執行核心修復 (Bug) 與開發 (Feature) 任務。
    """
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def run_bug(self, task: str, dry_run: bool):
        from nexus.engine.coordinator import NexusEngine
        from nexus.engine.config import EngineConfig
        config = EngineConfig(project_root=self.repo_root)
        engine = NexusEngine(config=config)
        run_bug = getattr(engine, "run_bug")
        if dry_run:
            click.echo(f"🧪 [Dry-Run] Testing Transaction Rollback for: {task}")
            return run_bug(bug_id="test-rollback", desc=task)
        return run_bug(desc=task)

    def run_feature(self, roadmap_str: str):
        from nexus.engine.coordinator import NexusEngine
        from nexus.engine.config import EngineConfig
        config = EngineConfig(project_root=self.repo_root)
        engine = NexusEngine(config=config)
        run_feature = getattr(engine, "run_feature")
        return run_feature(desc=roadmap_str)
