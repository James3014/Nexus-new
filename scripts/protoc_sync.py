import os
import hashlib
import yaml
import sys
from datetime import datetime

# --- CONFIG ---
WORKSPACE_ROOT = "/Users/jameschen/Workspace/nexus"
BRAIN_PATH = "/Users/jameschen/Downloads/obsidian/知識庫/01_Operations/WORKFLOW.md"
STATE_FILE = os.path.join(WORKSPACE_ROOT, "STATE.yaml")
PROTO_FILE = os.path.join(WORKSPACE_ROOT, "MUSE_PROTO.md")
AUDIO_NOTIFY = "/usr/bin/python3 /Users/jameschen/Workspace/_agents/skills/audio-notify/scripts/notify.py"

def get_md5(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def sync():
    print(f"[*] Starting Muse-Core Protocol Sync...")
    
    # 1. Check Brain Hash
    current_hash = get_md5(BRAIN_PATH)
    if not current_hash:
        print(f"[!] Brain file not found at {BRAIN_PATH}")
        return

    # 2. Read current state
    try:
        with open(STATE_FILE, "r") as f:
            state = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[!] Errow reading STATE.yaml: {e}")
        state = {}

    old_hash = state.get("brain_hash")
    
    # 3. Detect Drift
    drift_score = 0.0
    if old_hash != current_hash:
        print(f"[!] DRIFT DETECTED: Brain hash mismatch!")
        print(f"    Old: {old_hash}")
        print(f"    New: {current_hash}")
        drift_score = 1.0
        # Trigger Audio Alert
        os.system(f'{AUDIO_NOTIFY} "大腦協議已更新，請重新同步"')
    else:
        print(f"[+] Brain is in sync. (Hash: {current_hash})")

    # 4. Update STATE.yaml
    state["brain_hash"] = current_hash
    state["last_sync_utc"] = datetime.utcnow().isoformat() + "Z"
    state["drift_score"] = drift_score
    
    with open(STATE_FILE, "w") as f:
        yaml.safe_dump(state, f, allow_unicode=True, sort_keys=False)
        
    print(f"[+] STATE.yaml updated.")

if __name__ == "__main__":
    sync()
