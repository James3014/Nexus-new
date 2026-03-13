import sys
import subprocess
import os
from datetime import datetime

# 1. 定義高風險關鍵字 (Risk Matrix)
RISK_KEYWORDS = ["delete", "rm", "quit", "pay", "send", "config", "install", "sudo"]

def capture_review_snapshot():
    print("🛡️ Security Intercept: High-risk action detected. Capturing snapshot for review...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_path = f"知識庫/01_Operations/Inbox/Action_Review_{timestamp}.png"
    # 呼叫 peekaboo 進行截圖 (模擬)
    subprocess.run(["peekaboo", "image", "--output", snapshot_path])
    return snapshot_path

def check_action_risk(command):
    # 檢查指令是否包含高風險詞
    for k in RISK_KEYWORDS:
        if k in command.lower():
            return True
    return False

def execute_with_guard(command):
    is_risky = check_action_risk(command)
    
    if is_risky:
        snapshot = capture_review_snapshot()
        print(f"\n⚠️ WARNING: The action [{command}] is flagged as HIGH RISK.")
        print(f"📸 Review Snapshot: {snapshot}")
        print("🛑 EXECUTION HALTED. Please type 'approve' to proceed or anything else to cancel.")
        # 在 CLI 互動模式下等待輸入
        return False
    else:
        # 低風險動作，直接執行
        print(f"✅ Safe Action Verified: {command}")
        return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: computer_guard.py [peekaboo_command]")
    else:
        cmd_to_check = " ".join(sys.argv[1:])
        execute_with_guard(cmd_to_check)
