#!/usr/bin/env python3
"""
skiing_graph_linker.py — 語義網格自動織網腳本 v1.2
=========================================================
策略：
  - 以 qmd vsearch CLI 做向量搜尋
  - 以 Title 字串為錨點做路徑對位
"""

import re
import subprocess
from pathlib import Path


def get_qmd_vsearch(query, limit=3):
    try:
        cmd = ["/usr/bin/qmd", "vsearch", query, "--limit", str(limit)]
        result = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode()
        # 解析 qmd 輸出，提取 [[Title]]
        matches = re.findall(r"(\d+):\s+(.+)\.md", result)
        return [m[1] for m in matches]
    except:
        return []


def link_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    title_match = re.search(r'^title:\s*["\']?(.*?)["\']?\s*$', content, re.MULTILINE)
    title = title_match.group(1) if title_match else file_path.stem

    links = get_qmd_vsearch(title)
    if not links:
        return False

    # 建立連結區塊
    link_section = "\n\n## 🔗 相關技術推薦\n"
    added = 0
    for l in links:
        if l != title:
            link_section += f"- [[{l}]]\n"
            added += 1

    if added == 0:
        return False

    # 追加並寫回
    new_content = (
        content.strip() + link_section + "\n%% 由 skiing_graph_linker 自動織網 %%\n"
    )
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    target_dir = Path(args.dir)
    files = list(target_dir.glob("*.md"))
    print(f"📂 目標目錄：{target_dir}")

    for f in files:
        if link_file(f):
            print(f"  ✅ [linked] {f.name}")
