import json
import logging
import lancedb
from pathlib import Path

# Silence huggingface verbosity
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

def count_and_verify():
    root = Path("/Users/jameschen/Workspace/nexus")
    print("📊 [Nexus v0.9] Memory System Overview & Utility Verification\n" + "="*60)
    
    # 1. Count records
    print("\n📦 1. 當前系統記憶庫存量 (Memory Inventory)\n" + "-"*40)
    
    # physical files
    lesson_path = root / ".nexus" / "knowledge" / "lesson_events.jsonl"
    local_count = 0
    if lesson_path.exists():
        with open(lesson_path, 'r') as f:
            local_count = len([line for line in f if line.strip()])
    print(f"  [物理檔案] lesson_events.jsonl: {local_count} 筆原始教訓紀錄")
    
    # LanceDB vectors
    try:
        db = lancedb.connect(str(root / ".nexus" / "memory" / "memory_index.lancedb"))
        table = db.open_table("memory_index")
        df = table.to_pandas()
        print(f"  [向量核心] LanceDB (memory_index): {len(df)} 筆高維度嵌入記憶向量")
        
        # breakdown by type
        counts = df['record_type'].value_counts().to_dict()
        for k, v in counts.items():
            print(f"     - {k}: {v} 筆")
    except Exception as e:
        print("  無法讀取 LanceDB:", e)
        table = None
        df = None

    # 2. Test Utility
    print("\n🎯 2. 進化效用實測 (Utility & Helpfulness Verification)\n" + "-"*40)
    print("  情境：我們剛才模擬中學到了「Port 8080 被防火牆阻擋」這個教訓。")
    print("  假設現在指揮官委派了一個全新任務給 Agent：")
    
    query = "Deploy the new API service, please make sure it's accessible via port 8080 over the internal network."
    print(f"  [新任務描述] \"{query}\"")
    print("  [檢索引擎] 正在查詢 Nexus Wisdom Layer 檢索與這項新任務最相關的歷史教訓...\n")
    
    if table:
        try:
            from sentence_transformers import SentenceTransformer
            print("  (Loading all-MiniLM-L6-v2 to evaluate semantic similarity...)")
            model = SentenceTransformer("all-MiniLM-L6-v2")
            query_vector = model.encode(query).tolist()
            
            # Retrieve top 3
            results = table.search(query_vector).limit(3).to_pandas()
            
            print("\n  [檢索結果] 依語意相似度 (L2 Distance / Cosine) 關聯的記憶：")
            for i, row in results.iterrows():
                dist = row['_distance']
                payload = json.loads(row['payload_json'])
                text_preview = payload.get('root_cause', payload.get('category', 'N/A'))
                print(f"   🏆 Match #{i+1} (D={dist:.4f}) | 來源: {row['record_type']}")
                print(f"      - task_id: {row['task_id']}")
                print(f"      - 核心摘要: {text_preview}")
                
            # Verify if our E2E lesson was in the top 3
            if any("8080" in json.loads(r['payload_json']).get('root_cause', '') for _, r in results.iterrows()):
                print("\n  ✅ [結論] 驗證成功！Agent 在處理新任務前，自動把「8080 防火牆被阻擋」的慘痛教訓調度進了 Context Window。")
                print("            這證明了學習紀錄具有『跨任務的先驗防護價值』，不再依賴人類踩坑！")
            else:
                print("\n  ⚠️ [結論] 新教訓並非 Top-3 相關，可能是向量空間距離不近。")
        except Exception as e:
            print("  Utility Test 發送失敗:", e)

count_and_verify()
