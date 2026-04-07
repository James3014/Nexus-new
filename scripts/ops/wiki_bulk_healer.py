import os
import re
from pathlib import Path

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"

REQUIRED_HEADERS = [
    "## One-sentence summary", "## Role / responsibility", "## Upstream",
    "## Downstream", "## Related modules / files", "## Source notes",
    "## Open questions / conflicts"
]

def fix_content(content, rel_path):
    original = content
    
    # 1. 修正路徑噪音
    content = content.replace("scriptsscripts", "scripts")
    content = content.replace("scripts/scripts/", "scripts/")
    content = content.replace("ReferenceReference/", "Reference/")
    content = content.replace("nexus/nexus/", "nexus/")
    content = content.replace("'/scripts/", "'scripts/")
    content = content.replace("/scripts/nexus_cli.py", "scripts/engine/nexus_cli.py")
    
    # 2. 清理工作區殘留
    content = re.sub(r"/?\.nexus/workspaces/bug-\d+/scripts/ops/", "scripts/ops/", content)
    content = re.sub(r"/?\.nexus/workspaces/bug-\d+/nexus/core/", "nexus/core/", content)
    content = re.sub(r"/?\.nexus/workspaces/bug-\d+/nexus/services/", "nexus/services/", content)
    
    # 3. 強制補上回鏈
    if "[[System Overview]]" not in content and "System Overview" not in str(rel_path):
        content += "\n\n---\n[[System Overview]]"
    
    # 4. 補全缺失的 8 大標題 (如果檔案是空的或嚴重缺失)
    for header in REQUIRED_HEADERS:
        if header not in content:
            content += f"\n\n{header}\n- TBD"
            
    return content

def run():
    print("🩹 [Bulk Healer] Starting mass synchronization of 88+ files...")
    count = 0
    for f in VAULT_ROOT.glob("**/*.md"):
        if ".obsidian" in str(f): continue
        rel_path = f.relative_to(VAULT_ROOT)
        content = f.read_text()
        new_content = fix_content(content, rel_path)
        
        if content != new_content:
            f.write_text(new_content)
            count += 1
    print(f"✅ Successfully healed {count} files.")

if __name__ == "__main__":
    run()
