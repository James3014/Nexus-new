from __future__ import annotations

import pytest

from nexus.orchestrator.shepherd_supervisor import (
    ShepherdSupervisor,
    ActionTrace,
    ForkReceipt,
)


class TestShepherdSupervisor:

    def test_fork_records_in_log(self):
        sup = ShepherdSupervisor()
        sup.fork("agent-1", "new_behavior")
        assert len(sup._fork_log) == 1  # noqa: SLF001

    def test_fork_returns_fork_receipt(self):
        sup = ShepherdSupervisor()
        receipt = sup.fork("agent-1", "new_behavior")
        assert isinstance(receipt, ForkReceipt)
        assert receipt.subagent_id == "agent-1"
        assert receipt.new_definition == "new_behavior"
        assert receipt.fork_id != ""

    def test_observe_returns_latest_action_trace(self):
        sup = ShepherdSupervisor()
        sup.record_trace(ActionTrace("agent-1", 1, "act1", "ok", 1.0))
        sup.record_trace(ActionTrace("agent-1", 2, "act2", "ok", 2.0))
        trace = sup.observe("agent-1")
        assert trace is not None
        assert trace.step == 2
        assert trace.action == "act2"

    def test_replay_to_returns_traces_up_to_step(self):
        sup = ShepherdSupervisor()
        for i in range(5):
            sup.record_trace(ActionTrace("agent-1", i, f"act{i}", "ok", float(i)))
        replay = sup.replay_to("agent-1", 2)
        assert len(replay) == 3
        assert replay[0].step == 0
        assert replay[-1].step == 2

    def test_shepherd_supervisor_does_not_manage_subagents(self):
        sup = ShepherdSupervisor()
        receipt = sup.fork("agent-x", "def")
        assert receipt.subagent_id == "agent-x"
        trace = sup.observe("nonexistent")
        assert trace is None
