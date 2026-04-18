import os
from nexus.orchestrator.file_lock_registry import FileLockRegistry

class SecurityGate:
    def __init__(self, registry: FileLockRegistry):
        self.registry = registry

    def validate_write_access(self, task_id: str, files: list[str]) -> list[str]:
        """Returns list of unauthorized files."""
        unauthorized = []
        for f in files:
            if not self.registry.check_access(task_id, f):
                unauthorized.append(f)
        return unauthorized

    def enforce_briefing(self, task_id: str):
        """Enforces the v2.4 briefing requirement."""
        briefing_path = ".nexus/reports/enforced_agent_briefing.md"
        if not os.path.exists(briefing_path):
            raise RuntimeError(f"MISSING: {briefing_path}. Agent briefing is mandatory.")
# v24.13 final hardening
