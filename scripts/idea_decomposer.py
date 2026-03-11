#!/usr/bin/env python3
# 🛡️ Codex-Verified: Codex-Auth-Lvl13-Final (2026-03-03)
import sys
import json


def decompose_idea(idea):
    """將一個 Idea 拆解為四個維度的子任務指令"""
    print("🧩 [Decomposer] 正在將 Idea 解構為平行任務集...")

    tasks = [
        {
            "agent": "main",
            "prompt": f"請在我的知識庫 (Obsidian) 中搜尋關於 '{idea}' 的過往想法、會議紀錄或筆記，摘要 3 個核心關聯點。僅輸出 Markdown 列表。",
        },
        {
            "agent": "main",
            "prompt": f"請檢索 GitHub 上的開源專案，尋找是否有與 '{idea}' 類似的實作、SDK 或 API 參考。列出前 3 名及優缺點。",
        },
        {
            "agent": "main",
            "prompt": f"請利用 Felo 搜尋當前市場上關於 '{idea}' 的競爭對手、新聞趨勢或最新的相關科技快訊。摘要 3 則關鍵資訊。",
        },
        {
            "agent": "main",
            "prompt": f"針對 '{idea}'，從『成本、技術難度、市場需求』三個角度給予 1-10 分的現實評估與一句話建議。",
        },
    ]
    return tasks


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(decompose_idea(sys.argv[1]), ensure_ascii=False))
    else:
        print("[]")
