from __future__ import annotations

from nexus.services.unified_runtime import materialize_selected_capability_evidence


def _run(**overrides):
    selected = overrides.pop("selected_capabilities", ["memory", "acceptance_check"])
    calls = []

    def invoker(name):
        def execute(context):
            calls.append(name)
            return {
                "task_id": context["task_id"],
                "invoked": True,
                "gate_passed": True,
                "status": "SUCCEEDED",
                "evidence_refs": [f"evidence:{name}"],
                "consumer_payload": {"result": f"payload:{name}"},
            }

        return execute

    invokers = overrides.pop(
        "capability_invokers",
        {
            "memory": invoker("memory"),
            "acceptance_check": invoker("acceptance_check"),
            "unselected": invoker("unselected"),
        },
    )
    result = materialize_selected_capability_evidence(
        planner_output={"plan_hash": "plan-1"},
        selected_capabilities=selected,
        task_id="task-1",
        task_statement="inspect",
        workspace_revision="rev-1",
        plan_hash="plan-1",
        planner_decision_id="decision-1",
        capability_invokers=invokers,
        capability_context={"capability_results": {}},
        **overrides,
    )
    return result, calls


def test_materializes_selected_non_local_non_postflight_once_and_seals_payload():
    (results, bundle), calls = _run()
    assert calls == ["memory"]
    assert list(results) == ["memory"]
    assert bundle["entries"][0]["consumer_payload"]["fields"]["result"] == "payload:memory"
    assert bundle["entries"][0]["has_consumer_payload"] is True


def test_empty_selection_returns_compatible_empty_bundle():
    (results, bundle), calls = _run(selected_capabilities=[])
    assert results == {}
    assert calls == []
    assert bundle["selected_capabilities"] == []
    assert bundle["entries"] == []


def test_reverse_and_duplicate_selection_runs_each_registry_entry_once():
    order = []

    def memory(context):
        order.append("memory")
        return {
            "task_id": context["task_id"],
            "invoked": True,
            "status": "SUCCEEDED",
            "gate_passed": True,
            "evidence_refs": ["memory"],
        }

    def codeintel(context):
        order.append("codeintel")
        return {
            "task_id": context["task_id"],
            "invoked": True,
            "status": "SUCCEEDED",
            "gate_passed": True,
            "evidence_refs": ["codeintel"],
        }

    (results, bundle), calls = _run(
        selected_capabilities=["memory", "codeintel", "memory"],
        capability_invokers={"memory": memory, "codeintel": codeintel},
    )
    assert calls == []
    assert order == ["codeintel", "memory"]
    assert list(results) == ["codeintel", "memory"]
    assert [entry["name"] for entry in bundle["entries"]] == ["memory", "codeintel", "memory"]


def test_explicit_skip_remains_visible_without_materialized_success():
    def skipped(_context):
        return {
            "task_id": "task-1",
            "invoked": False,
            "status": "SKIPPED",
            "skipped": True,
            "skip_reason": "not applicable",
            "evidence_refs": ["skip:1"],
        }

    (results, bundle), calls = _run(
        selected_capabilities=["skipped"],
        capability_invokers={"skipped": skipped},
    )
    assert calls == []
    assert results["skipped"]["status"] == "SKIPPED"
    assert bundle["entries"][0]["status"] == "SKIPPED"
    assert bundle["entries"][0]["success"] is False


def test_exception_and_non_callable_are_not_materialized_successes():
    def broken(_context):
        raise RuntimeError("boom")

    (results, bundle), _ = _run(
        selected_capabilities=["broken", "missing"],
        capability_invokers={"broken": broken, "missing": object()},
    )
    assert list(results) == ["broken", "missing"]
    assert all(not entry["success"] for entry in bundle["entries"])
    assert all(not entry["has_consumer_payload"] for entry in bundle["entries"])


def test_local_capability_is_excluded_from_preflight():
    calls = []

    def local(context):
        calls.append(context["task_id"])
        return {
            "task_id": context["task_id"],
            "invoked": True,
            "status": "SUCCEEDED",
            "gate_passed": True,
            "evidence_refs": ["local"],
        }

    (results, bundle), _ = _run(
        selected_capabilities=["local_model_executor"],
        capability_invokers={"local_model_executor": local},
    )
    assert calls == []
    assert results == {}
    assert bundle["entries"][0]["status"] == "PENDING_OR_STAGE_OWNED"


def test_run_once_uses_shared_materialization_helper(monkeypatch):
    import sys

    from nexus.services import runtime_compat
    from tests.services.test_unified_runtime import _Planner, _request

    exports = runtime_compat.build_host_runtime_exports()
    original = exports.materialize_selected_capability_evidence
    calls = []

    old_profile = sys.getprofile()

    def profile(frame, event, arg):
        if event == "call" and frame.f_code is original.__code__:
            calls.append(frame.f_locals.get("selected_capabilities"))
        if old_profile is not None:
            old_profile(frame, event, arg)

    sys.setprofile(profile)
    try:
        receipt = exports.UnifiedRuntime(planner=_Planner()).run(
            _request(),
            online_invoker=lambda context: {
                "task_id": context["task_id"],
                "invoked": True,
                "status": "SUCCEEDED",
                "gate_passed": True,
                "evidence_refs": ["online"],
            },
            verifier=lambda context: {
                "task_id": context["task_id"],
                "invoked": True,
                "status": "SUCCEEDED",
                "gate_passed": True,
                "evidence_refs": ["verifier"],
            },
            learning=lambda context: {
                "task_id": context["task_id"],
                "invoked": True,
                "status": "SUCCEEDED",
                "gate_passed": True,
                "evidence_refs": ["learning"],
            },
        )
    finally:
        sys.setprofile(old_profile)
    assert len(calls) == 1
    assert receipt["capability_evidence_bundle"]["bundle_hash"]


def test_run_once_preserves_structured_seal_failure_receipt(monkeypatch):
    import nexus_runtime_support_candidate.composition as bundle_module

    from nexus.services import runtime_compat
    from tests.services.test_unified_runtime import _Planner, _request

    monkeypatch.setattr(
        bundle_module, "build_capability_evidence_bundle", lambda **_: {"tampered": True}
    )
    receipt = (
        runtime_compat
        .build_host_runtime_exports()
        .UnifiedRuntime(planner=_Planner())
        .run(_request())
    )
    assert receipt["terminal_status"] == "BLOCKED"
    assert receipt["stages"][1]["status"] == "BLOCKED"
    assert receipt["online"]["status"] == "NOT_REQUESTED"
