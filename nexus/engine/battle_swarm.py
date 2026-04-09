import os
import shutil
import subprocess
import logging
import concurrent.futures
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

logger = logging.getLogger(__name__)

class BattleSwarm:
    """
    ⚔️ BattleSwarm (Layer 4 AutoEvolution)
    即時平行展開試錯。第一次修復失敗時觸發，利用 Git worktree 創建 4 個平行任務。
    """
    
    def __init__(self, project_root: str, default_workers: int = 4, run_dir: Optional[str] = None):
        self.project_root = Path(project_root)
        self.run_dir = Path(run_dir) if run_dir else (self.project_root / ".nexus" / "runs" / "battle_swarm")
        self.default_workers = default_workers
        self.strategies = [
            {"name": "conservative", "params": {"temperature": 0.2, "prompt_modifier": "Maintain high backward compatibility. Make minimal isolated changes."}},
            {"name": "aggressive", "params": {"temperature": 0.8, "prompt_modifier": "Rewrite code blocks for global correctness. Favor modern idioms."}},
            {"name": "decompose", "params": {"temperature": 0.4, "prompt_modifier": "Break down the failure logic. Introduce helper functions to simplify."}},
            {"name": "wisdom_guided", "params": {"temperature": 0.5, "prompt_modifier": "Search vector DB thoroughly and synthesize historical lessons."}}
        ]
        
    def _create_worktree(self, strategy_name: str, branch_name: str) -> Optional[Path]:
        worktree_path = self.run_dir / f"worktree_{strategy_name}"
        if worktree_path.exists():
            subprocess.run(["git", "worktree", "remove", "-f", str(worktree_path)], cwd=str(self.project_root), capture_output=True)
            if worktree_path.exists():
                shutil.rmtree(worktree_path, ignore_errors=True)
            
        try:
            subprocess.run(["git", "branch", "-f", branch_name, "HEAD"], cwd=str(self.project_root), check=True, capture_output=True)
            subprocess.run(["git", "worktree", "add", str(worktree_path), branch_name], cwd=str(self.project_root), check=True, capture_output=True)
            return worktree_path
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode('utf-8') if e.stderr else str(e)
            logger.error(f"Failed to create worktree for {strategy_name}: {err}")
            return None

    def _cleanup_worktrees(self, worktree_paths: List[Path], branches: List[str]):
        """Clean up generated worktrees and branches."""
        for wp in worktree_paths:
            subprocess.run(["git", "worktree", "remove", "-f", str(wp)], cwd=str(self.project_root), capture_output=True)
        subprocess.run(["git", "worktree", "prune"], cwd=str(self.project_root), capture_output=True)
        for b in branches:
            subprocess.run(["git", "branch", "-D", b], cwd=str(self.project_root), capture_output=True)

    def trigger_battle(self, task_id: str, desc: str, context: Dict[str, Any], execute_fn: Callable) -> Dict[str, Any]:
        """
        觸發 BattleSwarm 平行修復，由外部提供 `execute_fn`(strategy, worktree_path, task_id, desc, context)。
        """
        logger.info(f"⚔️ [BattleSwarm] Triggered for task {task_id}. Forking {self.default_workers} strategies...")
        self.run_dir.mkdir(parents=True, exist_ok=True)
        
        branches_created = []
        worktrees = []
        strategy_to_worktree = {}  # name -> path for reliable lookup
        for i, s in enumerate(self.strategies[:self.default_workers]):
            branch_name = f"battle_{task_id}_{s['name']}_{i}"
            path = self._create_worktree(s['name'], branch_name)
            if path:
                branches_created.append(branch_name)
                worktrees.append((s, path))
                strategy_to_worktree[s["name"]] = str(path)
                
        if not worktrees:
            logger.error("⚔️ [BattleSwarm] Zero worktrees created. Aborting battle.")
            return {"status": "aborted"}

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.default_workers) as executor:
            future_to_strategy = {
                executor.submit(execute_fn, s, str(wt), task_id, desc, context): s
                for s, wt in worktrees
            }
            
            for future in concurrent.futures.as_completed(future_to_strategy):
                strategy = future_to_strategy[future]
                try:
                    res = future.result()
                    results.append({
                        "strategy": strategy["name"],
                        "score": res.get("score", 0.0),
                        "passed": res.get("passed", False),
                        "params": strategy["params"],
                        "language": res.get("language", "unknown"),
                        "file_patterns": res.get("file_patterns", []),
                        "worktree_path": strategy_to_worktree.get(strategy["name"])
                    })
                except Exception as e:
                    logger.error(f"⚔️ [BattleSwarm] Strategy {strategy['name']} exception: {e}")
                    results.append({"strategy": strategy["name"], "passed": False, "score": 0.0})

        winners = sorted([r for r in results if r["passed"]], key=lambda x: x["score"], reverse=True)
        if not winners:
            winners = sorted(results, key=lambda x: x["score"], reverse=True)
            
        winner = winners[0] if winners else None
        
        # We don't cleanup the winner's worktree right away if it passed because the system needs to merge it back?
        # Typically the system would copy files from winner's path back to current HEAD.
        
        return {
            "status": "winner_found" if (winner and winner["passed"]) else "all_failed",
            "winner": winner,
            "all_results": results,
            "worktrees_to_clean": [wt[1] for wt in worktrees],
            "branches_to_clean": branches_created
        }

    def cleanup(self, result: Dict[str, Any]):
        """Clean up based on battle result data."""
        self._cleanup_worktrees(result.get("worktrees_to_clean", []), result.get("branches_to_clean", []))
