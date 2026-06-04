from typing import List, Optional
import re
from nexus.verifiers.contracts import VerifierVerdict, FailureTag

class AstropyAstrophysicsGuard:
    """
    🌌 [v27.2 B05 & v27.3 T2] Astropy_Astrophysics
    職責: 攔截物理計算、座標系統與 FITS I/O 中的高危操作，避免數據無聲污染。
    """
    
    @staticmethod
    def evaluate(candidate_id: str, patch: str) -> VerifierVerdict:
        failure_tags = []
        
        # 1. 偵測危險的純數值加減 (不帶單位的運算)
        if (" += " in patch or " -= " in patch) and not any(u in patch for u in ["Quantity(", "u.", "units."]):
            failure_tags.append(FailureTag(
                code="UNIT_STRIPPING_RISK", 
                description="Mathematical operation detected without explicit astropy unit context."
            ))
                
        # 2. 偵測座標系對齊風險
        frames = ["ICRS", "Galactic", "FK5", "FK4", "AltAz"]
        # 修正: 即使只有一個 frame，如果沒有 transform_to 也應該警告
        found_frames = [f for f in frames if f.lower() in patch.lower()]
        
        if found_frames:
            # 如果偵測到 frame 但沒有 transform_to，視為硬編碼風險
            if "transform_to(" not in patch:
                if len(set(found_frames)) > 1:
                    failure_tags.append(FailureTag(
                        code="AMBIGUOUS_FRAME_ALIGNMENT", 
                        description="Multiple coordinate frames detected without explicit transform_to() alignment."
                    ))
                else:
                    failure_tags.append(FailureTag(
                        code="RIGID_COORDINATE_FRAME", 
                        description="Hardcoded coordinate frame detected without transformation capability."
                    ))

        # 3. [v27.3] FITS Header 完整性檢查
        mandatory_keys = ["'SIMPLE'", "'BITPIX'", "'NAXIS'"]
        if "del header[" in patch or ".remove(" in patch:
            if any(key in patch for key in mandatory_keys):
                failure_tags.append(FailureTag(
                    code="MANDATORY_HEADER_MISSING", 
                    description="Attempted deletion of mandatory FITS header key detected."
                ))

        if failure_tags:
             return VerifierVerdict(
                verifier_name="astropy_astrophysics", 
                candidate_id=candidate_id, 
                passed=False, 
                score=-6.0, 
                failure_tags=failure_tags
            )
            
        return VerifierVerdict(
            verifier_name="astropy_astrophysics", 
            candidate_id=candidate_id, 
            passed=True, 
            score=4.0, 
            failure_tags=[FailureTag(code="SUCCESS", description="Astrophysics and I/O logic passes all constraints.")]
        )
