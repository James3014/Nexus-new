import subprocess
import time
import json
import base64
import random
from concurrent.futures import ThreadPoolExecutor

ENDPOINTS = [
    "http://localhost:2379",
    "http://localhost:2381",
    "http://localhost:2382",
    "http://localhost:2383",
    "http://localhost:2384"
]

def put_key(endpoint, key, value):
    key_b64 = base64.b64encode(key.encode()).decode()
    val_b64 = base64.b64encode(value.encode()).decode()
    payload = {
        "key": key_b64,
        "value": val_b64
    }
    cmd = [
        "curl", "-s", "-X", "POST",
        f"{endpoint}/v3/kv/put",
        "-d", json.dumps(payload)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        return res.stdout
    except:
        return None

def get_status(endpoint):
    # status doesn't need base64 usually for just status
    cmd = [
        "curl", "-s", "-X", "POST",
        f"{endpoint}/v3/maintenance/status",
        "-d", "{}"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        return json.loads(res.stdout)
    except:
        return None

def get_leader(endpoint):
    status = get_status(endpoint)
    if status:
        return status.get('leader')
    return None

def chaos_injector():
    print("🔥 Starting Hard-Kill Chaos Injector...")
    for _ in range(3):
        time.sleep(3)
        try:
            target = f"etcd-abyss-{random.randint(1,5)}"
            print(f"🧨 Hard-Killing {target}...")
            subprocess.run(["docker", "kill", target])
            time.sleep(2)
            print(f"♻️ Restarting {target}...")
            # Use docker start from the compose project
            subprocess.run(["docker", "start", target])
        except:
            pass

def load_tester():
    print("🚀 Starting Extreme Load Tester (10000 tasks)...")
    with ThreadPoolExecutor(max_workers=50) as executor:
        for i in range(10000):
            ep = random.choice(ENDPOINTS)
            executor.submit(put_key, ep, f"abyss-key-{i}", f"abyss-val-{i}")
    print("✅ Load Test Finished.")

if __name__ == "__main__":
    print("🌑 Nexus Abyss Reproduction Script (#13766)")
    
    # Run load and chaos in parallel
    with ThreadPoolExecutor(max_workers=2) as main_executor:
        main_executor.submit(load_tester)
        main_executor.submit(chaos_injector)
    
    time.sleep(5)
    print("\n📊 Final Consistency Audit:")
    results = []
    for i, ep in enumerate(ENDPOINTS):
        status = get_status(ep)
        if status:
            rev = status.get('header', {}).get('revision')
            db_size = status.get('dbSize')
            results.append((f"Node-{i+1}", rev, db_size))
            print(f"  {f'Node-{i+1}':<10} | Revision: {rev:<10} | DB Size: {db_size}")
        else:
            print(f"  Node-{i+1:<10} | OFFLINE")

    revisions = [r[1] for r in results if r[1] is not None]
    if len(set(revisions)) > 1:
        print("\n❌ [ABYSS DETECTED] Consistency Drift Found!")
        print(f"   Delta: {max(revisions) - min(revisions)} revisions.")
    else:
        print("\n✅ [SOTA SURVIVAL] No drift detected in this run.")
