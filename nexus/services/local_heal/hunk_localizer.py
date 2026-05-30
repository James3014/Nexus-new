import ast
import re
from typing import List, Tuple, Optional
from dataclasses import dataclass

@dataclass
class Hunk:
    name: str
    kind: str  # "class" or "def"
    start_line: int
    end_line: int
    content: str
    context_before: str
    context_after: str


class HunkLocalizer:
    """精微定位器：在定位出檔案後，提取最相關的 class/function 前後 5 行精微上下文切片 (SRP / SWE-agent 100行窗口)"""

    def extract_hunks(self, file_content: str, problem_statement: str, max_lines: int = 80) -> str:
        """
        解析原始碼 AST，根據問題報告中的關鍵字，選取最相符的 class/function 精巧切片。
        若解析失敗或找不到合適切片，則回傳原內容前 200 行作為安全網。
        """
        lines = file_content.splitlines()
        if len(lines) <= max_lines:
            return file_content

        try:
            tree = ast.parse(file_content)
        except Exception:
            return "\n".join(lines[:200]) + "\n... [truncated fallback]"

        hunks: List[Hunk] = []
        
        # 遍歷 AST 尋找 ClassDef 和 FunctionDef
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                start = node.lineno - 1
                # 取得結束行號（Python 3.8+ 支援 end_lineno）
                end = getattr(node, "end_lineno", start + 20) - 1
                
                kind = "class" if isinstance(node, ast.ClassDef) else "def"
                content = "\n".join(lines[start:end+1])
                
                # 擷取前後 5 行作為環境 context
                before_idx = max(0, start - 5)
                context_before = "\n".join(lines[before_idx:start])
                
                after_idx = min(len(lines), end + 6)
                context_after = "\n".join(lines[end+1:after_idx])
                
                hunks.append(Hunk(
                    name=node.name,
                    kind=kind,
                    start_line=node.lineno,
                    end_line=end + 1,
                    content=content,
                    context_before=context_before,
                    context_after=context_after
                ))

        if not hunks:
            return "\n".join(lines[:200]) + "\n... [truncated fallback]"

        # 根據 problem_statement 中的關鍵字，對 hunk 進行匹配評分
        problem_words = set(re.findall(r'\b[a-zA-Z_0-9]{2,}\b', problem_statement.lower()))
        
        best_hunk: Optional[Hunk] = None
        best_score = -1
        
        for h in hunks:
            score = 0
            # 若 class 或 function 名稱在問題描述中精準出現，大加分
            if h.name.lower() in problem_words:
                score += 50
            # 內容關鍵字重疊評分
            hunk_words = set(re.findall(r'\b[a-zA-Z_0-9]{2,}\b', h.content.lower()))
            overlap = len(problem_words.intersection(hunk_words))
            score += overlap
            
            if score > best_score:
                best_score = score
                best_hunk = h

        if best_hunk:
            # 重組精微上下文
            result_lines = []
            if best_hunk.context_before:
                result_lines.append(f"# ... [context lines {best_hunk.start_line - len(best_hunk.context_before.splitlines())} to {best_hunk.start_line - 1}]")
                result_lines.append(best_hunk.context_before)
            
            result_lines.append(f"# === Target Definition: {best_hunk.kind} {best_hunk.name} ===")
            result_lines.append(best_hunk.content)
            
            if best_hunk.context_after:
                result_lines.append(best_hunk.context_after)
                result_lines.append(f"# ... [context lines {best_hunk.end_line + 1} to {best_hunk.end_line + len(best_hunk.context_after.splitlines())}]")
                
            return "\n".join(result_lines)
            
        return "\n".join(lines[:200]) + "\n... [truncated fallback]"
