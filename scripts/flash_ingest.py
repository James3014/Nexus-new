import os
import lancedb
import requests
import json
import time


# ==============================================================================
# 🧠 Muse-Core 自動化金鑰提取邏輯
# ==============================================================================
def get_jina_key():
    # 1. 優先嘗試環境變數
    env_key = os.getenv("JINA_API_KEY")
    if env_key:
        return env_key

    # 2. 自動從 OpenClaw 設定檔提取 (SSoT: Single Source of Truth)
    config_path = os.path.expanduser("~/.openclaw/openclaw.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                # 定位 memory-lancedb-pro 插件的 Embedding API Key
                key = (
                    config.get("plugins", {})
                    .get("entries", {})
                    .get("memory-lancedb-pro", {})
                    .get("config", {})
                    .get("embedding", {})
                    .get("apiKey")
                )
                if key:
                    return key
        except Exception as e:
            print(f"⚠️  警告: 無法讀取 OpenClaw 設定檔: {e}")

    # 3. 最後的 Fallback (原有的 Key)
    return os.environ.get("JINA_API_KEY", "MISSING_KEY")


JINA_KEY = get_jina_key()
DB_PATH = os.path.expanduser("~/.openclaw/memory/lancedb-pro")
ROOT_DIR = "/Users/jameschen/Downloads/obsidian/知識庫"
FOLDERS = [
    "00_System_Knowledge",
    "01_Operations",
    "05_External_Infusion",
    "20_Family_Education",
    "Skiing",
]


def get_embedding(texts):
    try:
        res = requests.post(
            "https://api.jina.ai/v1/embeddings",
            headers={"Authorization": f"Bearer {JINA_KEY}"},
            json={
                "model": "jina-embeddings-v3",
                "input": texts,
                "task": "retrieval.passage",
            },
        ).json()
        return [item["embedding"] for item in res["data"]]
    except Exception as e:
        print(f"❌ Embedding 失敗: {e}")
        return None


def main():
    if not os.path.exists(DB_PATH):
        print(f"❌ 錯誤: 找不到資料庫路徑 {DB_PATH}")
        return

    db = lancedb.connect(DB_PATH)
    table = db.open_table("agent_main")

    # 掃描尚未結晶的檔案 (Resume Mode)
    df = table.to_pandas()
    existing = set(df["metadata"].apply(lambda x: json.loads(x).get("source")))

    pending = []
    for fld in FOLDERS:
        path = os.path.join(ROOT_DIR, fld)
        if not os.path.exists(path):
            continue
        for r, d, files in os.walk(path):
            for f in files:
                if f.endswith(".md"):
                    rel = os.path.relpath(os.path.join(r, f), ROOT_DIR)
                    if rel not in existing:
                        pending.append(os.path.join(r, f))

    print("🚀 [Muse-Core] 大腦同步啟動...")
    print(f"🔑 已自動掛載金鑰來源: {'OpenClaw Config' if JINA_KEY else 'None'}")
    print(f"待注入檔案: {len(pending)} 份")

    if not pending:
        print("✅ 大腦已是最新狀態，無需同步。")
        return

    for i in range(0, len(pending), 5):
        batch = pending[i : i + 5]
        texts = []
        valid_paths = []
        for p in batch:
            try:
                content = open(p, "r", errors="ignore").read().strip()
                if content:
                    texts.append(content)
                    valid_paths.append(p)
            except:
                continue

        if not texts:
            continue

        vectors = get_embedding(texts)
        if vectors:
            data = [
                {
                    "text": t,
                    "vector": v,
                    "metadata": json.dumps({"source": os.path.relpath(p, ROOT_DIR)}),
                }
                for t, v, p in zip(texts, vectors, valid_paths)
            ]
            table.add(data)
            print(f"✅ 完成 {min(i + 5, len(pending))}/{len(pending)}")
            time.sleep(1)


if __name__ == "__main__":
    main()
