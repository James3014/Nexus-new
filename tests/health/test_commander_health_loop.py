from types import SimpleNamespace

from nexus.core.commander import Commander
from nexus.core.harness import default_director
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


def test_red_r1_logical_repair_token_mismatches_physical_capability_gate():
    """R1: Logical tool 'repair' is physically forbidden by Phase R CapabilityGate."""
    status, messages = default_director.run_pre_execute(
        "repair",
        {"target_file": "sample.py"},
        {"phase": "R", "budget_remaining": 5000},
    )
    assert status == "BLOCKED"
    assert any("forbidden in Phase R" in msg for msg in messages)


def test_h1_normal_r_path_allows_repair(tmp_path):
    """H1: Normal R-stage state with sufficient budget and permitted preflight returns RUN_SKILL:repair."""
    state = NexusState(task_id="h1-normal", current_phase="R")
    state.metadata["budget_token"] = 5000
    state.total_token_usage = 0
    io = _FakeStateIO(state)
    commander = Commander(
        run_dir=str(tmp_path),
        state_io=io,
        router=SimpleNamespace(),
        context_hub=SimpleNamespace(),
    )
    result = commander.next_step()
    assert result == "RUN_SKILL:repair"


def test_h2_canonical_capability_gate_denial_hard_stops(monkeypatch, tmp_path):
    """H2: When canonical CapabilityGate denies the physical preflight action, Commander hard-stops with HARNESS_BLOCKED."""
    state = NexusState(task_id="h2-cap-denial", current_phase="R")
    io = _FakeStateIO(state)
    commander = Commander(
        run_dir=str(tmp_path),
        state_io=io,
        router=SimpleNamespace(),
        context_hub=SimpleNamespace(),
    )

    from nexus.governance.capability_gate import CapabilityGate

    monkeypatch.setattr(
        CapabilityGate,
        "get_tools",
        lambda self, phase: ["read_file", "view_file"],
    )

    result = commander.next_step()
    assert result == "HARNESS_BLOCKED"


def test_h3_cost_hook_blocked_hard_stops(tmp_path):
    """H3: When budget is insufficient for safe_patch (cost 900+300=1200), CostHook blocks and Commander hard-stops."""
    state = NexusState(task_id="h3-cost-blocked", current_phase="R")
    state.metadata["target_file"] = "app.py"
    state.metadata["budget_token"] = 500
    state.total_token_usage = 0  # remaining = 500 < 1200
    io = _FakeStateIO(state)
    commander = Commander(
        run_dir=str(tmp_path),
        state_io=io,
        router=SimpleNamespace(),
        context_hub=SimpleNamespace(),
    )

    result = commander.next_step()
    assert result == "HARNESS_BLOCKED"


def test_h4_cost_hook_warn_stays_advisory(tmp_path):
    """H4: When predicted cost is >70% but <=100% of remaining budget, CostHook WARN stays advisory."""
    state = NexusState(task_id="h4-cost-warn", current_phase="R")
    state.metadata["target_file"] = "app.py"
    state.metadata["budget_token"] = 1500
    state.total_token_usage = 0  # predicted 1200 > 1500 * 0.7 (1050), but <= 1500
    io = _FakeStateIO(state)
    commander = Commander(
        run_dir=str(tmp_path),
        state_io=io,
        router=SimpleNamespace(),
        context_hub=SimpleNamespace(),
    )

    result = commander.next_step()
    assert result == "RUN_SKILL:repair"


def test_h5_critique_hook_warn_stays_advisory(monkeypatch, tmp_path):
    """H5: When CritiqueHook raises advisory prescan exception, it remains WARN and does not block repair."""
    state = NexusState(task_id="h5-critique-warn", current_phase="R")
    state.metadata["target_file"] = "app.py"
    state.metadata["budget_token"] = 5000
    state.total_token_usage = 0
    io = _FakeStateIO(state)
    commander = Commander(
        run_dir=str(tmp_path),
        state_io=io,
        router=SimpleNamespace(),
        context_hub=SimpleNamespace(),
    )

    from scripts.engine.critique_engine import CritiqueEngine

    def _failing_prescan(self, plan_text):
        raise ValueError("Aesthetic rule: line length check advisory")

    monkeypatch.setattr(CritiqueEngine, "prescan", _failing_prescan)

    result = commander.next_step()
    assert result == "RUN_SKILL:repair"


def test_h6_legacy_harness_enforce_block_false_cannot_bypass_denial(tmp_path):
    """H6: Old compatibility bypass harness_enforce_block=False cannot reopen execution on hard denial."""
    state = NexusState(task_id="h6-bypass-retired", current_phase="R")
    state.metadata["target_file"] = "app.py"
    state.metadata["harness_enforce_block"] = False
    state.metadata["budget_token"] = 500
    state.total_token_usage = 0  # budget hard denial
    io = _FakeStateIO(state)
    commander = Commander(
        run_dir=str(tmp_path),
        state_io=io,
        router=SimpleNamespace(),
        context_hub=SimpleNamespace(),
    )

    result = commander.next_step()
    assert result == "HARNESS_BLOCKED"
