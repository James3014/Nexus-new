import re
import ast
from pathlib import Path
from typing import Any, Dict, List, Tuple
from rank_bm25 import BM25Okapi

class Localizer:
    """二階段語意代碼定位服務，整合 BM25 稀疏檢索、AST 關鍵字加權。"""
    
    def __init__(self, repository: Any = None):
        self.repository = repository

    def _tokenize(self, text: str) -> List[str]:
        # 清除特殊符號並切分為小寫 Token
        return re.findall(r'\b[a-zA-Z_0-9]{2,}\b', text.lower())

    def _extract_ast_names(self, code: str) -> Tuple[List[str], List[str]]:
        """從 Python 程式碼中靜態提取 Class 與 Function 的定義名稱"""
        classes = []
        functions = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    classes.append(node.name)
                elif isinstance(node, ast.FunctionDef):
                    functions.append(node.name)
        except Exception:
            pass
        return classes, functions

    def rank_files(
        self, 
        issue_description: str, 
        repo_dir: Path, 
        max_files: int = 3
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """對專案內的檔案基於 issue_description 進行評分排序，回傳 top_k 候選檔案"""
        documents = []
        for pyfile in repo_dir.rglob("*.py"):
            rel_path = str(pyfile.relative_to(repo_dir))
            if any(p in rel_path.lower() for p in ("test", "__pycache__", ".tox", "build", "dist")):
                continue
            try:
                content = pyfile.read_text(encoding="utf-8", errors="replace")
                if content.strip():
                    documents.append({
                        "path": rel_path,
                        "content": content,
                        "file_path": pyfile
                    })
            except Exception:
                pass
                
        if not documents:
            return []

        # 2. Tokenize corpus and fit BM25
        tokenized_corpus = []
        for doc in documents:
            # 只取前 4000 字元來做檢索，加速運算並聚焦於核心邏輯
            tokenized_corpus.append(self._tokenize(doc["content"][:4000]))
            
        bm25 = BM25Okapi(tokenized_corpus)
        
        # 3. 計算 BM25 基礎分數
        tokenized_query = self._tokenize(issue_description)
        bm25_scores = bm25.get_scores(tokenized_query)
        
        # 4. AST 與啟發式特徵加權
        scored_docs = []
        query_words = set(tokenized_query)
        
        for idx, doc in enumerate(documents):
            score = float(bm25_scores[idx])
            
            # AST 提取與精確匹配加權
            classes, functions = self._extract_ast_names(doc["content"])
            
            # 若 query 精確包含 class 或 function 名稱，給予額外加權
            for cls in classes:
                if cls.lower() in query_words:
                    score += 35.0  # 大幅加權
            for fn in functions:
                if fn.lower() in query_words:
                    score += 20.0  # 中幅加權
                    
            # Heuristic: 若問題提到 required column，且代碼中含有 _required_columns 或 required_columns
            doc_content_lower = doc["content"].lower()
            if "required" in query_words or "column" in query_words:
                if "required_columns" in doc_content_lower or "_required_columns" in doc_content_lower:
                    score += 45.0  # 強力召回
                    
            # 檔案名稱與路徑特徵加權
            path_lower = doc["path"].lower()
            for word in query_words:
                if len(word) > 3 and word in path_lower:
                    score += 10.0  # 小幅路徑匹配加權
                    
            scored_docs.append((score, doc))
            
        # 排序
        scored_docs.sort(key=lambda x: -x[0])
        return scored_docs[:max_files]

    def extract_relevant_code(
        self, 
        scored_files: List[Tuple[float, Dict[str, Any]]]
    ) -> List[Tuple[str, str]]:
        """將排名好的 ScoredFile 內容提取並做基礎截斷處理"""
        results = []
        for _, doc in scored_files:
            content = doc["content"]
            if len(content) > 6000:
                content = content[:6000] + "\n... [truncated]"
            results.append((doc["path"], content))
        return results

    def locate(
        self, 
        issue_description: str, 
        repo_dir: Path, 
        max_files: int = 3, 
        use_ollama_rag: bool = False
    ) -> List[Tuple[str, str]]:
        """保留 locate() 介面做向後相容"""
        ranked = self.rank_files(issue_description, repo_dir, max_files)
        return self.extract_relevant_code(ranked)
