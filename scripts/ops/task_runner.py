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
from scripts.utils.pid_lock import acquire_lock, release_lock
from nexus.delivery.interactive import resolve_delivery_mode
from nexus.delivery.gate import evaluate_completion
from nexus.delivery.models import CompletionRequest, TaskLevel
from nexus.delivery.report import write_report_bundle
from nexus.core.task_graph import topo_sort
wt_manager = GitWorktreeManager(ROOT)
incident_adapter = IncidentRCAAdapter(ROOT)
MANIFEST = ROOT / os.environ.get("MANIFEST", "task_manifest.yaml")
POLICY = ROOT / "configs" / "ask_policy.yaml"
STATUS = ROOT / ".nexus" / "task_status.json"
HEARTBEAT = ROOT / "docs" / "EXEC_LIVE_STATUS.md"
LOCK_FILE = ROOT / ".nexus" / "task_runner.lock"
PHASE_SECTION_START = "<!-- NEXUS_PHASE_METRICS:START -->"
PHASE_SECTION_END = "<!-- NEXUS_PHASE_METRICS:END -->"

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
        preserved_phase_section = ""
        if HEARTBEAT.exists():
            existing = HEARTBEAT.read_text(encoding="utf-8")
            start = existing.find(PHASE_SECTION_START)
            end = existing.find(PHASE_SECTION_END)
            if start != -1 and end != -1 and end >= start:
                end = end + len(PHASE_SECTION_END)
                preserved_phase_section = existing[start:end].strip()

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
        if preserved_phase_section:
            lines += ["", preserved_phase_section]
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
                success = cli.service.execute_bug(
                    task_desc,
                    delivery_mode="standard",
                    bug_id=tid,
                )
            else:
                success = cli.service.execute_feature(
                    task_desc,
                    domain=domain,
                    delivery_mode="standard",
                )
        else:
            success = cli.service.execute_feature(
                task_desc,
                domain=domain,
                delivery_mode="standard",
            )

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


def run_completion_gate_for_task(
    task: dict,
    manifest_defaults: dict,
    cwd: Path | str | None = None,
) -> tuple[bool, str]:
    gate_cfg = task.get("completion_gate")
    gate_required = bool(
        task.get(
            "require_completion_gate",
            manifest_defaults.get("require_completion_gate", False),
        )
    )
    if not gate_cfg:
        if gate_required:
            return False, "completion_gate_missing"
        return True, "completion_gate_skipped"

    verify_commands = list(gate_cfg.get("verify_commands", []))
    if not verify_commands:
        return False, "completion_gate_missing_verify_commands"

    task_level = TaskLevel(gate_cfg.get("task_level", "small_fix"))
    artifact_paths = [
        Path(path)
        for path in gate_cfg.get("artifact_paths", task.get("evidence_paths", []))
    ]
    output_dir = Path(gate_cfg.get("output_dir", ROOT / "logs" / "delivery"))
    request = CompletionRequest(
        task_name=task["id"],
        task_level=task_level,
        verification_commands=verify_commands,
        artifact_paths=artifact_paths,
        cwd=Path(cwd) if cwd else ROOT,
    )
    result = evaluate_completion(request)
    write_report_bundle(result, output_dir)
    return result.gate_passed, result.status.value



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
                gate_passed, gate_note = run_completion_gate_for_task(
                    task,
                    manifest_defaults,
                    cwd=wt_path or ROOT,
                )
                if not gate_passed:
                    with state_lock:
                        state["tasks"][tid].update(
                            {
                                "status": "failed",
                                "note": f"completion_gate:{gate_note}",
                                "updated_at": now_str(),
                            }
                        )
                    save_status(state)
                    write_heartbeat(state)
                    incident_adapter.generate_report(tid, f"completion_gate:{gate_note}")
                    time.sleep(1)
                    continue
                with state_lock:
                    state["tasks"][tid].update(
                        {
                            "status": "done",
                            "note": f"{note}; completion_gate:{gate_note}",
                            "updated_at": now_str(),
                        }
                    )
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
    parser.add_argument("--with-deps", action="store_true", help="Run with recursive dependencies")
    parser.add_argument(
        "--delivery-mode",
        choices=["ask", "standard", "high"],
        default="ask",
        help="Choose whether task completion requires high-standard delivery verification.",
    )
    args = parser.parse_args()

    lock_fd = acquire_lock(LOCK_FILE)
    if lock_fd is None: return 3

    try:
        print(f"DEBUG: ROOT dir: {ROOT}")
        print(f"DEBUG: Loading MANIFEST from: {MANIFEST}")
        with open(MANIFEST, "r") as f:
            print(f"DEBUG: Manifest snippet: {f.read(100)}...")
        manifest = load_config(MANIFEST)
        policy = load_config(POLICY)
        defaults = dict(manifest.get("defaults", {}))
        delivery_mode = resolve_delivery_mode(args.delivery_mode)
        defaults["require_completion_gate"] = delivery_mode == "high"
        all_tasks = manifest.get("tasks", [])
        print(f"DEBUG: all_tasks count: {len(all_tasks)}")
        if all_tasks:
            print(f"DEBUG: first task ID: {all_tasks[0]['id']}")

        tasks_to_run = all_tasks
        if args.task:
            if args.with_deps:
                # 🧬 Recursive dependency resolution
                needed = set()
                def add_needed(tid):
                    if tid in needed: return
                    needed.add(tid)
                    t_obj = next((t for t in all_tasks if t["id"] == tid), None)
                    if t_obj:
                        for dep in t_obj.get("depends_on", []):
                            add_needed(dep)
                add_needed(args.task)
                tasks_to_run = [t for t in all_tasks if t["id"] in needed]
            else:
                tasks_to_run = [t for t in all_tasks if t["id"] == args.task]
        
        # Re-sort to maintain topo order after filtering
        print(f"DEBUG: tasks_to_run IDs: {[t['id'] for t in tasks_to_run]}")
        try:
            tasks_to_run = topo_sort(tasks_to_run)
        except Exception as e:
            print(f"❌ TopoSort Error: {e}")
            return 5

        state = {
            "started_at": now_str(),
            "tasks": {},
            "result": "running",
            "delivery_mode": delivery_mode,
        }
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
        try:
            optimize_cmd = [
                sys.executable,
                str(ROOT / "scripts" / "ops" / "skills_optimization_runner.py"),
                "--project-root",
                str(ROOT),
            ]
            subprocess.run(optimize_cmd, capture_output=True, text=True, check=False)
        except Exception:
            pass
        return 0 if not failed_tids else 1
    finally:
        release_lock(LOCK_FILE, lock_fd)

if __name__ == "__main__":
    import sys
    sys.exit(main())
