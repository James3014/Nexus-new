from dataclasses import dataclass, field
from typing import List, Dict, Any
import json
import hashlib
from nexus.governance.application.finalization_report import OperationalSealReport
from nexus.ci.verification_bundle import VerificationBundle

@dataclass(frozen=True)
class GovernanceArchive:
    """[NEXUS v27.1] 治理歸檔總包"""
    version: str
    report: OperationalSealReport
    bundle: VerificationBundle
    approved_adr_hashes: Dict[str, str]
    archive_hash: str = ""

class ArchiveManager:
    """
    🗄️ Task: Governance Archive Management (Application)
    職責: 執行最終結案歸檔，確保資產完整性與不可篡改。
    """
    @staticmethod
    def create_archive(version: str, 
                       report: OperationalSealReport, 
                       bundle: VerificationBundle,
                       adr_hashes: Dict[str, str]) -> GovernanceArchive:
        
        # 建立歸檔雜湊 (Fingerprint)
        raw_identity = f"{version}|{bundle.bundle_hash}|{json.dumps(adr_hashes, sort_keys=True)}"
        archive_hash = hashlib.sha256(raw_identity.encode()).hexdigest()
        
        return GovernanceArchive(
            version=version,
            report=report,
            bundle=bundle,
            approved_adr_hashes=adr_hashes,
            archive_hash=archive_hash
        )
