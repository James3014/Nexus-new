from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .protocols import LearnContextProtocol


class PhaseBridgeService:
    def __init__(self, ctx: LearnContextProtocol):
        self.ctx = ctx

    def _decide_learn_phase_route(self, *, phase: str, topic: str, metrics: dict[str, Any]) -> dict[str, Any]:
        phase = str(phase or "").upper()
        coverage = float(metrics.get("coverage", 0.0) or 0.0)
        pass_rate = float(metrics.get("self_question_pass_rate", metrics.get("pass_rate", 0.0)) or 0.0)
        citation_valid_ratio = float(metrics.get("citation_valid_ratio", 0.0) or 0.0)
        stale_claims_count = int(metrics.get("stale_claims_count", 0) or 0)
        conflict_count = int(metrics.get("conflict_count", 0) or 0)

        risk_score = 0.0
        if coverage < 0.6:
            risk_score += 0.35
        if pass_rate < 0.6:
            risk_score += 0.35
        if citation_valid_ratio < 0.95:
            risk_score += 0.2
        if stale_claims_count > 0:
            risk_score += 0.05
        if conflict_count > 0:
            risk_score += 0.15
        risk_score = round(min(1.0, risk_score), 4)

        if phase in {"P", "D"}:
            mode = "light"
            reason = "plan_diagnose_context_sync"
        elif phase == "X":
            mode = "research" if risk_score >= 0.5 else "light"
            reason = "research_needed" if mode == "research" else "research_optional"
        elif phase == "R":
            mode = "research" if risk_score >= 0.45 else "light"
            reason = "repair_needs_evidence" if mode == "research" else "repair_low_risk"
        elif phase == "A":
            mode = "strict"
            reason = "audit_requires_citation_integrity"
        elif phase == "C":
            mode = "strict"
            reason = "crystallize_requires_writeback"
        else:
            mode = "off"
            reason = "unknown_phase"

        return {
            "phase": phase,
            "topic": topic,
            "mode": mode,
            "risk_score": risk_score,
            "reason": reason,
            "metrics_snapshot": {
                "coverage": coverage,
                "self_question_pass_rate": pass_rate,
                "citation_valid_ratio": citation_valid_ratio,
                "stale_claims_count": stale_claims_count,
                "conflict_count": conflict_count,
            },
        }

    @staticmethod
    def _phase_writeback_policy(*, phase: str, route: dict[str, Any]) -> dict[str, Any]:
        phase = str(phase or "").upper()
        mode = str(route.get("mode", "off"))
        required = phase in {"R", "A", "C"} or mode in {"research", "strict"}
        return {
            "required": required,
            "policy": "required" if required else "optional",
            "reason": f"phase={phase},mode={mode}",
        }

    def _append_phase_writeback(self, payload: dict[str, Any]) -> None:
        self.ctx.phase_writeback_path.parent.mkdir(parents=True, exist_ok=True)
        with self.ctx.phase_writeback_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def sync_phase_learning_closure(
        self,
        *,
        topic: str,
        metrics: dict[str, Any],
        phase_status: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        written = 0
        routes: dict[str, Any] = {}
        statuses = {k.upper(): str(v).upper() for k, v in (phase_status or {}).items()}

        for phase in self.ctx.PHASES:
            route = self._decide_learn_phase_route(phase=phase, topic=topic, metrics=metrics)
            policy = self._phase_writeback_policy(phase=phase, route=route)
            status = statuses.get(phase, "SUCCESS")
            payload = {
                "timestamp": now,
                "topic": topic,
                "phase": phase,
                "phase_status": status,
                "route": route,
                "writeback_policy": policy,
                "writeback_done": True,
            }
            self._append_phase_writeback(payload)
            routes[phase] = route
            written += 1

        summary = self.ctx.build_phase_slo_report(window=300)
        return {
            "status": "SUCCESS",
            "topic": topic,
            "entries_written": written,
            "phase_routes": routes,
            "phase_slo_summary": summary,
        }
