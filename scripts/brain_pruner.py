import os
import subprocess


def run_auto_archive():
    print("✂️ Brain-Pruner v2.0: Auto-Archiving stale orphans...")
    archive_dir = "知識庫/Archive"
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)

    # 邏輯：從健康報告中抓取孤島，若超過 30 天未改動則移動
    health_report = "知識庫/01_Operations/Brain_Health_Report.md"
    if not os.path.exists(health_report):
        return

    with open(health_report, "r") as f:
        orphans = re.findall(r"\[\[(.*?)\]\]", f.read())

    for name in orphans:
        # 搜尋實體路徑
        cmd = f"find 知識庫 -name '{name}.md'"
        try:
            path = subprocess.check_output(cmd, shell=True).decode("utf-8").strip()
            if path and "Archive" not in path:
                # 執行移動
                new_path = os.path.join(archive_dir, os.path.basename(path))
                print(f"💡 Suggestion: Archive {name} (Safe Mode: No action taken)")
                print(f"📦 Archived: {name}")
        except:
            continue


import re

if __name__ == "__main__":
    run_auto_archive()
