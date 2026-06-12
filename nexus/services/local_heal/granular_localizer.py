from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple
import ast
import re
from pathlib import Path
from rank_bm25 import BM25Okapi

@dataclass
class LocalizationBundle:
    file_path: str
    primary_snippet: str
    supporting_snippets: List[str] = field(default_factory=list)
    related_definitions: List[str] = field(default_factory=list)
    slice_reason: str = ""
    confidence: float = 0.0
    fallback_mode: str | None = None
    start_line: int | None = None
    end_line: int | None = None

    @staticmethod
    def _annotate_with_lineno(snippet: str, start_line: int = 1) -> str:
        """為每行加上行號標記，讓模型可以精確定位 verbatim 代碼位置"""
        lines = snippet.splitlines()
        annotated = []
        for i, line in enumerate(lines):
            annotated.append(f"{start_line + i:4d} | {line}")
        return "\n".join(annotated)

    def build_context(self, annotate_lines: bool = True) -> str:
        parts = [f"### FILE: {self.file_path}"]
        if self.fallback_mode == "file_scope":
            if annotate_lines:
                parts.append("# NOTE: Line numbers shown for reference. Your SEARCH block must use verbatim code WITHOUT line numbers.")
                parts.append(self._annotate_with_lineno(self.primary_snippet, start_line=self.start_line or 1))
            else:
                parts.append(self.primary_snippet)
            return "\n".join(parts)

        parts.append(f"# Refined snippets for {self.file_path}")
        parts.append("# NOTE: Line numbers shown for reference. SEARCH block must copy code verbatim WITHOUT line numbers.")
        parts.append(f"## Primary Target:")
        if annotate_lines:
            parts.append(self._annotate_with_lineno(self.primary_snippet, start_line=self.start_line or 1))
        else:
            parts.append(self.primary_snippet)
        parts.append("")

        if self.supporting_snippets:
            parts.append("## Supporting Helpers:")
            for s in self.supporting_snippets:
                if annotate_lines:
                    parts.append(self._annotate_with_lineno(s))
                else:
                    parts.append(s)
            parts.append("")

        if self.related_definitions:
            parts.append("## Related Definitions (Regex/Constants):")
            for d in self.related_definitions:
                parts.append(f"    {d}")
            parts.append("")

        return "\n".join(parts)


class GranularMethodLocalizer:
    """
    🛡️ Granular Method Localizer (v1)
    Responsibilities: Ranked surgical context extraction.
    Formula: Symbol Match + Structure (Call Chain) + Semantic (Parser/Regex) + Patchability.
    """
    
    def __init__(self, refine_threshold: int = 5000):
        self.refine_threshold = refine_threshold
        self.python_keywords = {
            'def', 'class', 'import', 'from', 'return', 'pass', 'if', 'else', 
            'elif', 'for', 'while', 'in', 'is', 'not', 'and', 'or', 'try', 
            'except', 'finally', 'raise', 'as', 'assert', 'async', 'await', 
            'break', 'continue', 'del', 'global', 'nonlocal', 'with', 'yield', 'self', 'cls'
        }

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r'\b[a-zA-Z_0-9]{2,}\b', text.lower())

    def _extract_paths_from_issue(self, text: str) -> List[str]:
        # 1. 捕捉 Traceback 中的路徑
        paths = []
        # Pattern: File "path/to/file.py", line X, in function
        for m in re.finditer(r'File "([^"]+\.py)"', text):
            paths.append(m.group(1))
        
        # 2. 捕捉 Prose 中的路徑 (e.g. `django/contrib/auth/models.py`)
        for m in re.finditer(r'`?([a-zA-Z0-9_/]+\.py)`?', text):
            paths.append(m.group(1))
            
        return list(dict.fromkeys(paths)) # De-duplicate preserving order

    def rank_files(
        self,
        issue_description: str,
        repo_dir: Path,
        max_files: int = 10,  # 提升至 10 以應對大型框架
        search_symbols: List[str] | None = None,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        explicit_paths = self._extract_paths_from_issue(issue_description)
        found_explicit = []
        for path in explicit_paths:
            p = repo_dir / path if not Path(path).is_absolute() else Path(path)
            if p.exists():
                found_explicit.append((10000.0, {"path": str(path), "content": p.read_text(errors="replace"), "file_path": p}))

        if found_explicit:
            return found_explicit[:max_files]

        documents = []
        py_files = list(repo_dir.rglob("*.py"))
        for i, pyfile in enumerate(py_files):
            rel_path = str(pyfile.relative_to(repo_dir))
            # 排除非專案代碼：測試、緩存、編譯產物、虛擬環境、以及 Nexus 產生的重現腳本
            if any(p in rel_path.lower() for p in (
                "test", "__pycache__", "build", "docs", ".venv", "site-packages", 
                "egg-info", "reproduce_bug.py", "debug_repro.py", "temp_", "scratch"
            )): 
                continue
            try:
                content = pyfile.read_text(encoding="utf-8", errors="replace")
                if content.strip():
                    documents.append({"path": rel_path, "content": content, "file_path": pyfile})
            except: pass

        if not documents: 
            return []
        
        tokenized_corpus = [self._tokenize(doc["content"]) for doc in documents]
        bm25 = BM25Okapi(tokenized_corpus)
        bm25_scores = bm25.get_scores(self._tokenize(issue_description))

        # Symbol & Definition Boost
        symbol_bonus = 500.0
        definition_bonus = 5000.0  # 提升至 5000，確保定義檔案絕對領先
        scored_docs = []
        for idx, doc in enumerate(documents):
            score = float(bm25_scores[idx])
            if search_symbols:
                full_content = doc["content"]
                for sym in search_symbols:
                    if not sym: continue
                    # A. 符號出現在檔案中 (BM25 補充)
                    if re.search(r'\b' + re.escape(sym) + r'\b', full_content):
                        score += symbol_bonus
                        # B. 符號在檔案中被定義 (定義優先原則)
                        if re.search(r'^\s*(class|def)\s+' + re.escape(sym) + r'\b', full_content, re.MULTILINE):
                            score += definition_bonus
            scored_docs.append((score, doc))
        
        scored_docs.sort(key=lambda x: -x[0])
        
        # 動態過濾：若有檔案命中符號或定義 (分數 >= symbol_bonus)，
        # 則直接剔除完全沒命中符號的雜訊檔案，防止 Context Bloat。
        if scored_docs and scored_docs[0][0] >= symbol_bonus:
            scored_docs = [(s, d) for s, d in scored_docs if s >= symbol_bonus]

        # 強制將 max_files 限制在 3，避免 14B 模型 OOM 或 Timeout
        hard_max = min(max_files, 3)
        return scored_docs[:hard_max]

    def build_query(self, issue_description: str, search_symbols: List[str] | None = None, evidence: str = "") -> str:
        parts = [issue_description]
        if search_symbols:
            parts.append(f"Symbols: {' '.join(search_symbols)}")
        if evidence:
            parts.append(f"Evidence: {evidence[:1000]}")
        return "\n".join(parts)

    def localize(self, file_path: str, content: str, query: str) -> LocalizationBundle:
        if len(content) <= self.refine_threshold:
            return LocalizationBundle(
                file_path=file_path,
                primary_snippet=content,
                fallback_mode="file_scope",
                confidence=1.0
            )

        try:
            tree = ast.parse(content)
            lines = content.splitlines()
            
            # 1. 提取所有 Top-level 或是 Class 中的 Method
            nodes = []
            constants = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    nodes.append(node)
                elif isinstance(node, ast.Assign):
                    # 捕捉可能是 Regex 或 Constants 的定義
                    for target in node.targets:
                        if isinstance(target, ast.Name) and (target.id.isupper() or "_re" in target.id.lower()):
                            start = node.lineno - 1
                            end = getattr(node, "end_lineno", node.lineno)
                            body = "\n".join(lines[max(0, start):end])
                            constants.append(body)

            if not nodes:
                return LocalizationBundle(file_path=file_path, primary_snippet=content, fallback_mode="file_scope")

            # 2. 評分系統 (Formula Implementation)
            snippets = []
            query_tokens = set(self._tokenize(query)) - self.python_keywords
            
            # 提取查詢中的行號 (從 Evidence: ... line x 提取)
            # P0-4: 增加對不同格式的容錯，並確保整數轉換
            target_linenos = []
            for n in re.findall(r'(?i)(?:line|L)\s*(\d+)', query):
                try:
                    target_linenos.append(int(n))
                except: continue
            
            for i, node in enumerate(nodes):
                start = node.lineno
                end = getattr(node, "end_lineno", node.lineno + 5)
                body = "\n".join(lines[max(0, start-1):end+1])
                body_tokens = set(self._tokenize(body))
                
                score = 0.0
                # A. 符號命中分
                overlap = len(query_tokens.intersection(body_tokens))
                score += overlap * 2.0
                
                # B. 行號精確命中分 (Traceback Guide)
                for t_line in target_linenos:
                    if start <= t_line <= end:
                        score += 500.0  # 絕對權重，優先選擇報錯行所在的函數
                
                # C. 文義分 (Parser/Regex 權重)
                parser_keywords = {"parser", "regex", "token", "read", "parse", "command", "match", "ignorecase"}
                if any(kw in body.lower() for kw in parser_keywords):
                    score += 15.0
                
                # C. 修補分 (邏輯密集度)
                if any(kw in body for kw in ["if ", "elif ", "re.compile", ".upper()", "ValueError"]):
                    score += 10.0
                
                snippets.append({
                    "name": node.name,
                    "content": body,
                    "score": score,
                    "lineno": node.lineno,
                    "end_lineno": end
                })

            # 3. 組裝 Bundle
            sorted_snippets = sorted(snippets, key=lambda x: -x["score"])

            primary = sorted_snippets[0]
            
            # P0-4: 實施 Surgical Line-Level Snippets
            # 如果函數體超過 30 行且有精確行號命中，則僅提供行號附近的 +/- 15 行
            primary_body = primary["content"]
            method_lines = primary_body.splitlines()
            if len(method_lines) > 30:
                # 尋找與 target_linenos 最匹配的行
                hit_line = -1
                for t_line in target_linenos:
                    if primary["lineno"] <= t_line <= primary["end_lineno"]:
                        hit_line = t_line
                        break
                
                if hit_line != -1:
                    # 換算成 snippet 內部的相對行號 (0-indexed for slice)
                    rel_hit = hit_line - primary["lineno"]
                    start_idx = max(0, rel_hit - 15)
                    end_idx = min(len(method_lines), rel_hit + 16)
                    cropped_body = "\n".join(method_lines[start_idx:end_idx])
                    
                    # 更新 primary 資訊
                    primary_body = cropped_body
                    primary["lineno"] = primary["lineno"] + start_idx
                    primary["end_lineno"] = primary["lineno"] + (end_idx - start_idx) - 1
                    primary["slice_note"] = f"(Surgical crop: L{primary['lineno']}-L{primary['end_lineno']})"

            supporting = [s["content"] for s in sorted_snippets[1:3] if s["score"] > 5.0]

            # 過濾相關的 Constants (簡單 Regex 匹配)
            relevant_constants = []
            for c in constants:
                if any(token in c.lower() for token in query_tokens) or any(kw in c.lower() for kw in ["re.compile", "re.ignorecase"]):
                    relevant_constants.append(c)

            slice_msg = f"Surgical slice based on score {primary['score']:.2f}"
            if "slice_note" in primary:
                slice_msg += f" {primary['slice_note']}"

            return LocalizationBundle(
                file_path=file_path,
                primary_snippet=primary_body,
                supporting_snippets=supporting,
                related_definitions=relevant_constants[:2],
                slice_reason=slice_msg,
                confidence=min(1.0, primary["score"] / 50.0),
                start_line=primary["lineno"],
                end_line=primary["end_lineno"]
            )

        except Exception as e:
            return LocalizationBundle(
                file_path=file_path,
                primary_snippet=content,
                fallback_mode="file_scope",
                slice_reason=f"AST Failure: {str(e)}"
            )
