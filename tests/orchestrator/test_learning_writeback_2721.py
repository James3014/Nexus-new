"""#2721: P1 post-verification learning write-back and the read-only switch."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.core.belief_engine import BeliefEngine
from nexus.orchestrator import p1_learning_writeback as lw
from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore


def _contract(target: Path) -> SimpleNamespace:
    # Real shape (task_build): target_repo_root = the task's worktree,
    # target_worktree_root = its parent (the Gateway-managed targets directory).
    return SimpleNamespace(
        task_id="t-2721",
        objective="Fix the retry counter in pkg/mod.py",
        target_repo_root=str(target),
        target_worktree_root=str(target.parent),
    )


def _candidate() -> SimpleNamespace:
    return SimpleNamespace(changed_files=["pkg/mod.py", "tests/test_mod.py"], untracked_files=[])


def _verified(passed: bool) -> SimpleNamespace:
    return SimpleNamespace(
        verifier_gate_passed=passed,
        candidate_state_hash="ab" * 32,
        verifier_evidence=(
            SimpleNamespace(
                command="python -m pytest tests/test_mod.py",
                status="COMPLETED",
                exit_code=0 if passed else 1,
            ),
        ),
    )


@pytest.fixture
def state_root(tmp_path, monkeypatch):
    root = tmp_path / "state"
    root.mkdir()
    monkeypatch.setenv("NEXUS_STATE_ROOT", str(root))
    monkeypatch.delenv(lw.WRITEBACK_ENV, raising=False)
    monkeypatch.delenv(lw.READ_ONLY_ENV, raising=False)
    # Treat tmp_path/nexus-runtime-targets as the Gateway-managed targets directory.
    monkeypatch.setattr(
        "nexus.core.state_root._target_worktree_bases",
        lambda roots: {tmp_path / "nexus-runtime-targets"},
    )
    return root


def _target(tmp_path: Path) -> Path:
    # A Gateway-managed target worktree (…/nexus-runtime-targets/<task>) moves to NEXUS_STATE_ROOT.
    target = tmp_path / "nexus-runtime-targets" / "t-2721"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _run(tmp_path, passed=True, verdict="PROVEN", **kw):
    kw.setdefault("fail_to_pass_status", None)
    return lw.run_learning_writeback(
        contract=_contract(kw.pop("target", None) or _target(tmp_path)),
        candidate=_candidate(),
        verified=_verified(passed),
        resolution_verdict=verdict,
        **kw,
    )


def test_disabled_by_default_writes_nothing(tmp_path, state_root):
    obs = _run(tmp_path)
    assert obs["enabled"] is False and obs["skip_reason"] == "DISABLED"
    assert not (state_root / ".nexus").exists()


def test_enabled_writes_card_and_belief_to_reader_root(tmp_path, state_root, monkeypatch):
    monkeypatch.setenv(lw.WRITEBACK_ENV, "1")
    monkeypatch.setattr(
        "nexus.core.state_root._target_worktree_bases",
        lambda roots: {tmp_path / "nexus-runtime-targets"},
    )
    target = _target(tmp_path)
    store = {}

    def memory_factory(root):
        store["root"] = Path(root)
        return FindingsMemoryStore(Path(root))

    obs = _run(tmp_path, target=target, memory_store_factory=memory_factory)
    assert obs["enabled"] and obs["card_written"] and obs["outcome"] == "PASSED"
    assert obs["belief_keys"] == [
        "repair_outcome:file:pkg/mod.py",
        "repair_outcome:file:tests/test_mod.py",
    ]
    root = Path(obs["store_root"])
    assert root == state_root.resolve()
    beliefs = json.loads((root / ".nexus" / "belief_state.json").read_text())
    assert beliefs["repair_outcome:file:pkg/mod.py"]["confidence"] == pytest.approx(0.9)
    cards = FindingsMemoryStore(root).search("retry counter", kind="episodes", scope="both")
    assert [c.task_id for c in cards] == ["t-2721"]
    assert "Nexus's own verifiers): PASSED" in cards[0].body


def test_failed_verifier_records_low_confidence(tmp_path, state_root, monkeypatch):
    monkeypatch.setenv(lw.WRITEBACK_ENV, "1")
    obs = _run(tmp_path, passed=False, verdict="FAILED")
    assert obs["outcome"] == "FAILED" and obs["belief_confidence"] == pytest.approx(0.1)


def test_read_only_skips_writeback_and_store_writes(tmp_path, state_root, monkeypatch):
    monkeypatch.setenv(lw.WRITEBACK_ENV, "1")
    monkeypatch.setenv(lw.READ_ONLY_ENV, "1")
    obs = _run(tmp_path)
    assert obs["enabled"] is False and obs["skip_reason"] == "READ_ONLY"
    # The stores themselves refuse writes while read-only (any other writer during L-B).
    belief_file = tmp_path / "b" / "belief_state.json"
    engine = BeliefEngine(belief_file)
    engine.update_belief("t", "repair_outcome:file:x.py", 0.9, "e")
    assert not belief_file.exists()
    mem_root = tmp_path / "m"
    mem_root.mkdir()
    assert FindingsMemoryStore(mem_root).write(FindingsCard(kind="episodes", body="x")) == ""
    assert not list((mem_root / ".nexus" / "memory").rglob("*.json"))


def test_card_carries_no_hidden_test_or_scorer_terms(tmp_path, state_root, monkeypatch):
    monkeypatch.setenv(lw.WRITEBACK_ENV, "1")
    written = []

    class Recorder:
        def __init__(self, root):
            pass

        def write(self, card):
            written.append(card)
            return "x"

    _run(tmp_path, memory_store_factory=Recorder)
    text = json.dumps(written[0].to_dict()).lower()
    for term in ("f2p", "p2p", "fail_to_pass", "pass_to_pass", "hidden", "scorer", "resolved"):
        assert term not in text


def test_writeback_failure_never_raises(tmp_path, state_root, monkeypatch):
    monkeypatch.setenv(lw.WRITEBACK_ENV, "1")

    def broken(root):
        raise OSError("disk")

    obs = _run(tmp_path, memory_store_factory=broken)
    assert obs["card_written"] is False and obs["error_type"] == "OSError"


def test_finalize_calls_writeback_before_verified_update():
    src = (Path(lw.__file__).parent / "self_hosted_task_service_parts" / "finalize_runtime.py").read_text()
    call = src.index("writeback = run_learning_writeback(")
    assert call < src.index('update("VERIFIED", verified_values)')


def test_reader_and_writer_resolve_the_same_root(tmp_path, state_root, monkeypatch):
    """Writer root == the P1 memory reader's root (persistent_state_root(workspace_root=task worktree))."""
    from nexus.core.state_root import persistent_state_root

    monkeypatch.setenv(lw.WRITEBACK_ENV, "1")
    monkeypatch.setattr(
        "nexus.core.state_root._target_worktree_bases",
        lambda roots: {tmp_path / "nexus-runtime-targets"},
    )
    target = _target(tmp_path)
    obs = _run(tmp_path, target=target)
    assert Path(obs["store_root"]) == persistent_state_root(target) == state_root.resolve()
    # The parent (contract.target_worktree_root) would not have been rebased.
    assert persistent_state_root(target.parent) != state_root.resolve()


def test_fail_to_pass_not_verified_records_failed(tmp_path, state_root, monkeypatch):
    monkeypatch.setenv(lw.WRITEBACK_ENV, "1")
    obs = _run(tmp_path, fail_to_pass_status="BASE_ALREADY_PASS")
    assert obs["outcome"] == "FAILED" and obs["belief_confidence"] == pytest.approx(0.1)
    obs = _run(tmp_path, fail_to_pass_status="VERIFIED")
    assert obs["outcome"] == "PASSED"


def test_read_only_store_neither_creates_dirs_nor_promotes(tmp_path, state_root, monkeypatch):
    mem_root = tmp_path / "m2"
    mem_root.mkdir()
    store = FindingsMemoryStore(mem_root)
    store.write(FindingsCard(id="c1", kind="episodes", body="x", task_id="t"))
    monkeypatch.setenv(lw.READ_ONLY_ENV, "1")
    assert store.promote_to_global("c1", "episodes") is False
    assert store.read("c1", scope="task", kind="episodes", task_id="t") is not None
    fresh = tmp_path / "m3"
    fresh.mkdir()
    FindingsMemoryStore(fresh)
    assert not (fresh / ".nexus").exists()


def test_without_state_root_nothing_is_written_into_the_candidate(
    tmp_path, state_root, monkeypatch
):
    monkeypatch.setenv(lw.WRITEBACK_ENV, "1")
    monkeypatch.delenv("NEXUS_STATE_ROOT")
    target = _target(tmp_path)
    obs = _run(tmp_path, target=target)
    assert obs["skip_reason"] == "NO_STATE_ROOT" and not obs["card_written"]
    assert not (target / ".nexus").exists()


def test_task_root_outside_gateway_targets_is_not_written(tmp_path, state_root, monkeypatch):
    monkeypatch.setenv(lw.WRITEBACK_ENV, "1")
    other = tmp_path / "elsewhere" / "repo"
    other.mkdir(parents=True)
    obs = _run(tmp_path, target=other)
    assert obs["skip_reason"] == "ROOT_NOT_REBASED"
    assert not (other / ".nexus").exists() and not (state_root / ".nexus").exists()


def test_only_diff_checks_is_unverified_and_writes_no_belief(tmp_path, state_root, monkeypatch):
    monkeypatch.setenv(lw.WRITEBACK_ENV, "1")
    verified = SimpleNamespace(
        verifier_gate_passed=True,
        candidate_state_hash="cd" * 32,
        verifier_evidence=(
            SimpleNamespace(command="git diff --check", status="COMPLETED", exit_code=0),
        ),
    )
    obs = lw.run_learning_writeback(
        contract=_contract(_target(tmp_path)),
        candidate=_candidate(),
        verified=verified,
        resolution_verdict="PROVEN",
    )
    assert obs["outcome"] == "UNVERIFIED" and obs["belief_keys"] == []
    assert not (Path(obs["store_root"]) / ".nexus" / "belief_state.json").exists()


def test_fail_to_pass_not_run_is_unverified(tmp_path, state_root, monkeypatch):
    monkeypatch.setenv(lw.WRITEBACK_ENV, "1")
    obs = _run(tmp_path, fail_to_pass_status="NOT_RUN")
    assert obs["outcome"] == "UNVERIFIED" and obs["belief_keys"] == []


def test_state_root_inside_the_task_worktree_is_refused(tmp_path, state_root, monkeypatch):
    monkeypatch.setenv(lw.WRITEBACK_ENV, "1")
    target = _target(tmp_path)
    inside = target / "state"
    inside.mkdir()
    monkeypatch.setenv("NEXUS_STATE_ROOT", str(inside))
    obs = _run(tmp_path, target=target)
    assert obs["skip_reason"] == "ROOT_NOT_REBASED" and not (inside / ".nexus").exists()


def test_card_is_built_from_whitelisted_fields_only(tmp_path, state_root, monkeypatch):
    """Poisoned extra inputs (hidden tests, scorer, task bank) never reach the card or Belief."""
    monkeypatch.setenv(lw.WRITEBACK_ENV, "1")
    poison = "POISON_F2P_P2P_SCORER_TASKBANK"
    contract = _contract(_target(tmp_path))
    contract.hidden_tests = poison
    contract.scorer_result = poison
    contract.task_bank_entry = poison
    candidate = _candidate()
    candidate.fail_to_pass = poison
    candidate.stdout = poison
    verified = _verified(True)
    verified.scorer = poison
    verified.verifier_evidence = (
        SimpleNamespace(
            command="python -m pytest tests/test_mod.py",
            status="COMPLETED",
            exit_code=0,
            stdout=poison,
            stderr=poison,
        ),
    )
    written = []

    class Recorder:
        def __init__(self, root):
            pass

        def write(self, card):
            written.append(card)
            return "x"

    obs = lw.run_learning_writeback(
        contract=contract,
        candidate=candidate,
        verified=verified,
        resolution_verdict="PROVEN",
        fail_to_pass_status=poison,
        memory_store_factory=Recorder,
    )
    assert poison not in json.dumps(written[0].to_dict())
    beliefs = (Path(obs["store_root"]) / ".nexus" / "belief_state.json").read_text()
    assert poison not in beliefs and poison not in json.dumps(obs)


def test_read_only_leaves_in_memory_belief_unchanged(tmp_path, state_root, monkeypatch):
    engine = BeliefEngine(tmp_path / "b2" / "belief_state.json")
    monkeypatch.setenv(lw.READ_ONLY_ENV, "1")
    engine.update_belief("t", "repair_outcome:file:x.py", 0.9, "e")
    assert "repair_outcome:file:x.py" not in engine.beliefs


def test_read_only_disables_local_heal_learning_closure(monkeypatch):
    from nexus.services.local_heal import learning_closure_bridge as bridge

    monkeypatch.delenv(bridge.LEARNING_WRITEBACK_ENV, raising=False)
    monkeypatch.delenv(lw.READ_ONLY_ENV, raising=False)
    assert bridge._learning_writeback_disabled() is False
    monkeypatch.setenv(lw.READ_ONLY_ENV, "1")
    assert bridge._learning_writeback_disabled() is True


@pytest.mark.parametrize(
    "command", ["/usr/bin/true", "echo ok", "git diff --check", "code_integrity_v1", "test -f x"]
)
def test_non_test_verifier_commands_are_unverified(tmp_path, state_root, monkeypatch, command):
    monkeypatch.setenv(lw.WRITEBACK_ENV, "1")
    verified = SimpleNamespace(
        verifier_gate_passed=True,
        candidate_state_hash="ef" * 32,
        verifier_evidence=(SimpleNamespace(command=command, status="COMPLETED", exit_code=0),),
    )
    obs = lw.run_learning_writeback(
        contract=_contract(_target(tmp_path)),
        candidate=_candidate(),
        verified=verified,
        resolution_verdict="PROVEN",
    )
    assert obs["outcome"] == "UNVERIFIED" and obs["belief_keys"] == []


@pytest.mark.parametrize(
    "command",
    [
        "python -m pytest tests/test_mod.py",
        "cd sub && pytest -q",
        ".venv/bin/python -m unittest t",
        "npm test",
    ],
)
def test_test_runner_commands_count_as_tested(tmp_path, state_root, monkeypatch, command):
    monkeypatch.setenv(lw.WRITEBACK_ENV, "1")
    verified = SimpleNamespace(
        verifier_gate_passed=True,
        candidate_state_hash="ef" * 32,
        verifier_evidence=(SimpleNamespace(command=command, status="COMPLETED", exit_code=0),),
    )
    obs = lw.run_learning_writeback(
        contract=_contract(_target(tmp_path)),
        candidate=_candidate(),
        verified=verified,
        resolution_verdict="PROVEN",
    )
    assert obs["outcome"] == "PASSED"


def test_deleted_files_are_recorded(tmp_path, state_root, monkeypatch):
    monkeypatch.setenv(lw.WRITEBACK_ENV, "1")
    candidate = SimpleNamespace(changed_files=[], untracked_files=[], deleted_files=["pkg/old.py"])
    obs = lw.run_learning_writeback(
        contract=_contract(_target(tmp_path)),
        candidate=candidate,
        verified=_verified(True),
        resolution_verdict="PROVEN",
    )
    assert obs["belief_keys"] == ["repair_outcome:file:pkg/old.py"]


def test_read_only_audit_outcome_returns_result_without_change(tmp_path, state_root, monkeypatch):
    from nexus.core.belief_contracts import AuditOutcome

    engine = BeliefEngine(tmp_path / "b3" / "belief_state.json")
    monkeypatch.setenv(lw.READ_ONLY_ENV, "1")
    outcome = AuditOutcome(
        task_id="t", assumption="new-assumption", passed=True, evidence_id="e", reason="r"
    )
    result = engine.process_audit_outcome(outcome)
    assert result["assumption"] == "new-assumption" and result["accepted"] is True
    assert "new-assumption" not in engine.beliefs
    assert not (tmp_path / "b3" / "belief_state.json").exists()


def test_read_only_learn_mode_closure_persists_nothing(tmp_path, state_root, monkeypatch):
    from nexus.research.learn_mode import LearnModeService

    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setenv(lw.READ_ONLY_ENV, "1")
    service = LearnModeService(project, run_root=tmp_path / "run")
    out = service._persist_learning_closure(
        action="ask",
        status="SUCCESS",
        reason="r",
        topic_or_source="t",
        evidence_paths=[],
        retrieval_hints=[],
        metrics={},
    )
    assert out["skipped"] == lw.READ_ONLY_ENV
    assert not list(tmp_path.rglob("*.jsonl")) and not (state_root / ".nexus").exists()
