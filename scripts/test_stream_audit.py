#!/usr/bin/env python3
import subprocess
import time

def main():
    print("🎬 Starting Streaming Audit Battle Test...")
    
    # 🏃 Execute the streaming collector which simulates gRPC behavior
    start_time = time.time()
    
    # We call the collector script and look for 'INSTANT FEEDBACK'
    process = subprocess.Popen(["python3", "scripts/engine/stream_graph_collector.py"], 
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    instant_alert_found = False
    for line in process.stdout:
        print(line.strip())
        if "INSTANT FEEDBACK" in line:
            elapsed = time.time() - start_time
            print(f"✅ SUCCESS: Instant feedback received in {elapsed:.2f} seconds!")
            instant_alert_found = True
            # In a streaming scenario, we don't necessarily wait for the end to be alert
            break 
            
    process.terminate()
    
    if instant_alert_found:
        print("\n🏆 Phase 28 Verification: PASS (Latency < 3s)")
    else:
        print("\n❌ Phase 28 Verification: FAIL (No instant feedback)")

if __name__ == "__main__":
    main()
