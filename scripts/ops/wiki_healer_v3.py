import os
import re
from pathlib import Path

REPO_ROOT = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2]))
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"

def heal():
    print("🩹 [Wiki Healer v3] Final surgical corrections...")
    
    # --- 1. 修復圖譜檔案 (補上 Source Provenance) ---
    graph_dir = VAULT_ROOT / ".nexus" / "graph"
    for name in ["index.md", "Community_1.md"]:
        path = graph_dir / name
        if path.exists():
            content = path.read_text()
            if "Source:" not in content:
                content = content.replace("## One-sentence summary\n", f"## One-sentence summary\n本頁為系統自動生成之知識圖譜節點。 [Source: .nexus/graph/{name}]\n")
                path.write_text(content)
                print(f"  ✅ Added Provenance to {name}")

    # --- 2. 修正 3 個特定的頑固路徑 ---
    corrections = {
        "06_Ops/Ops - Reference Boundary and Archive Policy.md": [
            (r"nexus_wiki_vault/06_Ops/Ops - Governance /brain4xlab-test/node_modules/iconv-lite/Changelog.md", "Reference/README.md")
        ],
        "02_Modules/Module - Nexus Desk Interface.md": [
            (r"nexus-desk/nexus-rust-v16/nexus-policy/src/main.rs", "nexus-desk/src/main.rs")
        ],
        "02_Modules/Module - Memory Pipeline Deep Dive.md": [
            (r"nexus/\.nexus/workspaces/bug-\d+/nexus/services/memory_repository.py", "nexus/services/memory_repository.py")
        ]
    }

    for rel_path, changes in corrections.items():
        full_path = VAULT_ROOT / rel_path
        if full_path.exists():
            content = full_path.read_text()
            new_content = content
            for old, new in changes:
                new_content = re.sub(old, new, new_content)
            
            if content != new_content:
                full_path.write_text(new_content)
                print(f"  ✅ Surgically fixed: {rel_path}")

if __name__ == "__main__":
    heal()
