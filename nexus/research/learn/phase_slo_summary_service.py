from __future__ import annotations

import json
from typing import Any

from .protocols import LearnContextProtocol


class PhaseSLOSummaryService:
    def __init__(self, ctx: LearnContextProtocol):
        self.ctx = ctx

    @staticmethod
    def _unavailable(reason: str) -> dict[str, Any]:
        return {
            "status": "UNAVAILABLE",
            "phase_slo_pass": False,
            "global": {
                "required_done_ratio": 0.0,
                "success_ratio": 0.0,
            },
            "phases": {},
            "reason": reason,
        }

    def read_phase_slo_summary(self) -> dict[str, Any]:
        if not self.ctx.phase_slo_summary_path.exists():
            return self._unavailable("phase_slo_summary_missing")
        try:
            data = json.loads(self.ctx.phase_slo_summary_path.read_text(encoding="utf-8"))
        except Exception:
            return self._unavailable("phase_slo_summary_parse_error")
        if not isinstance(data, dict):
            return self._unavailable("phase_slo_summary_invalid_type")
        return data
