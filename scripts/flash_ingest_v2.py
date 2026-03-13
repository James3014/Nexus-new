import os
import lancedb
import requests
import json
import time
import re
from datetime import datetime
from dotenv import load_dotenv

# 核心配置 (Jina Embedding v3)
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
load_dotenv(os.path.expanduser("~/.openclaw/.env"))
JINA_KEY = os.environ.get("JINA_API_KEY", "MISSING_KEY")
DB_PATH = os.path.expanduser("~/.openclaw/memory/lancedb-pro")
ROOT_DIR = os.environ.get("MUSE_VAULT_ROOT", "/Users/jameschen/Downloads/obsidian/知識庫")
TABLE_NAME = os.environ.get("MUSE_SEARCH_TABLE", "agent_main")
HOT_TABLE_NAME = os.environ.get("MUSE_HOT_TABLE", "agent_hot")
HOT_SOURCE_PATTERNS = [
    p.strip()
    for p in os.environ.get(
        "MUSE_HOT_SOURCE_PATTERNS",
        "01_Operations/WORKFLOW.md,"
        "00_System_Knowledge/00_Manifesto/MANIFESTO.md,"
        "01_Operations/00_Current_Focus.md,"
        "01_Operations/01_Hook_Protocols.md,"
        "01_Operations/02_Habit_Registry.md",
    ).split(",")
    if p.strip()
]
EMBED_TIMEOUT_SEC = int(os.environ.get("MUSE_EMBED_TIMEOUT_SEC", "30"))
EMBED_RETRIES = int(os.environ.get("MUSE_EMBED_RETRIES", "2"))


def is_hot_source(rel_path: str) -> bool:
    path_lower = rel_path.lower()
    return any(p.lower() in path_lower for p in HOT_SOURCE_PATTERNS)


def get_embeddings(texts):
    url = "https://api.jina.ai/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {JINA_KEY}",
        "Content-Type": "application/json",
    }
    data = {"model": "jina-embeddings-v3", "input": texts, "task": "retrieval.passage"}
    for attempt in range(1, EMBED_RETRIES + 2):
        try:
            res = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=EMBED_TIMEOUT_SEC,
            )
            payload = res.json()
            return [item["embedding"] for item in payload["data"]]
        except Exception as e:
            if attempt >= EMBED_RETRIES + 1:
                print(f"❌ Batch Embedding Error: {e}")
                return None
            print(f"⚠️ Embedding retry {attempt}/{EMBED_RETRIES} due to: {e}")
            time.sleep(1.5)


def prune_content(content):
    # 使用轉義符號處理換行，防止寫入錯誤
    content = re.sub(r"\|.*\|", "", content)
    content = re.sub(r"<[^>]*>", "", content)
    content = re.sub(r"\n\s*\n", "\n", content)
    content = content.replace("[[", "").replace("]]", "")
    return content.strip()


def extract_trunk(content):
    trunk_match = re.search(
        r"## 🌳 TREE 核心提煉 \(Trunk\)\n(.*?)(?=\n##|---|$)", content, re.DOTALL
    )
    if trunk_match:
        return trunk_match.group(1).strip()
    items_match = re.search(r"items:\n((?:\s*-\s*.*\n?)+)", content)
    if items_match:
        return items_match.group(1).replace("- ", "").strip()
    return "No explicit summary."


def main():
    if not os.path.exists(ROOT_DIR):
        print(f"❌ ROOT_DIR {ROOT_DIR} not found!")
        return
    if JINA_KEY == "MISSING_KEY":
        print("❌ 錯誤：未設定環境變數 JINA_API_KEY")
        return

    db = lancedb.connect(DB_PATH)
    db.drop_table(TABLE_NAME, ignore_missing=True)
    db.drop_table(HOT_TABLE_NAME, ignore_missing=True)
    print("🧹 Table Dropped. Starting FLASH Ingest (Batch: 5)...")

    all_docs = []
    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.endswith(".md") and not f.startswith("_") and f != "README.md":
                all_docs.append(os.path.join(root, f))

    total = len(all_docs)
    print(f"🚀 掃描完成！共發現 {total} 份檔案。")

    table = None
    hot_table = None
    success_count = 0
    hot_count = 0

    for i in range(0, total, 5):
        batch_paths = all_docs[i : i + 5]
        batch_texts = []
        batch_metadata = []

        for p in batch_paths:
            try:
                rel_p = os.path.relpath(p, ROOT_DIR)
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    raw = f.read()

                trunk = extract_trunk(raw)
                body = prune_content(raw)

                if len(body) > 10:
                    final_text = f"TITLE: {rel_p}\nSUMMARY: {trunk}\nCONTENT: {body}"
                    batch_texts.append(final_text)
                    batch_metadata.append(
                        {"source": rel_p, "updated_at": datetime.now().isoformat()}
                    )
            except:
                continue

        if batch_texts:
            vectors = get_embeddings(batch_texts)
            if vectors:
                data = [
                    {"text": t, "vector": v, "metadata": json.dumps(m)}
                    for t, v, m in zip(batch_texts, vectors, batch_metadata)
                ]
                if table is None:
                    table = db.create_table(TABLE_NAME, data=data)
                else:
                    table.add(data)

                hot_data = []
                for item in data:
                    try:
                        meta = json.loads(item["metadata"])
                        src = str(meta.get("source", ""))
                        if is_hot_source(src):
                            hot_data.append(item)
                    except Exception:
                        continue
                if hot_data:
                    if hot_table is None:
                        hot_table = db.create_table(HOT_TABLE_NAME, data=hot_data)
                    else:
                        hot_table.add(hot_data)
                    hot_count += len(hot_data)

                success_count += len(data)
                print(f"✅ [{i + len(data)}/{total}] Synced batch.")
                time.sleep(2)
            else:
                print(f"⚠️ Batch {i // 5 + 1} failed. Skipping.")

    print(f"✨ [閃電結晶完成] 成功: {success_count}/{total} (hot={hot_count})")


if __name__ == "__main__":
    main()
