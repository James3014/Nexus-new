import lancedb
import os
import json
import requests

JINA_KEY = os.environ.get("JINA_API_KEY", "MISSING_KEY")
DB_PATH = os.path.expanduser("~/.openclaw/memory/lancedb-pro")


def get_embedding(text):
    url = "https://api.jina.ai/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {JINA_KEY}",
        "Content-Type": "application/json",
    }
    data = {"model": "jina-embeddings-v3", "input": [text], "task": "retrieval.query"}
    res = requests.post(url, headers=headers, json=data).json()
    return res["data"][0]["embedding"]


def test_query():
    db = lancedb.connect(DB_PATH)
    table = db.open_table("agent_main")
    query = "目前的結晶腳本是在哪一個目錄？"

    # 手動產生查詢向量
    vector = get_embedding(query)

    # 執行向量搜尋
    results = table.search(vector).limit(3).to_pandas()

    print(f"🔍 [對位測試] 搜尋關鍵字: {query}")
    for i, row in results.iterrows():
        meta = json.loads(row["metadata"])
        print(f"📍 命中 {i + 1}: {meta['source']}")
        print(f"📄 片段: {row['text'][:100]}...")
        print("-" * 30)


if __name__ == "__main__":
    test_query()
