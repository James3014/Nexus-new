from __future__ import annotations

import logging
from typing import Any

from nexus.learning.predictor_toggle import (
    LATENT_PREDICTOR,
    influence_entry,
    predictor_enabled,
    record_influence,
)

logger = logging.getLogger(__name__)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


class ForecastGateService:
    """Coordinator preflight: forecast + governance gate + ASH fallback."""

    def __init__(
        self,
        *,
        latent_forecaster: Any,
        gate_eval: Any,
        ash_selector: Any,
        state_io: Any,
    ):
        self.latent_forecaster = latent_forecaster
        self.gate_eval = gate_eval
        self.ash_selector = ash_selector
        self.state_io = state_io

    def evaluate(self, *, task_id: str, task_desc: str, state: Any, phase: str = "D") -> dict[str, Any]:
        forecast = {
            "est_tokens": state.metadata.get("forecast_tokens", 0),
            "roi_score": state.metadata.get("roi_score", 0.0),
        }
        risk = {
            "reject_prob": state.metadata.get("reject_prob", 0.0),
        }

        needs_predictor = forecast["roi_score"] == 0.0
        enabled = predictor_enabled(LATENT_PREDICTOR) and self.latent_forecaster is not None
        if needs_predictor and not enabled:
            # Predictor absent: there is no forecast to gate on, so the preflight passes.
            influence = record_influence(
                influence_entry(
                    LATENT_PREDICTOR,
                    enabled=False,
                    consulted=False,
                    before={"proceed": True},
                    after={"proceed": True},
                    site="forecast_gate",
                ),
                metadata=state.metadata,
            )
            return {
                "proceed": True,
                "reason": "latent_predictor_disabled",
                "forecast": {},
                "risk": {},
                "predictor_influence": influence,
            }

        if needs_predictor:
            forecast = self.latent_forecaster.forecast_roi(task_desc)
            risk = self.latent_forecaster.predict_risk(task_desc)

        est_tokens = _as_float(forecast.get("est_tokens", 0), 0.0)
        roi_score = _as_float(forecast.get("roi_score", 0.0), 0.0)
        state.metadata["forecast_tokens"] = est_tokens
        state.metadata["forecast_roi"] = roi_score

        logger.info("[%s] [v20:JEPA] Forecast Tokens: %s, ROI: %.2f", state.task_id, est_tokens, roi_score)

        proceed, reason = self.gate_eval.should_proceed(phase, forecast, risk)
        if not proceed:
            logger.error("🚨 [Gate:Reject] %s! Triggering Adaptive Self-Healing...", reason)
            repair_plan = self.ash_selector.trigger_ash(task_id, task_desc, str(risk))
            ash_influence = getattr(self.ash_selector, "last_influence", None)
            if isinstance(ash_influence, dict):
                state.metadata.setdefault("predictor_influence", []).append(ash_influence)
            state.metadata["last_rejection_reason"] = reason
            state.metadata["ash_selected_strategy"] = str((repair_plan or {}).get("selected_strategy", ""))
            self.state_io.save_global_state(state)

        influence = record_influence(
            influence_entry(
                LATENT_PREDICTOR,
                enabled=enabled,
                consulted=needs_predictor,
                before={"proceed": True},
                after={"proceed": bool(proceed)},
                site="forecast_gate",
            ),
            metadata=state.metadata,
        )
        return {
            "proceed": bool(proceed),
            "reason": str(reason),
            "forecast": forecast,
            "risk": risk,
            "predictor_influence": influence,
        }
