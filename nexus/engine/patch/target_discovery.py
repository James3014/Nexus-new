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
        # 匹配常見的 diff header 與 Aider 格式
        self.diff_patterns = [
            re.compile(r'^---\s+a/(.*?)\s*$', re.MULTILINE),
            re.compile(r'^\+\+\+\s+b/(.*?)\s*$', re.MULTILINE),
            re.compile(r'^diff\s+--git\s+a/.*?\s+b/(.*?)\s*$', re.MULTILINE),
            # Aider 格式: 檔案路徑單獨一行在 SEARCH 區塊之上
            re.compile(r'^([A-Za-z0-9_./-]+)\s*\n\s*<<<<<<< SEARCH', re.MULTILINE)
        ]

    def resolve(
        self, 
        raw_patch: str, 
        context_files: List[str] = None, 
        project_root: Optional[str] = None
    ) -> TargetFileResolutionResult:
        import subprocess
        from pathlib import Path

        candidates = set()
        
        # 0. 獲取當前 Git 變更檔案列表
        git_changes = set()
        if project_root:
            try:
                res = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    check=False
                )
                if res.returncode == 0:
                    for line in res.stdout.splitlines():
                        if len(line) > 3:
                            status_code = line[:2]
                            file_path = line[3:].strip()
                            if "->" in file_path:
                                file_path = file_path.split("->")[-1].strip()
                            if "D" not in status_code:
                                git_changes.add(file_path)
            except Exception:
                pass

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
                    
        # 3. 如果 Context 也是空的，嘗試從 raw_patch 提取常見檔案路徑
        if not candidates:
            from nexus.engine.direct_mode import extract_target_files
            fallback_files = extract_target_files(raw_patch)
            for f in fallback_files:
                if f and str(f).strip():
                    candidates.add(str(f).strip())

        # 3.5. 過濾與自動補齊 (如果有提供 project_root)
        if project_root:
            # A. 過濾在 project_root 中不存在的 candidates
            if candidates:
                filtered = set()
                for cand in candidates:
                    cand_path = Path(project_root) / cand
                    if cand_path.exists():
                        filtered.add(cand)
                    else:
                        # 嘗試拿掉 a/ 或 b/
                        cleaned = cand
                        if cand.startswith("a/"):
                            cleaned = cand[2:]
                        elif cand.startswith("b/"):
                            cleaned = cand[2:]
                        cleaned_path = Path(project_root) / cleaned
                        if cleaned_path.exists():
                            filtered.add(cleaned)
                candidates = filtered

            # B. 當候選檔案 ambiguous 時，若其中只有一個存在於 Git 變更集合中，優先選它
            if len(candidates) > 1 and git_changes:
                intersection = candidates.intersection(git_changes)
                if len(intersection) == 1:
                    candidates = intersection

            # C. 當無候選檔案時，若 Git 變更檔案只有唯一一個，則 fallback 作為目標檔案
            if not candidates and git_changes:
                if len(git_changes) == 1:
                    candidates.add(list(git_changes)[0])
                    
        # 4. 唯一性判斷 (Fail-closed)
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
