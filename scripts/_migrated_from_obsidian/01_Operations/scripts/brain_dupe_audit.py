# 🛡️ Codex-Verified: Lvl13-Master-Seal (2026-03-03)
import lancedb
import os
import json
import pandas as pd

DB_PATH = os.path.expanduser("~/.openclaw/memory/lancedb-pro")

def audit_duplicates():
    db = lancedb.connect(DB_PATH)
    
    # 1. 檢查主表 agent_main
    table = db.open_table("agent_main")
    df = table.to_pandas()
    df['source'] = df['metadata'].apply(lambda x: json.loads(x).get('source'))
    
    total = len(df)
    unique_sources = df['source'].nunique()
    
    print(f"🕵️ [重複性審核 - agent_main]")
    print(f"---")
    print(f"總記錄數: {total}")
    print(f"唯一路徑數: {unique_sources}")
    
    if total > unique_sources:
        print(f"🚨 警告: 發現 {total - unique_sources} 筆路徑重複！這代表同一路徑被寫入多次。")
        dupes = df[df.duplicated('source')]['source'].unique()
        print(f"📍 重複範例: {dupes[:3]}")
    else:
        print(f"✅ 路徑層面: 無重複路徑。")

    # 2. 檢查內容碰撞 (相同內容，不同路徑)
    content_dupes = df[df.duplicated('text')]
    if len(content_dupes) > 0:
        print(f"🚨 警告: 發現 {len(content_dupes)} 筆內容完全重複 (不同路徑指向相同文字)！")
        for i, row in content_dupes.head(3).iterrows():
            orig = df[df['text'] == row['text']]['source'].iloc[0]
            print(f"⚠️ {row['source']} 與 {orig} 內容完全相同。")
    else:
        print(f"✅ 內容層面: 無完全重複內容。")

    # 3. 檢查影子表格
    tables = db.table_names()
    print(f"---")
    print(f"📁 發現影子表格: {tables}")
    if "knowledge_crystallized" in tables:
        print(f"⚠️ 建議: 您的 OpenClaw 若同時掛載 knowledge_crystallized，可能會發生重影。")

if __name__ == "__main__":
    audit_duplicates()
