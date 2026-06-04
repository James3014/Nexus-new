from typing import Optional, Dict, Any
from nexus.replay.replay_artifact import ReplayArtifact
from nexus.telemetry.telemetry_models import TelemetryBundle

class BlockerCodes:
    INCOMPLETE_TELEMETRY = "INCOMPLETE_TELEMETRY"
    MISSING_REPLAY_EVIDENCE = "MISSING_REPLAY_EVIDENCE"
    REPLAY_FAILURE = "REPLAY_FAILURE"
    EVIDENCE_VERIFICATION_FAILED = "EVIDENCE_VERIFICATION_FAILED"
    NONE = "NONE"

class GateJudge:
    """
    ⚖️ Task: Pure Gate Judge (Immutable version)
    職責: 實現「相同輸入必得相同判決」。
    """
    
    @staticmethod
    def decide(ticket_id: str, 
               replay: Optional[ReplayArtifact] = None, 
               telemetry: Optional[TelemetryBundle] = None,
               evidence_seal: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        
        # 1. 物理完整性檢查 (Fail-Closed)
        if not telemetry or not telemetry.complete:
            return {"task_id": ticket_id, "allowed": False, "blocker": BlockerCodes.INCOMPLETE_TELEMETRY}
            
        if not replay:
            return {"task_id": ticket_id, "allowed": False, "blocker": BlockerCodes.MISSING_REPLAY_EVIDENCE}

        # 2. 證據鏈驗證 (若提供則檢查)
        if evidence_seal:
            # 此處調用 EvidenceChainService 驗證，但在傳入前應已驗證過，
            # 判決器僅讀取 seal 標籤
            if not evidence_seal.get("sealed"):
                 return {"task_id": ticket_id, "allowed": False, "blocker": BlockerCodes.EVIDENCE_VERIFICATION_FAILED}

        # 3. 判決邏輯
        passed = (replay.status == "SUCCESS")
        
        return {
            "task_id": ticket_id,
            "allowed": passed,
            "score": 1.0 if passed else 0.0,
            "blocker": BlockerCodes.NONE if passed else BlockerCodes.REPLAY_FAILURE
        }
