"""Resource, memory safety, and learning telemetry for M5 Local execution.

Monitors host memory, swap pressure, elapsed execution times, and token usage.
Emits non-authoritative telemetry records for learning and cost-comparison analysis.

Guarantees:
- Never terminates unrelated user processes.
- Fails or defers cleanly under severe memory pressure (LOCAL_RESOURCE_PRESSURE).
- Telemetry does NOT become routing or completion authority.
"""

from __future__ import annotations

import sys
from typing import Optional

from .contracts import (
    M5_LOCAL_TELEMETRY_SCHEMA,
    TelemetryRecord,
)
from .host_inventory import get_host_memory_info, inspect_m5_host

# Conservative policy defaults for M5 (64GB unified memory):
# Note: These thresholds (16GB swap, 5000 pages) are conservative operational defaults,
# not measured M5 hardware limits.
MAX_SAFE_SWAP_USED_MB = 16384.0
MIN_SAFE_FREE_PAGES = 5000  # ~80 MB of immediate free pages


def check_host_resource_safety() -> tuple[bool, Optional[str]]:
    """Check whether host memory and swap allow safe local model execution."""
    if sys.platform != "darwin":
        return False, "RESOURCE_STATE_UNAVAILABLE: non-darwin platform cannot inspect M5 memory"

    try:
        mem = get_host_memory_info()
        if mem.total_ram_bytes == 0:
            return False, "RESOURCE_STATE_UNAVAILABLE: host physical memory stats unavailable"
        if mem.swap_used_mb > MAX_SAFE_SWAP_USED_MB:
            return (
                False,
                f"Host swap usage is high: {mem.swap_used_mb:.1f}MB used (policy limit {MAX_SAFE_SWAP_USED_MB}MB)",
            )
        if mem.free_pages < MIN_SAFE_FREE_PAGES and mem.inactive_pages < 10000:
            return False, f"Host free pages critically low: {mem.free_pages} pages"
        return True, None
    except Exception as exc:
        return False, f"RESOURCE_STATE_UNAVAILABLE: inspection failed ({exc})"


def record_execution_telemetry(
    *,
    task_family: str,
    local_role: str,
    runtime: str,
    model: str,
    elapsed_ms: int,
    rss_bytes: int = 0,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    context_limit: int = 4096,
    exit_reason: str = "SUCCESS",
    escalation_occurred: bool = False,
    escalation_reason: Optional[str] = None,
    repeated_acquisition_avoided: bool = False,
) -> TelemetryRecord:
    """Create a structured, non-authoritative telemetry record."""
    mem = get_host_memory_info()
    swap_used_bytes = int(mem.swap_used_mb * 1024 * 1024)
    host_brand = inspect_m5_host().cpu_brand

    return TelemetryRecord(
        schema=M5_LOCAL_TELEMETRY_SCHEMA,
        task_family=task_family,
        local_role=local_role,
        host=host_brand,
        runtime=runtime,
        model=model,
        elapsed_ms=elapsed_ms,
        rss_bytes=rss_bytes,
        swap_used_bytes=swap_used_bytes,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        context_limit=context_limit,
        exit_reason=exit_reason,
        escalation_occurred=escalation_occurred,
        escalation_reason=escalation_reason,
        repeated_acquisition_avoided=repeated_acquisition_avoided,
    )
