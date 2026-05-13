#!/usr/bin/env python3
import os
import time
import json
import shutil
import subprocess
import glob
from datetime import datetime

# Path Configuration
ROOT = os.getcwd()
PENDING_DIR = os.path.join(ROOT, ".nexus/agent_queue/tasks/pending")
RUNNING_DIR = os.path.join(ROOT, ".nexus/agent_queue/tasks/running")
DONE_DIR = os.path.join(ROOT, ".nexus/agent_queue/tasks/done")
FAILED_DIR = os.path.join(ROOT, ".nexus/agent_queue/tasks/failed")
LOG_FILE = os.path.join(ROOT, ".nexus/agent_queue/logs/gemini_worker.jsonl")
RESULTS_DIR = os.path.join(ROOT, ".nexus/agent_queue/results")

def latest_file(directory, pattern):
    files = glob.glob(os.path.join(directory, pattern))
    if not files:
        return ""
    return max(files, key=os.path.getmtime)

def latest_dir(directory, pattern):
    dirs = [path for path in glob.glob(os.path.join(directory, pattern)) if os.path.isdir(path)]
    if not dirs:
        return ""
    return max(dirs, key=os.path.getmtime)

def load_jsonl(path):
    if not path or not os.path.exists(path):
        return []
    rows = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows

def load_row_files(directory, pattern):
    if not directory or not os.path.isdir(directory):
        return []
    rows = []
    for path in sorted(glob.glob(os.path.join(directory, pattern))):
        try:
            with open(path, "r") as f:
                rows.append(json.load(f))
        except (OSError, json.JSONDecodeError):
            pass
    return rows

def arm_summary(rows):
    total = len(rows)
    verified_rows = [
        row for row in rows
        if row.get("run_eligible", True)
        and row.get("semantic_status") == "VERIFIED"
        and not row.get("report_trust_mismatch", False)
    ]
    def avg(key):
        if not rows:
            return 0
        return round(sum(float(row.get(key) or 0) for row in rows) / len(rows), 4)
    return {
        "verified": len(verified_rows),
        "total": total,
        "avg_wall_sec": avg("wall_duration_sec"),
        "avg_tokens": avg("total_tokens"),
        "avg_model_calls": avg("model_calls"),
    }

def log_event(event_type, run_id, message, extra=None):
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "type": event_type,
        "run_id": run_id,
        "message": message
    }
    if extra:
        log_entry.update(extra)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

def append_stdout(run_id, line):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    stdout_log = os.path.join(os.path.dirname(LOG_FILE), "worker_stdout.log")
    with open(stdout_log, "a") as f:
        f.write(f"[{datetime.now().isoformat()}][{run_id}] {line}\n")

def run_task(task_path):
    try:
        with open(task_path, "r") as f:
            task = json.load(f)
    except Exception as e:
        print(f"Failed to read task {task_path}: {e}")
        os.makedirs(FAILED_DIR, exist_ok=True)
        shutil.move(task_path, os.path.join(FAILED_DIR, os.path.basename(task_path)))
        return

    run_id = task.get("run_id") or task.get("task_id") or os.path.splitext(os.path.basename(task_path))[0]
    task_file = task.get("task_file")
    output_dir = task.get("output_dir", f".nexus/reports/{run_id}")
    max_tasks = task.get("max_tasks", 4)
    repeat_trials = task.get("repeat_trials", 1)
    fail_fast = bool(task.get("fail_fast", False))
    env_vars = task.get("env", {})
    args = task.get("args", [])
    task_cmd = task.get("cmd")
    
    # Move to running
    os.makedirs(RUNNING_DIR, exist_ok=True)
    running_path = os.path.join(RUNNING_DIR, os.path.basename(task_path))
    shutil.move(task_path, running_path)
    
    log_event("START", run_id, f"Starting task {run_id}")
    
    # Resolve output_dir relative to ROOT if not absolute
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(ROOT, output_dir)
    os.makedirs(output_dir, exist_ok=True)

    if task_cmd:
        cmd = [str(part) for part in task_cmd]
    else:
        if not task_file:
            raise ValueError("task_file is required when cmd is not provided")
        cmd = [
            "uv", "run", "python", "scripts/bench/capability_ab_runner.py",
            "--tasks-file", task_file,
            "--output-dir", output_dir,
            "--max-tasks", str(max_tasks),
            "--repeat-trials", str(repeat_trials),
            "--timeout-sec", "300",
            "--total-timeout-sec", "3600",
            "--stop-loss-sec", "3600",
            "--per-task-stop-loss-sec", "600"
        ] + args
    
    # Setup environment
    current_env = os.environ.copy()
    current_env.update({k: str(v) for k, v in env_vars.items()})
    
    try:
        log_event("CMD", run_id, " ".join(cmd), {"output_dir": output_dir})
        process = subprocess.Popen(
            cmd,
            env=current_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            cwd=ROOT
        )
        log_event("PID", run_id, f"Subprocess pid {process.pid}")
        
        fail_fast_triggered = False
        failed_task_id = ""
        for line in process.stdout:
            line_str = line.strip()
            append_stdout(run_id, line_str)
            try:
                event_payload = json.loads(line_str)
            except json.JSONDecodeError:
                event_payload = {}
            if (
                fail_fast
                and event_payload.get("event") == "task_end"
                and event_payload.get("mode") == "with_nexus"
                and event_payload.get("status") != "SUCCESS"
            ):
                fail_fast_triggered = True
                failed_task_id = str(event_payload.get("task_id") or "")
                log_event("FAIL_FAST", run_id, f"with_nexus failed on {failed_task_id}", event_payload)
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                break
            if any(kw in line_str.lower() for kw in ["verified", "failed", "verified:", "failed:", "error:"]):
                 log_event("PROGRESS", run_id, line_str)
            print(f"[{run_id}] {line_str}")
        
        process.wait()
        return_code = process.returncode
        
        if fail_fast_triggered:
            status = "FAILED"
            dest_dir = FAILED_DIR
        elif return_code == 0:
            status = "SUCCESS"
            dest_dir = DONE_DIR
        else:
            status = "FAILED"
            dest_dir = FAILED_DIR
            
        # Write results
        task_results_dir = os.path.join(RESULTS_DIR, run_id)
        os.makedirs(task_results_dir, exist_ok=True)
        
        evidence_bundle = os.path.join(output_dir, "evidence_bundle.json")
        evidence_dir = latest_dir(output_dir, "evidence_*")
        with_nexus_src = latest_file(output_dir, "with_nexus_*.jsonl")
        without_nexus_src = latest_file(output_dir, "without_nexus_*.jsonl")
        with_rows = load_jsonl(with_nexus_src)
        without_rows = load_jsonl(without_nexus_src)
        if not with_rows:
            with_rows = load_row_files(evidence_dir, "with_nexus__*.row.json")
        if not without_rows:
            without_rows = load_row_files(evidence_dir, "without_nexus__*.row.json")

        if os.path.exists(evidence_bundle) or with_rows or without_rows:
            summary = {
                "schema": "nexus_gemini_bench_summary_v1",
                "run_id": run_id,
                "status": status,
                "model": task.get("model"),
                "task_file": task_file,
                "output_dir": output_dir,
                "evidence_bundle": evidence_bundle if os.path.exists(evidence_bundle) else "",
                "evidence_dir": evidence_dir,
                "with_nexus": arm_summary(with_rows),
                "without_nexus": arm_summary(without_rows),
                "fail_fast_triggered": fail_fast_triggered,
                "failed_task_id": failed_task_id,
                "root_cause": f"with_nexus failed on {failed_task_id}" if fail_fast_triggered else "",
                "blocked_reason": "fail_fast" if fail_fast_triggered else ""
            }
        else:
            summary = {
                "schema": "nexus_gemini_bench_summary_v1",
                "run_id": run_id,
                "status": status,
                "model": task.get("model"),
                "task_file": task_file,
                "output_dir": output_dir,
                "evidence_bundle": "",
                "evidence_dir": evidence_dir,
                "with_nexus": {},
                "without_nexus": {},
                "fail_fast_triggered": fail_fast_triggered,
                "failed_task_id": failed_task_id,
                "root_cause": "Summary file not found",
                "blocked_reason": "Runner did not produce run_summary.json" if return_code == 0 else "Runner exited with error"
            }
            
        with open(os.path.join(task_results_dir, "summary.json"), "w") as f:
            json.dump(summary, f, indent=2)
            
        if os.path.exists(with_nexus_src):
            shutil.copy(with_nexus_src, os.path.join(task_results_dir, "with_nexus.jsonl"))
        if os.path.exists(without_nexus_src):
            shutil.copy(without_nexus_src, os.path.join(task_results_dir, "without_nexus.jsonl"))
            
        # Move task file
        os.makedirs(dest_dir, exist_ok=True)
        shutil.move(running_path, os.path.join(dest_dir, os.path.basename(task_path)))
        
        log_event("END", run_id, f"Task {run_id} finished with status {status}")

    except Exception as e:
        log_event("ERROR", run_id, str(e))
        failed_task_path = os.path.join(FAILED_DIR, os.path.basename(task_path))
        os.makedirs(FAILED_DIR, exist_ok=True)
        if os.path.exists(running_path):
            shutil.move(running_path, failed_task_path)
        
        task_results_dir = os.path.join(RESULTS_DIR, run_id)
        os.makedirs(task_results_dir, exist_ok=True)
        summary = {
            "schema": "nexus_gemini_bench_summary_v1",
            "run_id": run_id,
            "status": "FAILED",
            "root_cause": str(e),
            "blocked_reason": "Internal worker error"
        }
        with open(os.path.join(task_results_dir, "summary.json"), "w") as f:
            json.dump(summary, f, indent=2)

def main_loop():
    print(f"Gemini Worker Loop started. Monitoring {PENDING_DIR}")
    while True:
        tasks = glob.glob(os.path.join(PENDING_DIR, "*.json"))
        if tasks:
            tasks.sort(key=os.path.getmtime)
            run_task(tasks[0])
        else:
            time.sleep(10)

if __name__ == "__main__":
    main_loop()
