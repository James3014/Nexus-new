import os
import re
import yaml
from pathlib import Path

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"

def fix_path(p):
    # 將所有變體路徑歸一化
    p = p.replace("scriptsscripts", "scripts")
    p = p.replace("scripts/scripts/", "scripts/")
    p = p.replace("'/scripts/nexus_cli.py'", "'scripts/engine/nexus_cli.py'")
    p = p.replace("/scripts/nexus_cli.py", "scripts/engine/nexus_cli.py")
    p = re.sub(r"\.?nexus/workspaces/bug-\d+/scripts/ops/", "scripts/ops/", p)
    p = p.replace("nexus_wiki_vault//README.md", "Reference/README.md")
    p = p.replace("/README.md", "Reference/README.md")
    return p

def heal():
    print("🩹 [Wiki Healer v5] Starting final surgical strike...")
    
    # --- 1. 特別修復 Community_1.md 的 YAML ---
    c1_path = VAULT_ROOT / ".nexus" / "graph" / "Community_1.md"
    if c1_path.exists():
        c1_path.write_text("""---
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
本節點定義了 Nexus 知識圖譜中的第一社區集群。 [Source: .nexus/graph/Community_1.md]

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
""")

    # --- 2. 遍歷全量修復路徑與回鏈 ---
    for f in VAULT_ROOT.glob("**/*.md"):
        if ".obsidian" in str(f): continue
        content = f.read_text()
        original = content
        
        # 修復路徑
        content = fix_path(content)
        
        # 確保回鏈存在
        if "[[System Overview]]" not in content and "System Overview" not in f.name:
            content += "\n\n---\n[[System Overview]]"
            
        if content != original:
            f.write_text(content)
            print(f"  ✅ Surgically fixed: {f.relative_to(VAULT_ROOT)}")

if __name__ == "__main__":
    heal()
