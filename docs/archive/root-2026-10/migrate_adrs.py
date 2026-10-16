import os
import glob
import shutil

def migrate_adrs():
    src_pattern = "docs/arch/ADR-2026-05-*"
    dest_dir = "nexus_wiki_vault/01_System/ADR/"
    os.makedirs(dest_dir, exist_ok=True)
    
    frontmatter = """---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

"""
    
    for f in glob.glob(src_pattern):
        filename = os.path.basename(f)
        dest_path = os.path.join(dest_dir, filename)
        
        with open(f, 'r') as original:
            content = original.read()
            
        with open(dest_path, 'w') as new_file:
            new_file.write(frontmatter + content)
            
        os.remove(f)
        print(f"Migrated {f} to {dest_path}")

if __name__ == "__main__":
    migrate_adrs()
