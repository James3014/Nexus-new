from types import SimpleNamespace

from nexus.core.commander import Commander
from nexus.core.state_contracts import NexusState


class _FakeStateIO:
    def __init__(self, state):
        self.state = state
        self.saved = []

    def load_global_state(self):
        return self.state

    def save_global_state(self, state):
        self.saved.append(state)


def test_commander_runs_health_update_and_respects_auto_repair_toggle(monkeypatch, tmp_path):
    state = NexusState(task_id="cmd-health", current_phase="R")
    state.metadata["auto_repair_enabled"] = False
    io = _FakeStateIO(state)
    commander = Commander(run_dir=str(tmp_path), state_io=io, router=SimpleNamespace(), context_hub=SimpleNamespace())

    called = {"service": 0}

    class _FakeHealService:
        def run_cycle(self, s):
            called["service"] += 1
            s.metadata["health_snapshot"] = {"overall_score": 55.0}

    commander.self_heal_service = _FakeHealService()

    result = commander.next_step()

    assert result == "RUN_SKILL:repair"
    assert called["service"] == 1
    assert io.saved


def test_commander_skips_health_loop_during_benchmark_run(tmp_path):
    state = NexusState(task_id="cmd-benchmark", current_phase="R")
    state.metadata["benchmark_run"] = True
    io = _FakeStateIO(state)
    commander = Commander(run_dir=str(tmp_path), state_io=io, router=SimpleNamespace(), context_hub=SimpleNamespace())

    called = {"service": 0}

    class _FakeHealService:
        def run_cycle(self, s):
            called["service"] += 1
            s.metadata["health_snapshot"] = {"overall_score": 55.0}

    commander.self_heal_service = _FakeHealService()

    result = commander.next_step()

    assert result == "RUN_SKILL:repair"
    assert called["service"] == 0
