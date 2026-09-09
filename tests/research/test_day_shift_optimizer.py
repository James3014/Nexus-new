import hashlib
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from nexus.engine.canonical_task_seam import (
    DayShiftAdmissionContext,
    VerifiedTaskCardIdentity,
    build_day_shift_admission_context,
)
from nexus.research.day_shift_optimizer import DayShiftOptimizer


def _admitted_context(tmp_path: Path):
    card_file = tmp_path / "card.md"
    card_file.write_text("task_id: `negative`\nAUTO_CHAIN: false\n", encoding="utf-8")
    card = VerifiedTaskCardIdentity(
        task_id="negative",
        task_card_path="tasks/test/negative.md",
        canonical_task_card_path=str(card_file),
        task_card_hash=hashlib.sha256(card_file.read_bytes()).hexdigest(),
    )
    return build_day_shift_admission_context(
        task_text="Implement a bounded feature",
        task_card_identity=card,
        repository_root=tmp_path,
        workspace_revision="revision-001",
        allowed_files=("demo.py",),
        verifier_command=("pytest", "-q"),
    )


def _thaw(value):
    if isinstance(value, dict):
        return {key: _thaw(item) for key, item in value.items()}
    if hasattr(value, "items"):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def test_dayshift_missing_verified_admission_denies_before_transport(tmp_path: Path):
    optimizer = DayShiftOptimizer(
        project_root=tmp_path,
        swarm_dir=tmp_path,
        target_file="demo.py",
        task_desc="improve demo",
        min_round_delay_sec=0,
    )
    result = optimizer.optimize()
    assert result["status"] == "FAILED"
    assert result["reason"] == "dayshift_admission_context_missing"
    assert result["stage2_admitted"] is False


def test_dayshift_rejects_untyped_admission_context(tmp_path: Path):
    optimizer = DayShiftOptimizer(
        project_root=tmp_path,
        swarm_dir=tmp_path,
        target_file="demo.py",
        task_desc="improve demo",
        admission_context={"overall_decision": "ALLOW"},
    )
    result = optimizer.optimize()
    assert result["reason"] == "dayshift_admission_context_missing"


def test_dayshift_rejects_fabricated_typed_allow_context(tmp_path: Path):
    card = VerifiedTaskCardIdentity(
        task_id="forged",
        task_card_path="tasks/test/forged.md",
        canonical_task_card_path=str(tmp_path / "card.md"),
        task_card_hash="0" * 64,
    )
    with pytest.raises(ValueError, match="dayshift_context_not_source_owned"):
        DayShiftAdmissionContext(
            task_card_identity=card,
            repository_root=tmp_path,
            workspace_revision="revision-001",
            allowed_files=("demo.py",),
            verifier_command=("pytest",),
            admission={"overall_decision": "ALLOW"},
        )


def test_dayshift_admitted_context_denies_gateway_fallback(tmp_path: Path, monkeypatch):
    context = _admitted_context(tmp_path)
    optimizer = DayShiftOptimizer(
        tmp_path,
        tmp_path,
        "demo.py",
        "Implement a bounded feature",
        admission_context=context,
    )
    monkeypatch.setattr(optimizer, "_workspace_revision", lambda: "revision-001")
    monkeypatch.setattr(optimizer.gateway, "ask_unified", None)
    response, _raw, receipt = optimizer._ask_unified(
        prompt="Return a candidate",
        payload="Return FULL file content.",
        task_statement="Implement a bounded feature",
        round_id=1,
        attempt=1,
        model="admitted-model",
        output_schema={"patch": "full file"},
        task_kind="generation",
    )
    assert response["status"] == "FAIL"
    assert response["summary"] == "dayshift_gateway_unavailable"
    assert receipt["online"]["status"] == "FAILED"


def test_dayshift_rejects_copied_context_capability(tmp_path: Path):
    context = _admitted_context(tmp_path)
    copied = replace(context, task_text=context.task_text)
    optimizer = DayShiftOptimizer(
        tmp_path,
        tmp_path,
        "demo.py",
        "Implement a bounded feature",
        admission_context=copied,
    )
    result = optimizer.optimize()
    assert result["reason"] == "dayshift_context_not_issued"


def test_dayshift_rejects_symlink_target_escape(tmp_path: Path):
    context = _admitted_context(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside.write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "demo.py").symlink_to(outside)
    optimizer = DayShiftOptimizer(
        tmp_path,
        tmp_path,
        "demo.py",
        "Implement a bounded feature",
        admission_context=context,
    )
    optimizer._workspace_revision = lambda: "revision-001"
    result = optimizer.optimize()
    assert result["reason"] == "dayshift_target_out_of_scope"


def test_dayshift_revalidates_card_and_revision_before_transport(tmp_path: Path, monkeypatch):
    context = _admitted_context(tmp_path)
    optimizer = DayShiftOptimizer(
        tmp_path,
        tmp_path,
        "demo.py",
        "Implement a bounded feature",
        admission_context=context,
    )
    monkeypatch.setattr(optimizer, "_workspace_revision", lambda: "revision-001")
    Path(context.task_card_identity.canonical_task_card_path).write_text("changed", encoding="utf-8")
    response, _raw, _receipt = optimizer._ask_unified(
        prompt="candidate",
        payload="full file",
        task_statement=context.task_text,
        round_id=1,
        attempt=1,
        model="admitted-model",
        output_schema={"patch": "full file"},
        task_kind="generation",
    )
    assert response["summary"] == "dayshift_card_stale"
    card_path = Path(context.task_card_identity.canonical_task_card_path)
    card_path.write_text("task_id: `negative`\nAUTO_CHAIN: false\n", encoding="utf-8")
    monkeypatch.setattr(optimizer, "_workspace_revision", lambda: "revision-002")
    response, _raw, _receipt = optimizer._ask_unified(
        prompt="candidate",
        payload="full file",
        task_statement=context.task_text,
        round_id=1,
        attempt=2,
        model="admitted-model",
        output_schema={"patch": "full file"},
        task_kind="generation",
    )
    assert response["summary"] == "dayshift_workspace_revision_mismatch"


def test_dayshift_rejects_stale_card_and_revision(tmp_path: Path, monkeypatch):
    context = _admitted_context(tmp_path)
    optimizer = DayShiftOptimizer(tmp_path, tmp_path, "demo.py", "Implement a bounded feature", admission_context=context)
    context.task_card_identity.canonical_task_card_path and Path(context.task_card_identity.canonical_task_card_path).write_text("tampered", encoding="utf-8")
    assert optimizer.optimize()["reason"] == "dayshift_card_stale"
    context = _admitted_context(tmp_path)
    monkeypatch.setattr(optimizer, "_workspace_revision", lambda: "revision-999")
    optimizer.admission_context = context
    assert optimizer.optimize()["reason"] == "dayshift_workspace_revision_mismatch"


def test_dayshift_rejects_invalid_scope_and_verifier(tmp_path: Path):
    for allowed, verifier in [((), ("pytest",)), (("../demo.py",), ("pytest",)), (("demo.py",), ())]:
        try:
            _admitted_context(tmp_path) if allowed == ("demo.py",) and verifier == ("pytest",) else DayShiftAdmissionContext(
                task_card_identity=_admitted_context(tmp_path).task_card_identity,
                repository_root=tmp_path,
                workspace_revision="revision-001",
                allowed_files=allowed,
                verifier_command=verifier,
                admission=_admitted_context(tmp_path).admission,
                source_token=_admitted_context(tmp_path).source_token,
            )
        except ValueError:
            continue
        raise AssertionError("invalid scope/verifier was accepted")


def test_dayshift_rejects_foreign_repository_before_transport(tmp_path: Path):
    context = _admitted_context(tmp_path)
    foreign_root = tmp_path / "foreign"
    foreign_root.mkdir()
    optimizer = DayShiftOptimizer(
        foreign_root,
        foreign_root,
        "demo.py",
        "Implement a bounded feature",
        admission_context=context,
    )
    result = optimizer.optimize()
    assert result["status"] == "FAILED"
    assert result["reason"] == "dayshift_repository_mismatch"
    assert result["stage2_admitted"] is False


def test_dayshift_rejects_evaluator_block_and_model_conflict(tmp_path: Path):
    context = _admitted_context(tmp_path)
    blocked = _thaw(context.admission)
    blocked["workforce_admission"]["overall_decision"] = "BLOCK"
    try:
        DayShiftAdmissionContext(context.task_card_identity, tmp_path, "revision-001", ("demo.py",), ("pytest",), blocked, source_token=context.source_token)
    except ValueError as exc:
        assert str(exc) == "dayshift_admission_not_allowed"
    else:
        raise AssertionError("blocked evaluator accepted")
    conflict = _thaw(context.admission)
    conflict["binding"]["model"] = "foreign-model"
    try:
        DayShiftAdmissionContext(context.task_card_identity, tmp_path, "revision-001", ("demo.py",), ("pytest",), conflict, source_token=context.source_token)
    except ValueError as exc:
        assert str(exc) == "dayshift_admission_binding_conflict"
    else:
        raise AssertionError("model conflict accepted")


def test_dayshift_uses_actual_planner_admission_and_card_task_id(monkeypatch, tmp_path: Path):
    card_file = tmp_path / "card.md"
    card_file.write_text("task_id: `dayshift-positive`\nAUTO_CHAIN: false\n", encoding="utf-8")
    card = VerifiedTaskCardIdentity(
        task_id="dayshift-positive",
        task_card_path="tasks/test/dayshift-positive.md",
        canonical_task_card_path=str(card_file),
        task_card_hash=hashlib.sha256(card_file.read_bytes()).hexdigest(),
    )
    context = build_day_shift_admission_context(
        task_text="Implement a bounded feature",
        task_card_identity=card,
        repository_root=tmp_path,
        workspace_revision="revision-001",
        allowed_files=("demo.py",),
        verifier_command=("pytest", "-q"),
    )
    (tmp_path / "demo.py").write_text("value = 1\n", encoding="utf-8")
    optimizer = DayShiftOptimizer(
        project_root=tmp_path,
        swarm_dir=tmp_path,
        target_file="demo.py",
        task_desc="Implement a bounded feature",
        max_rounds=1,
        min_round_delay_sec=0,
        admission_context=context,
    )
    monkeypatch.setattr(optimizer, "_workspace_revision", lambda: "revision-001")
    monkeypatch.setattr(optimizer, "_run_tests", lambda: (0, "passed"))
    monkeypatch.setattr(
        optimizer.gateway,
        "ask_unified",
        lambda request, **_kwargs: {
            "schema": "nexus.unified_runtime.receipt.v1",
            "task_id": request.task_id,
            "online": {"status": "SUCCEEDED", "response": {"response": {"status": "APPROVED", "patch": "value = 2\n"}, "raw_response": "simulated"}},
            "receipt_complete": False,
            "claim_boundary": {"public_claim_allowed": False},
            "receipt_path": str(tmp_path / ".nexus" / "reports" / "unified_runtime" / "dayshift-positive-r1-a1.json"),
        },
    )
    result = optimizer.optimize()
    assert result["status"] == "SUCCESS"
    assert result["unified_runtime_receipts"][0]["task_id"] == "dayshift-positive"
    assert result["unified_runtime_receipts"][0]["receipt_path"].endswith("dayshift-positive-r1-a1.json")


def test_sprint_launcher_passes_admission_to_actual_dayshift_gateway(monkeypatch, tmp_path: Path):
    card_file = tmp_path / "card.md"
    card_file.write_text("task_id: `sprint-positive`\nAUTO_CHAIN: false\n", encoding="utf-8")
    card = VerifiedTaskCardIdentity(
        task_id="sprint-positive",
        task_card_path="tasks/test/sprint-positive.md",
        canonical_task_card_path=str(card_file),
        task_card_hash=hashlib.sha256(card_file.read_bytes()).hexdigest(),
    )
    (tmp_path / "demo.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "test_demo.py").write_text("def test_demo():\n    from demo import value\n    assert value == 3\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "demo.py", "test_demo.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=tmp_path, check=True)
    subprocess.run(["git", "worktree", "add", "-q", str(tmp_path / ".nexus-swarm-001"), "HEAD"], cwd=tmp_path, check=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    context = build_day_shift_admission_context(
        task_text="Implement a bounded feature",
        task_card_identity=card,
        repository_root=tmp_path,
        workspace_revision=revision,
        allowed_files=("demo.py",),
        verifier_command=(sys.executable, "-B", "-m", "pytest", "-q", "test_demo.py"),
    )
    slo = tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    slo.parent.mkdir(parents=True, exist_ok=True)
    slo.write_text('{"phase_slo_pass": true, "global": {"required_done_ratio": 1.0}}', encoding="utf-8")

    from nexus.research.sprint_service import CandidateEval, SprintConfig, run_hyper_sprint

    class _Generator:
        source = "llm"
        model_chain = ["fixture-model"]

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, **_kwargs):
            return "value = 2\n", {"source": "llm", "model_calls": 1, "tokens_used": 1}

    class _Executor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code=kwargs["code"], source=kwargs["source"])

    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", _Generator)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", _Executor)
    from nexus.research.swarm_broker import SwarmBroker
    from nexus.services.gateway import BattlesuitGateway

    original_broker_release = SwarmBroker.release

    def _release_with_readback(self, swarm_path):
        receipt = swarm_path / ".nexus" / "reports" / "unified_runtime" / "sprint-positive-r1-a1.json"
        if receipt.is_file():
            (tmp_path / "receipt-readback.json").write_bytes(receipt.read_bytes())
        (tmp_path / "target-readback.py").write_bytes((swarm_path / "demo.py").read_bytes())
        return original_broker_release(self, swarm_path)

    monkeypatch.setattr(SwarmBroker, "release", _release_with_readback)

    original_gateway_init = BattlesuitGateway.__init__

    def _gateway_init(self, *args, **kwargs):
        original_gateway_init(self, *args, **kwargs)
        self.ask_structured = lambda *_args, **_kwargs: (
            {"status": "APPROVED", "patch": "value = 3\n"},
            "simulated",
        )

    monkeypatch.setattr(BattlesuitGateway, "__init__", _gateway_init)

    def _simulated_online_invoker(context):
        return {
            "provider": "agy",
            "task_id": context["task_id"],
            "invoked": True,
            "output_delivered": True,
            "gate_passed": True,
            "provider_call_count": 1,
            "response": {"status": "APPROVED", "patch": "value = 3\n"},
            "raw_response": "simulated",
            "usage": {},
            "error": "",
            "evidence_refs": ["simulated:transport"],
            "transport": "simulated",
            "selection_source": "injected_transport",
        }

    _simulated_online_invoker.provider = "agy"
    _simulated_online_invoker.online_invoker_provider = "agy"
    result = run_hyper_sprint(
        repo_root=tmp_path,
        config=SprintConfig(
            task="Implement a bounded feature",
            target_file="demo.py",
            candidate_count=1,
            max_rounds=1,
            llm_mode=True,
            safe_mode=True,
            day_shift_admission_context=context,
            day_shift_online_invoker=_simulated_online_invoker,
        ),
    )
    assert result.status == "SUCCESS"
    runtime_receipt = result.unified_runtime_receipts[-1]
    assert runtime_receipt["task_id"] == "sprint-positive"
    assert runtime_receipt["online"]["status"] == "SUCCEEDED"
    assert ".nexus-swarm-001" in runtime_receipt["receipt_path"]
    assert (tmp_path / "target-readback.py").read_text(encoding="utf-8") == "value = 3\n"
    assert "sprint-positive" in (tmp_path / "receipt-readback.json").read_text(encoding="utf-8")
    assert result.unified_runtime_receipts[-1]["task_id"] == "sprint-positive"


def test_dayshift_generation_uses_unified_runtime_on_revisioned_workspace(monkeypatch, tmp_path: Path):
    optimizer = DayShiftOptimizer(
        project_root=tmp_path,
        swarm_dir=tmp_path,
        target_file="demo.py",
        task_desc="improve demo",
        max_rounds=1,
        min_round_delay_sec=0,
    )
    monkeypatch.setattr(optimizer, "_workspace_revision", lambda: "revision-001")
    monkeypatch.setattr(
        optimizer.gateway,
        "ask_structured",
        lambda *_args, **_kwargs: ({"status": "APPROVED", "patch": "value = 2\n"}, "raw"),
    )

    response, raw, receipt = optimizer._ask_unified(
        prompt="Return a candidate",
        payload="Return FULL file content.",
        task_statement="improve demo",
        round_id=1,
        attempt=1,
        model="gemini-test",
        output_schema={"status": "APPROVED | FAIL", "patch": "full file"},
        task_kind="generation",
    )

    assert response == {"status": "FAIL", "summary": "dayshift_admission_context_missing"}
    assert raw == ""
    assert receipt["online"]["status"] == "FAILED"
