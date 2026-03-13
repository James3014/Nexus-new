import os
import subprocess
import re

def generate_intelligent_skill():
    print("🧬 [Auto-Skill] Harvesting from Git history...")
    obsidian_root = "/Users/jameschen/Downloads/obsidian"
    try:
        commit_msg = subprocess.check_output(["git", "log", "-1", "--pretty=%B"], cwd=obsidian_root).decode("utf-8").strip()
        if "feat" in commit_msg.lower():
            skill_name = commit_msg.split(":")[1].strip().lower().replace(" ", "-")[:30]
            output_dir = "知識庫/02_Arsenal/Auto_Extracted_Skills"
            if not os.path.exists(output_dir): os.makedirs(output_dir)
            with open(os.path.join(output_dir, f"SKILL-{skill_name}.md"), "w") as f:
                f.write(f"# 🛡️ Auto-Generated Skill: {skill_name}\n\n> [!warning] 授權狀態: 🟥 PENDING\n\n## 📝 邏輯描述\n{commit_msg}")
            print(f"✨ Seed Skill Created: {skill_name}")
    except: pass

if __name__ == "__main__":
    generate_intelligent_skill()
