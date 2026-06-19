import os
import lancedb
import requests
import json
import time
import re
from datetime import datetime

# 核心配置 (Jina Embedding v3)
JINA_KEY = os.environ.get("JINA_API_KEY", "MISSING_KEY")
DB_PATH = os.path.expanduser("~/.openclaw/memory/lancedb-pro")
ROOT_DIR = "/Users/jameschen/Downloads/obsidian/知識庫"


def get_embedding(text, is_trunk=False):
    url = "https://api.jina.ai/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {JINA_KEY}",
        "Content-Type": "application/json",
    }
    # 為 Trunk (樹幹) 增加語義檢索權重
    task = "retrieval.passage" if not is_trunk else "retrieval.query"
    data = {"model": "jina-embeddings-v3", "input": [text], "task": task}
    try:
        res = requests.post(url, headers=headers, json=data).json()
        return res["data"][0]["embedding"]
    except Exception as e:
        print(f"Embedding Error: {e}")
        return None


def prune_content(content):
    # 噪音修剪: 移除 Markdown 表格、HTML、多餘換行
    content = re.sub(r"\|.*\|", "", content)
    content = re.sub(r"<[^>]*>", "", content)
    content = re.sub(r"\n\s*\n", "\n", content)
    # 移除 Wikilinks 符號保留文字
    content = content.replace("[[", "").replace("]]", "")
    return content.strip()


def extract_trunk_or_items(content):
    # 1. 優先嘗試抓取 TREE 提煉區塊
    trunk_match = re.search(
        r"## 🌳 TREE 核心提煉 \(Trunk\)\n(.*?)(?=\n##|---|$)", content, re.DOTALL
    )
    if trunk_match:
        return trunk_match.group(1).strip()

    # 2. 備案：抓取 YAML 中的 items
    items_match = re.search(r"items:\n((?:\s*-\s*.*\n?)+)", content)
    if items_match:
        return items_match.group(1).replace("- ", "").strip()

    return None


def main():
    if not os.path.exists(ROOT_DIR):
        print(f"❌ ROOT_DIR {ROOT_DIR} not found!")
        return

    db = lancedb.connect(DB_PATH)
    table_name = "agent_main"

    # 全庫掃描
    all_docs = []
    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.endswith(".md") and not f.startswith("_") and f != "README.md":
                all_docs.append(os.path.join(root, f))

    total = len(all_docs)
    print(f"🚀 [Lvl 12] 全量結晶引擎啟動！共發現 {total} 份檔案。")

    table = None
    success_count = 0

    for i, p in enumerate(all_docs):
        try:
            rel_p = os.path.relpath(p, ROOT_DIR)
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                raw_content = f.read()

            # 1. 提煉精華 (Trunk / Items)
            trunk = extract_trunk_or_items(raw_content)

            # 2. 去噪主體 (Body)
            body = prune_content(raw_content)

            if not body or len(body) < 10:
                print(f"ℹ️ [{i + 1}/{total}] Skip: Empty/Short file {rel_p}")
                continue

            # 3. 語義合成 (高品質結晶策略)
            final_text = f"TITLE: {rel_p}\nSUMMARY: {trunk if trunk else 'No explicit summary.'}\nCONTENT: {body}"

            vector = get_embedding(final_text)
            if vector:
                data = [
                    {
                        "text": final_text,
                        "vector": vector,
                        "metadata": json.dumps(
                            {
                                "source": rel_p,
                                "has_trunk": trunk is not None,
                                "updated_at": datetime.now().isoformat(),
                            }
                        ),
                    }
                ]

                # 採用增量同步
                if table is None:
                    table = db.create_table(table_name, data=data, mode="overwrite")
                else:
                    table.add(data)

                success_count += 1
                status_icon = "💎" if trunk else "✅"
                print(f"{status_icon} [{i + 1}/{total}] {rel_p}")

                # API 頻率保護
                time.sleep(10)

        except Exception as e:
            print(f"❌ [{i + 1}/{total}] Error at {rel_p}: {e}")
            time.sleep(30)

    print(f"✨ [結晶完成] 成功結晶: {success_count}/{total} 份檔案。")


if __name__ == "__main__":
    main()
