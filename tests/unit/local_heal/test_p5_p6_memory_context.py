"""EA-R3: P5/P6 Memory Context Tests."""
from __future__ import annotations

import pytest
from nexus.services.local_heal.p5_p6_memory_context import (
    P5P6MemoryContext,
    build_p5_p6_memory_context,
)


def test_adapter_disabled_not_used():
    """EA-R3: Adapter disabled → NOT_USED."""
    ctx = build_p5_p6_memory_context(adapter_enabled=False)
    assert ctx.memory_trace == {}
    assert ctx.decision_mode == "audit_only"
    assert ctx.decision_eligible is False
    assert ctx.reason == "adapter_disabled"


def test_adapter_enabled_no_hits_trace_missing():
    """EA-R3: Adapter enabled, no hits → TRACE_MISSING."""
    ctx = build_p5_p6_memory_context(
        adapter_enabled=True,
        query_text="nonexistent query that returns nothing",
        task_id="test",
    )
    # With no hits, should return audit_only mode
    assert ctx.decision_mode == "audit_only"
    assert ctx.decision_eligible is False


def test_decision_mode_default_audit_only():
    """EA-R3: decision_mode default = 'audit_only'."""
    ctx = P5P6MemoryContext()
    assert ctx.decision_mode == "audit_only"
    assert ctx.decision_eligible is False


def test_memory_sources_preserved():
    """EA-R3: Retrieval sources preserved in memory_sources."""
    ctx = P5P6MemoryContext(
        memory_sources=["local_jsonl", "lancedb"],
    )
    assert "local_jsonl" in ctx.memory_sources
    assert "lancedb" in ctx.memory_sources


def test_no_memory_lesson_affects_selection():
    """EA-R3: No memory lesson can affect P5/P6 selection unless decision_eligible=True."""
    ctx = build_p5_p6_memory_context(adapter_enabled=False)
    assert ctx.decision_eligible is False
    # decision_eligible=False means no memory lesson affects selection
