import os
import re
from pathlib import Path

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"

def normalize_all_paths(content):
    # --- 1. 處理極端路徑衝突 (Double prefix) ---
    content = content.replace("scriptsscripts", "scripts")
    content = content.replace("scripts/scripts/", "scripts/")
    content = content.replace("ReferenceReference/", "Reference/")
    content = content.replace("nexus/nexus/", "nexus/")
    
    # --- 2. 處理絕對路徑與斜線錯誤 ---
    content = content.replace("'/scripts/nexus_cli.py'", "'scripts/engine/nexus_cli.py'")
    content = content.replace("/scripts/nexus_cli.py", "scripts/engine/nexus_cli.py")
    content = content.replace("/scripts/ops/wiki_linter.py", "scripts/ops/wiki_linter.py")
    
    # --- 3. 清理 Workspace 殘留路徑 ---
    content = re.sub(r"\.?nexus/workspaces/bug-\d+/nexus/core/", "nexus/core/", content)
    content = re.sub(r"\.?nexus/workspaces/bug-\d+/nexus/services/", "nexus/services/", content)
    content = re.sub(r"\.?nexus/workspaces/bug-\d+/scripts/ops/", "scripts/ops/", content)
    content = re.sub(r"/\.nexus/workspaces/bug-\d+/scripts/ops/", "scripts/ops/", content)
    
    # --- 4. 針對特定檔案的硬編碼修復 ---
    content = content.replace("nexus-desk/nexus-rust-v16/nexus-policy/src/main.rs", "nexus-desk/src-tauri/src/main.rs")
    content = content.replace("nexus/scripts/swarm_orchestrator.py", "nexus/core/swarm_orchestrator.py")
    
    return content

def heal():
    print("🩹 [Wiki Healer v6] Starting final deep path normalization...")
    failed_files = [
        "90_Sources/Source - Nexus Anti Registry.md",
        "01_System/System - Next Questions for Human.md",
        "07_Diffs/Diff - v17.1 vs v22 vs v23.md",
        "02_Modules/Module - Intelligence and Logic (Remaining Core).md",
        "02_Modules/Module - State Contracts.md",
        "02_Modules/Module - Nexus Desk Interface.md",
        "02_Modules/Module - Advanced Core Intelligence.md",
        "02_Modules/Module - Runtime Services.md",
        "02_Modules/Module - Core Orchestrator.md",
        "02_Modules/Module - Core Orchestrator Deep Dive.md"
    ]
    
    for rel_path in failed_files:
        f = VAULT_ROOT / rel_path
        if f.exists():
            content = f.read_text()
            new_content = normalize_all_paths(content)
            if content != new_content:
                f.write_text(new_content)
                print(f"  ✅ Deep healed: {rel_path}")
        else:
            print(f"  ⚠️ File not found: {rel_path}")

if __name__ == "__main__":
    heal()
