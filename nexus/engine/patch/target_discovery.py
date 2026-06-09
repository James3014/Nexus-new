from dataclasses import dataclass
from typing import List, Optional
import re

@dataclass
class TargetFileResolutionResult:
    resolved: bool
    target_file: Optional[str] = None
    reason: Optional[str] = None

class TargetFileDiscovery:
    """
    🛡️ TargetFileDiscovery: 目標檔案探索器
    確保在 Patch Apply 前，能夠明確且唯一地識別出待修復的目標檔案。
    """
    def __init__(self):
        # 匹配常見的 diff header 格式
        self.diff_patterns = [
            re.compile(r'^---\s+a/(.*?)\s*$', re.MULTILINE),
            re.compile(r'^\+\+\+\s+b/(.*?)\s*$', re.MULTILINE),
            re.compile(r'^diff\s+--git\s+a/.*?\s+b/(.*?)\s*$', re.MULTILINE)
        ]

    def resolve(self, raw_patch: str, context_files: List[str] = None) -> TargetFileResolutionResult:
        candidates = set()
        
        # 1. 從 Diff Header 中提取
        for pattern in self.diff_patterns:
            matches = pattern.findall(raw_patch)
            for match in matches:
                candidates.add(match.strip())
                
        # 2. 如果沒有從 Diff 中找到，嘗試使用傳入的 Context (例如 P-Stage Plan 中的 files)
        if not candidates and context_files:
            for f in context_files:
                if f and str(f).strip():
                    candidates.add(str(f).strip())
                    
        # 3. 唯一性判斷 (Fail-closed)
        if not candidates:
            return TargetFileResolutionResult(
                resolved=False, 
                reason="NO_TARGET_FILE_FOUND"
            )
            
        if len(candidates) > 1:
            return TargetFileResolutionResult(
                resolved=False,
                reason=f"AMBIGUOUS_TARGET_FILES: {list(candidates)}"
            )
            
        return TargetFileResolutionResult(
            resolved=True,
            target_file=list(candidates)[0]
        )
