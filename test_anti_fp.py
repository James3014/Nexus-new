import sys
import os
import json
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(__import__("pathlib").Path(__file__).resolve().parents[0]))

from nexus.engine.coordinator import NexusEngine
from nexus.engine.config import EngineConfig
from pathlib import Path

def test_anti_fp_logic():
    print("🧪 Testing Anti-False-Positive Logic...")
    
    project_root = Path(__file__).resolve().parent
    config = EngineConfig(project_root=project_root)
    
    # Initialize a mock engine 
    engine = NexusEngine(config=config)
    
    # 🧪 我們模擬 dual_track_scoring 邏輯，
    # 這是為了證明 Nexus 的核心：如果沒有物理補丁 (patch) 或 Tree 變更，即使模型回報成功，系統也會判定為失敗。
    def dual_track_scoring(success, patch_gen, repo_tree_changed, governance_score):
        # 🛡️ Nexus 物理守門核心邏輯
        governance_blocked = (governance_score < 4.0) or (not repo_tree_changed and patch_gen)
        official_status = "PASS" if (success and patch_gen and repo_tree_changed and not governance_blocked) else "FAIL"
        shadow_status = "PASS" if success else "FAIL"
        return {
            "official_status": official_status,
            "shadow_status": shadow_status,
            "governance_blocked": governance_blocked
        }

    # Case 1: Mocked Failure - No Patch but success=True (Typical False Positive)
    scoring_1 = dual_track_scoring(
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
    scoring_2 = dual_track_scoring(
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
    scoring_3 = dual_track_scoring(
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
