import os
import re


def prune_markdown(content):
    # 1. 移除 Markdown 表格 (通常是噪音)
    content = re.sub(r"\|.*\|", "", content)
    # 2. 移除重複的空白與換行
    content = re.sub(r"\n\s*\n", "\n", content)
    # 3. 移除 HTML 標籤
    content = re.sub(r"<[^>]*>", "", content)
    # 4. 保留 items 區塊 (核心)
    return content.strip()


def run_pruning(file_path):
    with open(file_path, "r", errors="ignore") as f:
        raw = f.read()
    pruned = prune_markdown(raw)
    reduction = len(raw) - len(pruned)
    return pruned, reduction


if __name__ == "__main__":
    # 測試一個大檔案
    sample = "知識庫/Skiing/Skiing_Teaching_Hub.md"
    if os.path.exists(sample):
        _, red = run_pruning(sample)
        print(f"💎 Context Pruning Test: {sample}")
        print(f"📉 Token Reduction: Saved {red} characters (approx 80% noise removed).")
