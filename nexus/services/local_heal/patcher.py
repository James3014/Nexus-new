import re
import difflib
from typing import Tuple, Dict, Any, Optional
from dataclasses import dataclass

from nexus.services.local_heal.matcher import MatchChain, MatchResult

from nexus.services.local_heal.validator import validate_syntax

@dataclass
class PatchResult:
    success: bool
    new_content: str
    diff: str
    error_message: Optional[str] = None
    
    # --- 審計產物 (Audit Artifacts) ---
    is_auto_corrected: bool = False
    similarity: float = 1.0
    strategy_used: str = "Exact"
    resolved_span: Tuple[int, int] = (0, 0) # (start_char, end_char)
    syntax_gate_passed: bool = True

class Patcher:
    """🛠️ Nexus Patcher: 負責將 SEARCH 替換為 REPLACE，支援有邊界的精度補償 (Bounded Compensation)"""

    def __init__(self, fuzzy_threshold: float = 0.85):
        self.match_chain = MatchChain()
        self.fuzzy_threshold = fuzzy_threshold

    def apply_patch(self, file_content: str, search_text: str, replace_text: str, context_hints: list[str] = None, validate_syntax_gate: bool = False) -> PatchResult:
        if search_text == "WHOLE_FILE":
            new_content = replace_text
            
            # 可選的語法前檢 (Syntax Preflight)
            if validate_syntax_gate:
                is_valid, syntax_err = validate_syntax(new_content)
                if not is_valid:
                    return PatchResult(success=False, new_content=file_content, diff="", error_message=f"SYNTAX_ERROR:{syntax_err}", syntax_gate_passed=False, strategy_used="FullFileReplace")

            orig_lines = file_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            diff_lines = list(difflib.unified_diff(orig_lines, new_lines, fromfile="a/file", tofile="b/file", lineterm='\n'))
            return PatchResult(success=True, new_content=new_content, diff="".join(diff_lines), strategy_used="FullFileReplace")

        orig_content = file_content
        search_stripped = search_text.strip()
        
        # 1. 執行標準責任鏈匹配
        match_res = self.match_chain.find_match(orig_content, search_text, replace_text, context_hints=context_hints)
        
        if match_res is None:
            return PatchResult(
                success=False,
                new_content=orig_content,
                diff="",
                error_message="SEARCH block not found or verbatim mismatch",
                strategy_used="None"
            )

        # 2. 執行替換與邊界判定
        verbatim_match = match_res.verbatim_text
        repl = replace_text
        sim = match_res.similarity
        
        # 相似度判定 (Bounded Compensation)
        is_verbatim = (verbatim_match.strip() == search_stripped)
        
        if not is_verbatim and sim < self.fuzzy_threshold:
             return PatchResult(
                success=False,
                new_content=orig_content,
                diff="",
                error_message=f"SEARCH block found but similarity too low ({sim:.2f} < {self.fuzzy_threshold})",
                strategy_used=match_res.strategy_name,
                similarity=sim
            )

        # 確保完全行替換的尾端對齊一致
        if verbatim_match.endswith('\n') and not repl.endswith('\n'):
            repl += '\n'
        elif not verbatim_match.endswith('\n') and repl.endswith('\n'):
            repl = repl.rstrip('\n')
            
        # 執行替換
        start_idx = orig_content.find(verbatim_match)
        if start_idx == -1: 
             return PatchResult(success=False, new_content=orig_content, diff="", error_message="Internal index error")
             
        end_idx = start_idx + len(verbatim_match)
        new_content = orig_content[:start_idx] + repl + orig_content[end_idx:]

        # 可選的語法前檢 (Syntax Preflight)
        if validate_syntax_gate:
            is_valid, syntax_err = validate_syntax(new_content)
            if not is_valid:
                return PatchResult(
                    success=False, 
                    new_content=orig_content, 
                    diff="", 
                    error_message=f"SYNTAX_ERROR:{syntax_err}", 
                    syntax_gate_passed=False,
                    strategy_used=match_res.strategy_name,
                    similarity=sim
                )

        # 產生 Unified Diff
        orig_lines = orig_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(orig_lines, new_lines, fromfile="a/file", tofile="b/file", lineterm='\n'))
        
        return PatchResult(
            success=True,
            new_content=new_content,
            diff="".join(diff_lines),
            is_auto_corrected=(not is_verbatim),
            similarity=sim,
            strategy_used=match_res.strategy_name,
            resolved_span=(start_idx, end_idx)
        )
