from dataclasses import dataclass
from typing import Optional
from nexus.rollout.canary_guard import CanaryGuard
from nexus.governance.domain.blocker_taxonomy import BlockerCode

@dataclass(frozen=True)
class CanaryPanelViewModel:
    """
    🐥 Task: Thin Canary View Model (Application)
    職責: 僅映射發佈狀態，不包含任何業務決策邏輯。
    """
    mode: str          # OBSERVATION / CANARY / FULL_RELEASE
    rollout_percent: str # e.g., "10%"
    latest_blocker: Optional[str] # e.g., "DRIFT_DETECTED"
    health_status: str # HEALTHY / DEGRADED / CRITICAL

class CanaryPanelAssembler:
    """
    職責: 將底層 Guard 狀態與歷史阻斷記錄，組裝為前端 ViewModel。
    """
    @staticmethod
    def assemble(guard: CanaryGuard, 
                 rollout_fraction: float, 
                 recent_blocker_code: Optional[BlockerCode] = None) -> CanaryPanelViewModel:
        
        mode = "OBSERVATION" if guard.is_observation_mode() else "CANARY" if rollout_fraction < 1.0 else "FULL_RELEASE"
        
        health = "HEALTHY"
        latest_blocker_str = "None"
        
        if recent_blocker_code:
            latest_blocker_str = recent_blocker_code.name
            if recent_blocker_code in (BlockerCode.BASELINE_REGRESSION, BlockerCode.DRIFT_DETECTED):
                health = "CRITICAL"
            else:
                health = "DEGRADED"

        return CanaryPanelViewModel(
            mode=mode,
            rollout_percent=f"{rollout_fraction * 100:.1f}%",
            latest_blocker=latest_blocker_str,
            health_status=health
        )
