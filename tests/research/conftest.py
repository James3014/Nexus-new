"""Governed Workforce Admission fixtures for tests/research (#1929).

Fixture transports (a fake ``BattlesuitGateway.ask_structured`` or an injected online
invoker) are classified physical unless the request carries canonical Workforce bindings,
so Admission blocks the online call before the fake is reached.  The
``governed_admission`` fixture binds the canonical default worker
(``agy_flash_38`` / ``gemini-3.8-flash-medium``) with the controls it requires, the same
way ``tests/services/test_unified_runtime.py::_admit_gateway_request`` does.  Production
admission code is untouched; the runtime still resolves and enforces the decision.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest

ADMITTED_WORKER = "agy_flash_38"
ADMITTED_PROVIDER = "agy"
ADMITTED_MODEL = "gemini-3.8-flash-medium"
ONLINE_CONTROLS = [
    "task_card",
    "allowed_files",
    "mandatory_commands",
    "parser",
    "verifier",
    "independent_verification",
]
LOCAL_QWEN_CONTROLS = [
    "bounded_context",
    "parser",
    "external_verifier",
    "counterexample_suite",
    "role_specific_suite",
]
LOCAL_CODER_CONTROLS = [
    "small_scope",
    "parser",
    "compile",
    "focused_tests",
    "reversible_application",
]


FIXTURE_CAPABILITIES = (
    "harness_preflight_sensor",
    "repair_loop",
    "delivery_gate",
    "pregate",
    "plan_quality_gate",
    "mempalace_gate",
    "artifact_gate",
    "claim_gate",
    "research_route",
    "memory",
    "local_model_executor",
)


def _fixture_capability_invoker(name: str) -> Any:
    def invoke(ctx: Any) -> dict[str, Any]:
        return {
            "task_id": ctx["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"test:{name}:{ctx['task_id']}:fixture"],
        }

    return invoke


def _forwarding_invoker(invoker: Any) -> Any:
    """Forward the Local assist output into the online prompt, as the Gateway transport does."""

    def invoke(context: Any) -> dict[str, Any]:
        local_stage = context.get("local") if isinstance(context.get("local"), dict) else {}
        response = (
            local_stage.get("response") if isinstance(local_stage.get("response"), dict) else {}
        )
        outputs = (
            response.get("local_outputs") if isinstance(response.get("local_outputs"), dict) else {}
        )
        if not outputs:
            return invoker(context)
        prompt = str(context.get("online_prompt") or context.get("task_statement") or "")
        prompt += "\n\n[LOCAL_ASSIST_CONTEXT]\n" + json.dumps(
            outputs, ensure_ascii=False, sort_keys=True
        )
        payload = invoker({**context, "online_prompt": prompt})
        refs = list(payload.get("evidence_refs") or [])
        refs.append(f"gateway:{context['task_id']}:local_context_forwarded")
        return {**payload, "evidence_refs": refs}

    invoke.provider = ADMITTED_PROVIDER  # type: ignore[attr-defined]
    invoke.online_invoker_provider = ADMITTED_PROVIDER  # type: ignore[attr-defined]
    return invoke


def admit_request(request: Any, *, advisor_only: bool = False) -> Any:
    """Return ``request`` with canonical Workforce bindings attached to its route."""
    route = dict(request.route)
    local_request = getattr(request, "local_request", None)
    if advisor_only and request.local_enabled and getattr(local_request, "action", "") == "advisor":
        # Advisor-only Local assist (planning + advisor, #2089): bind the read-only advisor
        # worker.  task_type is NOT rewritten here; the test must declare "planning" itself.
        # A repair sprint with an advisor action is refused by the runtime (fail-closed).
        route["mutation_requested"] = False
        if not getattr(local_request, "planner_snapshot", None):
            request = replace(
                request,
                local_request=replace(
                    local_request,
                    requested_role="advisor",
                    mutation_policy="isolated_only",
                    planner_snapshot={
                        "route_truth_source": "CapabilityPlanner",
                        "execution_topology": "single_local_model",
                        "protocol_mode": "unified_diff",
                        "model_call_allowed": True,
                        "executor_provider": "ollama",
                        "executor_model": "qwen3.5:9b",
                    },
                ),
            )
    bindings = dict(route.get("workforce_bindings") or {})
    bindings.setdefault("online", {"worker_id": ADMITTED_WORKER, "controls": list(ONLINE_CONTROLS)})
    if request.local_enabled:
        if route.get("mutation_requested") is False:
            bindings.setdefault(
                "local", {"worker_id": "local_qwen35_9b", "controls": list(LOCAL_QWEN_CONTROLS)}
            )
        else:
            bindings.setdefault(
                "local", {"worker_id": "local_coder_7b", "controls": list(LOCAL_CODER_CONTROLS)}
            )
    route["workforce_bindings"] = bindings
    route["workforce_admission_enabled"] = True
    route["injected_transport"] = True
    route.setdefault("provider", ADMITTED_PROVIDER)
    route.setdefault("online_invoker_provider", ADMITTED_PROVIDER)
    changes: dict[str, Any] = {"route": route}
    if not getattr(request, "online_model_name", None):
        changes["online_model_name"] = ADMITTED_MODEL
    return replace(request, **changes)


def _install(monkeypatch: pytest.MonkeyPatch, *, advisor_only: bool) -> None:
    import nexus.services.unified_runtime as unified_runtime
    from nexus.services.gateway import BattlesuitGateway

    # Lane-declared bindings for the sprint candidate's route (sprint_service reads this).
    monkeypatch.setenv(
        "NEXUS_BENCH_WORKFORCE_BINDINGS_JSON",
        json.dumps({"online": {"worker_id": ADMITTED_WORKER, "controls": list(ONLINE_CONTROLS)}}),
    )
    # Only the admitted identity can be dispatched; the stale default chain is retired.
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", ADMITTED_MODEL)
    # BattlesuitGateway resolves NEXUS_OAUTH_PROVIDER=auto by probing localhost Ollama
    # (/api/tags): "ollama" on a host with a local gateway, "gemini" on a clean CI runner.
    # The route provider then differs by host and Admission blocks the online call on CI.
    # Pin the admitted provider so the result no longer depends on the host's Ollama.
    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", ADMITTED_PROVIDER)

    original_builder = unified_runtime.build_structured_online_invoker

    def build_admitted_invoker(*args: Any, **kwargs: Any) -> Any:
        kwargs["provider"] = ADMITTED_PROVIDER
        return original_builder(*args, **kwargs)

    monkeypatch.setattr(unified_runtime, "build_structured_online_invoker", build_admitted_invoker)

    original_ask_unified = BattlesuitGateway.ask_unified

    def ask_unified(self: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
        # A fixture ask_structured cannot be reached through the deferred Workforce
        # transport; hand the admitted runtime an explicit structured invoker instead.
        if kwargs.get("online_invoker") is None:
            kwargs["online_invoker"] = _forwarding_invoker(
                original_builder(
                    self.ask_structured,
                    phase=request.online_phase,
                    model_name=request.online_model_name,
                    output_schema=request.online_output_schema,
                    provider=ADMITTED_PROVIDER,
                )
            )
        kwargs.setdefault(
            "capability_invokers",
            {name: _fixture_capability_invoker(name) for name in FIXTURE_CAPABILITIES},
        )
        rq = admit_request(request, advisor_only=advisor_only)
        r = original_ask_unified(self, rq, *args, **kwargs)
        return r

    monkeypatch.setattr(BattlesuitGateway, "ask_unified", ask_unified)

    original_run = unified_runtime.UnifiedRuntime.run

    def run(self: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
        return original_run(
            self, admit_request(request, advisor_only=advisor_only), *args, **kwargs
        )

    monkeypatch.setattr(unified_runtime.UnifiedRuntime, "run", run)


@pytest.fixture
def governed_admission(monkeypatch: pytest.MonkeyPatch) -> None:
    """Admit the online worker; a Local assist binds the bounded code candidate worker."""
    _install(monkeypatch, advisor_only=False)


@pytest.fixture
def governed_admission_advisor(monkeypatch: pytest.MonkeyPatch) -> None:
    """As ``governed_admission`` but Local advisor assists bind the read-only advisor worker."""
    _install(monkeypatch, advisor_only=True)
