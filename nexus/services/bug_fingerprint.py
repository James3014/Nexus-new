"""
🛡️ Nexus Bug Fingerprint: 相似 Bug 指紋檢索與成功修復推薦 (P2-C)
利用 Traceback 進行語義檢索，並過濾出歷史成功修復路徑。
"""

from typing import List, Dict, Optional
import json
from pathlib import Path

from nexus.services.lesson_retrieval import retrieve_hybrid_candidates
from nexus.services.memory_indexer import connect_memory_db, TABLE_NAME

def find_similar_bugs(
    repo_root: Path, 
    traceback: str, 
    category: str = "", 
    top_k: int = 5
) -> List[Dict]:
    """相似 Bug 指紋檢索 + 成功修復模板 (P2-C)"""
    
    # 建構查詢文本 (對齊 MiniLM 語義密度)
    query_text = f"Traceback Pattern: {traceback[:400]} | Category: {category}"
    
    # 混合檢索 (向量優先)
    # 我們設定較大的 max_candidates 以確保在過濾 outcome 之前有充足候選
    candidates = retrieve_hybrid_candidates(
        repo_root, query_text, max_candidates=top_k * 4
    )
    
    # 只保留成功修復的記錄 (outcome=success 且含有 corrective_action)
    successful_fixes = []
    for cand in candidates:
        if (
            cand.get("outcome") == "success" and 
            cand.get("corrective_action") and
            ("lesson_id" in cand or "task_id" in cand)
        ):
            successful_fixes.append({
                "lesson_id": cand.get("lesson_id", "local_temp"),
                "similarity": cand.get("_vector_distance", 1.0),
                "category": cand.get("category", ""),
                "root_cause": cand.get("root_cause", ""),
                "fix_template": cand.get("corrective_action"),
                "success_rate": cand.get("success_rate", 1.0),
                "phase": cand.get("phase", cand.get("source_phase", "")),
            })
    
    # 按相似度排序 (LanceDB 距離越小越相似)
    successful_fixes.sort(key=lambda x: x["similarity"])
    return successful_fixes[:top_k]

def get_repair_recommendations(repo_root: Path, diagnosis: Dict) -> Dict:
    """根據診斷產出指令集的修復推薦"""
    traceback = diagnosis.get("traceback_snippet", "")
    category = diagnosis.get("primary_category", "")
    
    if not traceback:
        return {"status": "no_traceback", "recommendations": [], "prompt_context": ""}
    
    recommendations = find_similar_bugs(repo_root, traceback, category)
    
    return {
        "status": "ok",
        "total_matches": len(recommendations),
        "recommendations": recommendations,
        "prompt_context": format_repair_prompt(recommendations),
    }

def format_repair_prompt(recommendations: List[Dict]) -> str:
    """格式化給 LLM 的最佳修復提示 (P3 準備)"""
    if not recommendations:
        return "No similar successful fixes found in current memory index."
    
    lines = ["## 🔍 Historical Successful Fixes"]
    for i, rec in enumerate(recommendations[:3], 1):
        lines.extend([
            f"### Fix #{i} ({rec['category']}, Similarity: {rec['similarity']:.2f})",
            f"* **Root Cause**: {rec['root_cause']}",
            f"* **Fix Template**: `{rec['fix_template']}`",
            f"* **Success Rate**: {rec['success_rate']:.0%}",
            "",
        ])
    return "\n".join(lines).strip()
