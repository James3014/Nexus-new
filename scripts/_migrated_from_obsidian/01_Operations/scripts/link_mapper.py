import os
import re

def fix_links():
    vault_root = "知識庫"
    # 1. 建立實體檔案映射 (ID -> Full Name)
    id_to_name = {}
    for root, dirs, files in os.walk(vault_root):
        for file in files:
            if file.endswith(".md"):
                name = file.replace(".md", "")
                # 提取編號，如 #01 或 001
                match = re.search(r"(#\d+|^\d{3})", name)
                if match:
                    id_to_name[match.group(1)] = name

    # 2. 定義要修正的日文關鍵字 (從報表提取)
    # 這裡我們自動化處理：只要連結包含日文且有編號，就嘗試匹配
    jp_pattern = re.compile(r"\[\[(.*?[ぁ-んァ-ヶ].*?)\]\]")

    processed_count = 0
    for root, dirs, files in os.walk(vault_root):
        for file in files:
            if file.endswith(".md") and file != "Brain_Health_Report.md":
                path = os.path.join(root, file)
                with open(path, "r", errors="ignore") as f:
                    content = f.read()
                
                matches = jp_pattern.findall(content)
                if matches:
                    new_content = content
                    for old_link in matches:
                        # 嘗試從舊連結抓編號
                        id_match = re.search(r"(#\d+|^\d{3})", old_link)
                        if id_match and id_match.group(1) in id_to_name:
                            new_link = id_to_name[id_match.group(1)]
                            new_content = new_content.replace(f"[[{old_link}]]", f"[[{new_link}]]")
                            print(f"🔄 Fixed: [[{old_link}]] -> [[{new_link}]] in {file}")
                            processed_count += 1
                    
                    if new_content != content:
                        with open(path, "w") as f:
                            f.write(new_content)

    print(f"✨ Total links fixed: {processed_count}")

if __name__ == "__main__":
    fix_links()
