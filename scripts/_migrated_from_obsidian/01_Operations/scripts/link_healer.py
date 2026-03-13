import os
import re

def normalize(text):
    text = text.lower()
    text = text.replace("：", ":").replace("？", "?").replace("（", "(").replace("）", ")")
    text = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5]", "", text)
    return text

def heal_links():
    vault_root = "知識庫"
    all_files = {}
    orphans_original = {}

    for root, dirs, files in os.walk(vault_root):
        dirs[:] = [d for d in dirs if d not in ["00_System_Knowledge", "01_Operations", "scripts", ".git"]]
        for file in files:
            if file.endswith(".md"):
                name = file.replace(".md", "")
                norm_name = normalize(name)
                all_files[norm_name] = name
                orphans_original[norm_name] = name

    for root, dirs, files in os.walk(vault_root):
        for file in files:
            if file.endswith(".md"):
                path = os.path.join(root, file)
                with open(path, "r", errors="ignore") as f:
                    content = f.read()
                matches = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content)
                for m in matches:
                    norm_link = normalize(m.strip())
                    if norm_link in orphans_original:
                        del orphans_original[norm_link]

    report_path = "知識庫/01_Operations/Brain_Health_Report.md"
    orphan_list = sorted(list(orphans_original.values()))
    
    with open(report_path, "w") as f:
        f.write("# 🏥 大腦健康診斷報告 (Fuzzy Logic v2.0)\n\n")
        if not orphan_list:
            f.write("🎉 恭喜！大腦全神經網路已完全連通。\n")
        else:
            f.write(f"## 🏝️ 確診孤島檔案 ({len(orphan_list)})\n")
            for orphan in orphan_list:
                f.write(f"- [[{orphan}]]\n")

if __name__ == "__main__":
    heal_links()
