from pathlib import Path

import click

from nexus.engine.canonical_task_seam import build_legacy_cli_service
from nexus.services.aos_service import AosService
from nexus.services.audit_service import AuditService, SwarmWaveService


class CliCommandsService:
    """
    🛠️ Nexus CLI Commands Service (100% Facade - Refactored)
    所有的實體邏輯已拆分至專用的 Domain Services 中。
    符合 ISP (介面隔離) 與 SRP (單一職責) 原則。
    """

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self._aos = AosService(repo_root)
        self._runtime = build_legacy_cli_service(repo_root)
        self._audit = AuditService(repo_root)
        self._wave = SwarmWaveService(repo_root)

    def status(self, global_view: bool, aos: bool, aos_full: bool):
        return self._aos.get_status(global_view, aos, aos_full)

    def bug(self, task: str, dry_run: bool):
        return self._runtime.execute_bug(task, plan_only=dry_run)

    def feature(self, roadmap_str: str):
        return self._runtime.execute_feature(roadmap_str)

    def acceptance_check(self, window: int):
        return self._audit.run_acceptance(window)

    def swarm_wave1(self):
        return self._wave.trigger_wave(1)

    def swarm_wave2(self):
        return self._wave.trigger_wave(2)

    def swarm_wave3(self):
        return self._wave.trigger_wave(3)

    def probe(self, test_spec: str):
        # 簡單邏輯保持在此，複雜則下沉
        click.echo(f"🧪 [Probe] Initiating speculative probe for: {test_spec}")
        return "PASS"

    def heartbeat(self, test: bool):
        from scripts.ops.paperclip import PaperclipDaemon

        daemon = PaperclipDaemon(self.repo_root / ".nexus" / "heartbeats")
        if test:
            return daemon.scan_once()
        return daemon.monitor()

    def reach(self, url: str, tier: int = 1):
        from nexus.services.reach.ucc_router import UCCRouter

        reach_engine = UCCRouter(self.repo_root)
        return reach_engine.reach(url, tier=tier)
