import shutil
from typing import List, Optional
from nexus.env.models import EnvVerdict

class EnvDenoiser:
    """
    🛠️ Task T12: Environment Denoiser (Bounded Context)
    職責: 將環境判定邏輯從主編排器中徹底分離。
    """
    def __init__(self, repo_dir: str, python_exe: str):
        self.repo_dir = repo_dir
        self.python_exe = python_exe

    def get_verdict(self, evidence: str) -> EnvVerdict:
        # 1. 偵測特定領域的環境問題
        if "extension-helpers" in evidence.lower():
            return EnvVerdict(
                kind="NEEDS_REPAIR",
                reason="MISSING_BUILD_DEP",
                repair_hints=["uv pip install extension-helpers"],
                can_auto_heal=True
            )
            
        # 2. 物理衝突
        if "ASTROPY_311_NUMPY_VERSION_VIOLATION" in evidence:
            return EnvVerdict(kind="HARD_BLOCK", reason="VERSION_CONFLICT", repair_hints=["Downgrade numpy"])
            
        return EnvVerdict(kind="ALLOW", reason="STABLE", repair_hints=[])
