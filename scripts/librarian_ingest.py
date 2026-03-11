# 🛡️ Codex-Verified: Codex-Auth-Lvl13-Final (2026-03-03)
import os
import re


def clean_item(text):
    # 移除 Markdown 符號、引號、括號與結尾標點
    text = re.sub(r"[\]\[\*\"\'\.,，。；;！？\?]", "", text)
    text = text.replace(".txt", "").replace("]]", "").replace("**", "")
    return text.strip()


def update_frontmatter(file_path, items, insights):
    with open(file_path, "r", errors="ignore") as f:
        content = f.read()

    frontmatter_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    cleaned_items = sorted(
        list(set([clean_item(i) for i in items if len(clean_item(i)) > 1]))
    )[:8]

    new_fields = "items:\n" + "\n".join([f"  - {i}" for i in cleaned_items]) + "\n"
    new_fields += "insights:\n" + "\n".join([f"  - {i}" for i in insights]) + "\n"

    if frontmatter_match:
        old_fm = frontmatter_match.group(1)
        # 移除舊的 items 與 insights 區塊再重新注入
        fm_no_items = re.sub(r"items:\n(?:  - .*\n?)+", "", old_fm)
        fm_no_insights = re.sub(r"insights:\n(?:  - .*\n?)+", "", fm_no_items)
        updated_fm = f"---\n{fm_no_insights.strip()}\n{new_fields}---"
        new_content = content.replace(frontmatter_match.group(0), updated_fm + "\n")
    else:
        new_content = f"---\n{new_fields}---\n\n" + content

    with open(file_path, "w") as f:
        f.write(new_content)
    return True


def deep_clean_ingest(directory):
    print("🧹 Deep Cleaning Ingestion Started...")
    processed = 0
    for root, dirs, files in os.walk(directory):
        dirs[:] = [
            d
            for d in dirs
            if d not in ["00_System_Knowledge", "01_Operations", "scripts"]
        ]
        for file in files:
            if file.endswith(".md") and file != "README.md":
                path = os.path.join(root, file)
                with open(path, "r", errors="ignore") as f:
                    text = f.read()

                # 提取關鍵詞，增加「架構、技術、邏輯」等維度
                items = re.findall(
                    r"(?:重心|角度|發力|策略|結構|系統|架構|技術|邏輯)[^\s，。]*", text
                )
                if items:
                    update_frontmatter(path, items, ["Lvl 12 精準去噪提取 v2.0"])
                    processed += 1
    print(f"✅ Deep Clean Complete. Processed {processed} files.")


if __name__ == "__main__":
    deep_clean_ingest("知識庫")
