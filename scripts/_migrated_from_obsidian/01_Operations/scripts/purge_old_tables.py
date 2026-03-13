import lancedb
import os

DB_PATH = os.path.expanduser("~/.openclaw/memory/lancedb-pro")

def purge_tables():
    db = lancedb.connect(DB_PATH)
    target_tables = ["knowledge_crystallized", "memories"]
    
    print(f"🧹 [大腦去熵] 開始物理清除影子表格...")
    
    for t in target_tables:
        try:
            db.drop_table(t, ignore_missing=True)
            print(f"✅ 成功清除: {t}")
        except Exception as e:
            print(f"❌ 清除 {t} 失敗: {e}")
            
    print(f"---")
    print(f"📁 目前剩餘表格: {db.list_tables()}")
    print(f"✨ 大腦已達到極致純淨狀態。")

if __name__ == "__main__":
    purge_tables()
