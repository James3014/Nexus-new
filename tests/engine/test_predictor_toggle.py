"""Per-site tests for the latent predictor switch and ``predictor_influence``."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.state_contracts import NexusState
from nexus.engine.forecast_gate_service import ForecastGateService
from nexus.engine.repair_attempt_service import RepairAttemptService
from nexus.engine.self_healing_selector import SelfHealingSelector
from nexus.learning import predictor_toggle as toggle

LATENT_ENV = "NEXUS_LATENT_PREDICTOR"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv(LATENT_ENV, raising=False)
    toggle.drain_ledger()
    yield
    toggle.drain_ledger()


def _only(state, name):
    entries = [e for e in state.metadata.get("predictor_influence", []) if e["name"] == name]
    assert len(entries) == 1
    return entries[0]


# ---------------------------------------------------------------- toggle


@pytest.mark.parametrize("value", ["off", "OFF", "0", "false", "no", " off "])
def test_switch_off_values(monkeypatch, value):
    monkeypatch.setenv(LATENT_ENV, value)
    assert toggle.predictor_enabled(toggle.LATENT_PREDICTOR) is False


@pytest.mark.parametrize("value", ["", "on", "1", "true", "anything"])
def test_switch_default_and_on(monkeypatch, value):
    monkeypatch.setenv(LATENT_ENV, value)
    assert toggle.predictor_enabled(toggle.LATENT_PREDICTOR) is True


def test_changed_decision_requires_consulted():
    assert (
        toggle.influence_entry("p", enabled=True, consulted=False, before=1, after=2)[
            "changed_decision"
        ]
        is False
    )
    assert (
        toggle.influence_entry("p", enabled=True, consulted=True, before=1, after=2)[
            "changed_decision"
        ]
        is True
    )
    assert (
        toggle.influence_entry("p", enabled=True, consulted=True, before=1, after=1)[
            "changed_decision"
        ]
        is False
    )


# ---------------------------------------------------------- forecast gate


def _gate(latent, verdict):
    gate_eval = MagicMock()
    gate_eval.should_proceed.return_value = verdict
    ash = MagicMock()
    ash.trigger_ash.return_value = {"selected_strategy": "rollback"}
    ash.last_influence = None
    svc = ForecastGateService(
        latent_forecaster=latent, gate_eval=gate_eval, ash_selector=ash, state_io=MagicMock()
    )
    return svc, gate_eval


def _latent(roi=0.1, reject=0.9):
    latent = MagicMock()
    latent.forecast_roi.return_value = {"est_tokens": 42, "roi_score": roi}
    latent.predict_risk.return_value = {"reject_prob": reject}
    return latent


def test_gate_on_reject_records_changed_decision():
    latent = _latent()
    svc, _ = _gate(latent, (False, "too risky"))
    state = NexusState(task_id="g1")
    out = svc.evaluate(task_id="g1", task_desc="risky", state=state)
    assert out["proceed"] is False
    entry = _only(state, toggle.LATENT_PREDICTOR)
    assert entry["enabled"] and entry["consulted"] and entry["changed_decision"] is True
    assert entry["before"] == {"proceed": True} and entry["after"] == {"proceed": False}
    assert out["predictor_influence"] == entry


def test_gate_on_accept_records_unchanged_decision():
    latent = _latent(roi=0.9, reject=0.0)
    svc, _ = _gate(latent, (True, "ok"))
    state = NexusState(task_id="g2")
    svc.evaluate(task_id="g2", task_desc="fine", state=state)
    entry = _only(state, toggle.LATENT_PREDICTOR)
    assert entry["consulted"] is True and entry["changed_decision"] is False


def test_gate_off_matches_no_forecaster_path(monkeypatch):
    monkeypatch.setenv(LATENT_ENV, "off")
    latent = _latent()
    svc, gate_eval = _gate(latent, (False, "too risky"))
    state = NexusState(task_id="g3")
    off = svc.evaluate(task_id="g3", task_desc="risky", state=state)

    monkeypatch.delenv(LATENT_ENV)
    absent_svc, _ = _gate(None, (False, "too risky"))
    absent_state = NexusState(task_id="g3")
    absent = absent_svc.evaluate(task_id="g3", task_desc="risky", state=absent_state)

    for key in ("proceed", "reason", "forecast", "risk"):
        assert off[key] == absent[key]
    assert off["proceed"] is True
    latent.forecast_roi.assert_not_called()
    latent.predict_risk.assert_not_called()
    gate_eval.should_proceed.assert_not_called()
    entry = _only(state, toggle.LATENT_PREDICTOR)
    assert entry["enabled"] is False and entry["consulted"] is False
    assert entry["changed_decision"] is False


def test_gate_metadata_overdrive_is_not_a_consultation():
    latent = _latent()
    svc, _ = _gate(latent, (True, "ok"))
    state = NexusState(task_id="g4")
    state.metadata["roi_score"] = 0.8
    svc.evaluate(task_id="g4", task_desc="direct", state=state)
    entry = _only(state, toggle.LATENT_PREDICTOR)
    assert entry["consulted"] is False and entry["changed_decision"] is False


# ------------------------------------------------------ self healing selector


def _selector(predictor):
    strategies = {
        "cheap": SimpleNamespace(success_base=0.9),
        "safe": SimpleNamespace(success_base=0.8),
    }
    matrix = SimpleNamespace(strategies=strategies)
    resolver = MagicMock()
    resolver.resolve.side_effect = lambda strat, ctx: SimpleNamespace(
        strategy_id="cheap" if strat.success_base == 0.9 else "safe", commands=[]
    )
    return SelfHealingSelector(predictor, matrix, resolver)


class _Predictor:
    """Penalises the cheap strategy: low ROI for 'cheap', high for 'safe'."""

    def forecast_roi(self, desc):
        return {"roi_score": 0.2 if "cheap" in desc else 1.0}

    def predict_risk(self, desc):
        return {"status": "CLEAR", "reject_prob": 0.0}


def test_selector_on_reorders_and_records_change():
    sel = _selector(_Predictor())
    ranked = sel.rank_strategies("t", "ctx")
    assert [r["strategy"] for r in ranked] == ["safe", "cheap"]
    info = sel.last_influence
    assert info["enabled"] and info["consulted"] and info["changed_decision"] is True
    assert info["before"] == "cheap" and info["after"] == "safe"
    assert sel.trigger_ash("n", "t", "ctx")["predictor_influence"]["changed_decision"] is True


def test_selector_on_neutral_predictor_does_not_change():
    class Neutral(_Predictor):
        def forecast_roi(self, desc):
            return {"roi_score": 1.0}

    sel = _selector(Neutral())
    sel.rank_strategies("t", "ctx")
    assert sel.last_influence["consulted"] is True
    assert sel.last_influence["changed_decision"] is False


def test_selector_off_equals_no_predictor_path(monkeypatch):
    monkeypatch.setenv(LATENT_ENV, "off")
    off_sel = _selector(_Predictor())
    off = off_sel.rank_strategies("t", "ctx")
    monkeypatch.delenv(LATENT_ENV)
    absent = _selector(None).rank_strategies("t", "ctx")

    def strip(rows):
        return [(r["strategy"], r["success_prob"], r["prediction"], r["risk_status"]) for r in rows]

    assert strip(off) == strip(absent)
    assert [r["strategy"] for r in off] == ["cheap", "safe"]
    assert off_sel.last_influence["enabled"] is False
    assert off_sel.last_influence["consulted"] is False
    assert off_sel.last_influence["changed_decision"] is False


# ---------------------------------------------------------- repair attempt


def _repair():
    return RepairAttemptService(project_root="/tmp/x")


def _lewm_state():
    state = NexusState(task_id="r1")
    state.metadata["sim_lewm"] = True
    state.metadata["task_description"] = "touch NexusState serialization"
    return state


# LeWM was archived 2026-10-12: the three historical node ids below now assert the
# module-absent path (never consulted, never aborts) regardless of any switch.


def test_lewm_on_reject_aborts_and_records_change():
    state = _lewm_state()
    assert _repair()._run_lewm_sim(state) is None
    entry = _only(state, toggle.LEWM_PREDICTOR)
    assert entry["consulted"] is False and entry["changed_decision"] is False
    assert entry["before"] == "continue" and entry["after"] == "continue"
    assert not hasattr(RepairAttemptService, "lewm_cls")


def test_lewm_on_passed_does_not_change_decision():
    state = _lewm_state()
    assert _repair()._run_lewm_sim(state) is None
    entry = _only(state, toggle.LEWM_PREDICTOR)
    assert entry["consulted"] is False and entry["changed_decision"] is False
    assert "lewm_sim_status" not in state.metadata


def test_lewm_off_matches_sim_lewm_unset(monkeypatch):
    monkeypatch.setenv("NEXUS_LEWM_PREDICTOR", "off")
    off_state = _lewm_state()
    assert _repair()._run_lewm_sim(off_state) is None

    monkeypatch.delenv("NEXUS_LEWM_PREDICTOR")
    on_state = _lewm_state()
    assert _repair()._run_lewm_sim(on_state) is None
    plain = NexusState(task_id="r1")
    plain.metadata["task_description"] = "touch NexusState serialization"
    assert _repair()._run_lewm_sim(plain) is None

    # The switch is inert: on and off record the identical module-absent entry.
    assert _only(off_state, toggle.LEWM_PREDICTOR) == _only(on_state, toggle.LEWM_PREDICTOR)
    assert "lewm_sim_status" not in off_state.metadata
    assert "predictor_influence" not in plain.metadata


def test_lewm_module_not_imported_by_engine_sites():
    import subprocess
    import sys
    from pathlib import Path

    code = (
        "import sys\n"
        "import nexus.engine.bootstrap, nexus.engine.repair_attempt_service\n"
        "print('LEWM_LOADED' if 'nexus.learning.lewm_predictor' in sys.modules else 'LEWM_ABSENT')\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert out.returncode == 0, out.stderr
    assert "LEWM_ABSENT" in out.stdout


# ------------------------------------------------ capability executor receipt


def _forecast_plan(tmp_path):
    return CapabilityExecutionPlan(
        plan_id="p1",
        task_id="fg-toggle",
        phases=["D"],
        required_capabilities=["forecast_gate"],
        skill_slots={},
        constraints={"workspace_root": str(tmp_path)},
    )


def test_exec_forecast_gate_receipt_carries_predictor_influence(tmp_path, monkeypatch):
    from nexus.core import capability_executor_registry as reg

    fake_cls = MagicMock()
    fake_cls.return_value = _latent(roi=0.9, reject=0.0)
    with patch("nexus.learning.latent_predictor_v20.LatentPredictorV20", fake_cls):
        receipt = reg._exec_forecast_gate(_forecast_plan(tmp_path), "fine task")
    outcome = receipt.outcome
    entries = outcome["predictor_influence"]
    assert [e["name"] for e in entries] == [toggle.LATENT_PREDICTOR]
    assert entries[0]["consulted"] is True and entries[0]["enabled"] is True
    fake_cls.assert_called()


def test_exec_forecast_gate_off_never_builds_predictor(tmp_path, monkeypatch):
    from nexus.core import capability_executor_registry as reg

    monkeypatch.setenv(LATENT_ENV, "off")
    fake_cls = MagicMock()
    with patch("nexus.learning.latent_predictor_v20.LatentPredictorV20", fake_cls):
        receipt = reg._exec_forecast_gate(_forecast_plan(tmp_path), "fine task")
    fake_cls.assert_not_called()
    entries = receipt.outcome["predictor_influence"]
    assert entries[0]["enabled"] is False and entries[0]["consulted"] is False
    assert entries[0]["changed_decision"] is False
