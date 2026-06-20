"""
RepoMap MVP v1.0

File-level candidate ranking + symbol proximity expansion + prompt compression.
For localization phase — finds the most relevant files for a given issue.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from rank_bm25 import BM25Okapi


@dataclass
class FileCandidate:
    """A file candidate with relevance score and context."""
    path: str
    score: float
    symbols: List[str] = field(default_factory=list)
    snippet: str = ""
    start_line: int = 0
    end_line: int = 0


@dataclass
class RepoMapResult:
    """Result of RepoMap analysis."""
    candidates: List[FileCandidate]
    query_tokens: List[str]
    total_files_scanned: int = 0
    
    @property
    def top_candidates(self) -> List[FileCandidate]:
        return sorted(self.candidates, key=lambda c: -c.score)[:10]


class RepoMap:
    """
    MVP RepoMap: file-level candidate ranking using BM25 + symbol extraction.
    
    Three capabilities:
    1. File-level candidate ranking (BM25 over file contents)
    2. Symbol proximity expansion (callers/callees/same-file neighbors)
    3. Prompt compression output (top N candidates with key snippets)
    """
    
    def __init__(self, repo_dir: Path):
        self.repo_dir = repo_dir
        self._file_index: Dict[str, str] = {}  # path -> content
        self._symbol_index: Dict[str, List[str]] = {}  # symbol -> [files]
    
    def build_index(self) -> None:
        """Scan repo and build file + symbol indices."""
        for py_file in self.repo_dir.rglob("*.py"):
            try:
                rel = str(py_file.relative_to(self.repo_dir))
                content = py_file.read_text(encoding="utf-8", errors="replace")
                self._file_index[rel] = content
                
                # Extract top-level symbols
                try:
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            name = node.name
                            if name not in self._symbol_index:
                                self._symbol_index[name] = []
                            self._symbol_index[name].append(rel)
                except SyntaxError:
                    pass
            except Exception:
                pass
    
    def tokenize(self, text: str) -> List[str]:
        """Tokenize text for BM25."""
        return re.findall(r'\b[a-zA-Z_0-9]{2,}\b', text.lower())
    
    def rank_files(self, issue_description: str, max_files: int = 10) -> RepoMapResult:
        """Rank files by relevance to the issue description."""
        if not self._file_index:
            self.build_index()
        
        if not self._file_index:
            return RepoMapResult(candidates=[], query_tokens=[], total_files_scanned=0)
        
        # Tokenize issue description
        query_tokens = self.tokenize(issue_description)
        
        # BM25 ranking
        paths = list(self._file_index.keys())
        corpus = [self._file_index[p] for p in paths]
        tokenized_corpus = [self.tokenize(doc) for doc in corpus]
        
        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(query_tokens)
        
        # Build candidates
        candidates = []
        for i, (path, score) in enumerate(zip(paths, scores)):
            if score > 0:
                # Extract symbols from this file
                symbols = []
                for sym, files in self._symbol_index.items():
                    if path in files:
                        symbols.append(sym)
                
                # Get first 20 lines as snippet
                content = self._file_index[path]
                snippet = "\n".join(content.splitlines()[:20])
                
                candidates.append(FileCandidate(
                    path=path,
                    score=float(score),
                    symbols=symbols[:10],
                    snippet=snippet,
                ))
        
        # Sort by score descending
        candidates.sort(key=lambda c: -c.score)
        
        return RepoMapResult(
            candidates=candidates[:max_files],
            query_tokens=query_tokens,
            total_files_scanned=len(paths),
        )
    
    def expand_symbol(self, symbol: str, depth: int = 1) -> List[str]:
        """Find files that reference this symbol (callers/callees)."""
        if not self._symbol_index:
            self.build_index()
        
        # Direct references
        files = set(self._symbol_index.get(symbol, []))
        
        # Expand: find files that import or reference the symbol
        if depth > 0:
            for path, content in self._file_index.items():
                if path not in files and symbol in content:
                    files.add(path)
        
        return sorted(files)
    
    def compress_for_prompt(self, result: RepoMapResult, max_files: int = 5, max_lines_per_file: int = 30) -> str:
        """Compress RepoMap result into a compact prompt-ready string."""
        parts = []
        parts.append(f"# Repository Map ({result.total_files_scanned} files scanned)")
        parts.append(f"# Query tokens: {', '.join(result.query_tokens[:10])}")
        parts.append("")
        
        for i, cand in enumerate(result.top_candidates[:max_files]):
            parts.append(f"## Candidate {i+1}: {cand.path} (score={cand.score:.2f})")
            if cand.symbols:
                parts.append(f"Symbols: {', '.join(cand.symbols[:5])}")
            # Truncate snippet
            lines = cand.snippet.splitlines()[:max_lines_per_file]
            parts.append("\n".join(lines))
            parts.append("")
        
        return "\n".join(parts)
