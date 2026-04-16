from __future__ import annotations
import time
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

@dataclass
class RetryParams:
    attempt: int
    max_retries: int
    base_delay: float = 1.0
    max_delay: float = 10.0
    jitter: bool = True

def compute_time_budget(requested_sec: int, buffer_ratio: float = 0.1) -> int:
    """Calculate a hardened time budget with safety buffer."""
    return int(requested_sec * (1.0 + buffer_ratio))

def get_retry_delay(params: RetryParams) -> float:
    """Calculate exponential backoff delay with jitter."""
    if params.attempt <= 0:
        return 0.0
    delay = min(params.max_delay, params.base_delay * (2 ** (params.attempt - 1)))
    if params.jitter:
        delay = delay * (0.5 + random.random())
    return round(delay, 2)

def classify_infra_block(error_msg: str) -> Optional[str]:
    """Classify an error message into an infra_block category."""
    err_l = str(error_msg).lower()
    if "timeout" in err_l or "deadline" in err_l:
        return "infra_blocked:timeout"
    if any(k in err_l for k in ["quota", "429", "rate limit", "resource exhausted"]):
        return "infra_blocked:quota"
    if any(k in err_l for k in ["capacity", "overloaded", "server error", "500", "503"]):
        return "infra_blocked:capacity"
    if any(k in err_l for k in ["broker", "swarm", "no directory available"]):
        return "infra_blocked:resource"
    return None


def compute_adaptive_budget(recent_latencies: List[float], default_sec: int, hard_cap: int = 300) -> int:
    """Calculate an adaptive budget based on recent latency history (moving average + safety)."""
    if not recent_latencies:
        return default_sec
    
    avg_latency = sum(recent_latencies) / len(recent_latencies)
    # Target 1.5x average, but bounded
    suggested = int(avg_latency * 1.5)
    return max(min(suggested, hard_cap), default_sec)
