from typing import List, Tuple
from nexus.services.local_heal.evidence_compactor import EvidenceCompactor
from nexus.services.local_heal.interface import LocalizedFile

class ContextGuard:
    """🛡️ Context Guard: Protection against context window explosion and evidence noise."""
    
    DEFAULT_MAX_LOCALIZED_FILES = 3
    DEFAULT_MAX_TOTAL_CHARS = 10000
    DEFAULT_EVIDENCE_LIMIT = 3000

    def protect(self, ctx: any) -> None:
        """執行全方位的上下文保護與壓縮"""
        # 1. 證據壓縮
        ctx.op.repro_evidence = EvidenceCompactor.compact(
            ctx.op.repro_evidence, 
            limit=self.DEFAULT_EVIDENCE_LIMIT
        )

        # 2. 定位檔案縮減
        ctx.op.localized_files = self.limit_localized_files(
            ctx.op.localized_files,
            max_files=self.DEFAULT_MAX_LOCALIZED_FILES,
            max_total_chars=self.DEFAULT_MAX_TOTAL_CHARS
        )

    def limit_localized_files(
        self, 
        files: List[LocalizedFile], 
        max_files: int, 
        max_total_chars: int
    ) -> List[LocalizedFile]:
        """縮減定位檔案的數量與總體積，優先保留前面的檔案。"""
        truncated = []
        current_chars = 0
        for i, loc_file in enumerate(files):
            if i >= max_files:
                break
            if isinstance(loc_file, tuple) and len(loc_file) >= 2:
                loc_file = LocalizedFile(path=str(loc_file[0]), content=str(loc_file[1]))
            
            # Optimization: Noise filtering for stale or trivial localized contents
            if not loc_file.content or len(loc_file.content.strip()) < 15:
                continue

            if current_chars + len(loc_file.content) > max_total_chars:
                if truncated:
                    break
            
            truncated.append(loc_file)
            current_chars += len(loc_file.content)
        
        return truncated
