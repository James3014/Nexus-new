import os
import shutil
import re
from pathlib import Path

SKILL_ROOT = Path("/Users/jameschen/.agents/skills")
QUARANTINE = Path("/Users/jameschen/Downloads/nexus_quarantine")

def sanitize():
    print("🚀 [Brain Sanitizer] Starting operation...")
    
    # --- 1. 隔離雜質 ---
    for item in SKILL_ROOT.iterdir():
        if item.is_dir():
            if any(x in item.name.lower() for x in ["bak", "old", "archive", "copy", "crystallized", "tmp"]):
                print(f"📦 Quarantining: {item.name}")
                shutil.move(str(item), str(QUARANTINE / item.name))

    # --- 2. 處理嵌套與對齊 ---
    # 遍歷兩次，先打平再重命名
    for item in SKILL_ROOT.iterdir():
        if not item.is_dir(): continue
        
        skill_md = item / "SKILL.md"
        # 檢查嵌套: dir/dir/SKILL.md
        sub_dir = item / item.name
        if sub_dir.is_dir() and (sub_dir / "SKILL.md").exists():
            print(f"🚜 Flattening nested: {item.name}")
            # 將子層所有內容移到父層
            for sub_item in sub_dir.iterdir():
                dest = item / sub_item.name
                if dest.exists():
                    if dest.is_dir(): shutil.rmtree(dest)
                    else: dest.unlink()
                shutil.move(str(sub_item), str(item))
            shutil.rmtree(sub_dir)

        # 強制對齊內部 name
        if skill_md.exists():
            content = skill_md.read_text()
            new_name = item.name
            # 確保 name: 與 folder_name 一致
            new_content = re.sub(r"^name:.*", f"name: {new_name}", content, flags=re.MULTILINE)
            if content != new_content:
                print(f"🧬 Aligning metadata: {new_name}")
                skill_md.write_text(new_content)

if __name__ == "__main__":
    sanitize()
