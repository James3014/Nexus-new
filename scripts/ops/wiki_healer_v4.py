import os
from pathlib import Path

VAULT_ROOT = Path("/Users/jameschen/Workspace/nexus/nexus_wiki_vault")
REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")

def heal():
    print("🩹 [Wiki Healer v4] Executing mass backlink injection and syntax repair...")
    count = 0
    
    # 遍歷所有 Wiki 檔案
    for f in VAULT_ROOT.glob("**/*.md"):
        if ".obsidian" in str(f): continue
        
        content = f.read_text()
        original = content
        
        # --- 1. 強制補上 [[System Overview]] 回鏈 ---
        if "[[System Overview]]" not in content:
            content += "\n\n---\n[[System Overview]]"
            
        # --- 2. 修正 .nexus/graph/Community_1.md 的 YAML 錯誤 ---
        if "Community_1.md" in f.name:
            # 確保 meta 區塊正確封閉
            if not content.startswith("---"):
                content = "---\ntitle: Community Cluster 1\n" + content
        
        if content != original:
            f.write_text(content)
            count += 1
            
    print(f"  ✅ Successfully repaired {count} files.")

if __name__ == "__main__":
    heal()
