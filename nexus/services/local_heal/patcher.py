import re
import difflib
from typing import Tuple, Dict, Any, Optional
from dataclasses import dataclass

from nexus.services.local_heal.matcher import MatchChain, MatchResult

@dataclass
class PatchResult:
    success: bool
    new_content: str
    diff: str
    error_message: Optional[str] = None

class Patcher:
    """單一功能：負責將 SEARCH 替換為 REPLACE，產出 Unified Diff，不直接寫入實體檔案 (SRP)"""

    def __init__(self):
        self.match_chain = MatchChain()

    def _dedup_tokens(self, content: str) -> str:
        """解決因重複生成或引號導致的相鄰 token 無縫重複 Bug (DRY 優化)"""
        content = re.sub(r'\b([a-zA-Z_0-9]+)\s+\1\b', r'\1', content)
        return content

    def apply_patch(self, file_content: str, search_text: str, replace_text: str) -> PatchResult:
        orig_content = file_content
        
        # 使用 MatchChain 進行分層責任鏈匹配
        match_res = self.match_chain.find_match(orig_content, search_text, replace_text)
        if match_res is None:
            return PatchResult(
                success=False,
                new_content=orig_content,
                diff="",
                error_message="SEARCH block not found or verbatim mismatch"
            )

        verbatim_match = match_res.verbatim_text
        repl = replace_text
        
        # 確保完全行替換的尾端對齊一致
        if verbatim_match.endswith('\n') and not repl.endswith('\n'):
            repl += '\n'
        elif not verbatim_match.endswith('\n') and repl.endswith('\n'):
            repl = repl.rstrip('\n')
            
        # 若是 truncated 且替換程式包含多餘換行對齊，確保不殘存 duplicate suffix
        new_content = orig_content.replace(verbatim_match, repl, 1)
        # 移除過度積極的 _dedup_tokens，以防止正常的重複 token 或 truncated 部分語意受損，
        # 僅用在非常明確的 duplicate-word 特徵上
        new_content = self._dedup_tokens(new_content)

        # 解決相鄰重複行的 Bug (以行做去重)
        lines = new_content.splitlines(keepends=True)
        deduped_lines = []
        for line in lines:
            if deduped_lines and line.strip() and line.strip() == deduped_lines[-1].strip():
                stripped_line = line.strip()
                if stripped_line in ("pass", "else:", "return", "continue", "break"):
                    deduped_lines.append(line)
                    continue
                continue
            deduped_lines.append(line)
        new_content = "".join(deduped_lines)

        # 產生 Unified Diff
        orig_lines = orig_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(
            orig_lines, new_lines,
            fromfile="a/file",
            tofile="b/file",
            lineterm='\n'
        ))
        
        return PatchResult(
            success=True,
            new_content=new_content,
            diff="".join(diff_lines)
        )
