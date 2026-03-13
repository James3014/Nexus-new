import os
import json
import subprocess
from pathlib import Path

VAULT_DIR = "/Users/jameschen/Downloads/obsidian/知識庫"
SEARCH_SCRIPT = "/Users/jameschen/Downloads/Muse-Nexus/scripts/brain_search_v2.py"
TOPOLOGY_REPORT = "/tmp/topology_report.json"


def get_orphan_content(name):
    """取得孤兒節點路徑與內容"""
    matches = list(Path(VAULT_DIR).rglob(f"{name}.md"))
    if not matches:
        return None, None
    path = matches[0]
    with open(path, "r", encoding="utf-8") as f:
        return path, f.read()


def find_siblings(name, query_text):
    """透過向量搜尋找兄弟"""
    try:
        # 使用標題與內容前 500 字作為 query
        query = f"{name}\n{query_text[:500]}"
        # 使用 uv run 隔離執行檢索，確保相依套件 (lancedb, requests) 存在
        res = subprocess.run(
            [
                "/Users/jameschen/.local/bin/uv",
                "run",
                "--with",
                "lancedb",
                "--with",
                "requests",
                SEARCH_SCRIPT,
                query,
                "--json",
                "--limit",
                "3",
            ],
            capture_output=True,
            text=True,
            timeout=12,
        )
        if res.returncode == 0:
            results = json.loads(res.stdout)
            siblings = []
            for r in results:
                meta = json.loads(r.get("metadata", "{}"))
                source = meta.get("source", "")
                if source and source != f"{name}.md":
                    # 提取標題
                    sibling_name = os.path.splitext(os.path.basename(source))[0]
                    siblings.append(sibling_name)
            return siblings
    except Exception as e:
        print(f"Error searching for {name}: {e}")
    return []


def garden_orphans(limit=5):
    if not os.path.exists(TOPOLOGY_REPORT):
        print("❌ 找不到拓撲報告，請先執行掃描。")
        return

    with open(TOPOLOGY_REPORT, "r", encoding="utf-8") as f:
        report = json.load(f)

    orphans = report.get("orphans", [])
    count = 0

    for name in orphans[:limit]:
        path, content = get_orphan_content(name)
        if not path:
            continue

        print(f"🌿 正在整理孤兒：{name}...")
        siblings = find_siblings(name, content)

        if siblings:
            # 準備連結內容
            link_section = "\n\n---\n## 🔗 語義聯繫 (Gardener)\n"
            for s in siblings:
                link_section += f"- [[{s}]]\n"

            # 檢查是否已存在該區塊，避免重複添加
            if "## 🔗 語義聯繫" not in content:
                # 寫回內容
                new_content = content.strip() + link_section
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"  ✅ 已建立 {len(siblings)} 個語義連結。")
                count += 1
            else:
                print("  ⚠️ 連結已存在，跳過。")
        else:
            print("  ❓ 未找到相似筆記。")

    print(f"✨ 園丁任務完成！本次整理了 {count} 篇孤兒筆記。")


if __name__ == "__main__":
    import sys

    batch_size = 5
    if len(sys.argv) > 1:
        batch_size = int(sys.argv[1])
    garden_orphans(batch_size)
