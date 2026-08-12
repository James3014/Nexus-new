from pathlib import Path

import click


class AuditService:
    """🧪 Audit & Quality Gate Service"""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def run_acceptance(self, window: int):
        from scripts.ops.nexus_acceptance_check import run_acceptance

        return run_acceptance(project_root=self.repo_root, window=window)


class SwarmWaveService:
    """⚡ Swarm Wave Orchestration Service"""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def trigger_wave(self, wave_num: int):
        click.echo(f"⚡ [Swarm] Triggering Wave {wave_num}...")
        # 實體 Wave 邏輯遷移至此
        return {"status": "SUCCESS", "wave": wave_num}
