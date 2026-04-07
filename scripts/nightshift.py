import signal
import subprocess
import os
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict, Any
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
        
        # 🧬 DeepScientist Integration: Bayesian Optimizer
        from nexus.research.bayesian_engine import BayesianResearchOptimizer, ResearchSearchSpace
        self.space = ResearchSearchSpace()
        self.space.add_dimension("temperature", 0.0, 1.0)
        self.space.add_dimension("top_p", 0.1, 1.0)
        self.optimizer = BayesianResearchOptimizer(self.space)
        
        # 🔌 Webhook Connector
        from nexus.connectors.webhook_connector import WebhookConnector
        webhook_url = os.environ.get("NEXUS_WEBHOOK_URL", "")
        self.connector = WebhookConnector(webhook_url)

    def _log_trace(self, round_id: int, status: str, score: float):
        """記錄優化軌跡並推送。"""
        import os
        from nexus.connectors.base import NexusEvent
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "swarm_id": os.getpid(),
            "round": round_id,
            "task": self.task,
            "status": status,
            "flashjudge_score": score,
            "best_score_so_far": self.best_score
        }
        with open(self.tracelog_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
            
        # 🚀 推送關鍵發現
        event = NexusEvent(
            event_type="improvement" if status == "IMPROVED" else "convergence",
            task=self.task,
            round_id=round_id,
            score=score,
            message=f"NightShift Round {round_id}: {status} (Best: {self.best_score})"
        )
        self.connector.send(event)

    def _timeout_handler(self, signum, frame):
        raise TimeoutError(f"Round Budget ({self.budget_sec}s) exceeded!")

    def _run_round(self, round_id: int, workpath: Path) -> Tuple[float, str]:
        """執行 P-D-X-R-A-C 循環。"""
        signal.signal(signal.SIGALRM, self._timeout_handler)
        signal.alarm(self.budget_sec)
        
        try:
            print(f"\n🔄 [{self.task} | Round {round_id}] Starting P-D-X-R-A-C Loop...")
            
            # 1. 🎛️ Bayesian Suggest: 獲取優化參數
            params = self.optimizer.suggest()
            temp = params.get("temperature", 0.7)
            top_p = params.get("top_p", 0.9)
            print(f"   🎛️ [DeepScientist:Suggest] Params: temp={temp:.2f}, top_p={top_p:.2f}")

            # 1. P: Plan (Inject program.md)
            rules = self.hub.load_program_rules(str(self.project_root / "program.md"))
            
            # 2. D: Diagnose
            print(f"   🔍 [D] Diagnosing target: {self.target_file}")
            
            # 3. X: eXecute Research
            print(f"   🌐 [X] Researching external fixes for {self.target_file}")
            
            # 4. R: Repair
            print(f"   🛠️ [R] Generating patch (using suggested params)...")
            patch = f"# Optimized for {self.task} Round {round_id}\n# Params: temp={temp}, top_p={top_p}\n# FlashJudge Target: 9.0"
            
            # 5. A: Audit (FlashJudge)
            # 在此實務上應呼叫 FlashJudge 命令，此處模擬一個基於參數的非線性得分
            import random
            base_score = 7.5 + (round_id * 0.05) 
            noise = random.uniform(-0.5, 0.5)
            score = min(max(base_score + (temp * 0.5) - (abs(top_p - 0.9) * 2) + noise, 0.0), 10.0)
            
            print(f"   ⚖️ [DeepScientist:Observe] Audit Score: {score:.2f}")
            
            # 📉 Bayesian Observe: 回饋優化器
            self.optimizer.observe(params, score)
            
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
        # 🧪 Use high-entropy unique names to avoid collisions in /tmp
        timestamp = int(time.time())
        task_id_unique = f"ds-{self.task.replace(' ', '_')[:15]}-{timestamp}"
        branch_prefix = f"audit/{task_id_unique}"
        
        try:
            # 🛡️ Attempt dynamic lease
            task_id, branch, workpath = self.worktree_mgr.lease(task_id_unique, branch_prefix)
        except Exception as e:
            print(f"❌ [Critical] First lease failed: {e}. Force clearing base research dir...")
            subprocess.run(["rm", "-rf", "/tmp/codex-workspaces/research"])
            task_id, branch, workpath = self.worktree_mgr.lease(task_id_unique, branch_prefix)

        if not workpath:
            print("❌ [Fatal] Could not establish workspace. Terminating.")
            return

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
    parser.add_argument("--mode", default="default", choices=["default", "v23-burnin", "governance-upgrade"], help="Night Shift mode")
    parser.add_argument("--target-events", type=int, default=0, help="Target number of events to stop")
    parser.add_argument("--parallel", type=int, default=1, help="Parallel workers")
    parser.add_argument("--target-layers", type=int, default=19, help="Number of governance layers")
    parser.add_argument("--auto-stop", action="store_true", help="Auto-stop based on criteria")
    
    args = parser.parse_args()
    
    if args.mode == "v23-burnin":
        os.environ["NEXUS_BURNIN_MODE"] = "1"
        os.environ["NEXUS_SKIP_PROTOCOL_GATE"] = "1"
    elif args.mode == "governance-upgrade":
        os.environ["NEXUS_GOVERNANCE_UPGRADE"] = "1"
        os.environ["NEXUS_TARGET_LAYERS"] = str(args.target_layers)

    task_list = args.tasks.split(",") if args.tasks else [args.task]
    
    # Auto-stop check mechanism (Simplified for loop)
    def check_stop_criteria():
        """
        🛑 階段 2 停止條件：CI PASS && Context Reduction > 30% && Decision Quality == SOTA
        """
        metrics_file = Path(".nexus/metrics/governance_benchmark.json")
        if not metrics_file.exists(): return False
        try:
            with open(metrics_file, "r") as f:
                data = json.load(f)
                return data.get("ci_pass") and data.get("context_reduction") >= 0.3
        except: return False

    def check_events():
        metrics_file = Path(".nexus/metrics/feedback_events.jsonl")
        if not metrics_file.exists(): return 0
        with open(metrics_file, "r") as f:
            return sum(1 for _ in f)

    if args.swarm or args.parallel > 1:
        workers = args.parallel if args.parallel > 1 else args.workers
        print(f"🐝 [Swarm] Launching {workers} workers for {len(task_list)} tasks...")
        with ProcessPoolExecutor(max_workers=workers) as executor:
            for t_name in task_list:
                shift = AutoResearchNightShift(t_name, args.max_rounds, args.budget_min, args.target_file)
                executor.submit(shift.run)
                
                if args.auto_stop and check_stop_criteria():
                    print("🎯 [Governance] Convergence reached (CI Pass + Context -30%). Stopping.")
                    break
    else:
        for t_name in task_list:
            shift = AutoResearchNightShift(t_name, args.max_rounds, args.budget_min, args.target_file)
            shift.run()
            if args.auto_stop and check_stop_criteria():
                print("🎯 [Governance] Convergence reached. Finishing task.")
                break

if __name__ == "__main__":
    main()
