import os
import lancedb
import json

DB_PATH = os.path.expanduser("~/.openclaw/memory/lancedb-pro")
ROOT_DIR = "/Users/jameschen/Downloads/obsidian/知識庫"


def check_file_quality(content):
    has_trunk = "## 🌳 TREE 核心提煉 (Trunk)" in content
    has_items = "items:" in content and "-" in content
    is_active = "status: active" in content
    return has_trunk, has_items, is_active


def main():
    db = lancedb.connect(DB_PATH)
    table = db.open_table("agent_main")

    # 1. 讀取 LanceDB 現有清單
    df = table.to_pandas()
    crystallized_files = set(
        df["metadata"].apply(lambda x: json.loads(x).get("source"))
    )

    # 2. 掃描物理硬碟
    all_md_files = []
    high_quality_missing = []

    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.endswith(".md") and not f.startswith("_") and f != "README.md":
                rel_p = os.path.relpath(os.path.join(root, f), ROOT_DIR)
                all_md_files.append(rel_p)

                # 如果還沒結晶，檢查其品質
                if rel_p not in crystallized_files:
                    try:
                        with open(
                            os.path.join(root, f),
                            "r",
                            encoding="utf-8",
                            errors="ignore",
                        ) as file:
                            content = file.read()

                        has_trunk, has_items, is_active = check_file_quality(content)
                        if has_trunk or has_items or is_active:
                            high_quality_missing.append(
                                {
                                    "path": rel_p,
                                    "quality": f"Trunk:{has_trunk}, Items:{has_items}, Active:{is_active}",
                                }
                            )
                    except:
                        continue

    print("📊 [大腦語義審核報告]")
    print("---")
    print(f"📁 物理檔案總數: {len(all_md_files)}")
    print(f"💎 已結晶檔案數: {len(crystallized_files)}")
    print(f"📈 語義覆蓋率: {len(crystallized_files) / len(all_md_files) * 100:.1f}%")
    print("---")

    if high_quality_missing:
        print(
            f"🚨 警告：發現 {len(high_quality_missing)} 份具備高品質特徵但尚未結晶的檔案："
        )
        for item in high_quality_missing[:10]:  # 只列前 10 份
            print(f"📍 {item['path']} ({item['quality']})")
        if len(high_quality_missing) > 10:
            print(f"... 以及其他 {len(high_quality_missing) - 10} 份檔案。")
    else:
        print("✅ 完美對位！所有具備高品質特徵的檔案均已完成結晶。")


if __name__ == "__main__":
    main()
