"""Gate 2: CLI Local Assist Advisor policy, propagation, and repair-seam execution."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.services.canonical_local_assist_policy import (
    build_execution_context_fields,
    build_canonical_policy_receipt,
    collect_bounded_allowed_files,
    normalize_local_assist_policy,
)
from nexus.services.local_assist_service import LocalAssistService
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider


def test_normalize_policy_canonical_and_legacy_aliases() -> None:
    disabled = normalize_local_assist_policy("disabled")
    assert disabled["canonical_policy"] == "disabled"
    assert disabled["local_assist_requested"] is False
    assert disabled["runtime_behavior_changed"] is False

    shadow = normalize_local_assist_policy("shadow")
    assert shadow["canonical_policy"] == "shadow"
    assert shadow["runtime_behavior_changed"] is False

    advisor = normalize_local_assist_policy("advisor")
    assert advisor["canonical_policy"] == "advisor"
    assert advisor["runtime_behavior_changed"] is True

    planner = normalize_local_assist_policy("planner")
    assert planner["canonical_policy"] == "shadow"
    assert planner["legacy_policy_alias"] == "planner"
    assert "deprecated" in planner["migration_warning"]

    explicit = normalize_local_assist_policy("explicit")
    assert explicit["canonical_policy"] == "advisor"
    assert explicit["legacy_policy_alias"] == "explicit"


def test_invalid_policy_fails_closed() -> None:
    with pytest.raises(ValueError, match="invalid_local_assist_policy"):
        normalize_local_assist_policy("candidate")


def test_policy_receipt_records_alias_fields() -> None:
    task = {
        "task_id": "t-1",
        "workspace_revision": "rev-1",
        "task_statement": "fix one file",
        "task_type": "bugfix",
        "route": {"route_features": {"risk_score": 20, "adjusted_root_cause_confidence": 0.9}},
    }
    receipt = build_canonical_policy_receipt(policy="planner", task=task)
    assert receipt["canonical_policy"] == "shadow"
    assert receipt["legacy_policy_alias"] == "planner"
    assert receipt["automatic_dispatch"] is False
    assert receipt["runtime_behavior_changed"] is False
    assert receipt["planner_recommendation"] is not None


def test_execution_context_fields_for_propagation() -> None:
    fields = build_execution_context_fields(
        policy="advisor",
        task_id="cli-task-1",
        workspace_revision="rev-abc",
        policy_source="cli",
    )
    assert fields["local_assist_mode"] == "advisor"
    assert fields["local_assist_requested"] is True
    assert fields["local_assist_policy_source"] == "cli"
    assert fields["task_id"] == "cli-task-1"
    assert fields["workspace_revision"] == "rev-abc"


def test_execute_single_task_propagates_execution_context(monkeypatch, tmp_path: Path) -> None:
    from nexus.engine.canonical_task_seam import execute_single_task_via_service

    captured: dict = {}

    class _FakeService:
        def execute_bug(self, request):
            captured["request"] = request
            return True

        def execute_feature(self, request):
            raise AssertionError("unexpected feature path")

    monkeypatch.setattr(
        "nexus.engine.canonical_task_seam.build_command_service",
        lambda _root: _FakeService(),
    )
    ctx = build_execution_context_fields(
        policy="shadow",
        task_id="fix-race",
        workspace_revision="rev-1",
    )
    ok = execute_single_task_via_service("fix race condition", tmp_path, execution_context=ctx)
    assert ok is True
    request = captured["request"]
    assert request.execution_context["local_assist_mode"] == "shadow"
    assert request.execution_context["workspace_revision"] == "rev-1"
    assert request.execution_context["task_id"] == "fix-race"


def test_command_service_merges_local_assist_into_engine_context(monkeypatch, tmp_path: Path) -> None:
    from nexus.app.command_service import NexusCommandService, TaskRequest

    captured: dict = {}

    class _Engine:
        project_root = tmp_path
        run_dir = tmp_path / "runs"

        def run_bug(self, **kwargs):
            captured["context"] = kwargs.get("context") or {}
            return True

    service = NexusCommandService(_Engine())
    fields = build_execution_context_fields(
        policy="advisor",
        task_id="bug-1",
        workspace_revision="rev-9",
    )
    ok = service.execute_bug(
        TaskRequest(task="repair target.py", task_id="bug-1", execution_context=fields)
    )
    assert ok is True
    assert captured["context"]["local_assist_mode"] == "advisor"
    assert captured["context"]["workspace_revision"] == "rev-9"
    assert captured["context"]["task_id"] == "bug-1"


def _repair_mixin_harness(tmp_path: Path, *, mode: str, allowed: list[str] | None = None):
    from nexus.engine.pipeline_repair import PipelineRepairMixin

    class _Harness(PipelineRepairMixin):
        def __init__(self):
            self.engine = SimpleNamespace(project_root=tmp_path, run_dir=tmp_path / "runs")

    harness = _Harness()
    target = tmp_path / "demo.py"
    target.write_text("def demo():\n    return 1\n", encoding="utf-8")
    meta = {
        "local_assist_mode": mode,
        "local_assist_policy_raw": mode,
        "task_id": "gate2-task-1",
        "workspace_revision": "rev-gate2",
        "target_file": "demo.py",
        "target_files": allowed if allowed is not None else ["demo.py"],
        "local_assist_model": "fixture-model",
        "local_assist_planner_snapshot": {
            "route_truth_source": "CapabilityPlanner",
            "execution_topology": "single_local_model",
            "protocol_mode": "unified_diff",
            "model_call_allowed": True,
            "executor_provider": "ollama",
            "executor_model": "fixture-model",
        },
    }
    state = SimpleNamespace(metadata=meta, task_id="gate2-task-1")
    ctx = SimpleNamespace(state=state, task_id="gate2-task-1", task_desc="repair demo.py bounded")
    return harness, ctx, meta


def _assert_distinct_truth_booleans(meta: dict) -> None:
    for key in (
        "local_assist_success",
        "online_success",
        "runtime_receipt_complete",
        "task_pipeline_success",
    ):
        assert key in meta, f"missing distinct truth flag: {key}"
        assert isinstance(meta[key], bool), f"{key} must be bool, got {type(meta[key])}"


def test_disabled_mode_does_not_invoke_local(tmp_path: Path) -> None:
    harness, ctx, meta = _repair_mixin_harness(tmp_path, mode="disabled")
    calls: list[str] = []

    def online(prompt: str):
        calls.append(prompt)
        return {"status": "APPROVED", "patch": "ok"}, "raw-ok"

    res, raw = harness._run_unified_advisor_online(ctx, online_callable=online, repair_attempts=1)
    assert res["status"] == "APPROVED"
    assert raw == "raw-ok"
    assert meta.get("local_assist_status") == "NOT_REQUESTED"
    assert "LOCAL_ASSIST_CONTEXT" not in calls[0]
    assert meta.get("local_assist_contributed") is False
    _assert_distinct_truth_booleans(meta)
    assert meta["local_assist_success"] is False
    assert meta["online_success"] is True
    assert meta["task_pipeline_success"] is False


def test_shadow_mode_records_recommendation_without_local_call(tmp_path: Path) -> None:
    harness, ctx, meta = _repair_mixin_harness(tmp_path, mode="shadow")
    online_prompts: list[str] = []

    def online(prompt: str):
        online_prompts.append(prompt)
        return {"status": "APPROVED", "patch": "shadow-ok"}, "raw"

    provider_calls = {"n": 0}

    class _Counting(InjectedLocalModelProvider):
        def generate(self, request):  # type: ignore[override]
            provider_calls["n"] += 1
            return super().generate(request)

    meta["local_assist_service"] = LocalAssistService(
        provider=_Counting(lambda _r: "should-not-run")
    )
    res, _raw = harness._run_unified_advisor_online(ctx, online_callable=online, repair_attempts=1)
    assert res["patch"] == "shadow-ok"
    assert meta["local_assist_status"] == "SHADOW_RECORDED"
    assert provider_calls["n"] == 0
    assert "LOCAL_ASSIST_CONTEXT" not in online_prompts[0]
    assert meta.get("local_context_forwarded") is False
    assert meta.get("local_assist_contributed") is False
    _assert_distinct_truth_booleans(meta)
    assert meta["local_assist_success"] is False
    assert meta["online_success"] is True


def test_advisor_success_forwards_local_diagnosis_to_online(tmp_path: Path) -> None:
    harness, ctx, meta = _repair_mixin_harness(tmp_path, mode="advisor")
    online_prompts: list[str] = []

    def online(prompt: str):
        online_prompts.append(prompt)
        return {"status": "APPROVED", "patch": "fixed", "provider": "fixture-online"}, "raw-online"

    meta["local_assist_service"] = LocalAssistService(
        provider=InjectedLocalModelProvider(lambda _r: "local diagnosis: prefer strip whitespace")
    )
    res, raw = harness._run_unified_advisor_online(ctx, online_callable=online, repair_attempts=1)
    assert res["patch"] == "fixed"
    assert raw == "raw-online"
    assert "local diagnosis: prefer strip whitespace" in online_prompts[0]
    assert "LOCAL_ASSIST_CONTEXT" in online_prompts[0]
    assert meta["local_assist_status"] == "SUCCEEDED"
    assert meta["local_context_forwarded"] is True
    assert meta["local_assist_contributed"] is True
    assert meta["unified_runtime_task_id"] == "gate2-task-1"
    assert meta["workspace_revision"] == "rev-gate2"
    receipt = meta["unified_runtime_receipt"]
    assert receipt["schema"] == "nexus.unified_runtime.receipt.v1"
    assert receipt["task_id"] == "gate2-task-1"
    assert receipt["workspace_revision"] == "rev-gate2"
    assert receipt["local"]["invoked"] is True
    assert receipt["online"]["invoked"] is True
    assert receipt["claim_boundary"]["local_online_continuation"] is True
    assert receipt["claim_boundary"]["public_claim_allowed"] is False
    # Formal workspace unchanged
    assert (tmp_path / "demo.py").read_text(encoding="utf-8") == "def demo():\n    return 1\n"
    pointer = Path(meta["unified_runtime_pointer_path"])
    assert pointer.is_file()
    _assert_distinct_truth_booleans(meta)
    assert meta["local_assist_success"] is True
    assert meta["online_success"] is True
    assert meta["task_pipeline_success"] is False


def test_advisor_empty_local_outputs_does_not_force_forward(tmp_path: Path) -> None:
    """Local invoked with empty local_outputs must not force local_context_forwarded."""
    harness, ctx, meta = _repair_mixin_harness(tmp_path, mode="advisor")
    online_prompts: list[str] = []

    def online(prompt: str):
        online_prompts.append(prompt)
        return {"status": "APPROVED", "patch": "online"}, "raw"

    class _EmptyBody:
        def handle(self, request, **_kwargs):
            return SimpleNamespace(
                to_dict=lambda: {
                    "task_id": request.task_id,
                    "status": "SUCCEEDED",
                    "local_model_invoked": True,
                    "invoked": True,
                    "output_delivered": True,
                    "local_outputs": {},
                    "evidence_refs": [f"local:{request.task_id}:empty"],
                    "receipt_path": str(tmp_path / "empty_local.json"),
                    "provider": "injected",
                    "gate_passed": True,
                },
                task_id=request.task_id,
                status="SUCCEEDED",
                local_model_invoked=True,
                output_delivered=True,
                local_outputs={},
                evidence_refs=(f"local:{request.task_id}:empty",),
                receipt_path=str(tmp_path / "empty_local.json"),
            )

    meta["local_assist_service"] = _EmptyBody()
    res, _raw = harness._run_unified_advisor_online(ctx, online_callable=online, repair_attempts=1)
    assert res["patch"] == "online"
    assert "LOCAL_ASSIST_CONTEXT" not in online_prompts[0]
    assert meta["local_context_forwarded"] is False
    assert meta["local_assist_contributed"] is False
    assert meta["local_assist_status"] in {"EMPTY_OUTPUTS", "SUCCEEDED", "FAILED"}
    # If status is SUCCEEDED only with real body; empty body must not contribute.
    assert meta["local_assist_success"] is False
    assert meta["online_success"] is True
    _assert_distinct_truth_booleans(meta)


def test_advisor_degrades_when_bounded_scope_missing(tmp_path: Path) -> None:
    harness, ctx, meta = _repair_mixin_harness(tmp_path, mode="advisor", allowed=[])
    meta.pop("target_file", None)
    meta["target_files"] = []
    online_calls = {"n": 0}

    def online(prompt: str):
        online_calls["n"] += 1
        return {"status": "APPROVED", "patch": "online-only"}, "raw"

    meta["local_assist_service"] = LocalAssistService(
        provider=InjectedLocalModelProvider(lambda _r: "should-not-matter")
    )
    res, _raw = harness._run_unified_advisor_online(ctx, online_callable=online, repair_attempts=1)
    assert res["patch"] == "online-only"
    assert online_calls["n"] == 1
    assert meta["local_assist_status"] == "NOT_INVOKED"
    assert meta["degraded_to_online"] is True
    assert meta["degradation_reason"] == "bounded_scope_missing"
    assert meta["local_assist_contributed"] is False
    _assert_distinct_truth_booleans(meta)
    assert meta["local_assist_success"] is False
    assert meta["online_success"] is True


def test_advisor_degrades_when_local_provider_fails(tmp_path: Path) -> None:
    harness, ctx, meta = _repair_mixin_harness(tmp_path, mode="advisor")
    online_calls = {"n": 0}

    def online(prompt: str):
        online_calls["n"] += 1
        return {"status": "APPROVED", "patch": "continued"}, "raw"

    class _Boom:
        def handle(self, request, **_kwargs):
            raise RuntimeError("local_timeout")

    meta["local_assist_service"] = _Boom()
    res, _raw = harness._run_unified_advisor_online(ctx, online_callable=online, repair_attempts=1)
    assert res["patch"] == "continued"
    assert online_calls["n"] == 1
    assert meta.get("degraded_to_online") is True
    assert meta.get("local_assist_contributed") is False
    # Local stage failed; Online continued.
    receipt = meta.get("unified_runtime_receipt") or {}
    if receipt:
        assert receipt["local"]["status"] == "FAILED" or receipt["local"].get("invoked") is False
        assert receipt.get("claim_boundary", {}).get("public_claim_allowed") is False
    _assert_distinct_truth_booleans(meta)
    assert meta["local_assist_success"] is False
    assert meta["online_success"] is True


def test_collect_bounded_allowed_files_from_metadata() -> None:
    files = collect_bounded_allowed_files(
        {"target_file": "a.py", "target_files": ["b.py", "a.py"], "plan_target_files": ["../evil"]},
        task_desc="",
    )
    assert files == ["b.py", "a.py"]


def _build_execute_single_repair_ctx(tmp_path: Path, *, mode: str, surgical: bool):
    """Minimal real composition for PipelineRepairMixin._execute_single_repair."""
    from contextlib import nullcontext

    from nexus.engine.pipeline_repair import PipelineRepairMixin

    class _Harness(PipelineRepairMixin):
        def __init__(self):
            self.engine = SimpleNamespace(
                project_root=tmp_path,
                run_dir=tmp_path / "runs",
                _add_step_to_history=lambda *a, **k: None,
            )
            self.registry = None

        def _prepare_repair_context(self, ctx, repair_attempts):
            return None

        def _process_repair_response(self, ctx, res, repair_attempts):
            status = "APPROVED" if isinstance(res, dict) and res.get("status") == "APPROVED" else "FAILED"
            return {
                "status": status,
                "result": res if isinstance(res, dict) else {},
                "current_decision_id": "d1",
                "current_skill_id": "s1",
            }

        def _run_pregate_if_needed(self, ctx, status, result):
            return status

        def _write_hallucination_evidence_bundle(self, ctx):
            return None

        def _record_intra_loop_trauma(self, ctx, r_out):
            return None

        def _run_composition_repair_phase(self, ctx, repair_attempts):
            return None

        def _register_phase_decision(self, ctx, phase, name):
            return f"{phase}-{name}"

    (tmp_path / "demo.py").write_text("def demo():\n    return 1\n", encoding="utf-8")
    (tmp_path / "nexus").mkdir(exist_ok=True)

    online_prompts: list[str] = []

    def _surgical_ask(*, task, symbols=None, phase="R", rejection_receipt=None, attempt=1):
        online_prompts.append(str(task))
        return {"status": "APPROVED", "patch": "surgical-ok", "provider": "fixture"}, "raw-surgical"

    def _ask_structured(prompt, payload="", **kwargs):
        online_prompts.append(str(prompt))
        return {"status": "APPROVED", "patch": "nonsurgical-ok", "provider": "fixture"}, "raw-ns"

    class _Gateway:
        use_surgical_repair = surgical

        def surgical_ask(self, *, task, symbols=None, phase="R", rejection_receipt=None, attempt=1):
            return _surgical_ask(
                task=task,
                symbols=symbols,
                phase=phase,
                rejection_receipt=rejection_receipt,
                attempt=attempt,
            )

        def ask_structured(self, prompt, payload="", **kwargs):
            return _ask_structured(prompt, payload, **kwargs)

        def apply_patch_v2(self, *a, **k):
            return {"success": False}

    class _Repairer:
        def __init__(self):
            self.gateway = _Gateway()

        def run(self, state, pack, bayesian_params=None):
            return {"status": "APPROVED", "source": "repairer.run"}

    meta = {
        "local_assist_mode": mode,
        "local_assist_policy_raw": mode,
        "task_id": "exec-repair-1",
        "workspace_revision": "rev-exec",
        "target_file": "demo.py",
        "target_files": ["demo.py"],
        "use_surgical_repair": surgical,
        "local_assist_model": "fixture-model",
        "local_assist_planner_snapshot": {
            "route_truth_source": "CapabilityPlanner",
            "execution_topology": "single_local_model",
            "protocol_mode": "unified_diff",
            "model_call_allowed": True,
            "executor_provider": "ollama",
            "executor_model": "fixture-model",
        },
        "local_assist_service": LocalAssistService(
            provider=InjectedLocalModelProvider(lambda _r: "local diagnosis via execute_single_repair")
        ),
    }
    if not surgical:
        meta["local_assist_online_callable"] = lambda prompt: (
            online_prompts.append(str(prompt)) or ({"status": "APPROVED", "patch": "nonsurgical-ok"}, "raw-ns")
        )

    state = SimpleNamespace(metadata=meta, task_id="exec-repair-1", current_step_id="s1", retry_count=0)
    ctx = SimpleNamespace(
        state=state,
        task_id="exec-repair-1",
        task_desc="repair demo.py bounded",
        pack={},
        bayesian_params={},
        dry_run=False,
        repairer=_Repairer(),
        accumulator=SimpleNamespace(record=lambda *a, **k: None),
    )
    tracer = SimpleNamespace(phase_span=lambda *a, **k: nullcontext())
    harness = _Harness()
    return harness, ctx, meta, online_prompts


def test_execute_single_repair_surgical_advisor_path(tmp_path: Path) -> None:
    harness, ctx, meta, prompts = _build_execute_single_repair_ctx(
        tmp_path, mode="advisor", surgical=True
    )
    r_out = harness._execute_single_repair(ctx, tracer=SimpleNamespace(phase_span=lambda *a, **k: __import__("contextlib").nullcontext()), repair_attempts=1)
    assert r_out["status"] == "APPROVED"
    assert any("local diagnosis via execute_single_repair" in p for p in prompts)
    assert meta["local_context_forwarded"] is True
    assert meta["local_assist_contributed"] is True
    _assert_distinct_truth_booleans(meta)
    assert meta["local_assist_success"] is True
    assert meta["online_success"] is True


def test_execute_single_repair_nonsurgical_advisor_path(tmp_path: Path) -> None:
    harness, ctx, meta, prompts = _build_execute_single_repair_ctx(
        tmp_path, mode="advisor", surgical=False
    )
    from contextlib import nullcontext

    r_out = harness._execute_single_repair(
        ctx,
        tracer=SimpleNamespace(phase_span=lambda *a, **k: nullcontext()),
        repair_attempts=1,
    )
    assert r_out["status"] == "APPROVED"
    assert any("local diagnosis via execute_single_repair" in p for p in prompts)
    assert meta["local_assist_contributed"] is True
    _assert_distinct_truth_booleans(meta)
    assert meta["local_assist_success"] is True
    assert meta["online_success"] is True


def test_execute_single_repair_disabled_skips_local(tmp_path: Path) -> None:
    harness, ctx, meta, prompts = _build_execute_single_repair_ctx(
        tmp_path, mode="disabled", surgical=True
    )
    from contextlib import nullcontext

    provider_calls = {"n": 0}

    class _Count(InjectedLocalModelProvider):
        def generate(self, request):  # type: ignore[override]
            provider_calls["n"] += 1
            return super().generate(request)

    meta["local_assist_service"] = LocalAssistService(provider=_Count(lambda _r: "nope"))
    r_out = harness._execute_single_repair(
        ctx,
        tracer=SimpleNamespace(phase_span=lambda *a, **k: nullcontext()),
        repair_attempts=1,
    )
    assert r_out["status"] == "APPROVED"
    assert provider_calls["n"] == 0
    assert not any("LOCAL_ASSIST_CONTEXT" in p for p in prompts)
    _assert_distinct_truth_booleans(meta)
    assert meta["local_assist_success"] is False


def test_execute_single_repair_shadow_no_local_invoke(tmp_path: Path) -> None:
    harness, ctx, meta, prompts = _build_execute_single_repair_ctx(
        tmp_path, mode="shadow", surgical=True
    )
    from contextlib import nullcontext

    provider_calls = {"n": 0}

    class _Count(InjectedLocalModelProvider):
        def generate(self, request):  # type: ignore[override]
            provider_calls["n"] += 1
            return super().generate(request)

    meta["local_assist_service"] = LocalAssistService(provider=_Count(lambda _r: "nope"))
    r_out = harness._execute_single_repair(
        ctx,
        tracer=SimpleNamespace(phase_span=lambda *a, **k: nullcontext()),
        repair_attempts=1,
    )
    assert r_out["status"] == "APPROVED"
    assert provider_calls["n"] == 0
    assert meta["local_assist_status"] == "SHADOW_RECORDED"
    assert not any("LOCAL_ASSIST_CONTEXT" in p for p in prompts)
    _assert_distinct_truth_booleans(meta)
    assert meta["local_assist_success"] is False
    assert meta["online_success"] is True
