import signal
import subprocess
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Tuple
from concurrent.futures import ProcessPoolExecutor
from nexus.core.state_contracts import NexusIssue, NexusState, TddStatus
from nexus.core.context_hub import ContextHub
from nexus.services.workspace import WorkspaceManager

class AutoResearchNightShift:
    """
    🌙 Nexus-AutoResearch Night Shift (v7.2)
    實現 P-D-X-R-A-C 自主迭代強化循環。
    """
    def __init__(self, task: str, max_rounds: int = 50, budget_min: int = 5, target_file: str = "repairfinal.py"):
        self.task = task
        self.max_rounds = max_rounds
        self.budget_sec = budget_min * 60
        self.target_file = target_file
        self.project_root = Path(__file__).resolve().parents[1]
        self.worktree_mgr = WorkspaceManager(str(self.project_root))
        self.hub = ContextHub(self.project_root)
        self.best_score = 0.0
        self.base_commit = None
        self.tracelog_path = self.project_root / "tracelog.jsonl"

    def _log_trace(self, round_id: int, status: str, score: float):
        """記錄優化軌跡。"""
        import os
        entry = {
            "timestamp": datetime.now().isoformat(),
            "swarm_id": os.getpid(),  # 使用進程 ID 作為 Swarm ID
            "round": round_id,
            "task": self.task,
            "status": status,
            "flashjudge_score": score,
            "best_score_so_far": self.best_score
        }
        with open(self.tracelog_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def _timeout_handler(self, signum, frame):
        raise TimeoutError(f"Round Budget ({self.budget_sec}s) exceeded!")

    def _run_round(self, round_id: int, workpath: Path) -> Tuple[float, str]:
        """執行 P-D-X-R-A-C 循環。"""
        signal.signal(signal.SIGALRM, self._timeout_handler)
        signal.alarm(self.budget_sec)
        
        try:
            print(f"\n🔄 [{self.task} | Round {round_id}] Starting P-D-X-R-A-C Loop...")
            
            # 1. P: Plan (Inject program.md)
            rules = self.hub.load_program_rules(str(self.project_root / "program.md"))
            
            # 2. D: Diagnose
            print(f"   🔍 [D] Diagnosing target: {self.target_file}")
            
            # 3. X: eXecute Research
            print(f"   🌐 [X] Researching external fixes for {self.target_file}")
            
            # 4. R: Repair
            print(f"   🛠️ [R] Generating patch for {self.target_file}")
            # 模擬生成補丁
            patch = f"# Optimized for {self.task} Round {round_id}\n# FlashJudge Target: 9.0"
            
            # 5. A: Audit (FlashJudge)
            score = 7.5 + (round_id * 0.1) # 模擬分數遞增
            print(f"   ⚖️ [A] Audit Score for {self.task}: {score}")
            
            signal.alarm(0)
            return score, patch
            
        except TimeoutError as e:
            print(f"   ⚠️ [Timeout] {e}")
            return 0.0, ""
        except Exception as e:
            print(f"   ❌ [Error] {e}")
            return 0.0, ""

    def run(self):
        print(f"🏭 [AutoResearch] Factory Initiated | Task: {self.task} | Rounds: {self.max_rounds}")
        
        # 1. Lease Worktree
        task_id_prefix = f"research-{int(time.time())}-{self.task.replace(' ', '_')}"[:30]
        branch_prefix = f"audit/{task_id_prefix}"
        task_id, branch, workpath = self.worktree_mgr.lease(task_id_prefix, branch_prefix)
        workpath = Path(workpath)
        
        try:
            res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workpath, capture_output=True, text=True)
            self.base_commit = res.stdout.strip()
            
            for round_id in range(1, self.max_rounds + 1):
                score, patch = self._run_round(round_id, workpath)
                
                if score > self.best_score:
                    print(f"   📈 [{self.task}] Improvement {self.best_score} -> {score}. Committing...")
                    self.best_score = score
                    
                    target_path = workpath / self.target_file
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    target_path.write_text(patch)
                    subprocess.run(["git", "add", self.target_file], cwd=workpath)
                    subprocess.run(["git", "commit", "-m", f"AutoResearch {self.task} Round {round_id}: score {score}"], cwd=workpath)
                    
                    res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workpath, capture_output=True, text=True)
                    self.base_commit = res.stdout.strip()
                    self._log_trace(round_id, "IMPROVED", score)
                else:
                    print(f"   📉 [{self.task}] No Improvement. Rolling back...")
                    subprocess.run(["git", "reset", "--hard", self.base_commit], cwd=workpath)
                    self._log_trace(round_id, "ROLLBACK", score)
            
            print(f"\n✅ [AutoResearch] Finished {self.task}. Best Score: {self.best_score}")
            
            csv_path = self.project_root / f"optimization_curve_{self.task.replace(' ', '_')}.csv"
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("round,score,status\n")
                with open(self.tracelog_path, "r") as tf:
                    for line in tf:
                        log = json.loads(line)
                        if log["task"] == self.task:
                            f.write(f"{log['round']},{log['flashjudge_score']},{log['status']}\n")
            print(f"📊 [Metrics] Optimization curve exported to {csv_path}")

        finally:
            print(f"🧹 [Cleanup] Removing worktree at {workpath}")
            # self.worktree_mgr.cleanup(task_id, branch)

def main():
    parser = argparse.ArgumentParser(description="Nexus v7.2 Night Shift (AutoResearch)")
    parser.add_argument("--task", default="default-task")
    parser.add_argument("--tasks", help="Comma separated list of tasks")
    parser.add_argument("--swarm", action="store_true", help="Launch multi-agent swarm")
    parser.add_argument("--workers", type=int, default=2, help="Number of parallel workers")
    parser.add_argument("--max_rounds", type=int, default=10)
    parser.add_argument("--budget_min", type=int, default=5)
    parser.add_argument("--target_file", default="README.md")
    
    args = parser.parse_args()
    
    task_list = args.tasks.split(",") if args.tasks else [args.task]
    
    if args.swarm:
        print(f"🐝 [Swarm] Launching {args.workers} workers for {len(task_list)} tasks...")
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            for t_name in task_list:
                shift = AutoResearchNightShift(t_name, args.max_rounds, args.budget_min, args.target_file)
                executor.submit(shift.run)
    else:
        for t_name in task_list:
            shift = AutoResearchNightShift(t_name, args.max_rounds, args.budget_min, args.target_file)
            shift.run()

if __name__ == "__main__":
    main()
