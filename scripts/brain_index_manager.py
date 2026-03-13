import os
import json
import re

VAULT_ROOT = "/Users/jameschen/Downloads/obsidian/知識庫"
TARGET_DIRS = ["00_System_Knowledge", "01_Operations", "02_Arsenal", "04_Life_OS", "Skiing"]

def extract_metadata(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except:
        return []
    
    # Extract Tags from Frontmatter using Regex (Fallback for PyYAML)
    tags = []
    fm_match = re.search(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if fm_match:
        fm_content = fm_match.group(1)
        # Match tags: [a, b, c] or tags: \n - a \n - b
        tags_match = re.search(r'tags:\s*\[(.*?)\]', fm_content)
        if tags_match:
            tags = [t.strip() for t in tags_match.group(1).split(',')]
        else:
            tags_list_match = re.findall(r'^\s*-\s*(.*)', fm_content, re.MULTILINE)
            if tags_list_match:
                tags = [t.strip() for t in tags_list_match]
            
    # Extract core keywords from headers
    body = content[fm_match.end():] if fm_match else content
    keywords = set(tags)
    headers = re.findall(r'^#+\s+(.*)', body, re.MULTILINE)
    for h in headers:
        terms = re.findall(r'[\u4e00-\u9fa5]{2,}|[a-zA-Z]{3,}', h)
        keywords.update(terms)
        
    return list(keywords)

def update_index():
    total_files = 0
    for target in TARGET_DIRS:
        dir_path = os.path.join(VAULT_ROOT, target)
        if not os.path.exists(dir_path):
            continue
            
        index_data = {}
        for root, _, files in os.walk(dir_path):
            for file in files:
                if file.endswith(".md") and not file.startswith("_") and file != "README.md":
                    file_path = os.path.join(root, file)
                    rel_name = os.path.splitext(file)[0]
                    keywords = extract_metadata(file_path)
                    index_data[rel_name] = keywords
                    total_files += 1
        
        index_path = os.path.join(dir_path, "_index.json")
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
        print(f"Updated index for {target}")
    print(f"Total files indexed: {total_files}")

if __name__ == "__main__":
    update_index()
