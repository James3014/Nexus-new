"""SWE-Explore Lite: multi-granularity retrieval with line-window evidence."""
from __future__ import annotations
import ast
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class LineWindowEvidence:
    """Compact evidence for a line window in a file."""
    file_path: str
    start_line: int
    end_line: int
    content: str
    hit_reason: str  # "symbol_match", "traceback_line", "query_token_match"
    semantic_tags: List[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class RetrievalBudget:
    """Budget constraints for retrieval."""
    max_files: int = 3
    max_symbols_per_file: int = 5
    max_line_windows: int = 10
    max_lines_per_window: int = 30


class SWEExploreLite:
    """Multi-granularity retrieval: file → symbol/function → line-window."""
    
    def __init__(self, budget: RetrievalBudget = None):
        self.budget = budget or RetrievalBudget()
    
    def retrieve(
        self,
        query: str,
        repo_dir: Path,
        target_files: List[str] = None,
        symbols: List[str] = None,
    ) -> Dict[str, Any]:
        """Execute multi-granularity retrieval.
        
        Returns:
            {
                "files": [...],
                "symbols": [...],
                "line_windows": [...],
                "evidence_summary": "...",
                "metrics": {...}
            }
        """
        metrics = {"files_scanned": 0, "symbols_found": 0, "windows_extracted": 0}
        
        # Step 1: File-level retrieval
        files = self._retrieve_files(query, repo_dir, target_files, metrics)
        
        # Step 2: Symbol/function-level retrieval
        symbols_result = self._retrieve_symbols(query, files, symbols, metrics)
        
        # Step 3: Line-window retrieval
        line_windows = self._retrieve_line_windows(query, symbols_result, metrics)
        
        # Step 4: Build evidence summary
        evidence_summary = self._build_evidence_summary(line_windows)
        
        return {
            "files": files,
            "symbols": symbols_result,
            "line_windows": line_windows,
            "evidence_summary": evidence_summary,
            "metrics": metrics,
        }
    
    def _retrieve_files(
        self,
        query: str,
        repo_dir: Path,
        target_files: List[str] = None,
        metrics: Dict = None,
    ) -> List[Dict[str, Any]]:
        """File-level retrieval using BM25-like scoring."""
        results = []
        
        if target_files:
            for tf in target_files[:self.budget.max_files]:
                file_path = repo_dir / tf
                if file_path.exists():
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="replace")
                        results.append({
                            "path": tf,
                            "content": content,
                            "score": self._file_score(content, query),
                        })
                        if metrics:
                            metrics["files_scanned"] += 1
                    except Exception:
                        continue
        else:
            # Scan repo for Python files
            py_files = list(repo_dir.rglob("*.py"))
            for pyfile in py_files[:100]:  # Limit scan
                rel_path = str(pyfile.relative_to(repo_dir))
                if any(p in rel_path.lower() for p in ("test", "__pycache__", ".venv")):
                    continue
                try:
                    content = pyfile.read_text(encoding="utf-8", errors="replace")
                    score = self._file_score(content, query)
                    if score > 0:
                        results.append({
                            "path": rel_path,
                            "content": content,
                            "score": score,
                        })
                        if metrics:
                            metrics["files_scanned"] += 1
                except Exception:
                    continue
        
        results.sort(key=lambda x: -x["score"])
        return results[:self.budget.max_files]
    
    def _retrieve_symbols(
        self,
        query: str,
        files: List[Dict[str, Any]],
        target_symbols: List[str] = None,
        metrics: Dict = None,
    ) -> List[Dict[str, Any]]:
        """Symbol/function-level retrieval using AST."""
        results = []
        
        for file_info in files:
            try:
                tree = ast.parse(file_info["content"])
                lines = file_info["content"].splitlines()
                
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        start = node.lineno - 1
                        end = getattr(node, "end_lineno", node.lineno + 10)
                        body = "\n".join(lines[max(0, start):end + 1])
                        
                        # Score based on query tokens
                        score = self._symbol_score(body, query, target_symbols)
                        
                        if score > 0:
                            results.append({
                                "file_path": file_info["path"],
                                "name": node.name,
                                "type": type(node).__name__,
                                "start_line": node.lineno,
                                "end_line": end,
                                "content": body,
                                "score": score,
                            })
                            if metrics:
                                metrics["symbols_found"] += 1
            except SyntaxError:
                continue
        
        results.sort(key=lambda x: -x["score"])
        return results[:self.budget.max_symbols_per_file * len(files)]
    
    def _retrieve_line_windows(
        self,
        query: str,
        symbols: List[Dict[str, Any]],
        metrics: Dict = None,
    ) -> List[LineWindowEvidence]:
        """Line-window retrieval for precise evidence."""
        results = []
        query_tokens = set(self._tokenize(query))
        
        for sym in symbols:
            lines = sym["content"].splitlines()
            
            # Find lines matching query tokens
            matching_lines = []
            for i, line in enumerate(lines):
                line_tokens = set(self._tokenize(line))
                if query_tokens.intersection(line_tokens):
                    matching_lines.append(i)
            
            if matching_lines:
                # Create windows around matching lines
                for match_line in matching_lines[:3]:  # Max 3 windows per symbol
                    start = max(0, match_line - 5)
                    end = min(len(lines), match_line + 6)
                    window_content = "\n".join(lines[start:end])
                    
                    results.append(LineWindowEvidence(
                        file_path=sym["file_path"],
                        start_line=sym["start_line"] + start,
                        end_line=sym["start_line"] + end,
                        content=window_content,
                        hit_reason="query_token_match",
                        confidence=min(1.0, len(query_tokens.intersection(self._tokenize(window_content))) / max(1, len(query_tokens))),
                    ))
                    if metrics:
                        metrics["windows_extracted"] += 1
        
        return results[:self.budget.max_line_windows]
    
    def _build_evidence_summary(self, line_windows: List[LineWindowEvidence]) -> str:
        """Build compact evidence summary."""
        if not line_windows:
            return "No evidence found."
        
        parts = []
        for i, lw in enumerate(line_windows[:5]):  # Max 5 windows in summary
            parts.append(
                f"[{i+1}] {lw.file_path}:{lw.start_line}-{lw.end_line} "
                f"(confidence={lw.confidence:.2f}, reason={lw.hit_reason})"
            )
        
        return "\n".join(parts)
    
    def _file_score(self, content: str, query: str) -> float:
        """Simple BM25-like file scoring."""
        query_tokens = set(self._tokenize(query))
        content_tokens = set(self._tokenize(content[:4000]))
        overlap = len(query_tokens.intersection(content_tokens))
        return overlap * 2.0
    
    def _symbol_score(self, content: str, query: str, target_symbols: List[str] = None) -> float:
        """Score symbol by query match and target symbols."""
        query_tokens = set(self._tokenize(query))
        content_tokens = set(self._tokenize(content))
        score = len(query_tokens.intersection(content_tokens)) * 2.0
        
        if target_symbols:
            for sym in target_symbols:
                if sym in content:
                    score += 100.0  # Exact symbol match bonus
        
        return score
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization."""
        return [t.lower() for t in re.findall(r'\b[a-zA-Z_0-9]{2,}\b', text)]
