from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from nexus.services.local_heal.learning_closure_bridge import (
    LearningClosureBridge,
    write_learning_closure,
)
from nexus.services.local_heal.memory_retrieval_adapter import (
    CanonicalEpisodicMemoryLessonStore,
)
from nexus.services.local_heal.orchestrator import HealOrchestrator

LESSONS_RELATIVE = Path(".nexus/memory/learning_lessons.jsonl")
EPISODES_RELATIVE = Path(".nexus/memory/learning_episodes.jsonl")
REPRO = "assert parse('a=1') == {'a': '1'}\n"


def _bridge(tmp_path: Path) -> LearningClosureBridge:
    return LearningClosureBridge(
        path=tmp_path / "learning_closure.jsonl",
        enable_findings=False,
        project_root=tmp_path,
    )


def _op(**overrides) -> SimpleNamespace:
    values = {
        "task_id": "task-qual-1",
        "instance_id": "task-qual-1",
        "attempt_id": "attempt-1",
        "action_id": "action-1",
        "idempotency_key": "idem-qual-1",
        "terminal_outcome": "SUCCEEDED",
        "receipt_path": "receipt:pending",
        "terminal_evidence_present": True,
        "solve_eligible": True,
        "failure_reason": "",
        "problem_statement": "fix the parser so keys are parsed",
        "reproduced": True,
        "verifier_receipt": {"verifier_status": "pass", "receipt_id": "verifier:x"},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _ctx(op: SimpleNamespace, **extra) -> SimpleNamespace:
    return SimpleNamespace(op=op, repro_script=REPRO, **extra)


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _episode(tmp_path: Path) -> dict:
    rows = _rows(tmp_path / EPISODES_RELATIVE)
    assert len(rows) == 1
    return rows[0]


def test_reproduced_verified_op_writes_qualified_physical_episode(tmp_path: Path) -> None:
    op = _op()
    closure = write_learning_closure(_ctx(op), bridge=_bridge(tmp_path))

    episode = _episode(tmp_path)
    assert episode["qualification_status"] == "QUALIFIED"
    qualification = episode["qualification"]
    assert set(qualification) == {"repeatability", "prevention_rule", "authority_qualification"}
    assert qualification["repeatability"]["verifier_status"] == "pass"
    assert qualification["authority_qualification"]["receipt_id"] == "verifier:x"
    assert episode["terminal_evidence"]["receipt"] == "verifier:x"

    reflection = closure["reflection"]
    assert reflection["reflection_status"] == "written"
    assert reflection["evidence_origin"] == "physical"

    lessons = _rows(tmp_path / LESSONS_RELATIVE)
    assert len(lessons) == 1
    assert lessons[0]["retrieval_eligible"] is True
    assert lessons[0]["lesson_id"] == reflection["lesson_ids"][0]

    hits = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path).query(
        query_text="fix the parser keys", limit=3
    )
    assert [hit["episode_id"] for hit in hits] == [episode["episode_id"]]


def test_missing_reproduced_stays_unqualified_and_simulated(tmp_path: Path) -> None:
    op = _op()
    del op.reproduced
    write_learning_closure(_ctx(op), bridge=_bridge(tmp_path))

    episode = _episode(tmp_path)
    assert episode["qualification_status"] == "UNQUALIFIED"
    assert "repeatability" not in episode["qualification"]

    lessons = _rows(tmp_path / LESSONS_RELATIVE)
    assert len(lessons) == 1
    assert lessons[0]["evidence_origin"] != "physical"
    assert lessons[0]["retrieval_eligible"] is False


def test_missing_verifier_receipt_stays_unqualified(tmp_path: Path) -> None:
    op = _op()
    del op.verifier_receipt
    write_learning_closure(_ctx(op), bridge=_bridge(tmp_path))

    episode = _episode(tmp_path)
    assert episode["qualification_status"] == "UNQUALIFIED"
    assert "authority_qualification" not in episode["qualification"]


def test_preset_op_qualification_is_respected(tmp_path: Path) -> None:
    preset = {
        "repeatability": {"kind": "manual"},
        "prevention_rule": {"kind": "manual"},
        "authority_qualification": {"kind": "manual"},
    }
    op = _op(qualification=preset)
    write_learning_closure(_ctx(op), bridge=_bridge(tmp_path))

    episode = _episode(tmp_path)
    assert episode["qualification"] == preset
    assert op.qualification == preset


def test_failed_verified_episode_is_qualified_failure_polarity(tmp_path: Path) -> None:
    op = _op(
        terminal_outcome="FAILED",
        solve_eligible=False,
        failure_reason="verifier failed",
        verifier_receipt={"verifier_status": "fail", "receipt_id": "verifier:y"},
    )
    write_learning_closure(_ctx(op), bridge=_bridge(tmp_path))

    episode = _episode(tmp_path)
    assert episode["qualification_status"] == "QUALIFIED"
    assert episode["qualification"]["repeatability"]["verifier_status"] == "fail"

    lessons = _rows(tmp_path / LESSONS_RELATIVE)
    assert len(lessons) == 1
    assert lessons[0]["evidence_origin"] == "physical"
    assert lessons[0]["outcome_polarity"] == "failure"


def test_retry_exit_verifier_fail_is_parked_and_reflected(tmp_path: Path) -> None:
    # Real retry flow: failed heal exits at gate "patcher" with verifier-fail evidence.
    op = SimpleNamespace(
        task_id="task-qual-2",
        instance_id="task-qual-2",
        attempt=2,
        attempt_id="attempt-2",
        action_id="action-2",
        idempotency_key="idem-qual-2",
        receipt_path="receipt:pending",
        terminal_evidence_present=True,
        solve_eligible=False,
        failure_reason="LOGIC_REGRESSION:VERIFICATION_FAILED",
        failure_class="semantic_wrong",
        problem_statement="fix the parser so keys are parsed",
        reproduced=True,
        final_patch="--- a/parser.py\n+++ b/parser.py\n@@\n-x\n+y\n",
    )
    ctx = SimpleNamespace(op=op, repro_script=REPRO, gov=SimpleNamespace(gate_exit="patcher"))
    HealOrchestrator._bind_applied_attribution_inputs(object.__new__(HealOrchestrator), ctx)
    assert op.verifier_receipt["verifier_status"] == "fail"

    closure = write_learning_closure(ctx, bridge=_bridge(tmp_path))

    episode = _episode(tmp_path)
    assert episode["terminal_outcome"] == "PARKED"
    assert episode["qualification_status"] == "QUALIFIED"
    assert episode["terminal_evidence"]["verifier_status"] == "fail"
    reflection = closure["reflection"]
    assert reflection["reflection_status"] == "written"
    lessons = _rows(tmp_path / LESSONS_RELATIVE)
    assert len(lessons) == 1
    assert lessons[0]["outcome_polarity"] == "failure"
    assert lessons[0]["evidence_origin"] == "physical"
