from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .protocols import LearnContextProtocol


class PhaseKPIService:
    def __init__(self, ctx: LearnContextProtocol):
        self.ctx = ctx

    def build_phase_kpi_report(self, window: int = 300) -> dict[str, Any]:
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
        phases: dict[str, dict[str, Any]] = {}
        mode_breakdown: dict[str, int] = {}
        for phase in self.ctx.PHASES:
            items = [r for r in rows if str(r.get("phase", "")).upper() == phase]
            total = len(items)
            success = sum(1 for r in items if str(r.get("phase_status", "")).upper() == "SUCCESS")
            required = sum(1 for r in items if bool((r.get("writeback_policy") or {}).get("required", False)))
            done = sum(1 for r in items if bool(r.get("writeback_done", False)))
            done_required = sum(
                1
                for r in items
                if bool((r.get("writeback_policy") or {}).get("required", False)) and bool(r.get("writeback_done", False))
            )
            success_ratio = 1.0 if total == 0 else success / total
            required_done_ratio = 1.0 if required == 0 else done_required / required
            phases[phase] = {
                "total": total,
                "success": success,
                "success_ratio": round(success_ratio, 4),
                "writeback_required": required,
                "writeback_done": done,
                "writeback_done_required": done_required,
                "required_done_ratio": round(required_done_ratio, 4),
            }
            for item in items:
                mode = str((item.get("route") or {}).get("mode", "unknown"))
                mode_breakdown[mode] = mode_breakdown.get(mode, 0) + 1

        total_records = len(rows)
        total_success = sum(int(v["success"]) for v in phases.values())
        total_required = sum(int(v["writeback_required"]) for v in phases.values())
        total_done_required = sum(int(v["writeback_done_required"]) for v in phases.values())

        report = {
            "status": "SUCCESS",
            "window": max(1, int(window)),
            "total_records": total_records,
            "global": {
                "success_ratio": round(1.0 if total_records == 0 else total_success / total_records, 4),
                "required_done_ratio": round(1.0 if total_required == 0 else total_done_required / total_required, 4),
            },
            "mode_breakdown": mode_breakdown,
            "phases": phases,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return report
