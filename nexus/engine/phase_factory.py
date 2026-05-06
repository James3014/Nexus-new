from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nexus.engine.phase_plugin import PhaseExecutor


@dataclass(frozen=True)
class PhaseFactory:
    """Single construction seam for composition phase executors."""

    project_root: Path
    run_dir: Path
    hub: Any = None

    def create_phase(self, phase: str) -> PhaseExecutor:
        phase = str(phase or "").strip().upper()
        from nexus.engine import phase_executors

        if phase == "P":
            return phase_executors.build_plan_executor(self.project_root, self.run_dir)
        if phase == "X":
            return phase_executors.build_research_executor(self.project_root, self.run_dir)
        if phase == "D":
            return phase_executors.build_diagnose_executor(self.project_root, self.run_dir, hub=self.hub)
        if phase == "R":
            return phase_executors.build_repair_executor(self.project_root, self.run_dir)
        if phase == "A":
            return phase_executors.build_audit_executor(self.project_root, self.run_dir)
        if phase == "C":
            return phase_executors.build_crystallize_executor(self.project_root, self.run_dir)
        raise ValueError(f"unknown_phase:{phase}")

    def create_all(self) -> dict[str, PhaseExecutor]:
        return {phase: self.create_phase(phase) for phase in ("P", "X", "D", "R", "A", "C")}
