from unittest.mock import MagicMock

from nexus.core.state_contracts import NexusState
from nexus.engine.forecast_gate_service import ForecastGateService


def test_forecast_gate_service_uses_metadata_overdrive_without_forecaster_calls():
    latent = MagicMock()
    gate_eval = MagicMock()
    ash_selector = MagicMock()
    state_io = MagicMock()
    gate_eval.should_proceed.return_value = (True, "ok")

    svc = ForecastGateService(
        latent_forecaster=latent,
        gate_eval=gate_eval,
        ash_selector=ash_selector,
        state_io=state_io,
    )
    state = NexusState(task_id="gate-1")
    state.metadata["forecast_tokens"] = 99
    state.metadata["roi_score"] = 0.8
    state.metadata["reject_prob"] = 0.2

    out = svc.evaluate(task_id="gate-1", task_desc="direct", state=state, phase="D")

    assert out["proceed"] is True
    latent.forecast_roi.assert_not_called()
    latent.predict_risk.assert_not_called()
    gate_eval.should_proceed.assert_called_once()
    assert state.metadata["forecast_tokens"] == 99.0
    assert state.metadata["forecast_roi"] == 0.8


def test_forecast_gate_service_reject_triggers_ash_and_state_persist():
    latent = MagicMock()
    gate_eval = MagicMock()
    ash_selector = MagicMock()
    state_io = MagicMock()
    latent.forecast_roi.return_value = {"est_tokens": 42, "roi_score": 0.1}
    latent.predict_risk.return_value = {"reject_prob": 0.9}
    gate_eval.should_proceed.return_value = (False, "too risky")
    ash_selector.trigger_ash.return_value = {"selected_strategy": "rollback"}

    svc = ForecastGateService(
        latent_forecaster=latent,
        gate_eval=gate_eval,
        ash_selector=ash_selector,
        state_io=state_io,
    )
    state = NexusState(task_id="gate-2")
    state.metadata["task_description"] = "risky fix"

    out = svc.evaluate(task_id="gate-2", task_desc="risky fix", state=state, phase="D")

    assert out["proceed"] is False
    ash_selector.trigger_ash.assert_called_once()
    state_io.save_global_state.assert_called_once_with(state)
    assert state.metadata["last_rejection_reason"] == "too risky"
    assert state.metadata["ash_selected_strategy"] == "rollback"
