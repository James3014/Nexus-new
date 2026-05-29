from typing import Any, Dict, List

class Localizer:
    """二階段語義代碼定位服務，用於定位與 Issue 相關的原始碼檔案"""
    
    def __init__(self, repository: Any):
        self.repository = repository

    def locate(self, issue_description: str, table_name: str = "code_index", limit: int = 3) -> List[Dict[str, Any]]:
        # 第一階段 FTS 全文檢索 / 向量檢索
        try:
            rows = self.repository.search_fts(
                table_name=table_name,
                query=issue_description,
                limit=limit,
                fallback_columns=["content", "source_path"]
            )
        except Exception:
            rows = []
            
        results = []
        if isinstance(rows, list):
            for row in rows:
                results.append({
                    "file_path": row.get("source_path"),
                    "record_id": row.get("record_id")
                })
        return results
