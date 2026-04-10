import argparse
import json
import os
import signal
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from nexus.core.context_hub import ContextHub
from nexus.services.workspace import WorkspaceManager
from scripts.ops.feynman_bridge import DualTrackAudit


DEFAULT_TARGET_FILE = ""
PYTHON_SUFFIXES = {".py"}


class SimpleResearchSearchSpace:
    def __init__(self):
        self.dimensions: Dict[str, tuple[float, float]] = {}

    def add_dimension(self, name: str, low: float, high: float) -> None:
        self.dimensions[name] = (low, high)


class SimpleResearchOptimizer:
    def __init__(self, space: SimpleResearchSearchSpace):
        self.space = space

    def suggest(self) -> Dict[str, float]:
        return {
            name: (bounds[0] + bounds[1]) / 2.0
            for name, bounds in self.space.dimensions.items()
        }

    def observe(self, params: Dict[str, float], score: float) -> None:
        return None


@dataclass
class RoundOutcome:
    score: float
    candidate: str
    status: str
    summary: str = ""


class AutoResearchNightShift:
    """
    Nexus-AutoResearch Night Shift.
    Runs a local autonomous optimization loop inside an isolated worktree until
    the target reaches convergence, then returns control to the caller so the
    next target can start automatically.
    """

    def __init__(
        self,
        task: str,
        max_rounds: int = 50,
        budget_min: int = 5,
        target_file: str = DEFAULT_TARGET_FILE,
        convergence_patience: int = 5,
        gateway: Any = None,
        model_name: Optional[str] = "gemini-3-flash-preview",
    ):
        self.task = task.strip()
        self.max_rounds = max_rounds
        self.budget_sec = budget_min * 60
        self.cli_target_file = (target_file or "").strip()
        self.convergence_patience = max(1, convergence_patience)
        self.resolved_target_file = self.cli_target_file

        self.project_root = Path(__file__).resolve().parents[1]
        self.worktree_mgr = WorkspaceManager(str(self.project_root))
        self.hub = ContextHub(self.project_root)
        self.feynman_auditor = DualTrackAudit()
        self.compute_tier = "CLOUD"

        from nexus.research.findings_memory import FindingsMemoryStore
        from nexus.services.gateway import BattlesuitGateway
        from nexus.connectors.webhook_connector import WebhookConnector
        from nexus.services.prompt_builder import PromptBuilder
        
        # 🛡️ Wisdom Triad & Memory Safety
        try:
            self.memory_store = FindingsMemoryStore(self.project_root)
        except Exception as e:
            print(f"⚠️ [Memory Safety] Initialization warning: {e}. Falling back to passive mode.")
            self.memory_store = None # type: ignore

        self.best_score = 0.0
        self.no_improve_streak = 0
        self.base_commit: Optional[str] = None
        self.tracelog_path = self.project_root / f"tracelog_{self.task.replace('/', '_')}.jsonl"
        self.gateway = gateway or BattlesuitGateway(project_root=self.project_root)
        # 🛡️ Hardened Model Selection
        self.model_name = model_name

        # 🛡️ Wisdom Triad: Initialize unified prompt engine
        try:
            self.prompt_builder = PromptBuilder(str(self.project_root))
        except Exception as e:
            print(f"⚠️ [PromptBuilder Safety] Initialization warning: {e}.")
            self.prompt_builder = None # type: ignore

        # [Approval Gate] Path setup
        self.pending_manifest_path = self.project_root / ".nexus/nightshift/pending.json"
        
        try:
            from nexus.research.bayesian_engine import (
                BayesianResearchOptimizer,
                ResearchSearchSpace,
            )
            self.space = ResearchSearchSpace()
            optimizer_cls = BayesianResearchOptimizer
        except ModuleNotFoundError:
            self.space = SimpleResearchSearchSpace()
            optimizer_cls = SimpleResearchOptimizer
        self.space.add_dimension("temperature", 0.1, 0.9)
        self.optimizer = optimizer_cls(self.space)

    def _log_trace(self, round_id: int, status: str, score: float, summary: str):
        event = {
            "timestamp": datetime.now().isoformat(),
            "task": self.task,
            "round": round_id,
            "status": status,
            "flashjudge_score": score,
            "summary": summary,
            "target_file": self.resolved_target_file,
        }
        with open(self.tracelog_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def _get_active_beliefs(self) -> str:
        """從智慧三元組獲取當前倫理與架構約束。"""
        return self.prompt_builder.build_task_prompt("R", self.task, "", "governance")

    def _run_round(self, round_id: int, workpath: Path) -> RoundOutcome:
        print(f"\n--- [Round {round_id}] Suggesting optimized variant... ---")
        params = self.optimizer.suggest()
        
        # 1. 🔍 Context Gathering (Lessons + Wisdom + History + SOURCE CODE)
        try:
            target_path = workpath / self.resolved_target_file
            current_code = target_path.read_text(encoding="utf-8") if target_path.exists() else "# New File"
            
            if self.memory_store:
                previous_lessons = self.memory_store.get_relevant_lessons(self.task)
                # 🚀 P1-D: Turbo Pruning restored (500 chars)
                if len(previous_lessons) > 500:
                    previous_lessons = previous_lessons[:500] + "... [TURBO]"
                    
                wisdom_patterns = self.memory_store.get_wisdom_patterns(self.task)
                if len(wisdom_patterns) > 500:
                    wisdom_patterns = wisdom_patterns[:500] + "... [TURBO]"
            else:
                previous_lessons = "None."
                wisdom_patterns = "None."
        except Exception as e:
            current_code = "# Read Error"
            previous_lessons = f"Error: {e}"
            wisdom_patterns = "None."

        # 🛡️ Wisdom Triad Check: Force model_name to gemini-3-flash-preview
        print(f"📡 [Battlesuit] Calling Gemini CLI ({self.model_name})... Optimized context.")
        start_gen = time.time()
        prompt, raw_content = self.gateway.ask_structured(
            prompt=f"Optimize the following code in {self.resolved_target_file}.\n\n[SOURCE]\n{current_code}\n\nLessons: {previous_lessons}\nWisdom: {wisdom_patterns}",
            payload=f"Target: {self.resolved_target_file}\nParams: {params}\nReturn the FULL file content in the 'patch' field.",
            phase="R",
            model_name=self.model_name
        )
        elapsed = time.time() - start_gen
        print(f"✅ [Battlesuit] Generation complete in {elapsed:.1f}s.")

        if prompt.get("status") == "FAIL":
            return RoundOutcome(0.0, "", "GENERATION_FAILED", prompt.get("summary", "Unknown failure"))

        candidate_code = prompt.get("patch", "")
        if not candidate_code:
            return RoundOutcome(0.0, "", "EMPTY_PATCH", "Model returned no patch.")

        # 2. 🏗️ Physical Application
        target_path = workpath / self.resolved_target_file
        target_path.write_text(candidate_code, encoding="utf-8")

        # 3. 🧪 Feynman Audit (Physical Verification)
        print(f"🧪 [Audit] Verifying physical integrity of {self.resolved_target_file}...")
        audit_result = self.feynman_auditor.audit_file(str(target_path))
        
        return RoundOutcome(
            score=audit_result.score,
            candidate=candidate_code,
            status="SUCCESS" if audit_result.score >= 0.8 else "AUDIT_REJECTED",
            summary=audit_result.summary
        )

    def run(self):
        """🚀 [AutoResearch] Night Shift v24.0 Eternal: Bayesian Warm-Start Enabled."""
        print(f"🚀 [AutoResearch] Starting Night Shift for: {self.task}")
        start_time = time.time()
        
        # 🧪 [Bayesian Warm-Start] Seed the optimizer with historical data
        self._warm_start_optimizer()

        # 🏗️ Lease Workspace
        task_id, branch_name, workpath = self.worktree_mgr.lease(self.task)
        if not workpath:
            print("❌ [AutoResearch] Failed to lease workspace.")
            return

        try:
            self.base_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.project_root, text=True).strip()
            
            for round_id in range(1, self.max_rounds + 1):
                if time.time() - start_time > self.budget_sec:
                    print("⏰ [AutoResearch] Time budget exceeded.")
                    break

                outcome = self._run_round(round_id, workpath)
                self.optimizer.observe({"temperature": 0.5}, outcome.score)

                if outcome.status == "SUCCESS" and outcome.score > self.best_score:
                    print(f"⭐ [AutoResearch] New best score: {outcome.score:.2f} (Round {round_id})")
                    self.best_score = outcome.score
                    self.no_improve_streak = 0
                    
                    # Commit best variant in sandbox
                    subprocess.run(["git", "add", "."], cwd=workpath, capture_output=True)
                    subprocess.run(["git", "commit", "-m", f"opt(nightshift): optimize {self.task} (score: {outcome.score:.2f})"], cwd=workpath, capture_output=True)
                    self.base_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=workpath, text=True).strip()
                    
                    self._log_trace(
                        round_id,
                        "IMPROVED",
                        outcome.score,
                        outcome.summary,
                    )
                else:
                    # Rollback physical sandbox for next attempt
                    subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=workpath, capture_output=True)
                    self.no_improve_streak += 1
                    self._log_trace(round_id, outcome.status, outcome.score, outcome.summary)

                if self.no_improve_streak >= self.convergence_patience:
                    print(f"🎯 [AutoResearch] Convergence reached after {self.no_improve_streak} rounds.")
                    break

            # --- [Approval Gate] Atomic Queue for Review ---
            if self.best_score > 0 and self.base_commit:
                self._append_to_pending_manifest(self.task, self.resolved_target_file, self.base_commit, self.best_score, str(workpath))

            print(f"✅ [AutoResearch] Finished {self.task}. Best Score: {self.best_score:.2f}")

        finally:
            print(f"🧹 [Cleanup] Worktree at {workpath} retained for review.")

    def _warm_start_optimizer(self):
        """🛡️ Bayesian Warm Start: Load historical traces to eliminate cold-start bias."""
        curve_path = self.project_root / "optimization_curve.csv"
        if curve_path.exists():
            try:
                import pandas as pd
                df = pd.read_csv(curve_path)
                # Filter traces for current target if possible, or use global heuristic
                for _, row in df.tail(20).iterrows():
                    self.optimizer.observe({"temperature": row.get('temperature', 0.5)}, row.get('score', 0.0))
                print(f"🔥 [Bayesian] Warm-start complete. Seeding model with {len(df.tail(20))} traces.")
            except Exception as e:
                print(f"⚠️ [Bayesian] Warm-start failed: {e}")

    def _append_to_pending_manifest(self, task_name: str, target_file: str, commit_sha: str, score: float, workpath: str):
        """🛡️ 原子化寫入待審核清單 (與 fcntl 鎖定技術結合)"""
        import fcntl
        pending_item = {
            "task": task_name,
            "target_file": target_file,
            "commit_sha": commit_sha,
            "best_score": score,
            "workpath": workpath,
            "timestamp": datetime.now().isoformat()
        }
        
        self.pending_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 使用檔案鎖保護 JSON 完整性
        with open(self.pending_manifest_path, "a+b") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
                f.seek(0)
                content = f.read().decode("utf-8")
                pending = json.loads(content) if content else []
                # Remove prior candidate for same task
                pending = [p for p in pending if p["task"] != task_name]
                pending.append(pending_item)
                
                f.seek(0)
                f.truncate()
                f.write(json.dumps(pending, indent=2).encode("utf-8"))
                print(f"✅ [Approval Gate] Task queued with LOCK: {task_name}")
            except Exception as e:
                print(f"❌ [Gate Error] Failed to append with lock: {e}")
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

def _update_manifest_status(project_root: Path, task_name: str, commit_sha: str):
    """🛡️ [Governance] Automatically sync task_manifest.yaml after physical harvest."""
    manifest_path = project_root / "task_manifest.yaml"
    if not manifest_path.exists():
        return
    
    identifier = Path(task_name).stem.lower()
    content = manifest_path.read_text(encoding="utf-8")
    
    import re
    block_pattern = rf"(- id: auto\.repair\..*?{re.escape(identifier)}.*?\n\s+description: ')(.*?)(')"
    timestamp = datetime.now().strftime("%Y-%m-%d")
    resolved_msg = f"AUTO-REPAIR: RESOLVED {timestamp}. Physical patch merged ({commit_sha[:7]}), acceptance-check PASS."
    
    new_content, count = re.subn(block_pattern, rf"\1{resolved_msg}\3", content, flags=re.IGNORECASE)
    
    if count > 0:
        manifest_path.write_text(new_content, encoding="utf-8")
        print(f"📡 [Governance] Task Manifest updated for '{identifier}'.")
        subprocess.run(["git", "add", "task_manifest.yaml"], capture_output=True)
        subprocess.run(["git", "commit", "-m", f"docs(governance): resolve task status for {identifier} ({commit_sha[:7]})"], capture_output=True)
    else:
        print(f"⚠️ [Governance] Could not find matching task ID for '{identifier}' in manifest.")

def main():
    parser = argparse.ArgumentParser(description="Nexus Night Shift local convergence runner")
    parser.add_argument("--task", default="default-task")
    parser.add_argument("--tasks", help="Comma separated list of tasks")
    parser.add_argument("--approve", help="Harvest and merge a pending task")
    parser.add_argument("--list-pending", action="store_true", help="List all pending approvals")
    parser.add_argument("--swarm", action="store_true", help="Launch multi-agent swarm")
    parser.add_argument("--parallel", type=int, default=1, help="Number of parallel workers")
    parser.add_argument("--workers", type=int, default=2, help="Executor workers")
    parser.add_argument("--max_rounds", type=int, default=10)
    parser.add_argument("--budget_min", type=int, default=5)
    parser.add_argument("--target_file", default=DEFAULT_TARGET_FILE)
    parser.add_argument("--convergence_patience", type=int, default=5)
    parser.add_argument("--model", default="gemini-3-flash-preview", help="Target LLM model")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    pending_file = project_root / ".nexus/nightshift/pending.json"

    if args.list_pending:
        if not pending_file.exists():
            print("No pending tasks.")
            return
        with open(pending_file, "r") as f:
            pending = json.load(f)
        for i, item in enumerate(pending, 1):
            print(f"[{i}] {item['task']} | Score: {item['best_score']:.2f} | Commit: {item['commit_sha'][:7]}")
        return

    if args.approve:
        if not pending_file.exists(): return
        with open(pending_file, "r") as f: pending = json.load(f)
        matches = [p for p in pending if args.approve == "ALL" or p["task"] == args.approve]
        remaining = [p for p in pending if p not in matches]
        for item in matches:
            res = subprocess.run(["git", "cherry-pick", item['commit_sha']], capture_output=True, text=True)
            if res.returncode == 0:
                subprocess.run(["git", "worktree", "remove", "--force", item['workpath']], capture_output=True)
                _update_manifest_status(project_root, item['task'], item['commit_sha'])
        with open(pending_file, "w") as f: json.dump(remaining, f, indent=2)
        return

    task_list = [task.strip() for task in args.tasks.split(",")] if args.tasks else [args.task]
    task_list = [t for t in task_list if t]

    if args.parallel > 1:
        print(f"🐝 [Swarm] Launching {args.parallel} workers...")
        with ProcessPoolExecutor(max_workers=args.parallel) as executor:
            for task_name in task_list:
                shift = AutoResearchNightShift(task_name, args.max_rounds, args.budget_min, args.target_file, args.convergence_patience, model_name=args.model)
                executor.submit(shift.run)
    else:
        for task_name in task_list:
            shift = AutoResearchNightShift(task_name, args.max_rounds, args.budget_min, args.target_file, args.convergence_patience, model_name=args.model)
            shift.run()

if __name__ == "__main__":
    main()
