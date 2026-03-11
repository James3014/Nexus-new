#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path
from typing import List, NamedTuple, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed


def run_cmd(cmd: List[str], cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def get_base_branch() -> str:
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True
        ).strip()
        if branch != "HEAD":
            return branch
        remote = subprocess.check_output(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"], text=True
        ).strip()
        return remote.split("/")[-1]
    except Exception:
        try:
            result = subprocess.check_output(
                ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/"],
                text=True
            ).strip().split("\n")
            return result[0] if result else "main"
        except Exception:
            return "main"


def in_merge_conflict(cwd: str) -> bool:
    return run_cmd(["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=cwd).returncode == 0


def cleanup_worker(project_root: str, work_path: str, branch: str) -> None:
    run_cmd(["git", "worktree", "remove", work_path, "--force"], cwd=project_root)
    run_cmd(["git", "branch", "-D", branch], cwd=project_root)


class WorkerResult(NamedTuple):
    index: int
    subtask: str
    branch: Optional[str]
    path: Optional[str]
    error: Optional[str]


def process_subtask(
    i: int,
    sub: str,
    project_root: str,
    project_name: str,
    base_branch: str,
    task_desc: str
) -> WorkerResult:
    safe_sub = "".join(c if c.isalnum() else "_" for c in sub)
    pid = os.getpid()
    work_name = f"{project_name}_fix_{safe_sub}_{pid}_{i}"
    work_path = f"/tmp/{work_name}"
    branch_name = f"parallel/fix_{safe_sub}_{pid}_{i}"

    print(f"[Worker #{i+1}] Preparing: {sub}")

    run_cmd(["git", "worktree", "remove", work_path, "--force"], cwd=project_root)
    run_cmd(["git", "branch", "-D", branch_name], cwd=project_root)

    res = run_cmd(
        ["git", "worktree", "add", "-b", branch_name, work_path, base_branch],
        cwd=project_root
    )
    if res.returncode != 0:
        return WorkerResult(i, sub, None, None, f"Worktree fail: {res.stderr.strip()}")

    try:
        with open(Path(work_path) / ".fix_log", "w") as f:
            f.write(f"Task: {task_desc}\nSubtask: {sub}\n")

        check = subprocess.run(
            # Stage first, then verify, then re-stage any codex-loop edits before commit
            "git add . && codex-loop && git add .",
            shell=True, cwd=work_path, capture_output=True, text=True
        )
        if check.returncode != 0:
            cleanup_worker(project_root, work_path, branch_name)
            error_msg = f"Codex-Loop rejected (Code: {check.returncode})"
            if check.stdout:
                print(f"[Worker #{i+1}] Output: {check.stdout.strip()}")
            return WorkerResult(i, sub, None, None, error_msg)

        # 把自動產生的 .fix_log 從 staging 區拔除，避免污染 commit 與產生 merge conflict
        run_cmd(["git", "rm", "--cached", ".fix_log", "--ignore-unmatch"], cwd=work_path)

        # 🛡️ 空提交防護：如果拔除 .fix_log 後沒有任何 staged 變更，代表這是一個空任務
        staged_check = run_cmd(
            ["git", "diff", "--staged", "--name-only", "--diff-filter=ACMRD"],
            cwd=work_path
        )
        staged_files = staged_check.stdout.splitlines()

        if not staged_files:
            cleanup_worker(project_root, work_path, branch_name)
            return WorkerResult(
                i, sub, None, None,
                "空提交防護觸發：Staged 變更為零。沒有實質任務寫入。"
                " 請確保 Agent 實際進入 Worktree 完成修復任務後再執行 parallel_fix 收割。"
            )

        commit = run_cmd(
            ["git", "commit", "-m", f"feat(parallel): {sub} for {task_desc}"],
            cwd=work_path
        )
        if commit.returncode != 0:
            cleanup_worker(project_root, work_path, branch_name)
            return WorkerResult(i, sub, None, None, f"Commit failed: {commit.stderr.strip()}")

        return WorkerResult(i, sub, branch_name, work_path, None)
    except Exception as e:
        cleanup_worker(project_root, work_path, branch_name)
        return WorkerResult(i, sub, None, None, str(e))


def parallel_fix(task_desc: str, sub_tasks: Optional[List[str]] = None) -> int:
    try:
        project_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], text=True
        ).strip()
    except Exception:
        print("Error: Not in a Git repository.")
        return 1

    project_name = Path(project_root).name
    base_branch = get_base_branch()
    subs = sub_tasks if sub_tasks else ["part_1", "part_2"]

    print(f"[Parallel-Fix] Task: {task_desc}")
    print(f"[Parallel-Fix] Base: {base_branch} | Workers: {len(subs)}")

    results: List[WorkerResult] = []
    has_worker_failure = False
    with ThreadPoolExecutor(max_workers=len(subs)) as executor:
        futures = {
            executor.submit(
                process_subtask, i, sub, project_root, project_name, base_branch, task_desc
            ): sub
            for i, sub in enumerate(subs)
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if result.error:
                has_worker_failure = True
                print(f"[Worker] Failed ({result.subtask}): {result.error}")

    success_info = [(r.index, r.branch, r.path) for r in results if r.branch and r.path]

    if not success_info:
        print("[Harvest] No workers passed. Nothing to merge.")
        return 1

    # Deterministic merge order by original subtask index
    success_info.sort(key=lambda x: x[0])

    print(f"[Harvest] Merging {len(success_info)} verified branches...")
    merged_branches: Set[str] = set()
    harvest_success = True

    try:
        for _, branch, path in success_info:
            if in_merge_conflict(project_root):
                print("[Harvest] Merge conflict already active. Stopping harvest.")
                harvest_success = False
                break

            res = run_cmd(["git", "merge", branch, "--no-edit"], cwd=project_root)
            if res.returncode == 0:
                print(f"[Harvest] Merged: {branch}")
                merged_branches.add(branch)
                cleanup_worker(project_root, path, branch)
                continue

            print(f"[Harvest] Merge failed on {branch}.")
            harvest_success = False
            if in_merge_conflict(project_root):
                run_cmd(["git", "merge", "--abort"], cwd=project_root)
                print("[Harvest] Merge aborted to restore clean state.")
            break
    finally:
        print("[Cleanup] Pruning worktrees...")
        run_cmd(["git", "worktree", "prune"], cwd=project_root)
        for _, branch, path in success_info:
            if branch in merged_branches:
                if path and os.path.exists(path):
                    run_cmd(["git", "worktree", "remove", path, "--force"], cwd=project_root)
            else:
                print(f"[Cleanup] Keeping unmerged branch for recovery: {branch}")

    print("[Parallel-Fix] Completed.")
    return 0 if (not has_worker_failure and harvest_success) else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: parallel_fix.py '<task_description>' [subtask1,subtask2,...]")
        sys.exit(1)

    task = sys.argv[1].strip()
    sub_list: Optional[List[str]] = None
    if len(sys.argv) >= 3 and sys.argv[2].strip():
        sub_list = [s.strip() for s in sys.argv[2].split(",") if s.strip()]

    sys.exit(parallel_fix(task, sub_list))
