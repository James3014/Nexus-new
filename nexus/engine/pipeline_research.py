from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import subprocess
import sys
import time
from nexus.research.research_pack import build_research_pack

class PipelineResearchMixin:
    """🧪 Mixin for experimental research logic in NexusPipeline."""
    
    def _run_experimental_research(
        self,
        *,
        task_id: str,
        task_desc: str,
        workspace: str,
        rounds: int,
        stable_wins: int,
        proof_ratio_min: float,
    ) -> Dict[str, Any]:
        workspace_path = Path(workspace).expanduser()
        workspace_path = self._resolve_workspace_path(workspace_path)
        
        prefix = f"xphase_{task_id}"
        start_ts = time.time()
        
        cmd = self._prepare_research_cmd(workspace_path, rounds, stable_wins, proof_ratio_min, prefix)
        rc = subprocess.call(cmd, cwd=str(self.engine.project_root))
        
        report_path = workspace_path / f"{prefix}_final_report_cn.json"
        report = self._load_research_report(report_path)
        
        elapsed = time.time() - start_ts
        return self._build_research_result(task_desc, report, rc, elapsed, report_path)

    def _resolve_workspace_path(self, path: Path) -> Path:
        if not path.is_absolute():
            return (self.engine.project_root / path).resolve()
        return path.resolve()

    def _prepare_research_cmd(self, workspace_path: Path, rounds: int, stable_wins: int, proof_ratio_min: float, prefix: str) -> List[str]:
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
        if report_path.exists():
            try:
                return json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _build_research_result(self, task_desc: str, report: Dict[str, Any], rc: int, elapsed: float, report_path: Path) -> Dict[str, Any]:
        history = list(report.get("history", []) or [])
        hypotheses = []
        experiments = []
        
        for idx, row in enumerate(history, start=1):
            best = dict(row.get("best", {}) or {})
            hid = f"H{idx}"
            hypotheses.append({
                "id": hid,
                "description": f"min_samples={best.get('min_samples')} baseline={best.get('baseline')} learning_rate={best.get('learning_rate')}",
                "confidence": 0.8 if int(row.get("apply_rc", 1) or 1) == 0 else 0.4,
            })
            experiments.append({
                "round": idx, "hypothesis": hid,
                "metric": 1.0 if int(row.get("apply_rc", 1) or 1) == 0 else 0.0,
                "kept": int(row.get("apply_rc", 1) or 1) == 0,
                "sweep_report": row.get("sweep_report"),
            })

        from nexus.research.research_pack import ResearchContext
        ctx = ResearchContext(
            task=task_desc, mode="experimental", source="AUTORESEARCH_PHASE7_LOOP",
            reason="router_selected_experimental",
            hypotheses=hypotheses, experiments=experiments,
            winner={
                "hypothesis_id": f"H{len(history)}" if history else "",
                "patch_diff": "", "final_metric": 1.0 if bool(report.get("converged")) else 0.0,
                "params": dict(report.get("final_best", {}) or {}),
                "report_path": str(report_path),
            },
            eliminated=[h["id"] for h in hypotheses[:-1]] if hypotheses else [],
            rounds=int(report.get("loops_executed", len(history)) or len(history)),
            time_sec=elapsed, status="SUCCESS" if bool(report.get("converged")) and rc == 0 else "FAIL",
            findings=[f"phase7_loop_rc={rc}", f"converged={bool(report.get('converged'))}", f"report={report_path}"],
            raw={"report": report, "return_code": rc},
        )
        return build_research_pack(ctx=ctx)
