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

    def to_context_string(self) -> str:
        parts = [f"### FILE: {self.file_path}"]
        if self.fallback_mode == "file_scope":
            parts.append(self.primary_snippet)
            return "\n".join(parts)
            
        parts.append(f"# Refined snippets for {self.file_path}")
        parts.append(f"## Primary Target:\n{self.primary_snippet}\n")
        
        if self.supporting_snippets:
            parts.append("## Supporting Helpers:")
            for s in self.supporting_snippets:
                parts.append(f"{s}\n")
                
        if self.related_definitions:
            parts.append("## Related Definitions (Regex/Constants):")
            for d in self.related_definitions:
                parts.append(f"{d}\n")
                
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
        return list(set(re.findall(r'([a-zA-Z0-9_\-\./\+]+\.py)', text)))

    def rank_files(
        self,
        issue_description: str,
        repo_dir: Path,
        max_files: int = 3,
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
        for pyfile in py_files:
            rel_path = str(pyfile.relative_to(repo_dir))
            if any(p in rel_path.lower() for p in ("test", "__pycache__", "build", "docs")): continue
            try:
                content = pyfile.read_text(encoding="utf-8", errors="replace")
                if content.strip():
                    documents.append({"path": rel_path, "content": content, "file_path": pyfile})
            except: pass

        if not documents: return []
        
        tokenized_corpus = [self._tokenize(doc["content"][:4000]) for doc in documents]
        bm25 = BM25Okapi(tokenized_corpus)
        bm25_scores = bm25.get_scores(self._tokenize(issue_description))

        scored_docs = []
        for idx, doc in enumerate(documents):
            score = float(bm25_scores[idx])
            scored_docs.append((score, doc))
        scored_docs.sort(key=lambda x: -x[0])
        return scored_docs[:max_files]

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
            
            for node in nodes:
                start = node.lineno - 1
                end = getattr(node, "end_lineno", node.lineno + 5)
                body = "\n".join(lines[max(0, start-1):end+1])
                body_tokens = set(self._tokenize(body))
                
                score = 0.0
                # A. 符號命中分
                overlap = len(query_tokens.intersection(body_tokens))
                score += overlap * 2.0
                
                # B. 文義分 (Parser/Regex 權重)
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
                    "lineno": node.lineno
                })

            # 3. 組裝 Bundle
            sorted_snippets = sorted(snippets, key=lambda x: -x["score"])
            
            primary = sorted_snippets[0]
            supporting = [s["content"] for s in sorted_snippets[1:3] if s["score"] > 5.0]
            
            # 過濾相關的 Constants (簡單 Regex 匹配)
            relevant_constants = []
            for c in constants:
                if any(token in c.lower() for token in query_tokens) or any(kw in c.lower() for kw in ["re.compile", "re.ignorecase"]):
                    relevant_constants.append(c)

            return LocalizationBundle(
                file_path=file_path,
                primary_snippet=primary["content"],
                supporting_snippets=supporting,
                related_definitions=relevant_constants[:2],
                slice_reason=f"Surgical slice based on score {primary['score']:.2f}",
                confidence=min(1.0, primary["score"] / 50.0)
            )

        except Exception as e:
            return LocalizationBundle(
                file_path=file_path, 
                primary_snippet=content, 
                fallback_mode="file_scope",
                slice_reason=f"AST Failure: {str(e)}"
            )
