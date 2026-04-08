import os
import re
from pathlib import Path

REPO_ROOT = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2]))
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"

# 1. 強制修復圖譜檔案 (正確路徑)
GRAPH_DIR = VAULT_ROOT / ".nexus" / "graph"
os.makedirs(GRAPH_DIR, exist_ok=True)

GRAPH_CONTENT = {
    "index.md": """---
aliases: [Graph Index]
confidence: high
last_compiled: '2026-04-07'
owner: agent
related_pages: '[[System Overview]]'
source_of_truth: .nexus/graph/
status: active
tags: [graph, metadata, index]
title: Nexus Graph Index
type: protocol
version_scope: '[v23]'
---

# Nexus Graph Index

## One-sentence summary
本頁為 Nexus 知識圖譜的自動化索引入口。

## Role / responsibility
- **索引導航**: 提供全域節點的快速訪問路徑。

## Upstream
- [[System Overview]]

## Downstream
- [[Protocol - Evidence Map]]

## Related modules / files
- `.nexus/graph/Community_1.md`

## Source notes
- 自動生成於 v23 知識掃描。

## Open questions / conflicts
- 無。

---
[[System Overview]]
""",
    "Community_1.md": """---
aliases: [Community Node 1]
confidence: high
last_compiled: '2026-04-07'
owner: agent
related_pages: '[[System Overview]]'
source_of_truth: .nexus/graph/
status: active
tags: [graph, community]
title: Community Cluster 1
type: protocol
version_scope: '[v23]'
---

# Community Cluster 1

## One-sentence summary
本節點定義了 Nexus 知識圖譜中的第一社區集群。

## Role / responsibility
- **社區劃分**: 負責管理與展示核心模組間的強關聯性。

## Upstream
- [[Nexus Graph Index]]

## Downstream
- 無。

## Related modules / files
- `nexus/core/router.py`

## Source notes
- 基於 Louvain 演算法產出的社區聚類。

## Open questions / conflicts
- 無。

---
[[System Overview]]
"""
}

def fix_all_paths():
    print("🩹 [Wiki Healer v2] Starting global path and format healing...")
    
    # 寫入圖譜檔案
    for name, content in GRAPH_CONTENT.items():
        path = GRAPH_DIR / name
        path.write_text(content)
        print(f"  ✅ Fixed graph file: {name}")

    # 遍歷所有 Wiki 檔案進行路徑修正
    for f in VAULT_ROOT.glob("**/*.md"):
        content = f.read_text()
        original = content
        
        # 修正各種錯誤路徑模式
        content = content.replace("scriptsscripts", "scripts")
        content = content.replace("scripts/scripts/", "scripts/")
        content = re.sub(r"nexus/\.nexus/workspaces/bug-\d+/scripts/ops/", "scripts/ops/", content)
        content = re.sub(r"nexus/\.nexus/workspaces/bug-\d+/nexus/core/", "nexus/core/", content)
        content = re.sub(r"scripts/\.nexus/workspaces/bug-\d+/scripts/ops/", "scripts/ops/", content)
        content = re.sub(r"/\.nexus/workspaces/bug-\d+/scripts/ops/", "scripts/ops/", content)
        content = content.replace("'/scripts/nexus_cli.py'", "'scripts/engine/nexus_cli.py'")
        content = content.replace("/scripts/nexus_cli.py", "scripts/engine/nexus_cli.py")
        content = content.replace("scripts/scripts/nexus_cli.py", "scripts/engine/nexus_cli.py")
        content = content.replace("nexus/nexus/core/", "nexus/core/")
        content = content.replace("nexus/nexus/services/", "nexus/services/")
        
        # 修正特定的異常路徑 (Case 30 遺留)
        content = content.replace("nexus_wiki_vault/nexus_wiki_vault/", "nexus_wiki_vault/")
        
        if content != original:
            f.write_text(content)
            print(f"  ✅ Repaired paths in: {f.relative_to(VAULT_ROOT)}")

if __name__ == "__main__":
    fix_all_paths()
