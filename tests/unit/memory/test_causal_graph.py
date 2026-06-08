import pytest
from nexus.engine.memory.causal_graph import MemoryGraph

def test_causal_memory_traceback():
    graph = MemoryGraph()
    
    # Action 1: Slicing
    evt1 = graph.record_event("SLICE", "separability_matrix", "SUCCESS")
    
    # Action 2: Patching (caused by Slicing)
    evt2 = graph.record_event("PATCH", "separability_matrix", "SUCCESS", parent_id=evt1)
    
    # Action 3: Audit (caused by Patching)
    evt3 = graph.record_event("AUDIT", "separability_matrix", "FAILED", parent_id=evt2, reason="Nested models matrix remains diagonal.")
    
    trace = graph.trace_back(evt3)
    assert len(trace) == 3
    assert trace[0].action == "SLICE"
    assert trace[-1].outcome == "FAILED"
    assert "diagonal" in trace[-1].reasoning_trace
