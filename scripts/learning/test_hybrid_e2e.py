"""
🛡️ Nexus P2-B: Hybrid Retrieval E2E Validation
驗證從向量索引、混合檢索到共識輸出的全鏈路。
"""

import os
import json
import shutil
import sys
from pathlib import Path
from datetime import datetime, timezone

# 確保 nexus package 被匯入
sys.path.append(os.getcwd())

from nexus.services.memory_indexer import rebuild_memory_index
from nexus.services.lesson_retrieval import retrieve_with_resolution

def setup_mock_repo(tmp_path: Path):
    """建立測試場景：包含本地與聯邦教訓"""
    nexus_dir = tmp_path / ".nexus"
    knowledge_dir = nexus_dir / "knowledge"
    learning_dir = nexus_dir / "learning"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    learning_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. 本地 Lesson: Python Syntax
    l1 = {
        "lesson_id": "L1", "task_id": "T1", "category": "PYTHON",
        "root_cause": "Syntax error in list comprehension",
        "corrective_action": "Use proper bracket syntax",
        "confidence": 0.9, "timestamp_utc": "2026-04-01T12:00:00Z"
    }
    (knowledge_dir / "lesson_events.jsonl").write_text(json.dumps(l1) + "\n")
    
    # 2. 聯邦 Lesson: OS Permissions (Envelope 封裝)
    l2 = {
        "lesson_id": "L2", "task_id": "T2", "category": "OS",
        "root_cause": "Permissions denied on /tmp/nexus",
        "corrective_action": "chmod 755 /tmp/nexus",
        "timestamp_utc": "2026-04-02T10:00:00Z"
    }
    env2 = {
        "cache_id": "C2", "trust_tier": "peer", "source_type": "p2p",
        "local_weight": 0.85, "lesson": l2
    }
    (learning_dir / "shared_lessons.jsonl").write_text(json.dumps(env2) + "\n")
    
    return tmp_path

def run_e2e_test():
    repo_root = Path("/tmp/nexus_p2b_e2e")
    if repo_root.exists(): shutil.rmtree(repo_root)
    repo_root.mkdir(parents=True)
    
    try:
        print("🚀 [E2E] Phase 1: Setting up mock repo...")
        setup_mock_repo(repo_root)
        
        print("🚀 [E2E] Phase 2: Rebuilding vector index (P2-A/B)...")
        # 直接執行索引重建
        res = rebuild_memory_index(repo_root)
        print(f"✅ Records processed: {res['records_processed']}")
        
        print("🚀 [E2E] Phase 3: Testing Hybrid Retrieval (OS query)...")
        # 測試場景：針對 OS 權限問題發問
        diagnosis = {"primary_category": "OS"}
        resolution = retrieve_with_resolution(
            repo_root, 
            "Fixing permission denied errors on temporary directories",
            diagnosis=diagnosis
        )
        
        metadata = resolution.get("metadata", {})
        print(f"📊 Backend Used: {metadata.get('backend_used')}")
        print(f"📊 Candidate Count: {metadata.get('candidate_count')}")
        print(f"📊 Consensus Score: {resolution.get('consensus_score')}")
        print(f"📊 Top Lesson ID: {resolution.get('best_lesson_id')}")
        
        # 斷言
        assert metadata.get("backend_used") == "lancedb", f"Should use lancedb backend, got {metadata.get('backend_used')}"
        assert resolution["status"] == "high_consensus", f"Should achieve high consensus, got {resolution['status']}"
        assert resolution.get("best_lesson_id") == "L2", f"Should recall L2 (OS permissions), got {resolution.get('best_lesson_id')}"
        assert "chmod 755" in resolution["prompt_context"], "Context should be rich"
        
        print("\n🏆 [E2E:SUCCESS] Nexus P2-B Hybrid Retrieval is operationally sound.")
        
    finally:
        if repo_root.exists(): shutil.rmtree(repo_root)

if __name__ == "__main__":
    run_e2e_test()
