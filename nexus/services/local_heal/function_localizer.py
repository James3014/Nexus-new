import ast
from typing import List, Dict, Any

class FunctionLocalizer:
    """專門負責從 Python 檔案中提取 functions 並根據 issue 進行精確 AST 剪裁的 SRP 服務"""

    def extract_functions(self, code: str) -> List[Dict[str, Any]]:
        """使用 AST 解析並利用原始碼行號切片，保留註解與縮排的 verbatim 程式碼片段"""
        try:
            tree = ast.parse(code)
        except Exception:
            return []
            
        lines = code.splitlines(keepends=True)
        functions = []
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = node.lineno
                end = getattr(node, "end_lineno", start)
                # 切片 (lineno 是 1-based)
                func_lines = lines[start - 1 : end]
                func_code = "".join(func_lines)
                functions.append({
                    "name": node.name,
                    "code": func_code,
                    "start_line": start,
                    "end_line": end
                })
        return functions

    def score_functions(self, functions: List[Dict[str, Any]], issue_description: str) -> List[Dict[str, Any]]:
        """利用 keyword overlap 對每個 function 計算相關性得分"""
        import re
        query_words = set(re.findall(r'\b[a-zA-Z_0-9]{3,}\b', issue_description.lower()))
        
        scored = []
        for f in functions:
            name_lower = f["name"].lower()
            code_lower = f["code"].lower()
            
            score = 0.0
            for word in query_words:
                if word in name_lower:
                    score += 50.0  # 名稱精確匹配給予極高加權
                if word in code_lower:
                    score += 2.0   # 內文匹配給予基礎分
            
            f_copy = dict(f)
            f_copy["score"] = score
            scored.append(f_copy)
            
        scored.sort(key=lambda x: -x["score"])
        return scored

    def build_focused_context(self, file_path: str, code: str, issue_description: str) -> str:
        """建立極致精簡的 focused context，保留全域 Imports，僅將無關函數進行 AST 標記剪裁"""
        funcs = self.extract_functions(code)
        if not funcs:
            return code
            
        scored = self.score_functions(funcs, issue_description)
        # 篩選相關性高的函數，若全部都無匹配，至少保留前 2 個
        relevant = [f for f in scored if f["score"] >= 2.0]
        if not relevant:
            relevant = scored[:2]
            
        relevant_ranges = [(f["start_line"], f["end_line"]) for f in relevant]
        
        lines = code.splitlines(keepends=True)
        result_lines = []
        
        # 為了高效判定每行屬於哪個無關或相關函數
        line_to_func = {}
        for f in funcs:
            for l in range(f["start_line"], f["end_line"] + 1):
                line_to_func[l] = f
                
        trimmed_emitted = set()
        
        for idx, line in enumerate(lines):
            l_num = idx + 1
            if l_num in line_to_func:
                f = line_to_func[l_num]
                is_relevant = any(f["start_line"] == r[0] for r in relevant_ranges)
                if is_relevant:
                    result_lines.append(line)
                else:
                    if f["start_line"] not in trimmed_emitted:
                        indent = len(line) - len(line.lstrip())
                        result_lines.append(" " * indent + f"# ... [trimmed function {f['name']}]\n")
                        trimmed_emitted.add(f["start_line"])
            else:
                result_lines.append(line)
                
        return "".join(result_lines)
