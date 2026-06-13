import time
from typing import Dict, Optional
from nexus.engine.contracts.execution import ExecutionPhase, PhaseTiming

class PhaseTimer:
    """
    ⏱️ PhaseTimer: 計時器，追蹤補丁套用各相位的耗時
    """
    def __init__(self):
        self._active_phase: Optional[ExecutionPhase] = None
        self._start_times: Dict[ExecutionPhase, float] = {}
        self.timings: Dict[ExecutionPhase, PhaseTiming] = {}

    def start(self, phase: ExecutionPhase):
        self._active_phase = phase
        self._start_times[phase] = time.time()
        if phase not in self.timings:
            self.timings[phase] = PhaseTiming(phase=phase, status="RUNNING")
        else:
            self.timings[phase].status = "RUNNING"

    def stop(self, phase: ExecutionPhase):
        if phase in self._start_times:
            elapsed = time.time() - self._start_times[phase]
            if phase not in self.timings:
                self.timings[phase] = PhaseTiming(phase=phase, wall_time_sec=elapsed, status="COMPLETED")
            else:
                self.timings[phase].wall_time_sec += elapsed
                self.timings[phase].status = "COMPLETED"
            self._start_times.pop(phase, None)
        if self._active_phase == phase:
            self._active_phase = None
