
import os
from datetime import datetime

def check_active_tasks():
    state_path = "知識庫/01_Operations/STATE.yaml"
    if not os.path.exists(state_path):
        print("ℹ️ No active STATE.yaml found.")
        return

    # 模擬讀取 (因本地沒 yaml 模組，改用正則提取關鍵狀態)
    with open(state_path, "r") as f: content = f.read()
    
    status_match = re.search(r"status: \"(.*?)\"", content)
    task_id_match = re.search(r"task_id: \"(.*?)\"", content)
    
    if status_match and status_match.group(1) == "in-progress":
        task_name = task_id_match.group(1) if task_id_match else "Unknown Task"
        print(f"🧠 [TASK-RESUME] Detected active task: {task_name}")
        
        # 產出續傳簡報
        report_path = "知識庫/01_Operations/Inbox/Resume_Briefing.md"
        with open(report_path, "w") as rf:
            rf.write(f"# 🔄 斷點續傳簡報：{task_name}\n\n")
            rf.write(f"> **偵測時間**: {datetime.now().isoformat()}\n")
            rf.write("> **狀態**: 讀取中... 請 Sir 確認是否繼續執行此任務序列。\n")
        print(f"✅ Resume Briefing created at {report_path}")
    else:
        print("✅ All tasks completed. System Idle.")

import re
if __name__ == "__main__":
    check_active_tasks()
