import lancedb
import os
import json

DB_PATH = os.path.expanduser("~/.openclaw/memory/lancedb-pro")
ROOT_DIR = "/Users/jameschen/Downloads/obsidian/知識庫"


def identity_audit():
    db = lancedb.connect(DB_PATH)

    # 1. 建立目前物理硬碟的檔名索引 (Basename -> Full Relative Path)
    current_files = {}
    for root, dirs, files in os.walk(ROOT_DIR):
        for f in files:
            if f.endswith(".md"):
                rel_p = os.path.relpath(os.path.join(root, f), ROOT_DIR)
                current_files[f] = rel_p

    print("🕵️ [大腦整理 - 路徑位移核對報告]")
    print("---")

    for t_name in ["knowledge_crystallized", "memories"]:
        if t_name in db.table_names():
            tbl = db.open_table(t_name)
            df = tbl.to_pandas()
            df["old_source"] = df["metadata"].apply(
                lambda x: json.loads(x).get("source")
            )

            # 取得舊表中的所有檔名
            old_basenames = df["old_source"].apply(lambda x: os.path.basename(x))

            missing_for_real = []
            moved_successfully = 0

            for i, old_p in enumerate(df["old_source"]):
                bname = os.path.basename(old_p)
                if bname in current_files:
                    moved_successfully += 1
                else:
                    missing_for_real.append(old_p)

            print(f"📁 舊表: {t_name}")
            print(f"   - 總記錄: {len(df)}")
            print(f"   - 成功對位 (僅搬移): {moved_successfully}")
            print(f"   - 物理缺失 (找不到檔名): {len(missing_for_real)}")

            if missing_for_real:
                print("   ⚠️ 真實缺失範例:")
                for m in missing_for_real[:5]:
                    print(f"     - {m}")
            print("---")


if __name__ == "__main__":
    identity_audit()
