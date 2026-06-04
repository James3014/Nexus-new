import hashlib
import json
from typing import Dict, Any, Optional

class EvidenceChainService:
    """
    📜 Task: Evidence Chain Service
    職責: 實作證據封印 (Seal)、驗證 (Verify) 與 屏障 (Barrier) 契約。
    """
    
    @staticmethod
    def seal(evidence_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """產出帶有 SHA-256 指紋的證據封印"""
        serialized = json.dumps(payload, sort_keys=True)
        fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
        
        return {
            "evidence_id": evidence_id,
            "payload": payload,
            "fingerprint": fingerprint,
            "sealed": True
        }

    @staticmethod
    def verify(seal: Dict[str, Any]) -> bool:
        """物理驗證封印完整性"""
        if not seal.get("sealed"):
            return False
        
        payload = seal.get("payload", {})
        expected_fingerprint = seal.get("fingerprint")
        
        serialized = json.dumps(payload, sort_keys=True)
        actual_fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
        
        return actual_fingerprint == expected_fingerprint

    @staticmethod
    def barrier(seal: Optional[Dict[str, Any]], 
                *, 
                partial_telemetry: bool, 
                dirty_write: bool) -> Dict[str, Any]:
        """
        物理阻斷屏障。
        若偵測到指標不全或髒寫，物理阻斷 Claim 晉升。
        """
        if not seal or not EvidenceChainService.verify(seal):
            return {"status": "BLOCKED", "reason": "INVALID_EVIDENCE_SEAL"}
            
        if partial_telemetry:
            return {"status": "BLOCKED", "reason": "PARTIAL_TELEMETRY_DETECTED"}
            
        if dirty_write:
            return {"status": "BLOCKED", "reason": "DIRTY_EVIDENCE_WRITE_DETECTED"}
            
        return {"status": "PASS", "barrier_receipt": "SS-BARRIER-OK"}
