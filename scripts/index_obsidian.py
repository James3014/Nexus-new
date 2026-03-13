import os
import re
import yaml
import hashlib
import argparse
import lancedb
from pathlib import Path
from dotenv import load_dotenv

# 配置
load_dotenv(os.path.expanduser("~/.openclaw/.env"))
DB_PATH = os.path.expanduser("~/.openclaw/memory/lancedb-pro")
TABLE_NAME = "memories_v2"  # 升級至 v2 以匹配新 Schema


def parse_note(file_path):
    path = Path(file_path)
    if not path.exists():
        return None

    content = path.read_text(encoding="utf-8")

    # 1. 解析 YAML
    yaml_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not yaml_match:
        print(f"⚠️ {file_path} 缺失 YAML Header")
        return None

    metadata = yaml.safe_load(yaml_match.group(1))
    body = content[yaml_match.end() :]

    # 2. 解析 4 大區塊
    # 使用的正則表達式來尋找標題
    def get_section(name, text):
        pattern = rf"## {name}\n(.*?)(?=\n## |$)"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else ""

    agent_guide = get_section("Agent-Guide", body)
    agent_index = get_section("Agent-Index", body)
    agent_actions = get_section("Agent-Actions", body)

    # 3. 提取 Agent-Index 內的 sections (用於智慧 Chunking)
    sections_config = []
    if agent_index:
        try:
            # 嘗試解析 YAML 格式的 sections
            sections_data = yaml.safe_load(agent_index)
            if isinstance(sections_data, dict) and "sections" in sections_data:
                sections_config = sections_data["sections"]
        except:
            pass

    # 4. 智慧 Chunking 與 Row 準備
    rows = []
    note_id = path.stem

    # 提取所有連結
    links = re.findall(r"\[\[(.*?)\]\]", body)

    # 如果有定義 Agent-Index，則按照 Index 切分
    if sections_config:
        for sec in sections_config:
            sec_id = sec.get("id")
            sec_headings = sec.get("headings", [])
            sec_use = sec.get("primary_use", [])

            # 找出對應標題下的內容
            sec_text = ""
            for heading in sec_headings:
                # 簡單匹配標題下的內容
                h_pattern = rf"{re.escape(heading)}\n(.*?)(?=\n#|$)"
                h_match = re.search(h_pattern, body, re.DOTALL)
                if h_match:
                    sec_text += h_match.group(1).strip() + "\n\n"

            if sec_text:
                rows.append(
                    {
                        "id": hashlib.md5(f"{note_id}_{sec_id}".encode()).hexdigest(),
                        "note_id": note_id,
                        "section_id": sec_id,
                        "text": sec_text.strip(),
                        "ai_role": metadata.get("ai_role", []),
                        "ai_usage": metadata.get("ai_usage", []),
                        "ai_scope": metadata.get("ai_scope", []),
                        "domain": metadata.get("domain", ""),
                        "level": metadata.get("level", ""),
                        "tags": metadata.get("tags", []),
                        "link_notes": links,
                        "ai_related_core": metadata.get("ai_related_core", []),
                        "agent_guide": agent_guide,
                        "agent_actions": agent_actions,
                    }
                )

    # 如果沒有匹配到任何 section，或者沒有 Index，則將全文作為一個 chunk (Fallback)
    if not rows:
        rows.append(
            {
                "id": hashlib.md5(f"{note_id}_all".encode()).hexdigest(),
                "note_id": note_id,
                "section_id": "full_content",
                "text": body.strip(),
                "ai_role": metadata.get("ai_role", []),
                "ai_usage": metadata.get("ai_usage", []),
                "ai_scope": metadata.get("ai_scope", []),
                "domain": metadata.get("domain", ""),
                "level": metadata.get("level", ""),
                "tags": metadata.get("tags", []),
                "link_notes": links,
                "ai_related_core": metadata.get("ai_related_core", []),
                "agent_guide": agent_guide,
                "agent_actions": agent_actions,
            }
        )

    return rows


def index_file(file_path):
    print(f"🚀 正在索引: {file_path}")
    rows = parse_note(file_path)
    if not rows:
        return

    # 延遲載入以節省啟動時間
    import requests

    JINA_KEY = os.environ.get("JINA_API_KEY")

    # 批次取得 Embedding
    for row in rows:
        # 使用 Jina 取得 Embedding (簡化版)
        res = requests.post(
            "https://api.jina.ai/v1/embeddings",
            headers={"Authorization": f"Bearer {JINA_KEY}"},
            json={
                "model": "jina-embeddings-v3",
                "input": [row["text"]],
                "task": "retrieval.passage",
            },
        ).json()
        row["vector"] = res["data"][0]["embedding"]

    # 寫入 LanceDB
    db = lancedb.connect(DB_PATH)

    try:
        table = db.open_table(TABLE_NAME)
        # 先刪除舊的
        table.delete(f"note_id = '{rows[0]['note_id']}'")
        table.add(rows)
    except:
        table = db.create_table(TABLE_NAME, data=rows)

    print(f"✅ 索引完成：{len(rows)} 個區塊已存入 {TABLE_NAME}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="Obsidian 筆記路徑")
    args = parser.parse_args()
    index_file(args.file)
