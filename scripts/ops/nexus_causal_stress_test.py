import threading
import time
import json
from pathlib import Path
from nexus.core.event_bus import NexusEventBus

def simulate_swarm_node(node_id, shared_payload):
    time.sleep(0.01) # 增加並發機率
    NexusEventBus.publish("swarm_sync", shared_payload)

def run_test():
    NexusEventBus.configure(Path("."))
    shared_payload = {"data": "initial"}
    
    threads = []
    print(f"🚀 [Stress Test] Launching 50 Swarm Nodes with Shared Payload...")
    for i in range(50):
        t = threading.Thread(target=simulate_swarm_node, args=(i, shared_payload))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    # 讀取結果並檢查因果一致性
    events = NexusEventBus.get_recent_events("swarm_sync", limit=50)
    timestamps = [e["timestamp"] for e in events]
    
    # 檢查是否所有 timestamp 都是遞增的
    inversions = 0
    for i in range(1, len(timestamps)):
        if timestamps[i] < timestamps[i-1]:
            inversions += 1
            
    print(f"📊 [Result] Total Events: {len(events)}, Causal Inversions: {inversions}")
    if inversions > 0:
        print("❌ [FAILURE] Causal Consistency Broken!")
    else:
        print("✅ [PASS] System is consistent.")

if __name__ == "__main__":
    run_test()
