import json
import lancedb
from pathlib import Path

def generate_proof():
    root = Path("/Users/jameschen/Workspace/nexus")
    print("🔬 Nexus 演化系統資料庫深層取樣報告\n" + "="*50)
    
    # 1. Base Memory (Sys 1)
    lesson_path = root / ".nexus" / "knowledge" / "lesson_events.jsonl"
    try:
        with open(lesson_path, 'r') as f:
            lines = f.readlines()
            latest_lesson = json.loads(lines[-1])
        print("\n[系統一：物理教訓庫 (lesson_events.jsonl) 最新寫入]")
        print(f"  ➜ Task ID: {latest_lesson.get('task_id')}")
        print(f"  ➜ 根因捕捉 (Root Cause): {latest_lesson.get('root_cause')}")
        print(f"  ➜ 推薦行動 (Corrective Action): {latest_lesson.get('corrective_action')}")
        target_task_id = latest_lesson.get('task_id')
    except Exception as e:
        print("無法讀取 lesson_events.jsonl", e)
        return

    # 2. Soul Palace Belief Revision (Sys 2)
    beliefs_path = root / ".nexusknowledge" / "beliefs.jsonl"
    found_belief = None
    try:
        with open(beliefs_path, 'r') as f:
            for line in reversed(f.readlines()):
                b = json.loads(line)
                if b.get("task") == target_task_id:
                    found_belief = b
                    break
        print("\n[系統二：信念宮殿 (beliefs.jsonl) 狀態覆寫]")
        if found_belief:
            print(f"  ➜ 追蹤信念 ID: {found_belief.get('id')}")
            print(f"  ➜ 原始被挑戰內容: {found_belief.get('content')}")
            status = found_belief.get('status')
            icon = "✅" if status == "superseded" else "⚠️"
            print(f"  ➜ 當前信念狀態: {icon} {status.upper()}")
        else:
            print("  ➜ 未找到對應的信念紀錄。")
    except Exception as e:
        print("無法讀取 beliefs.jsonl", e)

    # 3. Wisdom Layer Incremental Index (Sys 3)
    try:
        db = lancedb.connect(str(root / ".nexus" / "memory" / "memory_index.lancedb"))
        table = db.open_table("memory_index")
        df = table.to_pandas()
        matched_df = df[df['task_id'] == target_task_id]
        print("\n[系統三：向量檢索層 (LanceDB memory_index) 增量更新]")
        if not matched_df.empty:
            record = matched_df.iloc[0]
            print(f"  ➜ 成功匹配 Task ID: {target_task_id}")
            print(f"  ➜ 紀錄類型 (record_type): {record['record_type']}")
            
            payload = json.loads(record['payload_json'])
            print(f"  ➜ 向量資料負荷 (Payload JSON excerpt):")
            print(f"      - 關聯類別 (Category): {payload.get('category')}")
            print(f"      - 自動生成教訓 ID: {payload.get('lesson_id')}")
            print(f"  ➜ 嵌入向量維度 (Vector Embedding Size): {len(record['embedding'])} dim")
        else:
            print("  ➜ LanceDB 中未找到對應的索引！")
    except Exception as e:
        print("無法查詢 LanceDB:", e)

generate_proof()
