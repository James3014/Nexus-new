import re
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class SpecGuardV2:
    """🛡️ [Wave 1] Spec-Guard v2: Constitutional Veto System"""
    
    FORBIDDEN_PATTERNS = [
        r"sdd\.os",             # Legacy repo references
        r"os\.system\(",        # Unsafe syscalls
        r"subprocess\.check_output\(shell=True\)",
        r"/Users/jameschen/sdd\.os",
    ]

    def __init__(self, spec_path: str = "MUSE_ENGINE_SPEC.md"):
        self.spec_path = spec_path

    def audit_diff(self, diff_text: str) -> Dict[str, Any]:
        """審計變更內容是否違憲"""
        violations = []
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, diff_text, re.IGNORECASE):
                violations.append(f"VIOLATION: Detect prohibited pattern '{pattern}'")
        
        is_vetoed = len(violations) > 0
        if is_vetoed:
            logger.error(f"🛡️ [Spec-Guard] VETOED change due to {len(violations)} violations.")
            
        return {
            "status": "VETOED" if is_vetoed else "PASSED",
            "violations": violations,
            "audit_mode": "v23-Hardened"
        }
