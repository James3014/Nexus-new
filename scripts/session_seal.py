import os
import yaml
import json
import subprocess
from datetime import datetime
from pathlib import Path

# --- CONFIG ---
WORKSPACE_ROOT = "/Users/jameschen/Workspace/nexus"
STATE_FILE = os.path.join(WORKSPACE_ROOT, "STATE.yaml")
NEXUS_SYNC_BIN = "/Users/jameschen/.local/bin/nexus-sync"

def seal(summary, next_step, session_id="6aa72168-a011-4c9d-bdcd-927825b50501", secret_code="Nexus-Zero-Amnesia-2026"):
    print(f"[*] Starting Universal Session Seal...")

    # 1. Update STATE.yaml (Machine State)
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            state = yaml.safe_load(f) or {}
    else:
        state = {}

    state["last_sync_utc"] = datetime.utcnow().isoformat() + "Z"
    state["last_actions_summary"] = [summary]
    state["active_task"] = next_step
    state["verification_code"] = secret_code
    state["session_id"] = session_id

    with open(STATE_FILE, "w") as f:
        yaml.safe_dump(state, f, allow_unicode=True, sort_keys=False)
    print(f"[+] STATE.yaml updated.")

    # 2. Push to nexus-sync (Communication Channel)
    sync_content = f"Summary: {summary} | Next: {next_step} | Secret: {secret_code}"
    try:
        subprocess.run([
            NEXUS_SYNC_BIN, 
            session_id, 
            "post", 
            "Antigravity", 
            "Session_Seal", 
            sync_content
        ], check=True)
        print(f"[+] Message posted to nexus-sync channel: {session_id}")
    except Exception as e:
        print(f"[!] Warning: nexus-sync failed: {e}")

    print(f"✅ Universal Seal Complete. Memory is now physical.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        seal(sys.argv[1], sys.argv[2])
    else:
        # Default seal for current status
        seal("已優化萬用協議錨點，完成 CLAUDE.md 與 .cursorrules 靜態化，並將 Session 記憶物理化至 nexus-sync 頻道。", 
             "請 Sir 開啟任意工具 (Antigravity/Codex/Gemini) 驗證是否能透過 nexus-sync 報號。")
