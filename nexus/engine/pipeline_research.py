from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import subprocess
import sys
import time
import logging
from nexus.research.research_pack import build_research_pack

# Configure logging for the research pipeline
logger = logging.getLogger(__name__)

    def _stage_research(self, ctx: Any, tracer: Any):
        """🧬 Phase X: Cross-Plane Research (v24.0 Hardened)"""
        logger.info(f"🔍 [Phase X] Initiating Master Loop Research for: {ctx.task_id}")
        
        # 🧪 [Round 20 Evolution] Warm Start from historical data
        nas_aggression = ctx.bayesian_params.get("nas_aggression", 0.7)
        if nas_aggression > 0.8:
            logger.info("🔥 [Phase X] High Aggression detected. Forcing deep-path exploration.")
            
        research_result = self._run_experimental_research(
            task_id=ctx.task_id,
            task_desc=ctx.task_desc,
            workspace=str(ctx.state.metadata.get("worktree_path", "/tmp")),
            rounds=int(5 * (1.0 + nas_aggression)),
            stable_wins=2,
            proof_ratio_min=0.8
        )
        
        # 🧪 [Round 20] Compile State for Phase D
        ctx.state.metadata["diagnostic_map"] = {
            "findings": research_result.get("findings", []),
            "winner_params": research_result.get("winner", {}).get("params", {}),
            "evolution_score": research_result.get("winner", {}).get("final_metric", 0.0)
        }
        return True
        self,
        *,
        task_id: str,
        task_desc: str,
        workspace: str,
        rounds: int,
        stable_wins: int,
        proof_ratio_min: float,
        timeout_sec: int = 300,  # Nexus-AutoResearch Rules v7.2 budget
    ) -> Dict[str, Any]:
        """Executes the Phase 7 autotune loop and collects research artifacts."""
        workspace_path = Path(workspace).expanduser()
        workspace_path = self._resolve_workspace_path(workspace_path)
        
        prefix = f"xphase_{task_id}"
        start_ts = time.time()
        
        cmd = self._prepare_research_cmd(workspace_path, rounds, stable_wins, proof_ratio_min, prefix)
        
        try:
            # Execute research script with timeout enforcement
            process = subprocess.run(
                cmd,
                cwd=str(self.engine.project_root),
                capture_output=True,
                text=True,
                timeout=timeout_sec
            )
            rc = process.returncode
        except subprocess.TimeoutExpired:
            logger.warning(f"Research task {task_id} exceeded budget of {timeout_sec}s.")
            rc = -1
        except Exception as e:
            logger.error(f"Unexpected error in research subprocess: {e}")
            rc = -2
        
        report_path = workspace_path / f"{prefix}_final_report_cn.json"
        report = self._load_research_report(report_path)
        
        elapsed = time.time() - start_ts
        return self._build_research_result(task_desc, report, rc, elapsed, report_path)

    def _resolve_workspace_path(self, path: Path) -> Path:
        """Resolves path relative to project root if not absolute."""
        if not path.is_absolute():
            return (self.engine.project_root / path).resolve()
        return path.resolve()

    def _prepare_research_cmd(self, workspace_path: Path, rounds: int, stable_wins: int, proof_ratio_min: float, prefix: str) -> List[str]:
        """Constructs the subprocess command for the autotune loop."""
        script = self.engine.project_root / "scripts" / "ops" / "phase7_autotune_loop.py"
        return [
            sys.executable,
            str(script),
            "--project-root", str(self.engine.project_root),
            "--workspace", str(workspace_path),
            "--rounds", str(rounds),
            "--proof-ratio-min", str(proof_ratio_min),
            "--max-loops", str(max(stable_wins + 2, 3)),
            "--stable-wins", str(stable_wins),
            "--output-prefix", prefix,
        ]

    def _load_research_report(self, report_path: Path) -> Dict[str, Any]:
        """Loads and parses the research JSON report safely."""
        if report_path.exists():
            try:
                content = report_path.read_text(encoding="utf-8").strip()
                if content:
                    return json.loads(content)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load research report at {report_path}: {e}")
        return {}

    def _build_research_result(self, task_desc: str, report: Dict[str, Any], rc: int, elapsed: float, report_path: Path) -> Dict[str, Any]:
        """Transforms raw report data into a structured ResearchPack."""
        history = list(report.get("history", []) or [])
        hypotheses = []
        experiments = []
        
        for idx, row in enumerate(history, start=1):
            best = dict(row.get("best", {}) or {})
            hid = f"H{idx}"
            
            # Construct readable description from parameters
            desc = ", ".join([f"{k}={v}" for k, v in best.items()]) or "default autotune"
            
            # Align with Nexus-AutoResearch Rules v7.2: prioritize val_flashjudge metric
            is_kept = int(row.get("apply_rc", 1) or 1) == 0
            metric_val = row.get("val_flashjudge", 1.0 if is_kept else 0.0)
            
            hypotheses.append({
                "id": hid,
                "description": desc,
                "confidence": 0.8 if is_kept else 0.4,
            })
            experiments.append({
                "round": idx, 
                "hypothesis": hid,
                "metric": metric_val,
                "kept": is_kept,
                "sweep_report": row.get("sweep_report"),
            })

        from nexus.research.research_pack import ResearchContext
        
        converged = bool(report.get("converged"))
        status = "SUCCESS" if converged and rc == 0 else "FAIL"
        if rc == -1: status = "TIMEOUT"
        
        ctx = ResearchContext(
            task=task_desc, 
            mode="experimental", 
            source="AUTORESEARCH_PHASE7_LOOP",
            reason="router_selected_experimental",
            hypotheses=hypotheses, 
            experiments=experiments,
            winner={
                "hypothesis_id": f"H{len(history)}" if history else "",
                "patch_diff": report.get("final_patch", ""), 
                "final_metric": report.get("final_score", 1.0 if converged else 0.0),
                "params": dict(report.get("final_best", {}) or {}),
                "report_path": str(report_path),
            },
            eliminated=[h["id"] for h in hypotheses[:-1]] if hypotheses else [],
            rounds=int(report.get("loops_executed", len(history)) or len(history)),
            time_sec=elapsed, 
            status=status,
            findings=[
                f"phase7_loop_rc={rc}", 
                f"converged={converged}", 
                f"final_score={report.get('final_score')}",
                f"report={report_path}"
            ],
            raw={"report": report, "return_code": rc},
        )
        return build_research_pack(ctx=ctx)
