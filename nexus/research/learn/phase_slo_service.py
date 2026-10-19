from __future__ import annotations
from .protocols import LearnContextProtocol
from .learn_models import LearnClaim
import json
import re
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request
from urllib.parse import quote_plus
import html
import time
import concurrent.futures
from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore
from nexus.services.mem_palace import MemPalace
from nexus.core.skill_outcomes import OutcomePayload, build_outcome_event, append_skill_outcome_event
from nexus.services.memory import MemoryService

class PhaseSLOService:
    def __init__(self, ctx: LearnContextProtocol):
        self.ctx = ctx
    def build_phase_slo_report(self, window: int = 300) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        if self.ctx.phase_writeback_path.exists():
            for line in self.ctx.phase_writeback_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        rows.append(row)
                except json.JSONDecodeError:
                    continue

        rows = rows[-max(1, int(window)):]
        per_phase: dict[str, dict[str, Any]] = {}
        for phase in self.ctx.PHASES:
            items = [r for r in rows if str(r.get("phase", "")).upper() == phase]
            total = len(items)
            required = sum(1 for r in items if bool((r.get("writeback_policy") or {}).get("required", False)))
            # #2702: only required rows count as done (a not-required row that happened to
            # write back used to inflate the ratio past 1 required-but-missing row).
            done = sum(
                1
                for r in items
                if bool((r.get("writeback_policy") or {}).get("required", False))
                and bool(r.get("writeback_done", False))
            )
            success = sum(1 for r in items if str(r.get("phase_status", "")).upper() == "SUCCESS")
            required_done_ratio = 1.0 if required == 0 else done / required
            success_ratio = 1.0 if total == 0 else success / total
            per_phase[phase] = {
                "total": total,
                "writeback_required": required,
                "writeback_done": done,
                "required_done_ratio": round(required_done_ratio, 4),
                "success_ratio": round(success_ratio, 4)}

        global_required = sum(v["writeback_required"] for v in per_phase.values())
        global_done = sum(v["writeback_done"] for v in per_phase.values())
        global_total = sum(v["total"] for v in per_phase.values())
        global_success = sum(int(round(v["success_ratio"] * v["total"])) for v in per_phase.values())
        # #2702: fail closed.  No rows is NO_DATA (not a pass), only phases that have rows are
        # judged, and at least one required write-back must exist to call the SLO met
        # (global_required > 0 implies global_total > 0).
        observed = [v for v in per_phase.values() if v["total"] > 0]
        phase_slo_pass = (
            global_required > 0
            and all(v["required_done_ratio"] >= 0.95 and v["success_ratio"] >= 0.5 for v in observed)
        )
        if global_total == 0:
            status, reason = "NO_DATA", "no_phase_rows"
        elif global_required == 0:
            status, reason = "SUCCESS", "no_required_writeback_rows"
        else:
            status, reason = "SUCCESS", "" if phase_slo_pass else "phase_slo_below_threshold"

        summary = {
            "status": status,
            "window": max(1, int(window)),
            "phase_slo_pass": bool(phase_slo_pass),
            "reason": reason,
            "global": {
                "writeback_required": global_required,
                "writeback_done": global_done,
                "required_done_ratio": round(0.0 if global_required == 0 else global_done / global_required, 4),
                "success_ratio": round(0.0 if global_total == 0 else global_success / global_total, 4)},
            "phases": per_phase,
            "timestamp": datetime.now(timezone.utc).isoformat()}
        self.ctx.phase_slo_summary_path.parent.mkdir(parents=True, exist_ok=True)
        self.ctx.phase_slo_summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return summary


    def validate_writeback_closure(self, task_id: str) -> dict[str, Any]:
        """Verify if a specific task has committed learning closure writeback."""
        if not self.ctx.history_path.exists():
            return {"ok": False, "code": "WB_MISSING"}
        
        try:
            import json
            history = [json.loads(line) for line in self.ctx.history_path.read_text().splitlines() if line.strip()]
            task_entries = [h for h in history if h.get("task_id") == task_id]
            
            if not task_entries:
                return {"ok": False, "code": "WB_MISSING"}
            
            # Check for essential fields
            if any(e.get("status") == "SUCCESS" for e in task_entries):
                return {"ok": True, "code": "WB_OK"}
            
            return {"ok": False, "code": "WB_PARTIAL"}
        except Exception as e:
            return {"ok": False, "code": f"WB_ERROR:{str(e)}"}
