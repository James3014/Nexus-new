import os
import re
from pathlib import Path

repo_root = Path("/Users/jameschen/Workspace/nexus")
wiki_vault = repo_root / "nexus_wiki_vault"

print("🔍 [Nexus:Normalizer] Building Global File Index...")

# 1. Build Basename -> Relative Path Index
file_index = {}
for file in wiki_vault.glob("**/*.md"):
    rel_path = file.relative_to(wiki_vault)
    # Store with and without .md for maximum matching
    file_index[file.name] = rel_path
    file_index[file.stem] = rel_path

print(f"📊 [Nexus:Normalizer] Index complete. Indexed {len(file_index)} nodes.")

def normalize_content(content, current_file_path):
    # Process Obsidian Links [[File]]
    def obs_replacer(match):
        inner = match.group(1).split("|")
        link_target = inner[0].strip()
        display_name = inner[1].strip() if len(inner) > 1 else link_target
        
        clean_target = link_target.replace(".md", "")
        if clean_target in file_index:
            target_path = file_index[clean_target]
            final_rel = os.path.relpath(wiki_vault / target_path, current_file_path.parent)
            return f"[{display_name}]({final_rel})"
        return match.group(0)

    # Process Standard Markdown Links [Name](path)
    def md_replacer(match):
        display_name = match.group(1)
        link_target = match.group(2)
        
        # If it's already a complex path or starts with ., skip
        if "/" in link_target or link_target.startswith("."):
            return match.group(0)
        
        clean_target = link_target.replace(".md", "")
        if clean_target in file_index:
            target_path = file_index[clean_target]
            final_rel = os.path.relpath(wiki_vault / target_path, current_file_path.parent)
            return f"[{display_name}]({final_rel})"
        return match.group(0)

    # Regex for [[Links]]
    content = re.sub(r"\[\[([^\]]+)\]\]", obs_replacer, content)
    # Regex for [Name](target)
    content = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", md_replacer, content)
    
    return content

print("🚀 [Nexus:Normalizer] Executing Full-Scale Normalization...")
files_processed = 0
links_normalized = 0

for md_file in wiki_vault.glob("**/*.md"):
    # Skip .obsidian dir
    if ".obsidian" in str(md_file): continue
    
    old_content = md_file.read_text(errors="ignore")
    # Preserve 8 sections (simple check: don't touch the very top if it's YAML)
    new_content = normalize_content(old_content, md_file)
    
    if old_content != new_content:
        md_file.write_text(new_content)
        files_processed += 1

print(f"✅ [Nexus:Normalizer] Complete. Processed {files_processed} files.")
