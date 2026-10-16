"""Counted A/B lanes: learn_mode / learn_phase_slo outcomes do not depend on earlier runs.

Before, both executors read the shared project learn store; ``phase_slo_pass`` flipped with the
rows earlier runs left inside the 300-row window, and the reports carried wall-clock timestamps
and host paths, all of which reached the with-Nexus prompt (consumer payload).  In counted
lanes (``NEXUS_SYMMETRIC_PROMPT=1``) they now run on a fresh empty store per call.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.capability_executor_registry import (
    COUNTED_FIXED_TIMESTAMP,
    _exec_learn_mode,
    _exec_learn_phase_slo,
)


def _plan(root: Path) -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(
        plan_id="p",
        task_id="sprint-abc-s0-a1",
        phases=["R"],
        constraints={"workspace_root": str(root)},
    )


def _seed_failing_phase_rows(root: Path) -> None:
    from nexus.research.learn_mode import LearnModeService

    LearnModeService(project_root=root, run_root=root).sync_phase_learning_closure(
        topic="earlier-run", metrics={"x": 1}, phase_status={"P": "failed", "X": "failed"}
    )


def _outcome(receipt: Any) -> dict[str, Any]:
    return dict(receipt.outcome)


def _evidence_view(name: str, receipt: Any) -> str:
    """The strict-lane [NEXUS CAPABILITY EVIDENCE] rendering of this capability's payload."""

    from nexus.services.capability_evidence_bundle import extract_bounded_consumer_payload
    from nexus.services.online_nexus_context import (
        _SYMMETRIC_PAYLOAD_SPEC,
        whitelist_block,
    )

    payload = extract_bounded_consumer_payload(
        capability=name, response={"outcome": _outcome(receipt)}, success=True
    )
    return json.dumps(whitelist_block(payload, _SYMMETRIC_PAYLOAD_SPEC), sort_keys=True)


@pytest.mark.parametrize(
    "executor,name", [(_exec_learn_phase_slo, "learn_phase_slo"), (_exec_learn_mode, "learn_mode")]
)
def test_counted_lane_learn_outcome_is_identical_across_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, executor: Any, name: str
) -> None:
    monkeypatch.setenv("NEXUS_SYMMETRIC_PROMPT", "1")
    first = executor(_plan(tmp_path), "task")
    _seed_failing_phase_rows(tmp_path)  # an earlier run's rows in the project store
    second = executor(_plan(tmp_path), "task")
    assert first.gate_passed and second.gate_passed
    assert _outcome(first) == _outcome(second)
    assert _evidence_view(name, first) == _evidence_view(name, second)
    text = json.dumps(_outcome(second), default=str)
    assert str(tmp_path) not in text and "nexus-counted-learn-" not in text
    assert "resolved_run_root" not in _outcome(second) and "output_paths" not in _outcome(second)
    stamps = {m for m in re.findall(r'"timestamp": "([^"]*)"', text)}
    assert stamps <= {COUNTED_FIXED_TIMESTAMP}
    if name == "learn_phase_slo":
        assert _outcome(second)["result"]["phase_slo_pass"] is True  # empty store, documented


def test_outside_counted_lanes_the_project_store_is_read_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NEXUS_SYMMETRIC_PROMPT", raising=False)
    _seed_failing_phase_rows(tmp_path)
    receipt = _exec_learn_phase_slo(_plan(tmp_path), "task")
    outcome = _outcome(receipt)
    assert outcome["result"]["phase_slo_pass"] is False  # reflects the project store
    assert outcome["resolved_run_root"] == str(tmp_path.resolve())
    assert outcome["result"]["timestamp"]
    assert outcome["result"]["timestamp"] != COUNTED_FIXED_TIMESTAMP
