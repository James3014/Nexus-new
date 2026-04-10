from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import json
import logging
import subprocess
import sys
import time

from nexus.research.research_pack import ResearchContext, build_research_pack

logger = logging.getLogger(__name__)


class PipelineResearchMixin:
    """Research helpers for Nexus pipeline experimental phase."""

    def _stage_research(self, ctx: Any, tracer: Any):
        """Run experimental research and write diagnostic map into state metadata."""
        logger.info("🔍 [Phase X] Initiating Master Loop Research for: %s", ctx.task_id)
        nas_aggression = (ctx.bayesian_params or {}).get("nas_aggression", 0.7)
        rounds = max(int(5 * (1.0 + nas_aggression)), 1)

        research_result = self._run_experimental_research(
            task_id=ctx.task_id,
            task_desc=ctx.task_desc,
            workspace=str(ctx.state.metadata.get("worktree_path", "/tmp")),
            rounds=rounds,
            stable_wins=2,
            proof_ratio_min=0.8,
        )

        ctx.state.metadata["diagnostic_map"] = {
            "findings": research_result.get("findings", []),
            "winner_params": research_result.get("winner", {}).get("params", {}),
            "evolution_score": research_result.get("winner", {}).get("final_metric", 0.0),
        }
        return True

    def _run_experimental_research(
        self,
        *,
        task_id: str,
        task_desc: str,
        workspace: str,
        rounds: int,
        stable_wins: int,
        proof_ratio_min: float,
        timeout_sec: int = 300,
    ) -> Dict[str, Any]:
        """Execute Phase 7 autotune loop and return normalized research pack."""
        workspace_path = self._resolve_workspace_path(Path(workspace).expanduser())
        prefix = f"xphase_{task_id}"
        start_ts = time.time()

        cmd = self._prepare_research_cmd(workspace_path, rounds, stable_wins, proof_ratio_min, prefix)

        try:
            process = subprocess.run(
                cmd,
                cwd=str(self.engine.project_root),
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            rc = process.returncode
        except subprocess.TimeoutExpired:
            logger.warning("Research task %s exceeded budget of %ss.", task_id, timeout_sec)
            rc = -1
        except Exception as exc:  # pragma: no cover
            logger.error("Unexpected error in research subprocess: %s", exc)
            rc = -2

        report_path = workspace_path / f"{prefix}_final_report_cn.json"
        report = self._load_research_report(report_path)
        elapsed = time.time() - start_ts
        return self._build_research_result(task_desc, report, rc, elapsed, report_path)

    def _resolve_workspace_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path.resolve()
        return (self.engine.project_root / path).resolve()

    def _prepare_research_cmd(
        self,
        workspace_path: Path,
        rounds: int,
        stable_wins: int,
        proof_ratio_min: float,
        prefix: str,
    ) -> List[str]:
        script = self.engine.project_root / "scripts" / "ops" / "phase7_autotune_loop.py"
        return [
            sys.executable,
            str(script),
            "--project-root",
            str(self.engine.project_root),
            "--workspace",
            str(workspace_path),
            "--rounds",
            str(rounds),
            "--proof-ratio-min",
            str(proof_ratio_min),
            "--max-loops",
            str(max(stable_wins + 2, 3)),
            "--stable-wins",
            str(stable_wins),
            "--output-prefix",
            prefix,
        ]

    def _load_research_report(self, report_path: Path) -> Dict[str, Any]:
        if not report_path.exists():
            return {}
        try:
            content = report_path.read_text(encoding="utf-8").strip()
            return json.loads(content) if content else {}
        except Exception as exc:
            logger.error("Failed to load research report at %s: %s", report_path, exc)
            return {}

    def _build_research_result(
        self,
        task_desc: str,
        report: Dict[str, Any],
        rc: int,
        elapsed: float,
        report_path: Path,
    ) -> Dict[str, Any]:
        history = list(report.get("history", []) or [])
        hypotheses = []
        experiments = []

        for idx, row in enumerate(history, start=1):
            best = dict(row.get("best", {}) or {})
            hid = f"H{idx}"
            desc = ", ".join([f"{k}={v}" for k, v in best.items()]) or "default autotune"
            is_kept = int(row.get("apply_rc", 1) or 1) == 0
            metric_val = row.get("val_flashjudge", 1.0 if is_kept else 0.0)
            hypotheses.append({"id": hid, "description": desc, "confidence": 0.8 if is_kept else 0.4})
            experiments.append(
                {
                    "round": idx,
                    "hypothesis": hid,
                    "metric": metric_val,
                    "kept": is_kept,
                    "sweep_report": row.get("sweep_report"),
                }
            )

        converged = bool(report.get("converged"))
        status = "SUCCESS" if converged and rc == 0 else "FAIL"
        if rc == -1:
            status = "TIMEOUT"

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
                f"report={report_path}",
            ],
            raw={"report": report, "return_code": rc},
        )
        return build_research_pack(ctx=ctx)

