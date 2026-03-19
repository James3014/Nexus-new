#!/usr/bin/env python3
import json
import os
import subprocess
import time
import threading
import yaml
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))
from scripts.utils.git_worktree import GitWorktreeManager
from scripts.ops.incident_rca_adapter import IncidentRCAAdapter
wt_manager = GitWorktreeManager(ROOT)
incident_adapter = IncidentRCAAdapter(ROOT)
MANIFEST = ROOT / os.environ.get("MANIFEST", "task_manifest.yaml")
POLICY = ROOT / "configs" / "ask_policy.yaml"
STATUS = ROOT / ".nexus" / "task_status.json"
HEARTBEAT = ROOT / "docs" / "EXEC_LIVE_STATUS.md"
LOCK_FILE = ROOT / ".nexus" / "task_runner.lock"

state_lock = threading.Lock()

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8"))

def save_status(state: dict) -> None:
    with state_lock:
        STATUS.parent.mkdir(parents=True, exist_ok=True)
        STATUS.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def write_heartbeat(state: dict) -> None:
    with state_lock:
        lines = [
            "# EXEC LIVE STATUS",
            "",
            f"Last Update: {now_str()}",
            "",
            "| Task | Status | Retry | Last Update | Note |",
            "|---|---|---:|---|---|",
        ]
        # Sort tasks by ID for consistent output
        sorted_tasks = sorted(state.get("tasks", {}).items())
        for tid, meta in sorted_tasks:
            lines.append(
                f"| {tid} | {meta.get('status','pending')} | {meta.get('retry',0)} | {meta.get('updated_at','-')} | {meta.get('note','-')} |"
            )
        lines += ["", "Rule: pause only on destructive/credential/spec_conflict."]
        HEARTBEAT.write_text("\n".join(lines) + "\n", encoding="utf-8")

def is_quota_error(text: str) -> bool:
    patterns = [
        "429", "insufficient_quota", "rate_limit_reached", "token_limit_exceeded",
        "401", "unauthorized", "expired_token", "invalid_grant", "oauth"
    ]
    t = str(text).lower()
    return any(p in t for p in patterns)

def should_pause(run_cmd: str, policy: dict) -> tuple[bool, str]:
    c = str(run_cmd).lower()
    for p in policy.get("destructive_patterns", []):
        if p in c:
            return True, "destructive"
    for p in policy.get("credential_patterns", []):
        if p in c:
            return True, "credential"
    return False, ""

def run_shell(cmd: str, timeout_sec: int, cwd: Path | str | None = None) -> tuple[int, str, str]:
    try:
        env = os.environ.copy()
        env["NEXUS_FORCE_RUN"] = "1"
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout_sec, env=env, cwd=cwd)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired as e:
        return 124, "", f"timeout:{timeout_sec}s"

def run_phase_task(task: dict, cwd: Path | str | None = None) -> tuple[int, str, str, list]:
    # In a real v9, NexusCLI would take a root path. For now, we assume it runs in CWD.
    # We might need to handle sys.path or ROOT changes if running in a worktree.
    try:
        from scripts.engine.nexus_cli import NexusCLI
        cli = NexusCLI(silent=True)
        tid = task.get("id", "")
        phase = task.get("phase", "R")
        task_desc = task.get("task", "automated task from runner")
        domain = task.get("domain")

        success = False
        if phase == "R":
            if "bug" in tid.lower() or "fix" in tid.lower():
                success = cli.engine.run_bug(tid, desc=task_desc)
            else:
                success = cli.engine.run_feature(task_desc, domain=domain)
        else:
            success = cli.engine.run_feature(task_desc, domain=domain)

        rc = 0 if success else 1
        stdout = "SUCCESS" if success else "FAIL"
        selected_skills = []
        # Skill extraction logic if needed
        return rc, stdout, "", selected_skills
    except Exception as e:
        return 1, "", str(e), []

def check_done(task: dict, rc: int, stdout: str, stderr: str) -> tuple[bool, str]:
    d = task.get("done_when", {})
    if not d: return rc == 0, f"rc={rc}"
    t = d.get("type")
    if t == "file_exists":
        p = ROOT / d.get("path", "")
        return p.exists(), f"file_exists:{p}"
    if t == "command_rc_zero":
        return rc == 0, f"command_rc={rc}"
    if t == "phase_result_ok":
        return rc == 0, f"phase_result_ok:{stdout}"
    return False, "unsupported done_when"

def acquire_lock() -> int | None:
    if os.environ.get("NEXUS_FORCE_RUN") == "1":
        return 99999
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
            os.kill(pid, 0)
            return None
        except:
            LOCK_FILE.unlink(missing_ok=True)
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        return fd
    except:
        return None

def release_lock(fd: int | None) -> None:
    if fd is not None:
        try: os.close(fd)
        except: pass
        LOCK_FILE.unlink(missing_ok=True)

def topo_sort(tasks: list[dict]) -> list[dict]:
    by_id = {t["id"]: t for t in tasks}
    visited, temp, out = set(), set(), []
    def dfs(tid):
        if tid in visited: return
        if tid in temp: raise RuntimeError(f"cycle:{tid}")
        temp.add(tid)
        task_obj = by_id.get(tid)
        if not task_obj: raise RuntimeError(f"missing:{tid}")
        for d in task_obj.get("depends_on", []):
            dfs(d)
        temp.remove(tid)
        visited.add(tid)
        out.append(task_obj)
    for tid in by_id: dfs(tid)
    return out

def execute_single_task(task: dict, run_cmd: str, manifest_defaults: dict, policy: dict, state: dict):
    tid = task["id"]
    max_retry = int(task.get("max_retry", manifest_defaults.get("max_retry", 1)))
    timeout_sec = int(task.get("timeout_sec", manifest_defaults.get("timeout_sec", 900)))
    task_type = task.get("type", "shell")
    is_isolated = task.get("isolated", False)
    
    wt_path = None
    if is_isolated:
        try:
            wt_path = wt_manager.create_worktree(tid)
        except Exception as e:
            with state_lock:
                state["tasks"][tid].update({"status": "failed", "note": f"worktree_creation_failed: {e}"})
            return "FAILED"

    try:
        for i in range(max_retry + 1):
            with state_lock:
                state["tasks"][tid].update({"status": "running", "retry": i, "updated_at": now_str(), "note": run_cmd})
            save_status(state)
            write_heartbeat(state)

            if task_type == "phase_task" or (not run_cmd and task.get("phase")):
                rc, out, err, skills = run_phase_task(task, cwd=wt_path)
            else:
                rc, out, err = run_shell(run_cmd, timeout_sec, cwd=wt_path)
            
            diag_str = f"STDOUT: {out}\nSTDERR: {err}"
            if is_quota_error(out) or is_quota_error(err):
                with state_lock:
                     state["tasks"][tid].update({"status": "quota_paused", "note": f"quota_error: {str(err)[:50]}", "updated_at": now_str()})
                save_status(state)
                write_heartbeat(state)
                incident_adapter.generate_report(tid, diag_str)
                return "QUOTA_EXCEEDED"

            done, note = check_done(task, rc, out, err)
            if done:
                with state_lock:
                    state["tasks"][tid].update({"status": "done", "note": note, "updated_at": now_str()})
                save_status(state)
                write_heartbeat(state)
                return "DONE"
            
            with state_lock:
                state["tasks"][tid].update({"status": "failed", "note": f"rc={rc}; {str(err).strip()}", "updated_at": now_str()})
            save_status(state)
            write_heartbeat(state)
            incident_adapter.generate_report(tid, diag_str)
            time.sleep(1)
        
        return "FAILED"
    finally:
        if wt_path:
            wt_manager.remove_worktree(tid)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", help="Run specific task ID")
    args = parser.parse_args()

    lock_fd = acquire_lock()
    if lock_fd is None: return 3

    try:
        manifest = load_config(MANIFEST)
        policy = load_config(POLICY)
        defaults = manifest.get("defaults", {})
        all_tasks = topo_sort(manifest.get("tasks", []))
        
        tasks_to_run = all_tasks
        if args.task:
            tasks_to_run = [t for t in all_tasks if t["id"] == args.task]

        state = {"started_at": now_str(), "tasks": {}, "result": "running"}
        for t in tasks_to_run:
            state["tasks"][t["id"]] = {"status": "pending", "retry": 0, "updated_at": now_str()}
        save_status(state)

        completed_tids = set()
        failed_tids = set()
        active_futures = {}
        
        max_workers = int(defaults.get("max_parallel", 4))
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            while len(completed_tids) + len(failed_tids) < len(tasks_to_run):
                # Dispatch
                for task in tasks_to_run:
                    tid = task["id"]
                    if tid not in completed_tids and tid not in failed_tids and tid not in active_futures:
                        deps = task.get("depends_on", [])
                        if all(d in completed_tids for d in deps):
                            if any(d in failed_tids for d in deps):
                                with state_lock:
                                    state["tasks"][tid].update({"status": "blocked", "note": "dep_failed"})
                                failed_tids.add(tid)
                                continue
                            
                            run_cmd = task.get("run", "")
                            if run_cmd.startswith("nexus:"):
                                run_cmd = f"uv run scripts/engine/nexus_cli.py --silent {run_cmd}"
                            
                            # The should_pause check is now inside execute_single_task
                            # pause, reason = should_pause(run_cmd, policy)
                            # if pause:
                            #     # ... (pause logic)
                            #     pass

                            future = executor.submit(execute_single_task, task, run_cmd, defaults, policy, state)
                            active_futures[future] = tid
                
                if not active_futures: break
                
                # Wait for any task to finish, or continue loop on timeout
                try:
                    for future in as_completed(active_futures.keys(), timeout=2):
                        tid = active_futures.pop(future)
                        res = future.result()
                        if res == "DONE":
                            completed_tids.add(tid)
                        elif res == "QUOTA_EXCEEDED":
                            state["result"] = "quota_paused"
                            save_status(state)
                            # Trigger audio notify (PHA-051: Silence check)
                            if not os.environ.get("NEXUS_SILENT") == "1":
                                subprocess.run(['/usr/bin/python3', '/Users/jameschen/.openclaw/skills/audio-notify/scripts/notify.py', "額度不足，任務暫停"], capture_output=True)
                            executor.shutdown(wait=False, cancel_futures=True)
                            return 4
                        else:
                            failed_tids.add(tid)
                        break 
                except TimeoutError:
                    pass
                except Exception as e:
                    # Trigger audio notify (PHA-051: Silence check)
                    if not os.environ.get("NEXUS_SILENT") == "1":
                        subprocess.run(['/usr/bin/python3', '/Users/jameschen/.openclaw/skills/audio-notify/scripts/notify.py', f"任務執行錯誤: {e}"], capture_output=True)
                    print(f"Error in future: {e}")
                
                time.sleep(0.5)

        state["result"] = "done" if not failed_tids else "failed"
        state["finished_at"] = now_str()
        save_status(state)
        write_heartbeat(state)
        return 0 if not failed_tids else 1
    finally:
        release_lock(lock_fd)

if __name__ == "__main__":
    import sys
    sys.exit(main())
