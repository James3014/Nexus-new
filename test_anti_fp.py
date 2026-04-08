import sys
import os
import json
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(__import__("pathlib").Path(__file__).resolve().parents[0]))

from nexus.engine.coordinator import NexusEngine

def test_anti_fp_logic():
    print("🧪 Testing Anti-False-Positive Logic...")
    
    # Initialize a mock engine 
    engine = NexusEngine(project_root=Path(str(__import__("pathlib").Path(__file__).resolve().parents[0])))
    
    # Case 1: Mocked Failure - No Patch but success=True (Typical False Positive)
    scoring_1 = engine.dual_track_scoring(
        success=True,
        patch_gen=False,
        repo_tree_changed=False,
        governance_score=3.5
    )
    print(f"Case 1 (No Patch): Official={scoring_1['official_status']}, Shadow={scoring_1['shadow_status']}")
    assert scoring_1["official_status"] == "FAIL"
    assert scoring_1["shadow_status"] == "PASS"
    assert scoring_1["governance_blocked"] is True

    # Case 2: Mocked Success - Patch + Tree Change + Success
    scoring_2 = engine.dual_track_scoring(
        success=True,
        patch_gen=True,
        repo_tree_changed=True,
        governance_score=4.2
    )
    print(f"Case 2 (True PASS): Official={scoring_2['official_status']}, Shadow={scoring_2['shadow_status']}")
    assert scoring_2["official_status"] == "PASS"
    assert scoring_2["shadow_status"] == "PASS"
    assert scoring_2["governance_blocked"] is False

    # Case 3: Mocked Governance Blocked - Model Success but Tree not changed (governance rejected)
    scoring_3 = engine.dual_track_scoring(
        success=True,
        patch_gen=True,
        repo_tree_changed=False,
        governance_score=3.8
    )
    print(f"Case 3 (Gov Blocked): Official={scoring_3['official_status']}, Shadow={scoring_3['shadow_status']}")
    assert scoring_3["official_status"] == "FAIL"
    assert scoring_3["governance_blocked"] is True

    print("\n✅ All logic tests PASSED!")

if __name__ == "__main__":
    try:
        test_anti_fp_logic()
    except Exception as e:
        print(f"❌ Test Failed: {e}")
        sys.exit(1)
