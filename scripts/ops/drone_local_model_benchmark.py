#!/usr/bin/env python3
import json
import time
from pathlib import Path
from typing import Dict
from nexus.core.drone_engine import TacticalDrone, LocalBonsaiBrain

def run_benchmark():
    project_root = Path(__file__).resolve().parent.parent.parent
    
    smoke_tasks = [
        "Create a file 'test1.txt' with content 'hello'",
        "Run 'echo success'",
        "Check if file exists using bash",
        "Write some python code to 'script.py'",
        "Fix a bug in 'script.py' by editing it",
        "Run 'ls -l' and mark DONE",
        "Mark task as DONE immediately",
        "Create a directory 'new_dir'",
        "Delete file 'old.txt'",
        "Append 'data' to 'log.txt'",
        "Compile the project",
        "Run tests",
        "Check system memory",
        "Create a React component",
        "Update the documentation",
        "Run 'pwd'",
        "Read a file and finish",
        "Just say hello and finish",
        "Install a dependency",
        "Check python version"
    ]
    
    total_tasks = len(smoke_tasks)
    legal_actions_tasks = 0
    total_action_step_count = 0
    legal_action_step_count = 0
    tool_success = 0
    false_success = 0
    invalid_actions_tasks = 0
    total_rounds = 0
    
    action_histogram = {"BASH": 0, "EDIT": 0, "DONE": 0, "UNKNOWN": 0}
    repair_applied_count = 0
    invalid_before_repair_count = 0
    invalid_after_repair_count = 0
    
    print(f"Starting Drone Local Model Benchmark on {total_tasks} tasks...")
    
    for i, task in enumerate(smoke_tasks):
        drone = TacticalDrone(f"benchmark-drone-{i}", project_root, max_rounds=3, timeout_sec=60)
        res = drone.sense_think_act(task)
        
        rounds = sum(1 for t in res["traces"] if t["phase"] == "THINK")
        total_rounds += rounds
        
        metrics = res.get("metrics", {})
        repair_applied_count += metrics.get("repair_applied_count", 0)
        invalid_before_repair_count += metrics.get("invalid_before_repair_count", 0)
        invalid_after_repair_count += metrics.get("invalid_after_repair_count", 0)
        
        current_task_actions = []
        for t in res["traces"]:
            if t["phase"] == "DECISION":
                raw_msg = t["message"]
                # Message is "{action}: {reasoning} (raw: {raw_action})"
                act = raw_msg.split(":")[0].strip()
                current_task_actions.append(act)
                
                if act not in action_histogram:
                    action_histogram[act] = 0
                action_histogram[act] += 1
                if act == "UNKNOWN":
                    pass
        
        task_step_count = len(current_task_actions)
        task_legal_step_count = sum(1 for a in current_task_actions if a in ["BASH", "EDIT", "DONE"])
        
        total_action_step_count += task_step_count
        legal_action_step_count += task_legal_step_count
        
        # Task is legal only if ALL its actions are in white-list
        if task_step_count > 0 and task_legal_step_count == task_step_count:
            legal_actions_tasks += 1
        else:
            invalid_actions_tasks += 1
            
        # 檢查 tool execution
        senses = [t for t in res["traces"] if t["phase"] == "SENSE" and ("Result" in t["message"] or "Sandbox" not in t["message"])]
        if senses:
            if any("'exit_code': 0" in s["message"] or "'status': 'SUCCESS'" in s["message"] for s in senses):
                tool_success += 1
                
        # 檢查 false success
        if res["outcome"] == "SUCCESS" and (task_legal_step_count < task_step_count or task_step_count == 0):
            false_success += 1
            
    legal_action_rate = legal_actions_tasks / total_tasks
    legal_action_step_rate = legal_action_step_count / total_action_step_count if total_action_step_count > 0 else 0
    tool_exec_success_rate = tool_success / total_tasks if total_tasks > 0 else 0
    avg_rounds = total_rounds / total_tasks
    
    report = {
        "timestamp": time.time(),
        "model_endpoint": "http://localhost:11435/completion",
        "total_tasks": total_tasks,
        "legal_actions_raw": legal_actions_tasks, # Task level
        "invalid_actions_raw": invalid_actions_tasks,
        "false_success_raw": false_success,
        "legal_action_step_count": legal_action_step_count,
        "total_action_step_count": total_action_step_count,
        "legal_action_rate": legal_action_rate, # Task level
        "legal_action_step_rate": legal_action_step_rate,
        "tool_success_raw": tool_success,
        "tool_exec_success_rate": tool_exec_success_rate,
        "false_success_count": false_success,
        "invalid_action_count": invalid_actions_tasks,
        "avg_rounds": avg_rounds,
        
        "action_histogram": action_histogram,
        "repair_applied_count": repair_applied_count,
        "invalid_before_repair_count": invalid_before_repair_count,
        "invalid_after_repair_count": invalid_after_repair_count
    }
    
    threshold_passed = True
    failure_reasons = []
    
    if legal_action_rate < 0.95:
        threshold_passed = False
        failure_reasons.append(f"legal_action_rate {legal_action_rate:.2f} < 0.95")
        
    if tool_exec_success_rate < 0.90:
        threshold_passed = False
        failure_reasons.append(f"tool_exec_success_rate {tool_exec_success_rate:.2f} < 0.90")
        
    report["threshold_passed"] = threshold_passed
    if not threshold_passed:
        report["failure_reasons"] = failure_reasons
    
    report_dir = project_root / ".nexus/reports/drone"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "local_model_benchmark.json"
    report_path.write_text(json.dumps(report, indent=2))
    
    print(f"Benchmark finished. Report saved to {report_path}")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    run_benchmark()
