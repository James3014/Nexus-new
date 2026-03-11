import lancedb
import os

DB_PATH = os.path.expanduser("~/.openclaw/memory/lancedb-pro")


def ghost_audit():
    db = lancedb.connect(DB_PATH)
    tables = db.table_names()

    # 讀取主表現狀
    main_table = db.open_table("agent_main")
    main_df = main_table.to_pandas()
    main_texts = set(main_df["text"])

    print("🕵️ [大腦影子表 - 遺珠偵測]")
    print("---")

    for t_name in ["knowledge_crystallized", "memories"]:
        if t_name in tables:
            tbl = db.open_table(t_name)
            df = tbl.to_pandas()
            # 找出那些 text 不在 agent_main 裡的記錄
            unique_to_old = df[~df["text"].isin(main_texts)]

            print(f"📁 表格: {t_name}")
            print(f"   - 總記錄: {len(df)}")
            print(f"   - 獨有紀錄 (遺珠): {len(unique_to_old)}")

            if len(unique_to_old) > 0:
                print(
                    f"   ⚠️ 警告: 發現 {len(unique_to_old)} 筆內容在目前知識庫中找不到！"
                )
                for i, row in unique_to_old.head(2).iterrows():
                    print(f"   📍 遺珠範例: {row['text'][:100]}...")
            else:
                print("   ✅ 此表僅含有舊路徑的副本，無任何遺失內容。")
            print("---")


if __name__ == "__main__":
    ghost_audit()
