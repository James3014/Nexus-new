import json
from pathlib import Path
from nexus.services.memory import MemoryService

def engrave():
    project_root = str(__import__("pathlib").Path(__file__).resolve().parents[2])
    memory = MemoryService(project_root)
    
    policies = [
        {
            "id": "PHA-051-A",
            "content": "語音通報分級機制：Urgency 為 critical 的提示不受 silent 模式限制。重要的提示（如啟動、完成、嚴重告警）應始終發聲。",
            "category": "UX_SHIELD",
            "relevance": 1.0
        },
        {
            "id": "PHA-051-B",
            "content": "指揮官協議 (Orchestrator Protocol)：除非 Sir 特別要求手動，否則所有實施類任務應委派給 Nexus 子代理執行，以累積學習樣本。",
            "category": "GOVERNANCE",
            "relevance": 1.0
        },
        {
            "id": "PHA-051-C",
            "content": "記憶持久化：核心運行策略應寫入政策記憶體 (Policy Memory)，確保系統重啟後能自動對齊 Sir 的偏好。",
            "category": "MEMORY",
            "relevance": 1.0
        }
    ]
    
    print("🧠 Engraving Core Policies into Nexus Brain...")
    for p in policies:
        # In a real v9, MemoryService would have an 'ingest_policy' method.
        # Currently, we'll append to the local knowledge/policies.jsonl if LanceDB isn't setup.
        # But MemoryService should handle the storage.
        memory.ingest_episode(p) # Using ingest_episode for now if it's the only available method
        print(f"✅ Engraved: {p['id']}")

if __name__ == "__main__":
    engrave()
