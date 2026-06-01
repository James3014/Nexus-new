from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

@dataclass
class UnifiedAggregateReport:
    mode: str  # baseline/hyper/nightshift/learn
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    commit_sha: str = ""
    total_cases: int = 0
    success_rate: float = 0.0
    algorithm_success_rate: float = 0.0
    regression_rate: float = 0.0
    infra_blocked_rate: float = 0.0
    time_to_green_p50: float = 0.0
    failure_reason_counts: Dict[str, int] = field(default_factory=dict)
    error_code_counts: Dict[str, int] = field(default_factory=dict)
    total_retries: int = 0
    total_token_calls: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
