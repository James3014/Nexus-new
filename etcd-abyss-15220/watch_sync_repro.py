import subprocess
import time
import json
import base64
import threading
from concurrent.futures import ThreadPoolExecutor

ENDPOINT = "http://localhost:2379"

def put_key(key, value):
    key_b64 = base64.b64encode(key.encode()).decode()
    val_b64 = base64.b64encode(value.encode()).decode()
    payload = {"key": key_b64, "value": val_b64}
    subprocess.run(["curl", "-s", "-X", "POST", f"{ENDPOINT}/v3/kv/put", "-d", json.dumps(payload)], capture_output=True)

def watch_stream():
    print("👀 Starting Watcher Stream...")
    # Watch request for 'abyss/' prefix (61627973732f)
    watch_req = {
        "create_request": {
            "key": base64.b64encode(b"abyss/").decode(),
            "range_end": base64.b64encode(b"abyss0").decode(), # prefix 'abyss/'
            "progress_notify": True
        }
    }
    
    # Use curl with --no-buffer to see stream in real-time
    cmd = ["curl", "-s", "-N", "-X", "POST", f"{ENDPOINT}/v3/watch", "-d", json.dumps(watch_req)]
    
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    current_rev = 0
    violations = 0
    
    start_time = time.time()
    while time.time() - start_time < 30: # Record for 30s
        line = process.stdout.readline()
        if not line: break
        try:
            resp = json.loads(line)
            header = resp.get('result', {}).get('header', {})
            rev = int(header.get('revision', 0))
            is_progress = resp.get('result', {}).get('created', False) == False and not resp.get('result', {}).get('events')
            
            if is_progress:
                print(f"  [ProgressNotify] Revision: {rev}")
                if rev < current_rev:
                    print(f"⚠️  [ABYSS DRIFT] Progress Notify Revision {rev} < Last Event Revision {current_rev}!")
                    violations += 1
            else:
                events = resp.get('result', {}).get('events', [])
                if events:
                    for ev in events:
                        ev_rev = int(ev.get('kv', {}).get('mod_revision', 0))
                        # print(f"  [Event] Mod Revision: {ev_rev}")
                        if ev_rev > current_rev:
                            current_rev = ev_rev
        except:
            continue
            
    process.kill()
    print(f"\n📊 Watcher Audit Finished. Total Violations: {violations}")

def load_generator():
    print("🚀 Starting Load Generator...")
    for i in range(200):
        put_key(f"abyss/key-{i}", f"val-{i}")
        time.sleep(0.1)
    print("✅ Load Generator Finished.")

if __name__ == "__main__":
    print("🌑 Nexus Abyss World-War: etcd #15220")
    
    t_watch = threading.Thread(target=watch_stream)
    t_load = threading.Thread(target=load_generator)
    
    t_watch.start()
    time.sleep(2)
    t_load.start()
    
    t_load.join()
    t_watch.join()
