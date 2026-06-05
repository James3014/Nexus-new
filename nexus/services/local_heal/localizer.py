import re
import ast
from pathlib import Path
from typing import Any, Dict, List, Tuple
from rank_bm25 import BM25Okapi

class Localizer:
    def __init__(self, repository: Any = None, refine_threshold: int = 5000):
        self.repository = repository
        self.refine_threshold = refine_threshold

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
        print(f"🔍 [Localizer] Scanning {repo_dir} for relevant files...", flush=True)
        explicit_paths = self._extract_paths_from_issue(issue_description)

        # 優先處理明確路徑
        found_explicit = []
        for path in explicit_paths:
            candidate = Path(path)
            if candidate.is_absolute():
                try:
                    rel_path = candidate.resolve().relative_to(repo_dir.resolve())
                except ValueError:
                    continue
                p = candidate
                display_path = str(rel_path)
            else:
                p = repo_dir / candidate
                display_path = path
            if p.exists():
                found_explicit.append((10000.0, {
                    "path": display_path,
                    "content": p.read_text(errors="replace"),
                    "file_path": p,
                    "issue_desc": issue_description  # 注入 Query 供後續精煉使用
                }))

        if found_explicit:
            print(f"✅ [Localizer] Found {len(found_explicit)} explicit files from issue description.")
            return found_explicit[:max_files]

        documents = []
        py_files = list(repo_dir.rglob("*.py"))
        total = len(py_files)
        print(f"📂 [Localizer] Indexing {total} files...", flush=True)

        for i, pyfile in enumerate(py_files):
            if i % 500 == 0 and i > 0:
                print(f"  → Indexed {i}/{total} files...", flush=True)
            rel_path = str(pyfile.relative_to(repo_dir))
            if any(p in rel_path.lower() for p in ("test", "__pycache__", ".tox", "build", "dist", "cextern", "docs")): continue
            try:
                # 僅讀取前 8k 以加速索引
                content = pyfile.read_text(encoding="utf-8", errors="replace")
                if content.strip():
                    documents.append({"path": rel_path, "content": content, "file_path": pyfile})
            except: pass

        if not documents: return []
        print(f"🧠 [Localizer] Running BM25 scoring on {len(documents)} candidates...", flush=True)
        tokenized_corpus = [self._tokenize(doc["content"][:4000]) for doc in documents]
        bm25 = BM25Okapi(tokenized_corpus)
        bm25_scores = bm25.get_scores(self._tokenize(issue_description))

        scored_docs = []
        for idx, doc in enumerate(documents):
            score = float(bm25_scores[idx]) + self._symbol_score(doc["content"], doc["path"], search_symbols or [])
            scored_docs.append((score, doc))
        scored_docs.sort(key=lambda x: -x[0])
        return scored_docs[:max_files]

    def _symbol_score(self, content: str, path: str, search_symbols: List[str]) -> float:
        if not search_symbols:
            return 0.0

        lowered_path = path.lower()
        score = 0.0
        defined_names = set()
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    defined_names.add(node.name)
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            defined_names.add(target.id)
        except SyntaxError:
            defined_names = set()

        for symbol in search_symbols:
            if not symbol:
                continue
            escaped = re.escape(symbol)
            if symbol in defined_names:
                score += 1000.0
            elif re.search(rf"\b{escaped}\b", content):
                score += 25.0
            if symbol.lower() in lowered_path:
                score += 10.0
        return score

    def extract_relevant_code(self, scored_files: List[Tuple[float, Dict[str, Any]]], query: str = "") -> List[Tuple[str, str]]:
        results = []
        for _, doc in scored_files:
            content = doc["content"]
            active_query = query or doc.get("issue_desc", "")
            # 若檔案太長，嘗試進行函式級精煉
            if len(content) > self.refine_threshold and active_query:
                refined = self.refine_by_functions(doc["path"], content, active_query)
                if refined:
                    content = refined

            if len(content) > 6000: content = content[:6000] + "\n... [truncated]"
            results.append((doc["path"], content))
        return results

    def refine_by_functions(self, file_path: str, content: str, query: str) -> str:
        """
        利用 AST 提取函式級片段，並利用 BM25 找出與 query 最相關的片段。
        """
        try:
            tree = ast.parse(content)
            snippets = []
            lines = content.splitlines()

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    start = node.lineno - 1
                    end = getattr(node, "end_lineno", node.lineno + 10)
                    body = "\n".join(lines[max(0, start-2):end+1]) # 帶 2 行 context
                    snippets.append({"name": node.name, "content": body, "start": start})

            if not snippets: return content

            tokenized_snippets = [self._tokenize(s["content"]) for s in snippets]
            bm25 = BM25Okapi(tokenized_snippets)
            scores = bm25.get_scores(self._tokenize(query))

            scored = sorted(zip(scores, snippets), key=lambda x: -x[0])
            # 取 top-3 相關片段並按原始順序排列以維持邏輯連貫
            top_snippets = sorted(scored[:3], key=lambda x: x[1]["start"])

            result = [f"# Refined snippets for {file_path}"]
            for score, s in top_snippets:
                if score > 0:
                    result.append(f"## {s['name']} (Score: {score:.2f})\n{s['content']}\n")

            return "\n".join(result) if len(result) > 1 else content
        except Exception:
            return content

    def locate(
        self,
        issue_description: str,
        repo_dir: Path,
        max_files: int = 3,
        search_symbols: List[str] | None = None,
        evidence: str = "",
    ) -> List[Tuple[str, str]]:
        query = self.build_query(issue_description, search_symbols=search_symbols, evidence=evidence)
        ranked = self.rank_files(query, repo_dir, max_files)
        # 傳遞 issue_description 供精煉使用
        for _, doc in ranked:
            doc["issue_desc"] = query
        return self.extract_relevant_code(ranked, query=query)

    def build_query(self, issue_description: str, search_symbols: List[str] | None = None, evidence: str = "") -> str:
        parts = [issue_description]
        symbols = " ".join(search_symbols or [])
        if symbols:
            parts.append(f"Symbols: {symbols}")
        if evidence:
            parts.append(f"Evidence: {evidence[:1000]}")
        return "\n".join(part for part in parts if part)
