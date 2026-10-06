import argparse
import importlib.util
import json
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).parents[2]
PATH = ROOT / "scripts" / "ops" / "nexus-hermes-continuation-controller"
LOADER = SourceFileLoader("hermes_continuation_controller", str(PATH))
SPEC = importlib.util.spec_from_loader("hermes_continuation_controller", LOADER)
assert SPEC is not None
MOD = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(MOD)


def _policy(tmp_path: Path, *, with_handler: bool = True) -> Path:
    local_prompt = tmp_path / "local.txt"
    local_prompt.write_text("Give one bounded advisory sentence.\n")
    value = {
        "schema": MOD.POLICY_SCHEMA,
        "handlers": {},
    }
    if with_handler:
        value["handlers"]["CONTINUE_BOUNDED_ISSUE_WORK"] = {
            "kind": "LOCAL_HERMES_THEN_AGY_PLAN",
            "local_prompt_file": "local.txt",
            "agy_prompt_prefix": "Return exactly CANARY_OK. Do not use tools.",
            "cwd": ".",
            "timeout": 30,
            "max_calls": 1,
        }
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(value))
    return path


def _args(
    tmp_path: Path,
    *,
    mode: str = "execute",
    run_id: str = "run-test",
    operation_id=None,
    core_root=None,
    expected_core_commit=None,
    expected_core_tree=None,
    work_product=None,
    source_revision=None,
    source_tree=None,
    allowed_paths=None,
):
    return argparse.Namespace(
        policy=str(_policy(tmp_path)),
        repo_root=str(tmp_path),
        repository="James3014/Nexus-new",
        issue=1392,
        pr=None,
        operation_id=operation_id,
        mode=mode,
        receipt_dir=str(tmp_path / "receipts"),
        run_id=run_id,
        max_cycles=3,
        core_root=core_root,
        expected_core_commit=expected_core_commit,
        expected_core_tree=expected_core_tree,
        work_product=work_product,
        source_revision=source_revision,
        source_tree=source_tree,
        allowed_paths=allowed_paths,
    )


def _doctor(disposition: str, gate: str, *, operation_id=None):
    next_gate = {"code": gate}
    if operation_id:
        next_gate["operation_id"] = operation_id
    return {
        "schema": "nexus.workflow_doctor.v1",
        "claim_ceiling": "READ_ONLY_WORKFLOW_OBSERVATION",
        "resume_disposition": disposition,
        "next_gate": next_gate,
    }


def _core_result(*, verified: bool, reason_codes=None):
    return {
        "schema": MOD.CORE_COMPLETION_SCHEMA,
        "claims_complete": verified,
        "claims_verified": verified,
        "core_commit": "94952e146615f74e45dbd780f6e2697460ce6184",
        "core_tree": "f7eb11d58fdd28a2c43ca49b1c15da2c597befc6",
        "reason_codes": list(reason_codes or []),
        "result_hash": "sha256:" + ("a" * 64),
    }


def _guard(doctor):
    disposition = doctor["resume_disposition"]
    gate = doctor["next_gate"]["code"]
    if disposition == "SAFE":
        return {
            "decision": "NOOP_TERMINAL"
            if gate == "NO_PENDING_GATE"
            else "CONTINUE_EXACT_NEXT_GATE",
            "next_gate": gate,
        }
    if disposition == "WAIT":
        return {"decision": "WAIT", "next_gate": gate}
    if disposition == "RECONCILE":
        return {"decision": "RECONCILE_EXISTING_EFFECT", "next_gate": gate}
    if disposition == "BLOCKED":
        return {"decision": "BLOCK", "next_gate": gate}
    return {"decision": "BLOCK_UNKNOWN", "next_gate": gate}


def test_observe_mode_never_executes_handler(tmp_path, monkeypatch):
    monkeypatch.setattr(
        MOD, "_doctor", lambda **kwargs: _doctor("SAFE", "CONTINUE_BOUNDED_ISSUE_WORK")
    )
    monkeypatch.setattr(MOD, "_guard_doctor", _guard)
    monkeypatch.setattr(
        MOD,
        "_handler_local_then_agy",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("effect must not run")),
    )
    assert MOD.run_controller(_args(tmp_path, mode="observe")) == 0
    receipt = json.loads((tmp_path / "receipts/run-test/cycle-0001.json").read_text())
    assert receipt["outcome"] == "OBSERVED_ONLY"


def test_wait_stops_without_effect(tmp_path, monkeypatch):
    monkeypatch.setattr(MOD, "_doctor", lambda **kwargs: _doctor("WAIT", "WAIT_OPERATION"))
    monkeypatch.setattr(MOD, "_guard_doctor", _guard)
    monkeypatch.setattr(
        MOD,
        "_handler_local_then_agy",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("effect must not run")),
    )
    assert MOD.run_controller(_args(tmp_path)) == 0
    receipt = json.loads((tmp_path / "receipts/run-test/cycle-0001.json").read_text())
    assert receipt["outcome"] == "STOP_WAIT"


def test_blocked_stops_nonzero(tmp_path, monkeypatch):
    monkeypatch.setattr(
        MOD, "_doctor", lambda **kwargs: _doctor("BLOCKED", "SOURCE_IDENTITY_UNAVAILABLE")
    )
    monkeypatch.setattr(MOD, "_guard_doctor", _guard)
    assert MOD.run_controller(_args(tmp_path)) == 4
    receipt = json.loads((tmp_path / "receipts/run-test/cycle-0001.json").read_text())
    assert receipt["outcome"] == "STOP_BLOCKED"


def test_safe_unknown_gate_has_no_effect(tmp_path, monkeypatch):
    monkeypatch.setattr(MOD, "_doctor", lambda **kwargs: _doctor("SAFE", "SOME_NEW_GATE"))
    monkeypatch.setattr(MOD, "_guard_doctor", _guard)
    assert MOD.run_controller(_args(tmp_path)) == 4
    receipt = json.loads((tmp_path / "receipts/run-test/cycle-0001.json").read_text())
    assert receipt["outcome"] == "STOP_NO_EXPLICIT_HANDLER"


def test_handler_persists_intent_then_operation_id(tmp_path, monkeypatch):
    policy_path = _policy(tmp_path)
    handler = MOD._load_policy(policy_path)["handlers"]["CONTINUE_BOUNDED_ISSUE_WORK"]
    state = MOD._load_state(tmp_path / "receipts", "handler-test")

    monkeypatch.setattr(
        MOD,
        "_hermes_local",
        lambda prompt, cwd: subprocess.CompletedProcess(
            ["hermes"], 0, stdout="LOCAL_ADVICE\n", stderr=""
        ),
    )
    observed = {}

    def fake_dispatch(**kwargs):
        state_path = tmp_path / "receipts/handler-test/state.json"
        persisted = json.loads(state_path.read_text())
        observed["intent_before_dispatch"] = persisted["effect_intent"]
        return {
            "operation_id": "agyop_test123",
            "source_attribution_state": "ATTRIBUTED",
            "base_head": "a" * 40,
        }

    monkeypatch.setattr(MOD, "_agy_dispatch_plan", fake_dispatch)
    result = MOD._handler_local_then_agy(
        handler=handler,
        policy_path=policy_path,
        state=state,
        receipt_dir=tmp_path / "receipts",
        run_id="handler-test",
        cycle=1,
    )
    assert "operation_id" not in observed["intent_before_dispatch"]
    assert result["operation_id"] == "agyop_test123"
    persisted = json.loads((tmp_path / "receipts/handler-test/state.json").read_text())
    assert persisted["operation_id"] == "agyop_test123"
    assert persisted["effect_intent"]["operation_id"] == "agyop_test123"
    assert persisted["effects_started"] == 1


def test_unbound_effect_intent_blocks_before_doctor(tmp_path, monkeypatch):
    args = _args(tmp_path, run_id="crash-test")
    state = MOD._load_state(tmp_path / "receipts", "crash-test")
    state["effect_intent"] = {
        "kind": "AGY_DISPATCH_PLAN",
        "cycle": 1,
        "prompt_sha256": "b" * 64,
        "cwd": str(tmp_path),
    }
    MOD._save_state(tmp_path / "receipts", state)
    monkeypatch.setattr(
        MOD,
        "_doctor",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("doctor should not permit replay path")
        ),
    )
    assert MOD.run_controller(args) == 5
    receipt = json.loads((tmp_path / "receipts/crash-test/cycle-0001.json").read_text())
    assert receipt["outcome"] == "BLOCK_UNBOUND_EFFECT_INTENT"


def test_reconcile_exact_operation_once_and_never_redispatch(tmp_path, monkeypatch):
    op = "agyop_unknown"
    doctors = iter([
        _doctor("RECONCILE", "RECONCILE_OPERATION", operation_id=op),
        _doctor("RECONCILE", "RECONCILE_OPERATION", operation_id=op),
    ])
    monkeypatch.setattr(MOD, "_doctor", lambda **kwargs: next(doctors))
    monkeypatch.setattr(MOD, "_guard_doctor", _guard)
    calls = []

    def reconcile(operation_id, cwd):
        calls.append(operation_id)
        return {"operation_id": operation_id, "status": "OUTCOME_UNKNOWN", "retry_permitted": False}

    monkeypatch.setattr(MOD, "_agy_reconcile", reconcile)
    monkeypatch.setattr(
        MOD,
        "_handler_local_then_agy",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not redispatch")),
    )
    assert MOD.run_controller(_args(tmp_path, operation_id=op)) == 6
    assert calls == [op]


def test_reconcile_mismatched_operation_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(
        MOD,
        "_doctor",
        lambda **kwargs: _doctor("RECONCILE", "RECONCILE_OPERATION", operation_id="agyop_other"),
    )
    monkeypatch.setattr(MOD, "_guard_doctor", _guard)
    monkeypatch.setattr(
        MOD,
        "_agy_reconcile",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("must not reconcile wrong identity")
        ),
    )
    assert MOD.run_controller(_args(tmp_path, operation_id="agyop_expected")) == 4


def test_restart_uses_persisted_operation_and_waits(tmp_path, monkeypatch):
    args = _args(tmp_path, run_id="restart-test")
    state = MOD._load_state(tmp_path / "receipts", "restart-test")
    state["operation_id"] = "agyop_resume"
    state["effect_intent"] = {
        "kind": "AGY_DISPATCH_PLAN",
        "operation_id": "agyop_resume",
        "prompt_sha256": "c" * 64,
    }
    state["effects_started"] = 1
    MOD._save_state(tmp_path / "receipts", state)

    seen = {}

    def doctor(**kwargs):
        seen["operation_id"] = kwargs["operation_id"]
        return _doctor("WAIT", "WAIT_OPERATION", operation_id="agyop_resume")

    monkeypatch.setattr(MOD, "_doctor", doctor)
    monkeypatch.setattr(MOD, "_guard_doctor", _guard)
    assert MOD.run_controller(args) == 0
    assert seen["operation_id"] == "agyop_resume"


def _frontier_args(tmp_path: Path, *, run_id="frontier-test"):
    signal = tmp_path / "signal.json"
    signal.write_text(json.dumps({"same_gate_failures": 2}))
    question = tmp_path / "question.txt"
    question.write_text("Should the original effect be reconciled?")
    return argparse.Namespace(
        signal_file=str(signal),
        question_file=str(question),
        cwd=str(tmp_path),
        receipt_dir=str(tmp_path / "receipts"),
        run_id=run_id,
        provider="copilot",
        model="gpt-4.1",
    )


def test_frontier_not_called_without_deterministic_trigger(tmp_path, monkeypatch):
    monkeypatch.setattr(
        MOD,
        "_guard_escalate",
        lambda signal: {
            "decision": "LOCAL_CONTINUE",
            "escalate": False,
            "reasons": [],
            "authority": "LOCAL_BOUNDED_REASONING",
        },
    )
    monkeypatch.setattr(
        MOD,
        "_hermes_frontier",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("frontier must not be called")
        ),
    )
    assert MOD.run_frontier(_frontier_args(tmp_path)) == 0


def test_frontier_transport_failure_is_terminal_and_no_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(
        MOD,
        "_guard_escalate",
        lambda signal: {
            "decision": "ASK_FRONTIER_ADVISER",
            "escalate": True,
            "reasons": ["REPEATED_GATE_FAILURE"],
            "authority": "ADVISORY_ONLY",
        },
    )
    calls = []

    def failed(prompt, cwd, provider, model):
        calls.append((provider, model))
        return subprocess.CompletedProcess(["hermes"], 9, stdout="", stderr="provider unavailable")

    monkeypatch.setattr(MOD, "_hermes_frontier", failed)
    assert MOD.run_frontier(_frontier_args(tmp_path)) == 7
    assert calls == [("copilot", "gpt-4.1")]
    receipt = json.loads((tmp_path / "receipts/frontier-test/frontier-0001.json").read_text())
    assert receipt["outcome"] == "FRONTIER_TRANSPORT_FAILED"
    assert receipt["authority"] == "ADVISORY_ONLY"


def test_effect_cycle_receipt_contains_post_effect_readback(tmp_path, monkeypatch):
    doctors = iter([
        _doctor("SAFE", "CONTINUE_BOUNDED_ISSUE_WORK"),
        _doctor("WAIT", "WAIT_OPERATION", operation_id="agyop_post"),
    ])
    monkeypatch.setattr(MOD, "_doctor", lambda **kwargs: next(doctors))
    monkeypatch.setattr(MOD, "_guard_doctor", _guard)
    monkeypatch.setattr(
        MOD,
        "_handler_local_then_agy",
        lambda **kwargs: {
            "outcome": "AGY_OPERATION_STARTED",
            "effect_started": True,
            "operation_id": "agyop_post",
        },
    )
    assert MOD.run_controller(_args(tmp_path)) == 0
    receipt = json.loads((tmp_path / "receipts/run-test/cycle-0001.json").read_text())
    assert receipt["post_effect_readback"]["doctor_disposition"] == "WAIT"
    assert receipt["post_effect_readback"]["guard"]["decision"] == "WAIT"


def _make_valid_envelope(
    *,
    issue=1392,
    run_id="run-test",
    operation_id="agyop_valid",
    source_revision="a" * 40,
    artifact_path="pkg/code.py",
    content_hash="sha256:" + ("b" * 64),
):
    core_mod = MOD._load_core_completion_mod()
    return core_mod.materialize_work_product_envelope(
        issue_number=issue,
        run_id=run_id,
        operation_id=operation_id,
        source_revision=source_revision,
        source_tree="c" * 40,
        target_revision="d" * 40,
        artifacts=[
            {
                "path": artifact_path,
                "artifact_id": "art-1",
                "content_hash": content_hash,
            }
        ],
        verifier_observation={
            "verifier_id": "pytest_unit",
            "artifact_id": "art-1",
            "artifact_hash": content_hash,
            "status": "PASS",
        },
    )


def test_red_control_terminal_completed_without_work_product_fails_closed(tmp_path, monkeypatch):
    op = "agyop_red"
    monkeypatch.setattr(
        MOD, "_doctor", lambda **kwargs: _doctor("SAFE", "NO_PENDING_GATE", operation_id=op)
    )
    monkeypatch.setattr(MOD, "_guard_doctor", _guard)
    args = _args(
        tmp_path,
        operation_id=op,
        core_root=str(ROOT / ".reference" / "nexus-core"),
    )
    assert MOD.run_controller(args) == 4
    receipt = json.loads((tmp_path / "receipts/run-test/cycle-0001.json").read_text())
    assert receipt["outcome"] == "CORE_COMPLETION_NOT_VERIFIED"
    assert receipt["core_completion"]["claims_verified"] is False
    assert "EMPTY_WORK_PRODUCT_ENVELOPE" in receipt["core_completion"]["reason_codes"]


def test_positive_control_verified_core_completion_allows_next_gate(tmp_path, monkeypatch):
    op = "agyop_green"
    monkeypatch.setattr(MOD, "_core_completion", lambda **kwargs: _core_result(verified=True))
    monkeypatch.setattr(
        MOD, "_doctor", lambda **kwargs: _doctor("SAFE", "EXACT_NEXT_GATE", operation_id=op)
    )
    monkeypatch.setattr(MOD, "_guard_doctor", _guard)
    envelope = _make_valid_envelope(operation_id=op)
    env_file = tmp_path / "envelope.json"
    env_file.write_text(json.dumps(envelope))

    args = _args(
        tmp_path,
        operation_id=op,
        core_root=str(ROOT / ".reference" / "nexus-core"),
        work_product=str(env_file),
        source_revision="a" * 40,
    )
    assert MOD.run_controller(args) == 0
    receipt = json.loads((tmp_path / "receipts/run-test/cycle-0001.json").read_text())
    assert receipt["outcome"] == "EXACT_NEXT_GATE_ELIGIBLE"
    assert receipt["core_completion"]["claims_verified"] is True
    assert receipt["core_completion"]["claims_complete"] is True
    assert receipt["core_completion"]["core_commit"] == "94952e146615f74e45dbd780f6e2697460ce6184"
    assert receipt["core_completion"]["core_tree"] == "f7eb11d58fdd28a2c43ca49b1c15da2c597befc6"
    assert receipt["core_completion"]["result_hash"] is not None

    state = json.loads((tmp_path / "receipts/run-test/state.json").read_text())
    assert state["core_completion_verified"] is True
    assert state["core_completion"]["claims_verified"] is True


def test_positive_control_noop_terminal_allows_closeout(tmp_path, monkeypatch):
    op = "agyop_noop_pass"
    monkeypatch.setattr(MOD, "_core_completion", lambda **kwargs: _core_result(verified=True))
    monkeypatch.setattr(
        MOD, "_doctor", lambda **kwargs: _doctor("SAFE", "NO_PENDING_GATE", operation_id=op)
    )
    monkeypatch.setattr(MOD, "_guard_doctor", _guard)
    envelope = _make_valid_envelope(operation_id=op)
    env_file = tmp_path / "envelope.json"
    env_file.write_text(json.dumps(envelope))

    args = _args(
        tmp_path,
        operation_id=op,
        core_root=str(ROOT / ".reference" / "nexus-core"),
        work_product=str(env_file),
        source_revision="a" * 40,
    )
    assert MOD.run_controller(args) == 0
    receipt = json.loads((tmp_path / "receipts/run-test/cycle-0001.json").read_text())
    assert receipt["outcome"] == "TERMINAL_NOOP"
    assert receipt["core_completion"]["claims_verified"] is True


def test_negative_stale_envelope_hash_fails_closed(tmp_path, monkeypatch):
    op = "agyop_tampered"
    monkeypatch.setattr(
        MOD, "_doctor", lambda **kwargs: _doctor("SAFE", "EXACT_NEXT_GATE", operation_id=op)
    )
    monkeypatch.setattr(MOD, "_guard_doctor", _guard)
    envelope = _make_valid_envelope(operation_id=op)
    envelope["issue_number"] = 1419  # tamper without re-hashing
    env_file = tmp_path / "envelope.json"
    env_file.write_text(json.dumps(envelope))

    args = _args(
        tmp_path,
        operation_id=op,
        core_root=str(ROOT / ".reference" / "nexus-core"),
        work_product=str(env_file),
        source_revision="a" * 40,
    )
    assert MOD.run_controller(args) == 4
    receipt = json.loads((tmp_path / "receipts/run-test/cycle-0001.json").read_text())
    assert receipt["outcome"] == "CORE_COMPLETION_NOT_VERIFIED"
    assert "ENVELOPE_HASH_MISMATCH" in receipt["core_completion"]["reason_codes"]


def test_negative_wrong_identities_fail_closed(tmp_path, monkeypatch):
    op = "agyop_ident"
    monkeypatch.setattr(
        MOD, "_doctor", lambda **kwargs: _doctor("SAFE", "EXACT_NEXT_GATE", operation_id=op)
    )
    monkeypatch.setattr(MOD, "_guard_doctor", _guard)
    envelope = _make_valid_envelope(operation_id="agyop_different")
    env_file = tmp_path / "envelope.json"
    env_file.write_text(json.dumps(envelope))

    args = _args(
        tmp_path,
        operation_id=op,
        core_root=str(ROOT / ".reference" / "nexus-core"),
        work_product=str(env_file),
        source_revision="a" * 40,
    )
    assert MOD.run_controller(args) == 4
    receipt = json.loads((tmp_path / "receipts/run-test/cycle-0001.json").read_text())
    assert receipt["outcome"] == "CORE_COMPLETION_NOT_VERIFIED"
    assert "WRONG_OPERATION_ID" in receipt["core_completion"]["reason_codes"]


def test_negative_wrong_source_tree_fails_closed(tmp_path, monkeypatch):
    op = "agyop_wrong_tree"
    monkeypatch.setattr(
        MOD, "_doctor", lambda **kwargs: _doctor("SAFE", "EXACT_NEXT_GATE", operation_id=op)
    )
    monkeypatch.setattr(MOD, "_guard_doctor", _guard)
    envelope = _make_valid_envelope(operation_id=op)
    env_file = tmp_path / "envelope.json"
    env_file.write_text(json.dumps(envelope))

    args = _args(
        tmp_path,
        operation_id=op,
        core_root=str(ROOT / ".reference" / "nexus-core"),
        work_product=str(env_file),
        source_revision="a" * 40,
        source_tree="9" * 40,
    )
    assert MOD.run_controller(args) == 4
    receipt = json.loads((tmp_path / "receipts/run-test/cycle-0001.json").read_text())
    assert receipt["outcome"] == "CORE_COMPLETION_NOT_VERIFIED"
    assert "WRONG_SOURCE_TREE" in receipt["core_completion"]["reason_codes"]


def test_negative_verifier_fail_status_fails_closed(tmp_path, monkeypatch):
    op = "agyop_fail_verifier"
    monkeypatch.setattr(
        MOD,
        "_core_completion",
        lambda **kwargs: _core_result(verified=False, reason_codes=["VERIFIER_STATUS_FAIL"]),
    )
    monkeypatch.setattr(
        MOD, "_doctor", lambda **kwargs: _doctor("SAFE", "EXACT_NEXT_GATE", operation_id=op)
    )
    monkeypatch.setattr(MOD, "_guard_doctor", _guard)
    core_mod = MOD._load_core_completion_mod()
    envelope = core_mod.materialize_work_product_envelope(
        issue_number=1392,
        run_id="run-test",
        operation_id=op,
        source_revision="a" * 40,
        source_tree="c" * 40,
        target_revision="d" * 40,
        artifacts=[
            {
                "path": "pkg/mod.py",
                "artifact_id": "art-1",
                "content_hash": "sha256:" + ("b" * 64),
            }
        ],
        verifier_observation={
            "verifier_id": "pytest_unit",
            "artifact_id": "art-1",
            "artifact_hash": "sha256:" + ("b" * 64),
            "status": "FAIL",
        },
    )
    env_file = tmp_path / "envelope.json"
    env_file.write_text(json.dumps(envelope))

    args = _args(
        tmp_path,
        operation_id=op,
        core_root=str(ROOT / ".reference" / "nexus-core"),
        work_product=str(env_file),
        source_revision="a" * 40,
    )
    assert MOD.run_controller(args) == 4
    receipt = json.loads((tmp_path / "receipts/run-test/cycle-0001.json").read_text())
    assert receipt["outcome"] == "CORE_COMPLETION_NOT_VERIFIED"
    assert any(
        "CONTRADICTORY:verifier" in code or code == "VERIFIER_STATUS_FAIL"
        for code in receipt["core_completion"]["reason_codes"]
    )


def test_negative_core_commit_mismatch_fails_closed(tmp_path, monkeypatch):
    op = "agyop_mismatch"
    monkeypatch.setattr(
        MOD,
        "_core_completion",
        lambda **kwargs: _core_result(verified=False, reason_codes=["CORE_COMMIT_MISMATCH"]),
    )
    monkeypatch.setattr(
        MOD, "_doctor", lambda **kwargs: _doctor("SAFE", "EXACT_NEXT_GATE", operation_id=op)
    )
    monkeypatch.setattr(MOD, "_guard_doctor", _guard)
    envelope = _make_valid_envelope(operation_id=op)
    env_file = tmp_path / "envelope.json"
    env_file.write_text(json.dumps(envelope))

    args = _args(
        tmp_path,
        operation_id=op,
        core_root=str(ROOT / ".reference" / "nexus-core"),
        expected_core_commit="0" * 40,
        work_product=str(env_file),
        source_revision="a" * 40,
    )
    assert MOD.run_controller(args) == 4
    receipt = json.loads((tmp_path / "receipts/run-test/cycle-0001.json").read_text())
    assert receipt["outcome"] == "CORE_COMPLETION_NOT_VERIFIED"
    assert "CORE_COMMIT_MISMATCH" in receipt["core_completion"]["reason_codes"]


def test_post_effect_readback_terminal_without_work_product_fails_closed(tmp_path, monkeypatch):
    doctors = iter([
        _doctor("SAFE", "CONTINUE_BOUNDED_ISSUE_WORK"),
        _doctor("SAFE", "NEXT_GATE", operation_id="agyop_instant"),
    ])
    monkeypatch.setattr(MOD, "_doctor", lambda **kwargs: next(doctors))
    monkeypatch.setattr(MOD, "_guard_doctor", _guard)
    monkeypatch.setattr(
        MOD,
        "_handler_local_then_agy",
        lambda **kwargs: {
            "outcome": "AGY_OPERATION_STARTED",
            "effect_started": True,
            "operation_id": "agyop_instant",
        },
    )
    args = _args(
        tmp_path,
        core_root=str(ROOT / ".reference" / "nexus-core"),
    )
    assert MOD.run_controller(args) == 4
    receipt = json.loads((tmp_path / "receipts/run-test/cycle-0001.json").read_text())
    assert receipt["outcome"] == "CORE_COMPLETION_NOT_VERIFIED"
    assert receipt["core_completion"]["claims_verified"] is False


def test_post_effect_readback_terminal_with_valid_work_product_succeeds(tmp_path, monkeypatch):
    op = "agyop_instant_pass"
    monkeypatch.setattr(MOD, "_core_completion", lambda **kwargs: _core_result(verified=True))
    doctors = iter([
        _doctor("SAFE", "CONTINUE_BOUNDED_ISSUE_WORK"),
        _doctor("SAFE", "NEXT_GATE", operation_id=op),
    ])
    monkeypatch.setattr(MOD, "_doctor", lambda **kwargs: next(doctors))
    monkeypatch.setattr(MOD, "_guard_doctor", _guard)
    monkeypatch.setattr(
        MOD,
        "_handler_local_then_agy",
        lambda **kwargs: {
            "outcome": "AGY_OPERATION_STARTED",
            "effect_started": True,
            "operation_id": op,
        },
    )
    envelope = _make_valid_envelope(operation_id=op)
    env_file = tmp_path / "receipts" / "run-test" / f"work_product_{op}.json"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text(json.dumps(envelope))

    args = _args(
        tmp_path,
        core_root=str(ROOT / ".reference" / "nexus-core"),
        source_revision="a" * 40,
    )
    assert MOD.run_controller(args) == 0
    receipt = json.loads((tmp_path / "receipts/run-test/cycle-0001.json").read_text())
    assert receipt["outcome"] == "EXACT_NEXT_GATE_ELIGIBLE"
    assert receipt["core_completion"]["claims_verified"] is True


def test_cli_parser_includes_core_completion_flags():
    parser = MOD.build_parser()
    args = parser.parse_args([
        "run",
        "--policy",
        "p.json",
        "--repo-root",
        ".",
        "--receipt-dir",
        "r",
        "--core-root",
        "/core",
        "--expected-core-commit",
        "abc",
        "--expected-core-tree",
        "def",
        "--work-product",
        "wp.json",
        "--source-revision",
        "src",
        "--source-tree",
        "tree",
        "--allowed-paths",
        "a.py",
        "b.py",
    ])
    assert args.core_root == "/core"
    assert args.expected_core_commit == "abc"
    assert args.expected_core_tree == "def"
    assert args.work_product == "wp.json"
    assert args.source_revision == "src"
    assert args.source_tree == "tree"
    assert args.allowed_paths == ["a.py", "b.py"]
