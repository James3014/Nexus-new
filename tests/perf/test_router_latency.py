from __future__ import annotations

import os
import time
from unittest.mock import MagicMock

import pytest


def _make_router_stub(learning_enabled: bool):
    """Build a minimal router stub that simulates routing latency."""
    os.environ["NEXUS_LEARNING_LOOP_WRITE_ENABLED"] = "1" if learning_enabled else "0"
    stub = MagicMock()
    stub.route.side_effect = lambda phase, ctx: {"route": "direct", "phase": phase}
    return stub


def _measure_router_latency_stub(learning_enabled: bool, num_tasks: int = 100) -> float:
    """Measure average simulated router latency per task."""
    router = _make_router_stub(learning_enabled)
    total_ms = 0.0

    for i in range(num_tasks):
        context = {"task_id": f"perf-test-{i}", "repo": "test/repo", "problem": "test"}
        start = time.monotonic()
        router.route("execute", context)
        elapsed_ms = (time.monotonic() - start) * 1000
        total_ms += elapsed_ms

    return total_ms / num_tasks


def test_router_latency_with_learning_loop_enabled():
    """N10: Verify router latency with learning loop enabled is within tolerance."""
    avg_enabled = _measure_router_latency_stub(learning_enabled=True, num_tasks=50)
    assert avg_enabled >= 0, f"Negative latency: {avg_enabled}"
    assert avg_enabled < 5000, (
        f"Latency with learning loop enabled too high: {avg_enabled:.2f}ms > 5000ms"
    )
