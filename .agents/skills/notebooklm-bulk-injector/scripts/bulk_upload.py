import os, subprocess, sys, json, time, re

def run_sync(root_dir, notebook_id):
    state_file = f".nexus/state/notebooklm/ledger_{notebook_id}.json"
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    
    synced = set()
    if os.path.exists(state_file):
        with open(state_file, 'r') as f: synced = set(json.load(f))

    exts = ('.md', '.txt', '.pdf', '.json', '.csv')
    files_to_sync = []
    for root, _, files in os.walk(root_dir):
        for f in files:
            if f.lower().endswith(exts):
                p = os.path.abspath(os.path.join(root, f))
                if p not in synced: files_to_sync.append(p)

    print(f"--- [Nexus Background Sync] Pending: {len(files_to_sync)} files ---")

    for path in files_to_sync:
        fname = os.path.basename(path)
        # JSON 格式降級
        target_path = path
        if fname.lower().endswith('.json'):
            target_path = path + ".txt"
            subprocess.run(["cp", path, target_path])

        cmd = ["notebooklm", "source", "add", target_path, "-n", notebook_id]
        time.sleep(2.0)
        res = subprocess.run(cmd, capture_output=True, text=True)
        
        if res.returncode == 0:
            synced.add(path)
            # 立即寫入檔案，確保即使當掉也不會重複
            with open(state_file, 'w') as f: json.dump(list(synced), f)
            print(f"✅ Synced: {fname}")
        else:
            print(f"❌ FAIL: {fname} | {res.stderr.strip()}")
        
        if target_path != path: os.remove(target_path)

    print(f"--- [Nexus] All tasks completed. Total: {len(synced)} ---")

if __name__ == "__main__":
    run_sync(sys.argv[1], sys.argv[2])
