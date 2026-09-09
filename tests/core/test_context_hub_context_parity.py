from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from nexus.core.context_hub import ContextDependencies, ContextHub


class _State:
    def __init__(self):
        self.task_id = "state-task"
        self.metadata = {
            "task_description": "deterministic context parity",
            "chat_history": ["first turn", "second turn", "third turn"],
        }


def _caller_hub(tmp_path: Path, *, handoff: dict, aggression: float, monkeypatch) -> ContextHub:
    state = _State()
    monkeypatch.setattr("nexus.core.state_io.StateIO.load_global_state", lambda _self: state)
    monkeypatch.setattr(
        "nexus.core.context_text_store.ContextTextStore.load_last_handoff",
        lambda _self: dict(handoff),
    )
    monkeypatch.setattr(
        "nexus.core.policy_loader.PolicyLoader.load",
        staticmethod(lambda _root: SimpleNamespace(global_nas_aggression=aggression)),
    )
    monkeypatch.setattr(
        "nexus.core.context_hub.ToonRenderer",
        type(
            "DeterministicRenderer",
            (),
            {"render": staticmethod(lambda _state, aggression=0.0: f"toon:{aggression:.2f}")},
        ),
    )
    monkeypatch.setattr(
        "nexus.core.context_hub.prune_dialogue", lambda history: "pruned:" + "|".join(history)
    )

    def deterministic_compactor(_root):
        return SimpleNamespace(
            compact=lambda value, confidence=0.5: {
                "task_id": value["task_id"],
                "confidence": confidence,
                "metadata": value["metadata"],
            }
        )

    monkeypatch.setattr("nexus.core.context_compactor.ContextCompactor", deterministic_compactor)
    monkeypatch.setattr(
        "nexus.core.context_runtime_bridge.ContextCompactor", deterministic_compactor
    )
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)
    return hub


def _donor_contexts(
    *, handoff: dict, aggression: float, budgets: list[int], params: list[dict]
) -> list[str]:
    script = r"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

path = Path("/private/tmp/astra-production-integrated-20260909/nexus/core/context_hub.py")
spec = importlib.util.spec_from_file_location("donor_context_hub", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class State:
    def __init__(self):
        self.task_id = "state-task"
        self.metadata = {
            "task_description": "deterministic context parity",
            "chat_history": ["first turn", "second turn", "third turn"],
        }

state = State()
handoff = json.loads(__HANDOFF__)
aggression = float(__AGGRESSION__)
hub = module.ContextHub(".", deps=module.ContextDependencies(), strict_deps=True)
hub.state_io.load_global_state = lambda: state
hub._text_store.load_last_handoff = lambda: dict(handoff)
import nexus.core.policy_loader as policy_loader
policy_loader.PolicyLoader.load = staticmethod(lambda _root: SimpleNamespace(global_nas_aggression=aggression))
module.ToonRenderer.render = staticmethod(lambda _state, aggression=0.0: f"toon:{aggression:.2f}")
module.prune_dialogue = lambda history: "pruned:" + "|".join(history)
import nexus.core.context_compactor as context_compactor
context_compactor.ContextCompactor = lambda _root: SimpleNamespace(compact=lambda value, confidence=0.5: {
    "task_id": value["task_id"], "confidence": confidence, "metadata": value["metadata"]
})
print(json.dumps([
    hub.assemble_context("state-task", [0, 1], budget=budget, bayesian_params=params)
    for budget, params in zip(__BUDGETS__, __PARAMS__)
]))
"""
    script = (
        script.replace("__HANDOFF__", json.dumps(json.dumps(handoff)))
        .replace("__AGGRESSION__", repr(aggression))
        .replace("__BUDGETS__", repr(budgets))
        .replace("__PARAMS__", repr(params))
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = "/private/tmp/astra-production-integrated-20260909"
    result = subprocess.run(
        [sys.executable, "-c", script], check=True, capture_output=True, text=True, env=env
    )
    return json.loads(result.stdout)


def test_context_hub_full_context_matches_frozen_donor_across_budget_and_seams(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("NEXUS_PHASE", "P")
    state = _State()
    handoff = {"task_id": "handoff-task", "state_token": "handoff-token"}
    aggression = 0.6
    params = [{}, {"nas_aggression": 0.0}, {"nas_aggression": 0.0}]
    probe = _caller_hub(tmp_path, handoff=handoff, aggression=aggression, monkeypatch=monkeypatch)
    probe_value = probe.assemble_context(
        state.task_id, [0, 1], budget=10_000, bayesian_params={"nas_aggression": 0.0}
    )
    estimated = int(
        sum(
            len(str(value))
            for value in (
                "L0: [BOUNDARIES: core, metrics] [PROHIBITED: delete-history, skip-verify]",
                "L1: [TASK: handoff-task] [PHASE: P] [TOKEN: handoff-token] [AOS: 131.5]",
                state.metadata["chat_history"],
                "toon:0.00",
                json.dumps(
                    {"task_id": state.task_id, "confidence": 0.5, "metadata": state.metadata}
                ),
            )
        )
        // 3.8
    )
    budgets = [10_000, 1, estimated]
    assert "STRUCTURED CONTEXT" in probe_value
    caller = _caller_hub(tmp_path, handoff=handoff, aggression=aggression, monkeypatch=monkeypatch)
    actual = [
        caller.assemble_context(state.task_id, [0, 1], budget=budget, bayesian_params=bayesian)
        for budget, bayesian in zip(budgets, params)
    ]
    donor = _donor_contexts(handoff=handoff, aggression=aggression, budgets=budgets, params=params)
    assert actual == donor


def test_context_hub_full_context_matches_donor_when_handoff_phase_falls_back(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("NEXUS_PHASE", "X")
    handoff = {"task_id": "handoff-task", "state_token": "handoff-token"}
    params = [{"nas_aggression": 0.0, "confidence": 0.8}]
    caller = _caller_hub(tmp_path, handoff=handoff, aggression=0.6, monkeypatch=monkeypatch)
    donor = _donor_contexts(handoff=handoff, aggression=0.6, budgets=[10_000], params=params)
    actual = [
        caller.assemble_context("state-task", [0, 1], budget=10_000, bayesian_params=params[0])
    ]
    assert actual == donor
    assert "[PHASE: X]" in actual[0]
