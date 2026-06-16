import re
import difflib
from pathlib import Path
from typing import List, Tuple, Any

class SurgicalContextBuilder:
    """手術級上下文切片器 (Surgical Context Slicing) - 依據 Linus 切小與關注點分離原則"""
    
    def __init__(self, max_context_lines: int = 350, window_size: int = 150):
        self.max_context_lines = max_context_lines
        self.window_size = window_size

    def _dynamic_window(self, total_lines: int, anchor_idx: int) -> int:
        """Compute window size based on file size and anchor position."""
        if total_lines <= 100:
            return min(30, total_lines // 2)
        if total_lines <= 300:
            return min(75, total_lines // 3)
        # Large file: adaptive based on anchor position
        edge_margin = min(50, total_lines // 10)
        if anchor_idx < edge_margin or anchor_idx > total_lines - edge_margin:
            return min(100, total_lines // 4)
        return self.window_size

    def build_annotated_context(
        self,
        repo_dir: Path,
        rel_path: str,
        source_text: str,
        attempt: int,
        failure_reason: str,
        plan: Any,
        user_prompt: str = None
    ) -> str:
        source_lines = source_text.splitlines()
        
        # 檔案行數小於等於閾值，不需要任何裁剪，直接輸出整份
        if len(source_lines) <= self.max_context_lines:
            return self._format_lines(source_lines, 0, len(source_lines), rel_path)

        # 否則需要進行 Anchor-based 局部裁剪
        anchor_line_idx = 0
        
        # 情況 A: 重試且前次為 SEARCH_MISMATCH，試圖從 user_prompt 中還原前次 SEARCH block 做 fuzzy 定位
        if attempt > 1 and failure_reason and "SEARCH_MISMATCH" in failure_reason and user_prompt:
            search_block = self._extract_last_search_block(user_prompt)
            if search_block:
                idx = self._find_fuzzy_anchor(source_lines, search_block)
                if idx is not None:
                    anchor_line_idx = idx

        # 情況 B: 首輪或未找到 fuzzy 定位點，嘗試從 plan 的 search_symbols 中定位
        if anchor_line_idx == 0 and plan:
            symbols = getattr(plan, "search_symbols", [])
            idx = self._find_symbol_anchor(source_lines, symbols)
            if idx is not None:
                anchor_line_idx = idx
                
        # 進行滑動視窗切片
        dyn_window = self._dynamic_window(len(source_lines), anchor_line_idx)
        start_idx = max(0, anchor_line_idx - dyn_window)
        end_idx = min(len(source_lines), anchor_line_idx + dyn_window + 1)
        
        return self._format_lines(source_lines, start_idx, end_idx, rel_path)

    def _extract_last_search_block(self, prompt: str) -> str | None:
        # 尋找 user prompt 中的 SEARCH/REPLACE 區塊
        pattern = re.compile(r"<<<<<<< SEARCH\n(.*?)\n=======", re.DOTALL)
        matches = pattern.findall(prompt)
        if matches:
            # 回傳最後一個匹配的 SEARCH block (通常是最新的一次嘗試)
            return matches[-1].strip()
        return None

    def _find_fuzzy_anchor(self, source_lines: List[str], search_block: str) -> int | None:
        search_lines = [line.strip() for line in search_block.splitlines() if line.strip()]
        if not search_lines:
            return None
            
        n_search = len(search_lines)
        best_ratio = 0.0
        best_idx = 0
        
        # 滑動對齊比對
        for i in range(len(source_lines) - n_search + 1):
            window = [source_lines[i + j].strip() for j in range(n_search)]
            ratio = difflib.SequenceMatcher(None, "\n".join(window), "\n".join(search_lines)).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = i
                
        # 相似度必須達到一定水準 (例如 0.3)，避免在無關處瞎猜
        if best_ratio >= 0.3:
            # 我們回傳匹配區段的中間行作為 anchor，或者起始行
            return best_idx
        return None

    def _find_symbol_anchor(self, source_lines: List[str], symbols: List[str]) -> int | None:
        if not symbols:
            return None
        for sym in symbols:
            for idx, line in enumerate(source_lines):
                if sym in line:
                    return idx
        return None

    def _format_lines(self, source_lines: List[str], start_idx: int, end_idx: int, rel_path: str) -> str:
        annotated = []
        for idx in range(start_idx, end_idx):
            annotated.append(f"{idx + 1:4d} | {source_lines[idx]}")
            
        header = (
            f"# NOTE: Showing lines {start_idx + 1} to {end_idx} of {rel_path}.\n"
            f"# Your SEARCH block must match verbatim code from this range WITHOUT line numbers.\n"
        )
        if start_idx > 0:
            header += f"... [truncated, lines 1 to {start_idx} are hidden] ...\n"
            
        footer = ""
        if end_idx < len(source_lines):
            footer = f"\n... [truncated, lines {end_idx + 1} to {len(source_lines)} are hidden] ..."
            
        return header + "\n".join(annotated) + footer
