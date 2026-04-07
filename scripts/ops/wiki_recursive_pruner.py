import os
import re
from pathlib import Path

wiki_vault = Path("/Users/jameschen/Workspace/nexus/nexus_wiki_vault")

# Defined mappings for common broken shorthand
SHORTHAND_MAP = {
    "Human.md": "01_System/System - Next Questions for Human.md",
    "Index.md": "90_Sources/Source Index.md",
    "Overview.md": "00_Home/System Overview.md",
    "Map.md": "00_Home/Vault Topology.md",
    "Playbook.md": "06_Ops/Ops - CI Failure Playbook.md",
    "Registry.md": "90_Sources/Source - Nexus Anti Registry.md",
    "Gate.md": "02_Modules/Module - Implementation Responsibility Matrix.md"
}

def prune_content(content, current_file_path):
    # 1. Prune redundant recursive paths: e.g. ../.nexus/nexus_wiki_vault/... -> ../
    # Pattern: matches any number of nested .nexus/nexus_wiki_vault sequences
    content = re.sub(r'(\.\./)+\.nexus/nexus_wiki_vault/(\.nexus/nexus_wiki_vault/)*', '../', content)
    
    # 2. Fix known shorthands that were missing from v2 normalizer or broken
    for short, full in SHORTHAND_MAP.items():
        # Match [[Short]] or [Name](Short)
        rel_to_current = os.path.relpath(wiki_vault / full, current_file_path.parent)
        
        # Replace [[Short]]
        content = content.replace(f"[[{short}]]", f"[{short.replace('.md', '')}]({rel_to_current})")
        # Replace [[Short|Alias]]
        content = re.sub(rf"\[\[{short}\|([^\]]+)\]\]", rf"[\1]({rel_to_current})", content)
        # Replace raw mentions if they look like links
        content = content.replace(f"({short})", f"({rel_to_current})")
        
    return content

print("🚀 [Nexus:Pruner] Starting Global Structure Purification...")
files_corrected = 0

for md_file in wiki_vault.glob("**/*.md"):
    if ".obsidian" in str(md_file): continue
    
    try:
        old_content = md_file.read_text(encoding="utf-8", errors="ignore")
        new_content = prune_content(old_content, md_file)
        
        if old_content != new_content:
            md_file.write_text(new_content, encoding="utf-8")
            files_corrected += 1
    except Exception as e:
        print(f"⚠️ Failed to prune {md_file}: {e}")

print(f"✅ [Nexus:Pruner] Complete. Purified {files_corrected} files.")
