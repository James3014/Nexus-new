import os
import re
import subprocess

def find_new_path(file_name, root_dir):
    # 在大腦庫中搜尋檔案的新位置
    try:
        cmd = f"find {root_dir} -name '{file_name}'"
        result = subprocess.check_output(cmd, shell=True).decode("utf-8").strip()
        return result.split("\n")[0] if result else None
    except: return None

def heal_all_skills():
    skills_dir = os.path.expanduser("~/.openclaw/skills")
    obsidian_root = "/Users/jameschen/Downloads/obsidian"
    print(f"🩹 Starting Path Healer in: {skills_dir}")
    
    fixed_count = 0
    # 掃描所有技能腳本
    for root, dirs, files in os.walk(skills_dir):
        for file in files:
            if file.endswith((".py", ".sh", ".json", ".md")):
                path = os.path.join(root, file)
                try:
                    with open(path, "r", errors="ignore") as f: content = f.read()
                    
                    # 找出所有 obsidian 路徑
                    matches = re.findall(r"(/Users/jameschen/Downloads/obsidian/[^\"]+)", content)
                    new_content = content
                    
                    for old_p in matches:
                        if not os.path.exists(old_p):
                            file_name = os.path.basename(old_p)
                            new_p = find_new_path(file_name, obsidian_root)
                            if new_p:
                                new_content = new_content.replace(old_p, new_p)
                                print(f"🔄 Healed: {file_name} in {file}")
                                fixed_count += 1
                    
                    if new_content != content:
                        with open(path, "w") as f: f.write(new_content)
                except: continue
                
    print(f"✨ Path Healing Complete. Total links fixed: {fixed_count}")

if __name__ == "__main__":
    heal_all_skills()
