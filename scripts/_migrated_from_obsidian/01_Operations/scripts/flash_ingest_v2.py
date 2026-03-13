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

def get_embeddings(texts):
    url = "https://api.jina.ai/v1/embeddings"
    headers = {"Authorization": f"Bearer {JINA_KEY}", "Content-Type": "application/json"}
    data = {"model": "jina-embeddings-v3", "input": texts, "task": "retrieval.passage"}
    try:
        res = requests.post(url, headers=headers, json=data).json()
        return [item["embedding"] for item in res["data"]]
    except Exception as e:
        print(f"❌ Batch Embedding Error: {e}")
        return None

def prune_content(content):
    # 使用轉義符號處理換行，防止寫入錯誤
    content = re.sub(r"\|.*\|", "", content)
    content = re.sub(r"<[^>]*>", "", content)
    content = re.sub(r"\n\s*\n", "\n", content)
    content = content.replace("[[", "").replace("]]", "")
    return content.strip()

def extract_trunk(content):
    trunk_match = re.search(r"## 🌳 TREE 核心提煉 \(Trunk\)\n(.*?)(?=\n##|---|$)", content, re.DOTALL)
    if trunk_match: return trunk_match.group(1).strip()
    items_match = re.search(r"items:\n((?:\s*-\s*.*\n?)+)", content)
    if items_match: return items_match.group(1).replace("- ", "").strip()
    return "No explicit summary."

def main():
    if not os.path.exists(ROOT_DIR):
        print(f"❌ ROOT_DIR {ROOT_DIR} not found!")
        return

    db = lancedb.connect(DB_PATH)
    table_name = "agent_main"
    db.drop_table(table_name, ignore_missing=True)
    print(f"🧹 Table Dropped. Starting FLASH Ingest (Batch: 5)...")

    all_docs = []
    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.endswith(".md") and not f.startswith("_") and f != "README.md":
                all_docs.append(os.path.join(root, f))
    
    total = len(all_docs)
    print(f"🚀 掃描完成！共發現 {total} 份檔案。")
    
    table = None
    success_count = 0
    
    for i in range(0, total, 5):
        batch_paths = all_docs[i:i+5]
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
                    batch_metadata.append({"source": rel_p, "updated_at": datetime.now().isoformat()})
            except: continue
        
        if batch_texts:
            vectors = get_embeddings(batch_texts)
            if vectors:
                data = [{"text": t, "vector": v, "metadata": json.dumps(m)} 
                        for t, v, m in zip(batch_texts, vectors, batch_metadata)]
                if table is None:
                    table = db.create_table(table_name, data=data)
                else:
                    table.add(data)
                success_count += len(data)
                print(f"✅ [{i+len(data)}/{total}] Synced batch.")
                time.sleep(2)
            else:
                print(f"⚠️ Batch {i//5 + 1} failed. Skipping.")

    print(f"✨ [閃電結晶完成] 成功: {success_count}/{total}")

if __name__ == "__main__":
    main()
