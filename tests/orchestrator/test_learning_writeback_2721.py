"""#2721: P1 post-verification learning write-back and the read-only switch."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.core.belief_engine import BeliefEngine
from nexus.orchestrator.self_hosted_task_service_parts import learning_writeback as lw
from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore


def _contract(target: Path) -> SimpleNamespace:
    return SimpleNamespace(
        task_id="t-2721",
        objective="Fix the retry counter in pkg/mod.py",
        target_worktree_root=str(target),
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
    return root


def _target(tmp_path: Path) -> Path:
    # A Gateway-managed target worktree (…/nexus-runtime-targets/<task>) moves to NEXUS_STATE_ROOT.
    target = tmp_path / "nexus-runtime-targets" / "t-2721"
    target.mkdir(parents=True)
    return target


def _run(tmp_path, passed=True, verdict="PROVEN", **kw):
    return lw.run_learning_writeback(
        contract=_contract(kw.pop("target", tmp_path / "plain-target")),
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
    src = Path(lw.__file__).with_name("finalize_runtime.py").read_text()
    call = src.index("writeback = run_learning_writeback(")
    assert call < src.index('update("VERIFIED", verified_values)')
