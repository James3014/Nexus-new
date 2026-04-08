import os
import re
from pathlib import Path
from collections import defaultdict

repo_root = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2]))
wiki_vault = repo_root / "nexus_wiki_vault"

print("🔍 [Nexus:Normalizer] Building Multi-Index for Collision Detection...")

# 1. Build Name -> List of Paths Multi-Index
file_index = defaultdict(list)
for file in wiki_vault.glob("**/*.md"):
    rel_path = file.relative_to(wiki_vault)
    file_index[file.name].append(rel_path)
    file_index[file.stem].append(rel_path)

print(f"📊 [Nexus:Normalizer] Multi-Index complete. Nodes: {len(file_index)}")

def find_best_match(target_name, current_file_path):
    # Strip potential Obsidian artifacts
    clean_target = target_name.replace(".md", "").split("|")[0].strip()
    matches = file_index.get(clean_target) or file_index.get(target_name)
    
    if not matches:
        return None
    
    # If unique, return it as a Path object
    if len(matches) == 1:
        return matches[0] if isinstance(matches[0], Path) else Path(matches[0])
    
    # If multiple, prioritize the one in the same parent directory
    current_parent_name = current_file_path.parent.name
    for m in matches:
        p = m if isinstance(m, Path) else Path(m)
        if p.parent.name == current_parent_name:
            return p
            
    # Default to the first one as a Path object
    return Path(matches[0]) if not isinstance(matches[0], Path) else matches[0]

def normalize_content(content, current_file_path):
    # Process Obsidian Links [[File]] or [[File|Alias]] 
    def obs_replacer(match):
        raw_inner = match.group(1)
        inner_parts = raw_inner.split("|")
        link_target = inner_parts[0].strip()
        display_name = inner_parts[1].strip() if len(inner_parts) > 1 else link_target
        
        target_path = find_best_match(link_target, current_file_path)
        if target_path:
            # target_path is relative to wiki_vault
            abs_target = wiki_vault / target_path
            final_rel = os.path.relpath(abs_target, current_file_path.parent)
            return f"[{display_name}]({final_rel})"
        return match.group(0)

    # Process Standard Markdown Links [Name](path)
    def md_replacer(match):
        display_name = match.group(1)
        link_target = match.group(2)
        
        # If it's already a complex path / URL / absolute, skip
        if "/" in link_target or link_target.startswith(".") or link_target.startswith("http"):
            return match.group(0)
        
        target_path = find_best_match(link_target, current_file_path)
        if target_path:
            abs_target = wiki_vault / target_path
            final_rel = os.path.relpath(abs_target, current_file_path.parent)
            return f"[{display_name}]({final_rel})"
        return match.group(0)

    # Regex for [[Links]]
    content = re.sub(r"\[\[([^\]]+)\]\]", obs_replacer, content)
    # Regex for [Name](target)
    content = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", md_replacer, content)
    
    return content

print("🚀 [Nexus:Normalizer] Executing Full-Scale Normalization...")
files_processed = 0

for md_file in wiki_vault.glob("**/*.md"):
    if ".obsidian" in str(md_file): continue
    
    try:
        old_content = md_file.read_text(encoding="utf-8", errors="ignore")
        new_content = normalize_content(old_content, md_file)
        
        if old_content != new_content:
            md_file.write_text(new_content, encoding="utf-8")
            files_processed += 1
    except Exception as e:
        print(f"⚠️ Failed to process {md_file}: {e}")

print(f"✅ [Nexus:Normalizer] Complete. Processed {files_processed} files.")
