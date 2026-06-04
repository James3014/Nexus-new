from typing import List, Dict, Any, Optional
from nexus.evaluation.manifest_manager import ManifestManager

class DriftStopGate:
    """
    🔍 Task: Drift aware auto-stop (Application)
    職責: 確保「現體規格」與「密封收據」完全對位，偵測任何未經核准的漂移。
    """
    @staticmethod
    def verify_alignment(receipt_manifest_hash: str) -> bool:
        current_hash = ManifestManager.get_manifest_hash()
        
        if current_hash != receipt_manifest_hash:
            print(f"❌ DRIFT DETECTED: Current({current_hash[:12]}) != Receipt({receipt_manifest_hash[:12]})")
            return False
            
        print("✅ DRIFT CHECK PASSED: Specifications aligned.")
        return True

    @staticmethod
    def check_policy_drift(old_policy: str, new_policy: str) -> bool:
        """偵測晉升政策是否發生非預期變更"""
        return old_policy == new_policy
