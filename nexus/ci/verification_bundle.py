from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import hashlib

@dataclass(frozen=True)
class VerificationBundle:
    """[NEXUS v27.1] 驗證包：聚攏所有治理收據"""
    bundle_id: str
    manifest_hash: str
    promotion_receipt_id: Optional[str]
    rejection_receipt_ids: List[str] = field(default_factory=list)
    drift_status: str = "STABLE"
    bundle_hash: str = ""

class VerificationBundleFactory:
    """
    📦 Task: Receipt Aggregation (CI)
    職責: 將零散收據聚合成單一審計單元，並生成 Bundle Hash。
    """
    @staticmethod
    def create_bundle(manifest_hash: str, 
                      promo_id: Optional[str] = None,
                      reject_ids: List[str] = None) -> VerificationBundle:
        reject_ids = reject_ids or []
        raw_string = f"{manifest_hash}|{promo_id}|{sorted(reject_ids)}"
        bundle_hash = hashlib.sha256(raw_string.encode()).hexdigest()
        
        return VerificationBundle(
            bundle_id=f"B-{bundle_hash[:8]}",
            manifest_hash=manifest_hash,
            promotion_receipt_id=promo_id,
            rejection_receipt_ids=reject_ids,
            bundle_hash=bundle_hash
        )
