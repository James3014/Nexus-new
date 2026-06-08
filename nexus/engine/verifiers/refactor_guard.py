import re
from nexus.engine.verifiers.base import BaseVerifier
from nexus.engine.contracts.verification import VerificationResult, VerifierType, Verdict

class RefactorGuard(BaseVerifier):
    """
    🛡️ RefactorGuard: 重構守衛
    防止「模組幻影」(Modular Mirage) 與糾纏式重構 (Tangled Refactoring)。
    - 禁止在修 bug 時夾帶 rename/move 檔案。
    - 禁止修改超過 3 個不相關模組。
    """
    
    def verify(self, candidate_patch: str, **kwargs) -> VerificationResult:
        # 1. 偵測檔案更名/移動 (Tangled with logic fix)
        has_rename = bool(re.search(r'^rename from\s+', candidate_patch, re.MULTILINE))
        has_logic_change = bool(re.search(r'^--- a/', candidate_patch, re.MULTILINE))
        
        if has_rename and has_logic_change:
            return VerificationResult(
                verifier_type=VerifierType.REFACTOR_GUARD,
                verdict=Verdict.HARD_REJECT,
                reason="Tangled Refactoring: Patch mixes file rename/move with logic changes.",
                constraint_for_next_round="Do not mix file renames or structural changes with bug fixes. Focus only on the logic."
            )
            
        # 2. 偵測跨模組擴散 (過多檔案變更)
        # 計算 diff 觸及的檔案數
        files_touched = len(re.findall(r'^diff --git a/', candidate_patch, re.MULTILINE))
        if files_touched > 3:
            return VerificationResult(
                verifier_type=VerifierType.REFACTOR_GUARD,
                verdict=Verdict.HARD_REJECT,
                reason=f"Surface Area Too Large: Patch touches {files_touched} files.",
                constraint_for_next_round="Limit the fix to a maximum of 3 files. Decouple your changes."
            )

        return VerificationResult(
            verifier_type=VerifierType.REFACTOR_GUARD,
            verdict=Verdict.PASS,
            reason="Patch maintains single responsibility."
        )
