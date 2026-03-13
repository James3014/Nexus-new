#!/usr/bin/env python3
# 🛡️ Codex-Verified: Codex-Auth-Lvl13-Final (2026-03-03)
import subprocess
import concurrent.futures
import sys
import json
import time

OPENCLAW_BIN = "/Users/jameschen/.npm-global/bin/openclaw"

def spawn_single_agent(index, agent_name, prompt, base_session):
    """執行單個 Agent 任務並返回結果，使用獨立 Session 隔離"""
    session_id = f"{base_session}_idx_{index}"
    cmd = [
        OPENCLAW_BIN, "agent",
        "--agent", agent_name,
        "--session-id", session_id,
        "--message", prompt,
        "--json"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return {
            "index": index,
            "success": res.returncode == 0,
            "output": res.stdout,
            "error": res.stderr
        }
    except Exception as e:
        return {"index": index, "success": False, "error": str(e)}

def run_parallel_agents(tasks, session_prefix="parallel_spawn"):
    if not tasks: return []
    print(f"🚀 [Spawning Engine] 正在啟動 {len(tasks)} 個平行子代理 (Session 隔離模式)...")
    base_session = f"{session_prefix}_{int(time.time())}"
    
    results = [None] * len(tasks)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        future_to_index = {
            executor.submit(spawn_single_agent, i, t["agent"], t["prompt"], base_session): i 
            for i, t in enumerate(tasks)
        }
        for future in concurrent.futures.as_completed(future_to_index):
            res = future.result()
            results[res["index"]] = res # 嚴格按原始索引存放結果
            
    return results

if __name__ == "__main__":
    test_tasks = [{"agent": "main", "prompt": "test"}]
    print(run_parallel_agents(test_tasks))
