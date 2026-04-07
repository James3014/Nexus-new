import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from nexus.research.findings_memory import FindingsMemoryStore, FindingsCard

def direct_write(i):
    store = FindingsMemoryStore(Path("/Users/jameschen/Workspace/nexus"))
    card = FindingsCard(
        task_id="direct_test",
        id=str(uuid.uuid4()),
        kind="episodes",
        scope="task",
        title=f"Direct Test {i}",
        body="Core Logic Persistence Check",
        extra={"index": i}
    )
    path = store.write(card)
    return f"✅ Written: {path}"

def main():
    print("🚀 [Nexus-Core] Testing Direct Parallel Writing (No Sandboxes)...")
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(direct_write, i) for i in range(100)]
        for future in as_completed(futures):
            print(future.result())

if __name__ == "__main__":
    main()
