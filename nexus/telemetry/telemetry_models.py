from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class TelemetryBundle:
    """
    📊 Telemetry Data Model (v28.1)
    職責: 收集指標 Facts，不負責任政策判定。
    """
    wall_time_ms: Optional[int]
    token_usage: Optional[int]
    provider_costs: Optional[float]
    overhead_ms: Optional[int]

    @property
    def complete(self) -> bool:
        """Claimability 的關鍵物理判準：指標是否收集完整"""
        return all(v is not None for v in [
            self.wall_time_ms, 
            self.token_usage, 
            self.provider_costs, 
            self.overhead_ms
        ])
