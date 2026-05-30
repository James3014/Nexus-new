import re
import ast
import urllib.request
import json
import numpy as np
from pathlib import Path
from typing import Any, Dict, List, Tuple
from rank_bm25 import BM25Okapi

class Localizer:
    """二階段語意代碼定位服務，整合 BM25 稀疏檢索、AST 關鍵字加權與稠密向量 RAG。"""
    
    def __init__(self, repository: Any = None, ollama_endpoint: str = "http://localhost:11434"):
        self.repository = repository
        self.ollama_endpoint = ollama_endpoint

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

    def _get_ollama_embedding(self, text: str) -> List[float]:
        """從 Ollama 獲取 nomic-embed-text 向量"""
        payload = json.dumps({
            "model": "nomic-embed-text",
            "prompt": text[:1500]  # 限制長度以避免向量計算溢出
        }).encode()
        req = urllib.request.Request(
            f"{self.ollama_endpoint}/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                return data.get("embedding", [])
        except Exception:
            return []

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2:
            return 0.0
        arr1 = np.array(v1)
        arr2 = np.array(v2)
        norm1 = np.linalg.norm(arr1)
        norm2 = np.linalg.norm(arr2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(arr1, arr2) / (norm1 * norm2))

    def _rerank_with_ollama(
        self, 
        issue_description: str, 
        candidates: List[Tuple[float, Dict[str, Any]]], 
        max_files: int
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """使用 nomic-embed-text 向量進行稠密重排"""
        query_vector = self._get_ollama_embedding(issue_description)
        if not query_vector:
            return candidates[:max_files]
            
        reranked = []
        for bm25_score, doc in candidates:
            # 計算該檔案前半部的 Embedding
            doc_vector = self._get_ollama_embedding(doc["content"][:2000])
            if doc_vector:
                similarity = self._cosine_similarity(query_vector, doc_vector)
                # 混合分數：0.3 * BM25_Score_Normalized + 0.7 * Cosine_Similarity
                # 為簡化，直接將 Similarity 作為重排依據
                reranked.append((similarity, doc))
            else:
                reranked.append((0.0, doc))
                
        reranked.sort(key=lambda x: -x[0])
        return reranked[:max_files]

    def locate(
        self, 
        issue_description: str, 
        repo_dir: Path, 
        max_files: int = 3, 
        use_ollama_rag: bool = False
    ) -> List[Tuple[str, str]]:
        # 1. 蒐集專案內所有 Python 檔案，排除測試與建置目錄
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
                    
            # 檔案名稱與路徑特徵加權
            path_lower = doc["path"].lower()
            for word in query_words:
                if len(word) > 3 and word in path_lower:
                    score += 10.0  # 小幅路徑匹配加權
                    
            scored_docs.append((score, doc))
            
        # 排序
        scored_docs.sort(key=lambda x: -x[0])
        
        # 取得 Top-K 候選檔案（粗篩）
        coarse_limit = max(10, max_files * 3)
        candidates = scored_docs[:coarse_limit]
        
        # 5. 若啟用 Ollama 稠密向量重排 (Ollama RAG)
        if use_ollama_rag:
            try:
                candidates = self._rerank_with_ollama(issue_description, candidates, max_files)
            except Exception as e:
                # Fallback to pure BM25+AST
                candidates = candidates[:max_files]
        else:
            candidates = candidates[:max_files]
            
        # 格式化輸出
        results = []
        for _, doc in candidates:
            content = doc["content"]
            if len(content) > 6000:
                content = content[:6000] + "\n... [truncated]"
            results.append((doc["path"], content))
            
        return results
