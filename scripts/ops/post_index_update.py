import os
import re
import json
from datetime import datetime
from pathlib import Path

# Paths
REPO_ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[2])
OBSIDIAN_ROOT = "/Users/jameschen/Downloads/obsidian/知識庫/01_Projects/nexus/docs"
INDEX_MD = "docs/INDEX.md"
TASK_STATUS = ".nexus/task_status.json"
BENCHMARK_CSV = "ci_benchmark.csv"

def load_json(path):
    if not os.path.exists(path): return {}
    with open(path, "r") as f: return json.load(f)

def update_index_content(content, task_status):
    # 1. 識別區塊 (使用更寬鬆的 re.DOTALL 以匹配置頂後的結構)
    # 這裡的邏輯基本上不需要變，只要區塊名稱（### Next 等）沒變即可。
    # 但為了確保置頂效果，我們維持原有的 re.sub 邏輯。
    
    sections = ["### In Progress", "### Next", "### Done"]
    found_sections = {s: re.search(rf"{s}\n(.*?)(?=\n##|\Z|---)", content, re.DOTALL) for s in sections}
    
    if not found_sections["### Next"]: return content
    
    next_lines = found_sections["### Next"].group(1).strip().split("\n") if found_sections["### Next"] else []
    tasks_map = task_status.get("tasks", {})
    
    remaining_next = []
    current_in_progress = []
    new_done_items = []
    
    for line in next_lines:
        match = re.search(r"^(\d+)\.\s*(.*)", line.strip())
        if match:
            idx_num = match.group(1)
            task_desc = match.group(2).strip()
            task_id = f"index.task.{idx_num}"
            status = tasks_map.get(task_id, {}).get("status")
            
            if status == "done":
                ts = datetime.now().strftime("%Y-%m-%d %H:%M")
                new_done_items.append(f"- {task_desc} (Done {ts} via Nex-CEx)")
            elif status == "running":
                current_in_progress.append(f"- {task_desc} (Executing...)")
            else:
                remaining_next.append(line)
        else:
            if line.strip() and line.strip() != "- (No tasks planned)":
                remaining_next.append(line)

    # 回寫 Done
    if new_done_items:
        done_header = "### Done\n"
        insertion = "\n".join(new_done_items) + "\n"
        content = content.replace(done_header, done_header + insertion)

    # 回寫 In Progress
    prog_str = "### In Progress\n" + ("\n".join(current_in_progress) if current_in_progress else "- (Everything handled via Nex-CEx automation loop)") + "\n"
    content = re.sub(r"### In Progress\n(.*?)(?=\n##|\Z|---)", prog_str, content, flags=re.DOTALL)

    # 回寫 Next
    next_str = "### Next\n" + ("\n".join(remaining_next) if remaining_next else "- (No tasks planned)") + "\n"
    content = re.sub(r"### Next\n(.*?)(?=\n##|\Z|---)", next_str, content, flags=re.DOTALL)

    # 更新 Snapshot (帶時區)
    ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = re.sub(r"Last Verified Snapshot: `.*`", f"Last Verified Snapshot: `(Verified at {ts_now} via Nex-CEx)`", content)
    
    # 4. 連動更新「計劃完工核對表」的狀態
    # 這裡我們用正則搜尋表格列，比對檔名關鍵字
    table_match = re.search(r"## 📋 計劃完工核對表\n(.*?)(?=\n---|\Z)", content, re.DOTALL)
    if table_match:
        table_content = table_match.group(1)
        new_table_content = table_content
        
        # 針對每個已完成的任務描述，去表格裡找關鍵字
        for item in new_done_items:
            # 提取關鍵字 (例如從 "- 修復任務單 (Done ...)" 提取 "修復任務單")
            kw_match = re.search(r"- (.*?) \(Done", item)
            if kw_match:
                kw = kw_match.group(1).strip()
                # 在表格中尋找含有該關鍵字且狀態為 TODO/IN_PROGRESS 的列
                # | 檔名 | TODO | ... |
                new_table_content = re.sub(
                    rf"\| ([^|]*?{re.escape(kw)}[^|]*?) \| (?:TODO|IN_PROGRESS) \|",
                    r"| \1 | `DONE` |",
                    new_table_content
                )
        
        if new_table_content != table_content:
            content = content.replace(table_content, new_table_content)

    return content

def main():
    print("🔄 [Post-Update] Syncing task results back to INDEX.md...")
    status = load_json(os.path.join(REPO_ROOT, TASK_STATUS))
    
    local_idx = os.path.join(REPO_ROOT, INDEX_MD)
    obsidian_idx = os.path.join(OBSIDIAN_ROOT, "INDEX.md")
    
    if os.path.exists(local_idx):
        content = Path(local_idx).read_text(encoding='utf-8')
        new_content = update_index_content(content, status)
        
        # 寫回本機
        Path(local_idx).write_text(new_content, encoding='utf-8')
        print(f"  [+] Local INDEX.md updated.")
        
        # 寫進 Obsidian (如果路徑存在)
        if os.path.exists(os.path.dirname(obsidian_idx)):
            Path(obsidian_idx).write_text(new_content, encoding='utf-8')
            print(f"  [+] Obsidian INDEX.md synchronized.")
        else:
            print(f"  [!] Obsidian path not found: {obsidian_idx}")

if __name__ == "__main__":
    main()
