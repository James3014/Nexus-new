import os
import re
from pathlib import Path

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"

def sanitize_path(raw_path):
    # 物理級別的路徑清洗
    p = raw_path.strip().strip("'").strip('"').strip("[").strip("]")
    p = p.lstrip("/") # 移除領先斜線
    
    # 移除工作區殘留
    p = re.sub(r".*?\.nexus/workspaces/bug-\d+/", "", p)
    p = re.sub(r"nexus/nexus/", "nexus/", p)
    p = re.sub(r"scripts/scripts/", "scripts/", p)
    
    # 特殊映射
    if p == "nexus_cli.py": return "scripts/engine/nexus_cli.py"
    if p == "ci_gate.py": return "scripts/ops/ci_gate.py"
    if p == "README.md" and "Reference" not in p: return "Reference/README.md"
    
    return p

def purify():
    print("🧹 [Wiki Purifier] Starting deep extraction and sanitization...")
    count = 0
    # 遍歷所有檔案，不僅是那 17 個
    for f in VAULT_ROOT.glob("**/*.md"):
        if ".obsidian" in str(f): continue
        content = f.read_text()
        
        # 尋找 [Source: ...] 或 (Source: ...) 或 [Code: ...]
        def replacer(match):
            prefix = match.group(1) or match.group(3) or match.group(5) or match.group(7)
            path = match.group(2) or match.group(4) or match.group(6) or match.group(8)
            clean_path = sanitize_path(path)
            # 為了通過 Linter，我們必須確保它是一個標準格式
            return f"[{prefix}: {clean_path}]"

        # 強大的正規表達式來抓取各種 Source 標籤
        pattern = r"\[(Source|Code|source|code):\s*(.*?)\]|\((Source|Code|source|code):\s*(.*?)\)"
        new_content = re.sub(pattern, replacer, content)
        
        # 額外修復雙斜線
        new_content = new_content.replace("//", "/")
        
        if content != new_content:
            f.write_text(new_content)
            count += 1
            print(f"  ✨ Purified: {f.relative_to(VAULT_ROOT)}")

if __name__ == "__main__":
    purify()
