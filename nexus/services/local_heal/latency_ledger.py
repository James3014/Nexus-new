"""Latency Ledger: observation-only phase timing for local hybrid pipeline."""
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class PhaseTiming:
    """Timing record for a single phase execution."""
    phase_name: str
    start_sec: float = 0.0
    end_sec: float = 0.0
    duration_sec: float = 0.0
    model_invoked: str = ""  # "3b", "7b", "14b", "none", "deterministic"
    model_time_sec: float = 0.0
    non_model_overhead_sec: float = 0.0
    success: bool = True
    error: str = ""


@dataclass
class LatencyLedger:
    """Complete latency record for one repair pipeline execution."""
    task_id: str = ""
    instance_id: str = ""
    wall_start: float = 0.0
    wall_end: float = 0.0
    wall_time_sec: float = 0.0
    phases: List[PhaseTiming] = field(default_factory=list)
    retry_count: int = 0
    total_model_time_sec: float = 0.0
    total_non_model_overhead_sec: float = 0.0
    cold_start_sec: float = 0.0
    model_tokens_by_phase: Dict[str, int] = field(default_factory=dict)
    
    def start_phase(self, phase_name: str) -> PhaseTiming:
        """Record phase start time."""
        pt = PhaseTiming(phase_name=phase_name, start_sec=time.monotonic())
        self.phases.append(pt)
        return pt
    
    def end_phase(self, phase_timing: PhaseTiming, **kwargs) -> None:
        """Record phase end time and optional metadata."""
        phase_timing.end_sec = time.monotonic()
        phase_timing.duration_sec = phase_timing.end_sec - phase_timing.start_sec
        for k, v in kwargs.items():
            if hasattr(phase_timing, k):
                setattr(phase_timing, k, v)
    
    def finalize(self) -> None:
        """Compute aggregate metrics."""
        self.wall_time_sec = self.wall_end - self.wall_start
        self.total_model_time_sec = sum(p.model_time_sec for p in self.phases)
        self.total_non_model_overhead_sec = sum(p.non_model_overhead_sec for p in self.phases)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for receipt."""
        return {
            "task_id": self.task_id,
            "instance_id": self.instance_id,
            "wall_time_sec": round(self.wall_time_sec, 3),
            "phases": [
                {
                    "name": p.phase_name,
                    "duration_sec": round(p.duration_sec, 3),
                    "model_invoked": p.model_invoked,
                    "model_time_sec": round(p.model_time_sec, 3),
                    "non_model_overhead_sec": round(p.non_model_overhead_sec, 3),
                    "success": p.success,
                    "error": p.error,
                }
                for p in self.phases
            ],
            "retry_count": self.retry_count,
            "total_model_time_sec": round(self.total_model_time_sec, 3),
            "total_non_model_overhead_sec": round(self.total_non_model_overhead_sec, 3),
            "cold_start_sec": round(self.cold_start_sec, 3),
            "model_tokens_by_phase": self.model_tokens_by_phase,
        }
