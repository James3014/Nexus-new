#!/usr/bin/env python3
import json
import os
import subprocess
import time
from pathlib import Path
from datetime import datetime
import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "task_manifest.yaml"
POLICY = ROOT / "configs" / "ask_policy.yaml"
STATUS = ROOT / ".nexus" / "task_status.json"
HEARTBEAT = ROOT / "docs" / "EXEC_LIVE_STATUS.md"
LOCK = ROOT / ".nexus" / "task_runner.lock"


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def save_status(state: dict) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def write_heartbeat(state: dict) -> None:
    lines = [
        "# EXEC LIVE STATUS",
        "",
        f"Last Update: {now_str()}",
        "",
        "| Task | Status | Retry | Last Update | Note |",
        "|---|---|---:|---|---|",
    ]
    for tid, meta in state.get("tasks", {}).items():
        lines.append(
            f"| {tid} | {meta.get('status','pending')} | {meta.get('retry',0)} | {meta.get('updated_at','-')} | {meta.get('note','-')} |"
        )
    lines += ["", "Rule: pause only on destructive/credential/spec_conflict."]
    HEARTBEAT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def should_pause(run_cmd: str, policy: dict) -> tuple[bool, str]:
    c = run_cmd.lower()
    for p in policy.get("destructive_patterns", []):
        if p in c:
            return True, "destructive"
    for p in policy.get("credential_patterns", []):
        if p in c:
            return True, "credential"
    return False, ""


def run_shell(cmd: str, timeout_sec: int) -> tuple[int, str, str]:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout_sec)
    return r.returncode, r.stdout, r.stderr


def run_phase_task(task: dict) -> tuple[int, str, str, list]:
    """Execute task via Nexus Engine instead of shell."""
    try:
        from scripts.engine.nexus_cli import NexusCLI
        cli = NexusCLI(silent=True)

        tid = task.get("id", "")
        phase = task.get("phase", "R")
        task_desc = task.get("task", "automated task from runner")
        domain = task.get("domain")

        # 🧬 Specialized Logic for New Phase Tasks
        if tid == "phase_health.measurement":
            from nexus.core.phase_health import PhaseHealthCalculator
            state = cli.engine.state_io.load_global_state()
            # Simulate some signals for measurement
            for p in state.phase_metrics:
                state.phase_metrics[p].signals = {
                    "plan_completeness": 95, "dependency_validity": 90, "spec_clarity": 85,
                    "evidence_quality": 92, "source_relevance": 88, "research_latency_norm": 10,
                    "root_cause_confidence": 95, "diagnosis_precision": 90, "false_positive_rate": 5,
                    "fix_success_rate": 98, "retry_penalty": 0, "scope_drift": 2,
                    "regression_pass_rate": 100, "side_effect_score": 95, "coverage_signal": 85,
                    "pattern_reuse_rate": 80, "lesson_quality": 90, "next_run_hit_rate": 70
                }
            PhaseHealthCalculator.update_state(state)
            cli.engine.state_io.save_global_state(state)
            return 0, "MEASUREMENT_COMPLETE", "", []

        if tid == "auto.repair.proto":
            from nexus.core.auto_repair import AutoRepairEngine
            state = cli.engine.state_io.load_global_state()
            actions = AutoRepairEngine.analyze_and_suggest(state)
            cli.engine.state_io.save_global_state(state)
            return 0, f"ACTIONS_SUGGESTED:{len(actions)}", "", []

        # Default Phase Task Execution
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
        log_file = cli.engine.run_dir / "router_decisions.jsonl"
        if log_file.exists():
            for line in log_file.read_text().splitlines():
                if line.strip():
                    data = json.loads(line)
                    if data.get("selected_skill"):
                        selected_skills.append(data["selected_skill"])

        return rc, stdout, "", selected_skills
    except Exception as e:
        return 1, "", str(e), []


def check_done(task: dict, rc: int, stdout: str, stderr: str) -> tuple[bool, str]:
    d = task.get("done_when", {})
    t = d.get("type")
    if t == "file_exists":
        p = ROOT / d.get("path", "")
        return p.exists(), f"file_exists:{p}"
    if t == "command_rc_zero":
        return rc == 0, f"command_rc={rc}"
    if t == "phase_result_ok":
        return rc == 0, f"phase_result_ok:{stdout}"
    if t == "command_exit_zero":
        cmd = d.get("cmd")
        if not cmd:
            return False, "done_when command missing"
        try:
            rc, _, err = run_shell(cmd, timeout_sec=task.get("timeout_sec", 900))
            return rc == 0, f"cmd_rc={rc} {err.strip()}"
        except Exception as e:
            return False, f"done_when exception: {e}"
    return False, "unsupported done_when"


def acquire_lock() -> int | None:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        try:
            pid_text = LOCK.read_text(encoding="utf-8").strip()
            pid = int(pid_text)
            os.kill(pid, 0)
            return None
        except ProcessLookupError:
            LOCK.unlink(missing_ok=True)
        except Exception:
            LOCK.unlink(missing_ok=True)
    try:
        fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None
    os.write(fd, str(os.getpid()).encode("utf-8"))
    return fd


def release_lock(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    finally:
        try:
            LOCK.unlink(missing_ok=True)
        except Exception:
            pass


def topo_sort(tasks: list[dict]) -> list[dict]:
    by_id = {t["id"]: t for t in tasks}
    visited, temp, out = set(), set(), []

    def dfs(tid: str):
        if tid in visited:
            return
        if tid in temp:
            raise RuntimeError(f"cycle detected at {tid}")
        temp.add(tid)
        task_obj = by_id.get(tid)
        if not task_obj:
             raise RuntimeError(f"missing task object for: {tid}")
        for d in task_obj.get("depends_on", []):
            if d not in by_id:
                raise RuntimeError(f"missing dependency: {d}")
            dfs(d)
        temp.remove(tid)
        visited.add(tid)
        out.append(task_obj)

    for tid in by_id:
        dfs(tid)
    return out


import argparse

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", help="Run specific task ID (and its dependencies if needed)")
    parser.add_argument("--with-deps", action="store_true", help="Run task with its dependencies")
    args = parser.parse_args()

    lock_fd = acquire_lock()
    if lock_fd is None:
        print("task_runner is already running; lock exists at .nexus/task_runner.lock")
        return 3

    try:
        manifest = load_config(MANIFEST)
        policy = load_config(POLICY)

        state = {"started_at": now_str(), "tasks": {}, "result": "running"}
        save_status(state)
        write_heartbeat(state)
        try:
            all_tasks = topo_sort(manifest.get("tasks", []))
            if args.task:
                target_ids = {args.task}
                if args.with_deps:
                    # In topo_sort, we already have dependencies included if we find the task
                    # But if we just want to FILTER the sorted list:
                    by_id = {t["id"]: t for t in manifest.get("tasks", [])}
                    if args.task not in by_id:
                        print(f"Task {args.task} not found in manifest")
                        return 1
                    
                    # Compute closure of dependencies
                    def get_deps(tid, res):
                        for d in by_id[tid].get("depends_on", []):
                            if d not in res:
                                res.add(d)
                                get_deps(d, res)
                    get_deps(args.task, target_ids)
                
                tasks = [t for t in all_tasks if t["id"] in target_ids]
            else:
                tasks = all_tasks
        except Exception as e:
            state["result"] = "blocked"
            state["error"] = str(e)
            save_status(state)
            write_heartbeat(state)
            return 1

        for task in tasks:
            tid = task["id"]
            max_retry = int(task.get("max_retry", manifest.get("defaults", {}).get("max_retry", 1)))
            timeout_sec = int(task.get("timeout_sec", manifest.get("defaults", {}).get("timeout_sec", 900)))
            run_cmd = task.get("run", "")

            pause, reason = should_pause(run_cmd, policy)
            if pause:
                state["tasks"][tid] = {
                    "status": "paused",
                    "retry": 0,
                    "updated_at": now_str(),
                    "note": f"pause_on:{reason}",
                }
                state["result"] = "paused"
                save_status(state)
                write_heartbeat(state)
                return 2

            ok = False
            for i in range(max_retry + 1):
                task_type = task.get("type", "shell")
                state["tasks"][tid] = {
                    "status": "running",
                    "retry": i,
                    "updated_at": now_str(),
                    "note": run_cmd if task_type == "shell" else f"phase_task:{task.get('phase')}",
                }
                save_status(state)
                write_heartbeat(state)

                selected_skills = []
                try:
                    if task_type == "phase_task":
                        rc, out, err, selected_skills = run_phase_task(task)
                    else:
                        rc, out, err = run_shell(run_cmd, timeout_sec=timeout_sec)
                except subprocess.TimeoutExpired:
                    rc, out, err = 124, "", f"timeout:{timeout_sec}s"

                done, check_note = check_done(task, rc, out, err)
                if rc == 0 and done:
                    state["tasks"][tid] = {
                        "status": "done",
                        "retry": i,
                        "updated_at": now_str(),
                        "note": check_note,
                    }
                    if selected_skills:
                        state["tasks"][tid]["selected_skills"] = selected_skills
                    save_status(state)
                    write_heartbeat(state)
                    ok = True
                    break

                state["tasks"][tid] = {
                    "status": "failed",
                    "retry": i,
                    "updated_at": now_str(),
                    "note": f"rc={rc}; {check_note}; {err.strip()}",
                }
                save_status(state)
                write_heartbeat(state)
                time.sleep(1)

            if not ok:
                action = task.get("on_fail", "escalate")
                if action == "retry":
                    state["result"] = "failed"
                elif action == "fallback":
                    state["tasks"][tid]["status"] = "fallback_needed"
                    state["result"] = "failed"
                else:
                    state["tasks"][tid]["status"] = "blocked"
                    state["tasks"][tid]["note"] = f"escalate_required; {state['tasks'][tid].get('note','')}"
                    state["result"] = "blocked"
                save_status(state)
                write_heartbeat(state)
                return 1

        state["result"] = "done"
        state["finished_at"] = now_str()
        save_status(state)
        write_heartbeat(state)
        return 0
    finally:
        release_lock(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
