import sys
from pathlib import Path
import json

# Add project root to path
sys.path.append(str(Path("/Users/jameschen/Workspace/nexus")))

from nexus.core.context_compactor import ContextCompactor

def test_compactor():
    root = Path("/Users/jameschen/Workspace/nexus")
    compactor = ContextCompactor(root)
    
    # Test 7-segment structuring
    state = {
        "tasks": {
            "t1": {"id": "t1", "status": "done", "note": "Fact 1 verified"},
            "t2": {"id": "t2", "status": "failed", "note": "Risk A detected"},
            "t3": {"id": "t3", "status": "pending"}
        }
    }
    
    summary = compactor.compact(state)
    print("Summary Output:")
    print(json.dumps(summary, indent=2))
    
    # Verify fields
    assert "verified_facts" in summary
    assert len(summary["verified_facts"]) == 1
    assert summary["verified_facts"][0]["outcome"] == "Fact 1 verified"
    assert "context" in summary["verified_facts"][0]
    
    # Test BoundaryAligner
    raw_seq = [
        {"role": "assistant", "tool_calls": [{"id": "call_1", "function": {"name": "test"}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "result_1"},
        {"role": "tool", "tool_call_id": "call_orphan", "content": "orphan_result"}
    ]
    
    aligned = compactor.compact_tool_calls(raw_seq)
    print("\nAligned Sequence Count:", len(aligned))
    # Should drop the orphan
    assert len(aligned) == 2
    assert aligned[1]["tool_call_id"] == "call_1"
    
    print("\n✅ Compactor V2 Verification Passed!")

if __name__ == "__main__":
    test_compactor()
