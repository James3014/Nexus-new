import os
import re
from pathlib import Path

VAULT_ROOT = Path("/Users/jameschen/Workspace/nexus/nexus_wiki_vault")
REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")

# 故障檔案清單 (從 jq 輸出轉化)
FAILED_FILES = [
    "06_Ops/Ops - CI Failure Playbook.md",
    "06_Ops/Ops - Reference Boundary and Archive Policy.md",
    "06_Ops/Ops - Optimization Proposal Protocol.md",
    "02_Modules/Module - Intelligence and Logic (Remaining Core).md",
    "02_Modules/Module - State Contracts.md",
    "02_Modules/Module - Implementation Responsibility Matrix.md",
    "02_Modules/Module - Nexus Desk Interface.md",
    "02_Modules/Module - Advanced Core Intelligence.md",
    "02_Modules/Module - Core Orchestrator.md",
    "02_Modules/Module - Core Orchestrator Deep Dive.md",
    "02_Modules/Module - Dual Phase Diagnosis.md",
    "02_Modules/Module - Task Scheduling and Swarm Adapters.md",
    "02_Modules/Module - Platform Core Registry.md",
    "02_Modules/Module - Security and Tool Guard Registry.md",
    "02_Modules/Module - Policy and Learning Governance.md",
    "02_Modules/Module - CLI Commands Service.md",
    "02_Modules/Module - Intelligence and Context Core.md",
    "02_Modules/Module - State Lifecycle and Snapshotting.md",
    ".nexus/graph/Community_1.md",
    ".nexus/graph/index.md"
]

def fix_content(content):
    # 1. 修正 scriptsscripts 錯誤
    content = content.replace("scriptsscripts", "scripts")
    # 2. 修正嵌套的 workspaces 路徑
    content = re.sub(r"nexus/\.nexus/workspaces/bug-\d+/scripts/ops/", "scripts/ops/", content)
    content = re.sub(r"nexus/\.nexus/workspaces/bug-\d+/nexus/core/", "nexus/core/", content)
    content = re.sub(r"\.nexus/workspaces/bug-\d+/scripts/ops/", "scripts/ops/", content)
    # 3. 修正雙重 nexus/nexus
    content = content.replace("nexus/nexus/core/", "nexus/core/")
    content = content.replace("nexus/nexus/services/", "nexus/services/")
    # 4. 修正失效的根路徑引言
    content = content.replace("'/scripts/nexus_cli.py'", "'scripts/engine/nexus_cli.py'")
    content = content.replace("/scripts/nexus_cli.py", "scripts/engine/nexus_cli.py")
    return content

def heal():
    print("🩹 [Wiki Healer] Starting global healing...")
    for rel_path in FAILED_FILES:
        full_path = REPO_ROOT / rel_path
        if not full_path.exists():
            full_path = VAULT_ROOT / rel_path
            
        if full_path.exists():
            print(f"  -> Healing: {rel_path}")
            content = full_path.read_text()
            new_content = fix_content(content)
            if content != new_content:
                full_path.write_text(new_content)
                print(f"  ✅ Fixed paths in {rel_path}")
        else:
            print(f"  ⚠️ File not found: {rel_path}")

if __name__ == "__main__":
    heal()
