from __future__ import annotations

from types import SimpleNamespace

from nexus.core.swarm import NexusSwarmOrchestrator


class NoWriteSwarm(NexusSwarmOrchestrator):
    def _analyze(self, context: str = "") -> str:
        return f"analysis:{context}"

    def _consensus_plan(self, analysis: str) -> str:
        return f"plan:{analysis}"

    def _repair(self, plan: str):
        self.repair_seen_plan = plan
        return {"status": "PASS"}

    def _verify(self, repair_result):
        return repair_result["status"]


def test_swarm_enters_quiet_moment_before_repair():
    calls = []

    def observe(event):
        calls.append(("observe", event["production_writes_allowed"]))
        return {"status": "observed", "event_type": event["event_type"]}

    def rollback(event):
        calls.append(("rollback", event["production_writes_allowed"]))
        return {"status": "armed", "event_type": event["event_type"]}

    engine = SimpleNamespace(
        project_root=".",
        swarm_observer=observe,
        swarm_rollback=rollback,
    )
    swarm = NoWriteSwarm(engine, "fix cross-module race")

    result = swarm.run()

    assert result["status"] == "PASS"
    assert result["quiet_moment"]["schema_version"] == "nexus_quiet_moment.v1"
    assert result["quiet_moment"]["production_writes_allowed"] is False
    assert result["quiet_moment"]["allowed_actions"] == ["observe", "report", "rollback"]
    assert calls == [("observe", False), ("rollback", False)]
