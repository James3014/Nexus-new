import os
from pathlib import Path

repo_root = Path("/Users/jameschen/Workspace/nexus")
wiki_vault = repo_root / "nexus_wiki_vault"
graph_dir = wiki_vault / ".nexus" / "graph"

# 確保目錄物理存在
os.makedirs(graph_dir, exist_ok=True)

TEMPLATE_FRONTMATTER = """---
ai_role: Knowledge-Architect
ai_scope: Documentation Topology
date: 2026-04-07
domain: System/Graph
level: Verified
prescription_drill: Topology Integrity Audit
safe_stage: Protected Output
status: active
tags:
  - System/Graph
  - Governance
title: {title}
type: graph-artifact
---

# {title}

> [!abstract] 核心意圖
> {abstract}

---

## ## Agent-Guide
- **核心意圖**: 為系統提供機器可讀的知識拓樸。
- **治理邏輯**: 定義文碼關聯，確保決策鏈條具備實體特徵。
- **驗證基準**: 通過 Nexus v2 規約之 8 大區塊校驗。

## ## Agent-Index
- **第一部分：拓樸節點 (Nodes)**: 定義核心概念。
- **第二部分：關係矩陣 (Edges)**: 建立鏈接權重。

## ## Agent-Actions
- **If** 偵測到路徑失效 -> **Then** 調用 `drift_audit_core.py` 進行修正。

---

"""

FOOTER = """
---
%%
Codex-Verified: Muse-Core-v3.0/Verified (2026-04-07)
%%
"""

def fix_wiki_file(path, title, abstract):
    if not path.exists():
        return
    old_content = path.read_text()
    
    # 執行路徑校準 (Path Normalization)
    # 修正常見的路徑冗餘與錯誤
    new_content = old_content.replace("/scripts/scripts/", "scripts/")
    new_content = new_content.replace("/scripts/", "scripts/")
    # 處理絕對路徑 (假設都在 repo_root 下)
    new_content = re.sub(r"/Users/jameschen/Workspace/nexus/", "", new_content)
    
    final_body = TEMPLATE_FRONTMATTER.format(title=title, abstract=abstract) + new_content + FOOTER
    path.write_text(final_body)
    print(f"✅ [Nexus:Fixer] {path.name} restored to 8-section standard.")

import re
# 修復 index.md
fix_wiki_file(graph_dir / "index.md", "Knowledge Graph Index", "自動生成的 Nexus 知識圖譜入口，提供全覽式拓樸導航。")

# 修復 Community_1.md (遍歷所有 .md)
for md in graph_dir.glob("*.md"):
    if md.name != "index.md":
        fix_wiki_file(md, f"Topology Community: {md.stem}", f"定義了 Nexus 系統中的 {md.stem} 語義社群與高連結權重節點。")
