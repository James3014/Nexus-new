"""Characterization of the dispatch-binding / action-request helpers of SHTS (split S4).

Big-file split step S4 moves eight module-level helpers out of
``nexus/orchestrator/self_hosted_task_service.py`` into a part module.  These tests pin
their behaviour before the move and must pass unchanged after it:

* workforce dispatch binding: ``_workforce_dispatch_inputs`` (source precedence),
  ``_tracked_dispatch_required``, ``_workforce_admission_readback_matches`` (only a
  forward ``verified_age_days`` drift is tolerated), ``validate_workforce_dispatch_binding``
  (every denial and its order, the exact evaluator / envelope-builder arguments, the
  result) and ``_recover_pre_provider_cli_envelope_drift`` (every guard, the call order
  of the two validations, the envelope rebuild and the persisted-dispatch assertion);
* action request validation: ``_validated_action_request`` (every denial and its order,
  including the #1579 RIE-identity and codeintel-lookup outer-copy checks,
  the effective request), ``_validate_project_entry_authority_binding`` and
  ``_reject_unbound_project_entry_authority_hints``;
* that every facade-module name the helpers read (including the helpers themselves when
  one calls another) is resolved through the facade at call time, so patches on
  ``nexus.orchestrator.self_hosted_task_service`` keep taking effect, also for the
  late-bound ``runtime_retry_bridge`` accessors.
"""

from __future__ import annotations

import copy
import inspect
import json
from types import SimpleNamespace
from typing import Any

import pytest

import nexus.orchestrator.self_hosted_task_service as service_module
from nexus.contracts.lifecycle_action import canonical_request_hash
from nexus.orchestrator import runtime_coordination_bridge, runtime_retry_bridge
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService as RealService

# ---------------------------------------------------------------------------
# member table

MEMBERS = {
    "_workforce_dispatch_inputs": "(request: 'Mapping[str, Any]') -> 'tuple[Any, Any]'",
    "_tracked_dispatch_required": (
        "(request: 'Mapping[str, Any]', state: 'Optional[Mapping[str, Any]]' = None) -> 'bool'"
    ),
    "_workforce_admission_readback_matches": (
        "(persisted: 'Mapping[str, Any]', fresh: 'Mapping[str, Any]') -> 'bool'"
    ),
    "validate_workforce_dispatch_binding": (
        "(request: 'Mapping[str, Any]', *, require_binding: 'bool' = False)"
        " -> 'Optional[dict[str, Any]]'"
    ),
    "_recover_pre_provider_cli_envelope_drift": (
        "(state: 'Mapping[str, Any]', request: 'Mapping[str, Any]', failure: 'RuntimeError')"
        " -> 'Optional[dict[str, Any]]'"
    ),
    "_validated_action_request": (
        "(request: 'Mapping[str, Any]') -> 'tuple[dict[str, Any], Optional[dict[str, Any]]]'"
    ),
    "_validate_project_entry_authority_binding": (
        "(request: 'Mapping[str, Any]', *, repository: 'str | None' = None,"
        " issue_number: 'int | None' = None) -> 'dict[str, str] | None'"
    ),
    "_reject_unbound_project_entry_authority_hints": ("(request: 'Mapping[str, Any]') -> 'None'"),
}


@pytest.mark.parametrize("name", sorted(MEMBERS))
def test_member_is_a_plain_function_with_pinned_signature(name: str) -> None:
    value = getattr(service_module, name)
    assert inspect.isfunction(value)
    assert value.__name__ == name
    assert str(inspect.signature(value)) == MEMBERS[name]


def test_coordination_bridge_imports_the_facade_objects() -> None:
    assert (
        runtime_coordination_bridge._tracked_dispatch_required
        is service_module._tracked_dispatch_required
    )
    assert (
        runtime_coordination_bridge.validate_workforce_dispatch_binding
        is service_module.validate_workforce_dispatch_binding
    )


def test_project_entry_hint_keys_are_pinned() -> None:
    assert service_module._PROJECT_ENTRY_AUTHORITY_HINTS == frozenset({
        "authority_goal_id",
        "authority_coordination_scope_id",
        "standing_grant_id",
        "autonomy_goal_id",
        "autonomy_submission_binding",
        "autonomy_goal_grant",
        "governed",
        "governed_task",
        "intended_action_family",
        "required_action_family",
    })


# ---------------------------------------------------------------------------
# _workforce_dispatch_inputs

PLANNER = {
    "signal_snapshot": {"workforce_demands": "planner-snapshot-demands"},
    "workforce_admission": "planner-adm",
}


@pytest.mark.parametrize(
    ("request_", "expected"),
    [
        ({}, (None, None)),
        ({"workforce_demands": "d", "workforce_admission": "a"}, ("d", "a")),
        ({"workforce_demands": "d", "admission_binding": "b"}, ("d", "b")),
        ({"workforce_admission": "a", "admission_binding": "b"}, (None, "a")),
        # request admission wins over the planner's; planner admission wins over admission_binding
        (
            {"planner_output": PLANNER, "workforce_admission": "a"},
            ("planner-snapshot-demands", "a"),
        ),
        (
            {"planner_output": PLANNER, "admission_binding": "b"},
            ("planner-snapshot-demands", "planner-adm"),
        ),
        ({"planner": PLANNER}, ("planner-snapshot-demands", "planner-adm")),
        # planner_output is preferred, a non-mapping planner_output falls back to planner
        ({"planner_output": {"workforce_admission": "po"}, "planner": PLANNER}, (None, "po")),
        ({"planner_output": "x", "planner": PLANNER}, ("planner-snapshot-demands", "planner-adm")),
        # the request snapshot wins over the planner snapshot
        (
            {"planner_output": PLANNER, "signal_snapshot": {"workforce_demands": "req-snap"}},
            ("req-snap", "planner-adm"),
        ),
        # a non-mapping request snapshot falls back to the planner snapshot
        (
            {"planner_output": PLANNER, "signal_snapshot": "x"},
            ("planner-snapshot-demands", "planner-adm"),
        ),
        # explicit demands win; an explicit None demands still falls back
        ({"planner_output": PLANNER, "workforce_demands": "d"}, ("d", "planner-adm")),
        (
            {"planner_output": PLANNER, "workforce_demands": None},
            ("planner-snapshot-demands", "planner-adm"),
        ),
        # a falsy but non-None value is kept
        ({"workforce_demands": {}, "workforce_admission": [], "admission_binding": "b"}, ({}, [])),
        # no planner: admission_binding only
        ({"admission_binding": "b"}, (None, "b")),
    ],
)
def test_workforce_dispatch_inputs_precedence(
    request_: dict[str, Any], expected: tuple[Any, Any]
) -> None:
    assert service_module._workforce_dispatch_inputs(request_) == expected


# ---------------------------------------------------------------------------
# _tracked_dispatch_required


@pytest.mark.parametrize(
    ("request_", "state", "expected"),
    [
        ({}, None, False),
        ({"contract_kind": "TRACKED_TASK_CARD"}, None, True),
        ({"contract_kind": "OWNER_INLINE"}, None, False),
        ({}, {"contract_kind": "TRACKED_TASK_CARD"}, True),
        ({"contract_kind": "NONE"}, {"contract_kind": "TRACKED_TASK_CARD"}, True),
        ({}, "TRACKED_TASK_CARD", False),
        ({"contract_kind": None}, {"contract_kind": None}, False),
        ({"contract_kind": "tracked_task_card"}, None, False),
    ],
)
def test_tracked_dispatch_required(request_: dict[str, Any], state: Any, expected: bool) -> None:
    assert service_module._tracked_dispatch_required(request_, state) is expected


def test_tracked_dispatch_required_enum_value_is_compared_as_text() -> None:
    from nexus.contracts.lifecycle_action import ContractKind

    assert (
        service_module._tracked_dispatch_required({"contract_kind": ContractKind.TRACKED_TASK_CARD})
        is False
    )


# ---------------------------------------------------------------------------
# _workforce_admission_readback_matches


def _receipt(*ages: Any, decision: str = "ALLOW", extra: Any = None) -> dict[str, Any]:
    return {
        "overall_decision": decision,
        "policy": "p",
        "records": [
            {
                "decision": {
                    "freshness_evidence": {"verified_age_days": age, "last_verified": "2026-10-01"},
                    "x": extra,
                }
            }
            for age in ages
        ],
    }


@pytest.mark.parametrize(
    ("persisted", "fresh", "expected"),
    [
        (_receipt(3), _receipt(3), True),
        (_receipt(3), _receipt(4), True),
        (_receipt(0, 2), _receipt(5, 2), True),
        (_receipt(), _receipt(), True),
        (_receipt(4), _receipt(3), False),
        (_receipt(-1), _receipt(0), False),
        (_receipt(3), _receipt(3, decision="BLOCK"), False),
        (_receipt(3, decision="BLOCK"), _receipt(3), False),
        (_receipt(3), _receipt(3, 3), False),
        (_receipt(True), _receipt(True), False),
        (_receipt(3.0), _receipt(3), False),
        (_receipt(3), _receipt("3"), False),
        (_receipt(None), _receipt(3), False),
        (_receipt(3), _receipt(4, extra="tampered"), False),
        ({**_receipt(3), "policy": "q"}, _receipt(3), False),
        (
            {"overall_decision": "ALLOW", "records": "x"},
            {"overall_decision": "ALLOW", "records": "x"},
            False,
        ),
        (
            {"overall_decision": "ALLOW", "records": ["x"]},
            {"overall_decision": "ALLOW", "records": ["x"]},
            False,
        ),
        (
            {"overall_decision": "ALLOW", "records": [{"decision": "x"}]},
            {"overall_decision": "ALLOW", "records": [{"decision": "x"}]},
            False,
        ),
        (
            {"overall_decision": "ALLOW", "records": [{"decision": {"freshness_evidence": "x"}}]},
            {"overall_decision": "ALLOW", "records": [{"decision": {"freshness_evidence": "x"}}]},
            False,
        ),
        ({"overall_decision": "ALLOW"}, {"overall_decision": "ALLOW"}, False),
    ],
)
def test_admission_readback_matches(
    persisted: dict[str, Any], fresh: dict[str, Any], expected: bool
) -> None:
    before = (copy.deepcopy(persisted), copy.deepcopy(fresh))
    assert service_module._workforce_admission_readback_matches(persisted, fresh) is expected
    assert (persisted, fresh) == before  # the inputs are never mutated


def test_admission_readback_age_is_only_ignored_inside_freshness_evidence() -> None:
    persisted = _receipt(3)
    fresh = _receipt(4)
    fresh["records"][0]["decision"]["verified_age_days"] = 1
    assert service_module._workforce_admission_readback_matches(persisted, fresh) is False


def test_admission_readback_rejects_non_json_payload() -> None:
    with pytest.raises(TypeError):
        service_module._workforce_admission_readback_matches(
            {**_receipt(3), "x": object()}, _receipt(3)
        )


# ---------------------------------------------------------------------------
# validate_workforce_dispatch_binding

DEMAND = {"demand_id": "d-1", "execution_channel": "local"}
RECORD_REQUEST = {
    "requested_worker_id": "w",
    "provider": "p",
    "model": "m",
    "provided_controls": ["c"],
    "explicit_experiment_authorization": 1,
}


def _demands() -> dict[str, Any]:
    return {"demands": [dict(DEMAND)]}


def _admission() -> dict[str, Any]:
    return {
        "overall_decision": "ALLOW",
        "records": [{"demand": dict(DEMAND), "request": dict(RECORD_REQUEST)}],
    }


def _fresh() -> dict[str, Any]:
    return {
        "overall_decision": "ALLOW",
        "policy_identity": {"policy_hash": "ph"},
        "aggregate_binding_hash": "agg",
        "records": [
            {
                "binding_hash": "bh",
                "decision": {
                    "decision": "ALLOW",
                    "resolved_worker_id": "rw",
                    "resolved_provider": "rp",
                    "resolved_model": "rm",
                },
            }
        ],
    }


EXPECTED_BINDING = {
    "worker_id": "rw",
    "provider": "rp",
    "model": "rm",
    "policy_hash": "ph",
    "binding_hash": "bh",
    "aggregate_binding_hash": "agg",
}


@pytest.fixture
def fake_admission(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Facade-patched evaluator / policy loader / readback / envelope builder."""
    control: dict[str, Any] = {
        "fresh": _fresh(),
        "readback": True,
        "calls": [],
        "evaluate_error": None,
        "envelope": {"env": 1},
        "build_error": None,
    }

    class Loader:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            control["calls"].append(("loader", args, kwargs))

    def evaluate(demands: Any, bindings: Any, loader: Any) -> Any:
        control["calls"].append((
            "evaluate",
            demands,
            copy.deepcopy(bindings),
            type(loader).__name__,
        ))
        if control["evaluate_error"] is not None:
            raise control["evaluate_error"]
        return SimpleNamespace(to_dict=lambda: copy.deepcopy(control["fresh"]))

    def readback(persisted: Any, fresh: Any) -> bool:
        control["calls"].append(("readback", persisted, fresh))
        return control["readback"]

    def build(planner: Any, binding: Any, **kwargs: Any) -> Any:
        control["calls"].append(("build", planner, dict(binding), kwargs))
        if control["build_error"] is not None:
            raise control["build_error"]
        return SimpleNamespace(to_dict=lambda: control["envelope"])

    monkeypatch.setattr(service_module, "WorkforcePolicyLoader", Loader)
    monkeypatch.setattr(service_module, "evaluate_runtime_workforce_admission", evaluate)
    monkeypatch.setattr(service_module, "_workforce_admission_readback_matches", readback)
    monkeypatch.setattr(service_module, "build_canonical_dispatch_envelope", build)
    return control


def _validate(request: dict[str, Any], **kwargs: Any) -> Any:
    return service_module.validate_workforce_dispatch_binding(request, **kwargs)


def _base_request(**extra: Any) -> dict[str, Any]:
    return {"workforce_demands": _demands(), "workforce_admission": _admission(), **extra}


def test_validate_no_binding(fake_admission: dict[str, Any]) -> None:
    assert _validate({}) is None
    with pytest.raises(RuntimeError, match="^WORKFORCE_ADMISSION_BINDING_MISSING$"):
        _validate({}, require_binding=True)
    assert fake_admission["calls"] == []


@pytest.mark.parametrize("missing", ["workforce_demands", "workforce_admission"])
@pytest.mark.parametrize("require", [False, True])
def test_validate_half_binding_is_missing(
    fake_admission: dict[str, Any], missing: str, require: bool
) -> None:
    request = _base_request()
    del request[missing]
    with pytest.raises(RuntimeError, match="^WORKFORCE_ADMISSION_BINDING_MISSING$"):
        _validate(request, require_binding=require)
    assert fake_admission["calls"] == []


@pytest.mark.parametrize("admission", ["x", [], {"overall_decision": "BLOCK"}, {"records": []}])
def test_validate_admission_not_allow(fake_admission: dict[str, Any], admission: Any) -> None:
    with pytest.raises(RuntimeError) as raised:
        _validate({"workforce_demands": "not-even-a-mapping", "workforce_admission": admission})
    assert str(raised.value) == "WORKFORCE_ADMISSION_BINDING_INVALID:overall decision is not ALLOW"
    assert raised.value.__cause__ is None


def _mutated(path: str, value: Any) -> dict[str, Any]:
    request = _base_request()
    target: Any = request
    keys = path.split(".")
    for key in keys[:-1]:
        target = target[int(key)] if isinstance(target, list) else target[key]
    last = keys[-1]
    if value is KeyError:
        del target[last]
    elif isinstance(target, list):
        target[int(last)] = value
    else:
        target[last] = value
    return request


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        ("workforce_demands", "x", "workforce dispatch requires exactly one demand"),
        ("workforce_demands.demands", "x", "workforce dispatch requires exactly one demand"),
        ("workforce_demands.demands", [], "workforce dispatch requires exactly one demand"),
        (
            "workforce_demands.demands",
            [DEMAND, DEMAND],
            "workforce dispatch requires exactly one demand",
        ),
        (
            "workforce_admission.records",
            "x",
            "workforce dispatch requires exactly one admission record",
        ),
        (
            "workforce_admission.records",
            [],
            "workforce dispatch requires exactly one admission record",
        ),
        (
            "workforce_admission.records",
            [{}, {}],
            "workforce dispatch requires exactly one admission record",
        ),
        ("workforce_admission.records.0", "x", "workforce admission demand/record mismatch"),
        ("workforce_admission.records.0.demand", "x", "workforce admission demand/record mismatch"),
        (
            "workforce_admission.records.0.demand.demand_id",
            "other",
            "workforce admission demand/record mismatch",
        ),
        (
            "workforce_admission.records.0.demand.execution_channel",
            "online",
            "workforce admission demand/record mismatch",
        ),
        (
            "workforce_admission.records.0.request",
            KeyError,
            "workforce admission record request missing",
        ),
        (
            "workforce_admission.records.0.request",
            "x",
            "workforce admission record request missing",
        ),
    ],
)
def test_validate_shape_denials_in_order(
    fake_admission: dict[str, Any], path: str, value: Any, message: str
) -> None:
    with pytest.raises(RuntimeError) as raised:
        _validate(_mutated(path, value))
    assert str(raised.value) == f"WORKFORCE_ADMISSION_BINDING_INVALID:{message}"
    assert isinstance(raised.value.__cause__, ValueError)
    assert fake_admission["calls"] == []


@pytest.mark.parametrize("channel", ["", None, "LOCAL", "remote"])
def test_validate_channel_invalid(fake_admission: dict[str, Any], channel: Any) -> None:
    request = _base_request()
    request["workforce_demands"]["demands"][0]["execution_channel"] = channel
    request["workforce_admission"]["records"][0]["demand"]["execution_channel"] = channel
    with pytest.raises(
        RuntimeError,
        match="^WORKFORCE_ADMISSION_BINDING_INVALID:workforce dispatch execution channel invalid$",
    ):
        _validate(request)
    assert fake_admission["calls"] == []


def test_validate_record_identity_missing(fake_admission: dict[str, Any]) -> None:
    request = _base_request()
    request["workforce_admission"]["records"][0]["request"] = {
        "requested_worker_id": "",
        "provider": None,
        "provided_controls": ["c"],
    }
    with pytest.raises(
        RuntimeError,
        match="^WORKFORCE_ADMISSION_BINDING_INVALID:workforce admission record identity missing$",
    ):
        _validate(request)
    assert fake_admission["calls"] == []


def test_validate_demand_item_without_get_is_not_wrapped(fake_admission: dict[str, Any]) -> None:
    request = _base_request()
    request["workforce_demands"]["demands"] = ["not-a-mapping"]
    with pytest.raises(AttributeError):
        _validate(request)


@pytest.mark.parametrize(
    ("identity", "expected_binding"),
    [
        (
            RECORD_REQUEST,
            {
                "worker_id": "w",
                "provider": "p",
                "model": "m",
                "controls": ["c"],
                "explicit_experiment_authorization": True,
            },
        ),
        (
            {"model": "m"},
            {
                "worker_id": None,
                "provider": None,
                "model": "m",
                "controls": [],
                "explicit_experiment_authorization": False,
            },
        ),
        (
            {
                "requested_worker_id": "w",
                "provided_controls": None,
                "explicit_experiment_authorization": "",
            },
            {
                "worker_id": "w",
                "provider": None,
                "model": None,
                "controls": [],
                "explicit_experiment_authorization": False,
            },
        ),
    ],
)
def test_validate_evaluates_record_identity_once_with_a_fresh_loader(
    fake_admission: dict[str, Any], identity: dict[str, Any], expected_binding: dict[str, Any]
) -> None:
    request = _base_request()
    request["workforce_admission"]["records"][0]["request"] = dict(identity)
    result = _validate(request)
    calls = fake_admission["calls"]
    assert [c[0] for c in calls] == ["loader", "evaluate", "readback"]
    assert calls[0] == ("loader", (), {})
    assert calls[1] == (
        "evaluate",
        request["workforce_demands"],
        {"local": expected_binding},
        "Loader",
    )
    assert calls[1][1] is request["workforce_demands"]
    assert calls[2][1] is request["workforce_admission"]
    assert calls[2][2] == _fresh()
    assert result == {
        "demands": _demands(),
        "admission": request["workforce_admission"],
        "demand_id": "d-1",
        **EXPECTED_BINDING,
    }


def test_validate_online_channel_binds_the_online_key(fake_admission: dict[str, Any]) -> None:
    request = _base_request()
    request["workforce_demands"]["demands"][0]["execution_channel"] = "online"
    request["workforce_admission"]["records"][0]["demand"]["execution_channel"] = "online"
    _validate(request)
    assert list(fake_admission["calls"][1][2]) == ["online"]


def test_validate_result_is_a_jsonable_copy(fake_admission: dict[str, Any]) -> None:
    from enum import Enum

    class Colour(Enum):
        RED = "red"

    request = _base_request()
    request["workforce_demands"]["extra"] = (Colour.RED, 1)
    result = _validate(request)
    assert result["demands"] == {"demands": [DEMAND], "extra": ["red", 1]}
    assert result["demands"] is not request["workforce_demands"]
    assert result["admission"] is not request["workforce_admission"]
    assert "canonical_dispatch_envelope" not in result
    assert list(result) == [
        "demands",
        "admission",
        "demand_id",
        "worker_id",
        "provider",
        "model",
        "policy_hash",
        "binding_hash",
        "aggregate_binding_hash",
    ]


def test_validate_demand_id_defaults_to_empty_string(fake_admission: dict[str, Any]) -> None:
    request = _base_request()
    del request["workforce_demands"]["demands"][0]["demand_id"]
    del request["workforce_admission"]["records"][0]["demand"]["demand_id"]
    assert _validate(request)["demand_id"] == ""


def test_validate_stale_or_tampered_readback(fake_admission: dict[str, Any]) -> None:
    fake_admission["readback"] = False
    with pytest.raises(RuntimeError) as raised:
        _validate(_base_request())
    assert (
        str(raised.value)
        == "WORKFORCE_ADMISSION_BINDING_INVALID:workforce admission receipt is stale or tampered"
    )
    assert isinstance(raised.value.__cause__, ValueError)


def _fresh_with(path: str, value: Any) -> dict[str, Any]:
    fresh = _fresh()
    target: Any = fresh
    keys = path.split(".")
    for key in keys[:-1]:
        target = target[int(key)] if isinstance(target, list) else target[key]
    if value is KeyError:
        del target[keys[-1]]
    else:
        target[keys[-1]] = value
    return fresh


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        ("overall_decision", "BLOCK", "workforce admission is not a single ALLOW record"),
        ("records", [], "workforce admission is not a single ALLOW record"),
        ("records", None, "workforce admission is not a single ALLOW record"),
        (
            "records.0.decision.decision",
            "BLOCK",
            "workforce admission is not a single ALLOW record",
        ),
        ("records.0.decision", None, "workforce admission is not a single ALLOW record"),
        (
            "records.0.decision.resolved_worker_id",
            "",
            "workforce admission resolved identity missing",
        ),
        (
            "records.0.decision.resolved_provider",
            " ",
            "workforce admission resolved identity missing",
        ),
        ("records.0.decision.resolved_model", 7, "workforce admission resolved identity missing"),
        ("policy_identity", None, "workforce admission resolved identity missing"),
        ("policy_identity.policy_hash", KeyError, "workforce admission resolved identity missing"),
        ("records.0.binding_hash", None, "workforce admission resolved identity missing"),
        ("aggregate_binding_hash", "", "workforce admission resolved identity missing"),
    ],
)
def test_validate_fresh_decision_denials(
    fake_admission: dict[str, Any], path: str, value: Any, message: str
) -> None:
    fake_admission["fresh"] = _fresh_with(path, value)
    with pytest.raises(RuntimeError) as raised:
        _validate(_base_request())
    assert str(raised.value) == f"WORKFORCE_ADMISSION_BINDING_INVALID:{message}"


def test_validate_fresh_two_records_denied(fake_admission: dict[str, Any]) -> None:
    fresh = _fresh()
    fresh["records"].append(fresh["records"][0])
    fake_admission["fresh"] = fresh
    with pytest.raises(RuntimeError, match="not a single ALLOW record$"):
        _validate(_base_request())


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (TypeError("t"), "WORKFORCE_ADMISSION_BINDING_INVALID:t"),
        (ValueError("v"), "WORKFORCE_ADMISSION_BINDING_INVALID:v"),
        (KeyError("k"), "WORKFORCE_ADMISSION_BINDING_INVALID:'k'"),
    ],
)
def test_validate_wraps_evaluator_type_value_key_errors(
    fake_admission: dict[str, Any], error: Exception, message: str
) -> None:
    fake_admission["evaluate_error"] = error
    with pytest.raises(RuntimeError) as raised:
        _validate(_base_request())
    assert str(raised.value) == message
    assert raised.value.__cause__ is error


@pytest.mark.parametrize("error", [RuntimeError("boom"), AttributeError("attr"), OSError("os")])
def test_validate_other_evaluator_errors_propagate(
    fake_admission: dict[str, Any], error: Exception
) -> None:
    fake_admission["evaluate_error"] = error
    with pytest.raises(type(error)) as raised:
        _validate(_base_request())
    assert raised.value is error


@pytest.mark.parametrize(
    ("extra", "denied"),
    [
        ({"fallback_worker": "other"}, True),
        ({"fallback_provider": "other"}, True),
        ({"fallback_worker": " RP "}, False),
        ({"fallback_provider": "Rp"}, False),
        ({"fallback_worker": "rp", "fallback_provider": "other"}, False),
        ({"fallback_worker": "other", "fallback_provider": "rp"}, True),
        # an explicit (even empty) fallback_worker hides fallback_provider
        ({"fallback_worker": None, "fallback_provider": "other"}, False),
        ({"fallback_worker": "", "fallback_provider": "other"}, False),
        ({"fallback_provider": None}, False),
    ],
)
def test_validate_fallback(
    fake_admission: dict[str, Any], extra: dict[str, Any], denied: bool
) -> None:
    if denied:
        with pytest.raises(RuntimeError) as raised:
            _validate(_base_request(**extra))
        assert str(raised.value) == "WORKFORCE_ADMISSION_FALLBACK_UNADMITTED"
        assert raised.value.__cause__ is None
    else:
        assert _validate(_base_request(**extra))["provider"] == "rp"


def test_validate_fallback_checked_before_envelope(fake_admission: dict[str, Any]) -> None:
    with pytest.raises(RuntimeError, match="^WORKFORCE_ADMISSION_FALLBACK_UNADMITTED$"):
        _validate(_base_request(fallback_worker="x", canonical_dispatch_envelope="bad"))


def test_validate_envelope_none_is_absent(fake_admission: dict[str, Any]) -> None:
    result = _validate(_base_request(canonical_dispatch_envelope=None))
    assert "canonical_dispatch_envelope" not in result
    assert "build" not in [c[0] for c in fake_admission["calls"]]


def test_validate_envelope_not_mapping(fake_admission: dict[str, Any]) -> None:
    with pytest.raises(RuntimeError, match="^WORKFORCE_DISPATCH_ENVELOPE_INVALID$"):
        _validate(_base_request(canonical_dispatch_envelope=["x"], planner_output={}))


@pytest.mark.parametrize("planner", [None, "x"])
def test_validate_envelope_planner_missing(fake_admission: dict[str, Any], planner: Any) -> None:
    extra: dict[str, Any] = {"canonical_dispatch_envelope": {"env": 1}}
    if planner is not None:
        extra["planner_output"] = planner
    with pytest.raises(RuntimeError, match="^WORKFORCE_DISPATCH_ENVELOPE_PLANNER_MISSING$"):
        _validate(_base_request(**extra))


def test_validate_envelope_planner_must_be_planner_output_not_planner(
    fake_admission: dict[str, Any],
) -> None:
    with pytest.raises(RuntimeError, match="^WORKFORCE_DISPATCH_ENVELOPE_PLANNER_MISSING$"):
        _validate(_base_request(canonical_dispatch_envelope={"env": 1}, planner={"p": 1}))


def test_validate_envelope_rebuilt_with_exact_arguments(fake_admission: dict[str, Any]) -> None:
    planner = {"plan": 1}
    request = _base_request(
        canonical_dispatch_envelope={"env": 1},
        planner_output=planner,
        task_id="t-1",
        attempt_id=None,
        task_card_path="cards/x.md",
        task_card_hash=0,
    )
    result = _validate(request)
    build = [c for c in fake_admission["calls"] if c[0] == "build"]
    assert build == [
        (
            "build",
            planner,
            {**EXPECTED_BINDING, "demand_id": "d-1"},
            {
                "task_id": "t-1",
                "attempt_id": "",
                "task_card_path": "cards/x.md",
                "task_card_hash": "",
            },
        )
    ]
    assert build[0][1] is planner
    assert result["canonical_dispatch_envelope"] is fake_admission["envelope"]
    assert [c[0] for c in fake_admission["calls"]] == ["loader", "evaluate", "readback", "build"]


def test_validate_envelope_mismatch(fake_admission: dict[str, Any]) -> None:
    with pytest.raises(RuntimeError, match="^WORKFORCE_DISPATCH_ENVELOPE_MISMATCH$"):
        _validate(_base_request(canonical_dispatch_envelope={"env": 2}, planner_output={}))


def test_validate_envelope_mapping_proxy_compared_as_dict(fake_admission: dict[str, Any]) -> None:
    from types import MappingProxyType

    result = _validate(
        _base_request(canonical_dispatch_envelope=MappingProxyType({"env": 1}), planner_output={})
    )
    assert result["canonical_dispatch_envelope"] == {"env": 1}


@pytest.mark.parametrize("error", [TypeError("t"), ValueError("v")])
def test_validate_envelope_builder_errors_wrapped(
    fake_admission: dict[str, Any], error: Exception
) -> None:
    fake_admission["build_error"] = error
    with pytest.raises(RuntimeError) as raised:
        _validate(_base_request(canonical_dispatch_envelope={"env": 1}, planner_output={}))
    assert str(raised.value) == f"WORKFORCE_DISPATCH_ENVELOPE_INVALID:{error}"
    assert raised.value.__cause__ is error


def test_validate_envelope_builder_key_error_propagates(fake_admission: dict[str, Any]) -> None:
    fake_admission["build_error"] = KeyError("k")
    with pytest.raises(KeyError):
        _validate(_base_request(canonical_dispatch_envelope={"env": 1}, planner_output={}))


def test_validate_reads_inputs_through_facade_dispatch_inputs(
    fake_admission: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Any] = []

    def inputs(request: Any) -> tuple[Any, Any]:
        seen.append(request)
        return None, None

    monkeypatch.setattr(service_module, "_workforce_dispatch_inputs", inputs)
    assert _validate(_base_request()) is None
    assert len(seen) == 1


def test_validate_converts_through_facade_jsonable(
    fake_admission: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service_module, "_jsonable", lambda value: ("J", type(value).__name__))
    result = _validate(_base_request())
    assert result["demands"] == ("J", "dict") and result["admission"] == ("J", "dict")


def test_validate_real_readback_tolerates_forward_age(
    fake_admission: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()  # drop the fake readback / evaluator; keep the real ones
    persisted = {
        "overall_decision": "ALLOW",
        **{k: v for k, v in _fresh().items() if k != "overall_decision"},
    }
    persisted["records"][0]["demand"] = dict(DEMAND)
    persisted["records"][0]["request"] = dict(RECORD_REQUEST)
    persisted["records"][0]["decision"]["freshness_evidence"] = {"verified_age_days": 1}
    fresh = copy.deepcopy(persisted)
    fresh["records"][0]["decision"]["freshness_evidence"]["verified_age_days"] = 2
    monkeypatch.setattr(service_module, "WorkforcePolicyLoader", lambda: None)
    monkeypatch.setattr(
        service_module,
        "evaluate_runtime_workforce_admission",
        lambda *a: SimpleNamespace(to_dict=lambda: copy.deepcopy(fresh)),
    )
    result = _validate({"workforce_demands": _demands(), "workforce_admission": persisted})
    assert result["worker_id"] == "rw"
    backwards = copy.deepcopy(persisted)
    backwards["records"][0]["decision"]["freshness_evidence"]["verified_age_days"] = 3
    with pytest.raises(RuntimeError, match="stale or tampered$"):
        _validate({"workforce_demands": _demands(), "workforce_admission": backwards})


# ---------------------------------------------------------------------------
# _recover_pre_provider_cli_envelope_drift

STALE_ENVELOPE = {"attempt_id": "stale", "planner": "p", "demand_id": "d-1"}


def _drift_state(**extra: Any) -> dict[str, Any]:
    return {
        "task_id": "t",
        "status": "FINAL_BLOCK",
        "error": "WORKFORCE_DISPATCH_ENVELOPE_IDENTITY_DRIFT",
        "cleanup_decision": "ALREADY_REMOVED",
        "telemetry": {
            "provider_calls": 0,
            "provider_attempts": 0,
            "provider_time_ms": 0,
            "worktree_time_ms": 0,
            "verifier_time_ms": 0,
        },
        "canonical_dispatch_envelope": dict(STALE_ENVELOPE),
        "attempt_id": "actual",
        "attempts": [{"attempt_id": "actual"}],
        "task_card_path": "cards/t.md",
        "task_card_hash": "h" * 64,
        **extra,
    }


def _drift_request(**extra: Any) -> dict[str, Any]:
    return {
        "canonical_dispatch_envelope": dict(STALE_ENVELOPE),
        "attempt_id": "stale",
        "planner_output": {"plan": 1},
        **extra,
    }


MISMATCH = RuntimeError("WORKFORCE_DISPATCH_ENVELOPE_MISMATCH")


@pytest.fixture
def drift(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Facade-patched validator, envelope builder and ``SelfHostedTaskService``."""
    control: dict[str, Any] = {
        "calls": [],
        "validate": [lambda n: {"provider": "rp", "demand_id": "d-1", "n": n}] * 2,
        "build": lambda planner, binding, **kw: {
            "attempt_id": kw["attempt_id"],
            "planner": "p",
            "demand_id": "d-1",
        },
        "assert_error": None,
    }

    def validate(request: Any, *, require_binding: bool = False) -> Any:
        n = sum(1 for c in control["calls"] if c[0] == "validate")
        control["calls"].append((
            "validate",
            copy.deepcopy(dict(request)),
            require_binding,
            request,
        ))
        step = control["validate"][n]
        if isinstance(step, BaseException):
            raise step
        return step(n)

    def build(planner: Any, binding: Any, **kwargs: Any) -> Any:
        control["calls"].append(("build", planner, dict(binding), kwargs))
        result = control["build"](planner, binding, **kwargs)
        if isinstance(result, BaseException):
            raise result
        return SimpleNamespace(to_dict=lambda: result)

    class FakeService:
        @staticmethod
        def _assert_persisted_workforce_dispatch(state: Any, request: Any, binding: Any) -> None:
            control["calls"].append((
                "assert",
                copy.deepcopy(state),
                copy.deepcopy(request),
                binding,
            ))
            if control["assert_error"] is not None:
                raise control["assert_error"]

    monkeypatch.setattr(service_module, "validate_workforce_dispatch_binding", validate)
    monkeypatch.setattr(service_module, "build_canonical_dispatch_envelope", build)
    monkeypatch.setattr(service_module, "SelfHostedTaskService", FakeService)
    return control


def _recover(state: dict[str, Any], request: dict[str, Any], failure: Any = MISMATCH) -> Any:
    return service_module._recover_pre_provider_cli_envelope_drift(state, request, failure)


def test_recover_success_call_order_and_arguments(drift: dict[str, Any]) -> None:
    state, request = _drift_state(), _drift_request()
    snapshot = (copy.deepcopy(state), copy.deepcopy(request))
    result = _recover(state, request)
    expected = {"attempt_id": "actual", "planner": "p", "demand_id": "d-1"}
    second = {"provider": "rp", "demand_id": "d-1", "n": 1}
    assert result == second
    calls = drift["calls"]
    assert [c[0] for c in calls] == ["validate", "build", "validate", "assert"]
    assert calls[0][1:3] == (request, True) and calls[0][3] is request
    assert calls[1] == (
        "build",
        request["planner_output"],
        {"provider": "rp", "demand_id": "d-1", "n": 0},
        {
            "task_id": "t",
            "attempt_id": "actual",
            "task_card_path": "cards/t.md",
            "task_card_hash": "h" * 64,
        },
    )
    reconciled_request = {
        **request,
        "attempt_id": "actual",
        "canonical_dispatch_envelope": expected,
    }
    assert calls[2][1:3] == (reconciled_request, True)
    assert calls[3][1] == {
        **state,
        "canonical_dispatch_envelope": expected,
        "workforce_dispatch": {**second, "canonical_dispatch_envelope": expected},
    }
    assert calls[3][2] == reconciled_request
    assert calls[3][3] is result
    assert (state, request) == snapshot  # inputs are never mutated


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("WORKFORCE_DISPATCH_ENVELOPE_MISMATCH:x"),
        RuntimeError("OTHER"),
        ValueError("WORKFORCE_DISPATCH_ENVELOPE_MISMATCH"),
    ],
)
def test_recover_only_for_the_exact_mismatch_text(
    drift: dict[str, Any], failure: Exception
) -> None:
    if isinstance(failure, ValueError):
        # only str(failure) is compared, so another exception type with the same text recovers
        assert _recover(_drift_state(), _drift_request(), failure) == {
            "provider": "rp",
            "demand_id": "d-1",
            "n": 1,
        }
        assert [c[0] for c in drift["calls"]] == ["validate", "build", "validate", "assert"]
        return
    assert _recover(_drift_state(), _drift_request(), failure) is None
    assert drift["calls"] == []


BLOCKING_STATE = [
    ("status", "BLOCKED"),
    ("status", None),
    ("error", "OTHER"),
    ("action", {}),
    ("action_id", "a"),
    ("target_created_at", "now"),
    ("lease", {}),
    ("worker_preflight", {}),
    ("active_provider", "agy"),
    ("worker_child_pgid", 0),
    ("execution", {}),
    ("candidate", {}),
    ("candidate_commit_sha", ""),
    ("candidate_ref", ""),
    ("candidate_state_hash", ""),
    ("verified_receipt", {}),
    ("verified_receipt_hash", ""),
    ("executions", [{}]),
    ("executions", ()),
    ("cleanup_decision", "REMOVED"),
    ("cleanup_decision", None),
    ("cleanup_performed", True),
    ("cleanup_blocker", "x"),
    ("promotion_status", "CREATED"),
    ("merge_performed", True),
    ("push_performed", True),
    ("telemetry", None),
    ("telemetry", "x"),
    ("telemetry.provider_calls", 1),
    ("telemetry.provider_attempts", 1),
    ("telemetry.provider_time_ms", 1),
    ("telemetry.worktree_time_ms", 1),
    ("telemetry.verifier_time_ms", 1),
    ("telemetry.provider_calls", "2"),
    ("canonical_dispatch_envelope", None),
    ("canonical_dispatch_envelope", "x"),
    ("canonical_dispatch_envelope", {"attempt_id": "stale"}),
    ("attempt_id", ""),
    ("attempt_id", "stale"),
    ("attempts", None),
    ("attempts", []),
    ("attempts", [{"attempt_id": "actual"}, {"attempt_id": "actual"}]),
    ("attempts", ["actual"]),
    ("attempts", [{"attempt_id": "other"}]),
]


@pytest.mark.parametrize(("key", "value"), BLOCKING_STATE)
def test_recover_state_guards(drift: dict[str, Any], key: str, value: Any) -> None:
    state = _drift_state()
    if key.startswith("telemetry."):
        state["telemetry"][key.split(".", 1)[1]] = value
    else:
        state[key] = value
    assert _recover(state, _drift_request()) is None
    assert drift["calls"] == []


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("active_provider", ""),
        ("executions", []),
        ("cleanup_performed", False),
        ("cleanup_performed", 0),
        ("cleanup_blocker", ""),
        ("promotion_status", "NOT_CREATED"),
        ("merge_performed", False),
        ("push_performed", False),
        ("telemetry.provider_calls", None),
        ("telemetry.provider_calls", "0"),
        ("telemetry.provider_time_ms", 0.4),
    ],
)
def test_recover_state_tolerated_values(drift: dict[str, Any], key: str, value: Any) -> None:
    state = _drift_state()
    if key.startswith("telemetry."):
        state["telemetry"][key.split(".", 1)[1]] = value
    else:
        state[key] = value
    assert _recover(state, _drift_request()) == {"provider": "rp", "demand_id": "d-1", "n": 1}


def test_recover_non_integer_telemetry_raises(drift: dict[str, Any]) -> None:
    state = _drift_state()
    state["telemetry"]["worktree_time_ms"] = "x"
    with pytest.raises(ValueError):
        _recover(state, _drift_request())
    assert drift["calls"] == []


def test_recover_missing_stale_attempt_in_envelope(drift: dict[str, Any]) -> None:
    envelope = {"planner": "p"}
    state = _drift_state(canonical_dispatch_envelope=dict(envelope))
    assert (
        _recover(state, _drift_request(canonical_dispatch_envelope=dict(envelope), attempt_id=""))
        is None
    )
    assert drift["calls"] == []


@pytest.mark.parametrize(
    "request_",
    [
        _drift_request(canonical_dispatch_envelope=None),
        _drift_request(canonical_dispatch_envelope="x"),
        _drift_request(canonical_dispatch_envelope={**STALE_ENVELOPE, "extra": 1}),
        _drift_request(attempt_id="actual"),
        _drift_request(attempt_id=None),
    ],
)
def test_recover_request_guards(drift: dict[str, Any], request_: dict[str, Any]) -> None:
    assert _recover(_drift_state(), request_) is None
    assert drift["calls"] == []


@pytest.mark.parametrize(
    "error", [KeyError("k"), RuntimeError("r"), TypeError("t"), ValueError("v")]
)
@pytest.mark.parametrize("step", [0, 1])
def test_recover_validation_errors_return_none(
    drift: dict[str, Any], error: Exception, step: int
) -> None:
    validate = list(drift["validate"])
    validate[step] = error
    drift["validate"] = validate
    assert _recover(_drift_state(), _drift_request()) is None
    assert [c[0] for c in drift["calls"]] == (
        ["validate"] if step == 0 else ["validate", "build", "validate"]
    )


def test_recover_other_validation_error_propagates(drift: dict[str, Any]) -> None:
    drift["validate"] = [AttributeError("a")]
    with pytest.raises(AttributeError):
        _recover(_drift_state(), _drift_request())


@pytest.mark.parametrize("step", [0, 1])
def test_recover_validation_none_returns_none(drift: dict[str, Any], step: int) -> None:
    validate = list(drift["validate"])
    validate[step] = lambda n: None
    drift["validate"] = validate
    assert _recover(_drift_state(), _drift_request()) is None
    assert [c[0] for c in drift["calls"]] == (
        ["validate"] if step == 0 else ["validate", "build", "validate"]
    )


def test_recover_missing_planner_output_returns_none(drift: dict[str, Any]) -> None:
    request = _drift_request()
    del request["planner_output"]
    assert _recover(_drift_state(), request) is None
    assert [c[0] for c in drift["calls"]] == ["validate"]


@pytest.mark.parametrize(
    "error", [ValueError("v"), TypeError("t"), KeyError("k"), RuntimeError("r")]
)
def test_recover_builder_error_returns_none(drift: dict[str, Any], error: Exception) -> None:
    drift["build"] = lambda *a, **k: error
    assert _recover(_drift_state(), _drift_request()) is None
    assert [c[0] for c in drift["calls"]] == ["validate", "build"]


def test_recover_rebuilt_envelope_must_match_apart_from_attempt(drift: dict[str, Any]) -> None:
    drift["build"] = lambda planner, binding, **kw: {
        "attempt_id": kw["attempt_id"],
        "planner": "q",
        "demand_id": "d-1",
    }
    assert _recover(_drift_state(), _drift_request()) is None
    assert [c[0] for c in drift["calls"]] == ["validate", "build"]


def test_recover_rebuilt_envelope_without_attempt_still_matches(drift: dict[str, Any]) -> None:
    drift["build"] = lambda planner, binding, **kw: {"planner": "p", "demand_id": "d-1"}
    result = _recover(_drift_state(), _drift_request())
    assert result == {"provider": "rp", "demand_id": "d-1", "n": 1}
    assert drift["calls"][2][1]["canonical_dispatch_envelope"] == {
        "planner": "p",
        "demand_id": "d-1",
    }


@pytest.mark.parametrize(
    "error", [KeyError("k"), RuntimeError("r"), TypeError("t"), ValueError("v")]
)
def test_recover_persisted_dispatch_assertion_failure_returns_none(
    drift: dict[str, Any], error: Exception
) -> None:
    drift["assert_error"] = error
    assert _recover(_drift_state(), _drift_request()) is None
    assert [c[0] for c in drift["calls"]] == ["validate", "build", "validate", "assert"]


def test_recover_build_receives_dispatch_demand_id(drift: dict[str, Any]) -> None:
    drift["validate"] = [lambda n: {"provider": "rp"}, lambda n: {"provider": "rp", "n": n}]
    _recover(_drift_state(), _drift_request())
    assert drift["calls"][1][2] == {"provider": "rp", "demand_id": None}


def test_recover_reaches_class_patch_of_the_real_service(
    drift: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Undo only the ``SelfHostedTaskService`` rebinding: the recovery then resolves the
    # real class through the facade and reaches a class-level patch of its assertion.
    monkeypatch.setattr(service_module, "SelfHostedTaskService", RealService)
    seen: list[Any] = []
    monkeypatch.setattr(
        RealService,
        "_assert_persisted_workforce_dispatch",
        staticmethod(lambda state, request, binding: seen.append(binding)),
    )
    result = _recover(_drift_state(), _drift_request())
    assert seen == [result] and result is not None


# ---------------------------------------------------------------------------
# runtime_retry_bridge reaches the facade objects at call time


def test_retry_bridge_dispatch_reaches_facade_patches(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []
    monkeypatch.setattr(
        service_module,
        "_workforce_dispatch_inputs",
        lambda r: seen.append(("inputs", r)) or ("d", "a"),
    )
    monkeypatch.setattr(
        service_module,
        "_recover_pre_provider_cli_envelope_drift",
        lambda s, r, f: seen.append(("recover", s, r, f)) or "recovered",
    )
    monkeypatch.setattr(
        service_module,
        "validate_workforce_dispatch_binding",
        lambda r, *, require_binding=False: (
            seen.append(("validate", dict(r), require_binding)) or "valid"
        ),
    )
    dispatch = runtime_retry_bridge._Dispatch(object())
    assert dispatch.workforce_inputs({"x": 1}) == ("d", "a")
    assert dispatch.recover_predecessor({"s": 1}, {"r": 1}, MISMATCH) == "recovered"
    assert dispatch.validate_repair({"r": 2}) == "valid"
    assert dispatch.validate_fresh({"r": 3}, {}) == "valid"
    assert [s[0] for s in seen] == ["inputs", "recover", "validate", "validate"]
    assert seen[2] == ("validate", {"r": 2}, True)


def test_retry_bridge_recover_reaches_patched_validator_through_moved_code(
    drift: dict[str, Any],
) -> None:
    dispatch = runtime_retry_bridge._Dispatch(object())
    assert dispatch.recover_predecessor(_drift_state(), _drift_request(), MISMATCH) == {
        "provider": "rp",
        "demand_id": "d-1",
        "n": 1,
    }
    assert [c[0] for c in drift["calls"]] == ["validate", "build", "validate", "assert"]


def test_retry_bridge_validate_predecessor_binds_state_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Any] = []
    monkeypatch.setattr(
        service_module,
        "validate_workforce_dispatch_binding",
        lambda r, *, require_binding=False: seen.append((dict(r), require_binding)) or "valid",
    )
    dispatch = runtime_retry_bridge._Dispatch(object())
    assert (
        dispatch.validate_predecessor(
            {"task_card_path": "req.md", "x": 1},
            {
                "task_id": "t",
                "attempt_id": "a",
                "task_card_hash": "h",
                "canonical_dispatch_envelope": {"e": 1},
            },
        )
        == "valid"
    )
    assert seen == [
        (
            {
                "task_card_path": "req.md",
                "x": 1,
                "task_id": "t",
                "attempt_id": "a",
                "task_card_hash": "h",
                "canonical_dispatch_envelope": {"e": 1},
            },
            True,
        )
    ]


# ---------------------------------------------------------------------------
# _validate_project_entry_authority_binding

VALUES = {
    "repository": "James3014/Nexus-new",
    "issue_number": 842,
    "goal_id": "goal-842",
    "coordination_scope_id": "scope-842",
    "canonical_remote": "https://github.com/James3014/Nexus-new.git",
    "intended_action_family": "TASK_SUBMIT",
}


def _binding(**over: Any) -> dict[str, Any]:
    values = {**VALUES, **over}
    return {**values, "binding_hash": canonical_request_hash(values)}


EXPECTED_VALUES = {**VALUES, "issue_number": "842"}


def _vpe(request: dict[str, Any], **kwargs: Any) -> Any:
    return service_module._validate_project_entry_authority_binding(request, **kwargs)


def test_project_entry_binding_absent() -> None:
    assert _vpe({}) is None
    assert (
        _vpe({"project_entry_authority_binding": None, "authority_goal_id": "x"}, repository="r")
        is None
    )


def test_project_entry_binding_valid_and_selectors() -> None:
    request = {"project_entry_authority_binding": _binding()}
    assert _vpe(request) == EXPECTED_VALUES
    assert _vpe(request, repository="James3014/Nexus-new", issue_number=842) == EXPECTED_VALUES
    result = _vpe(request)
    assert list(result) == [
        "repository",
        "issue_number",
        "goal_id",
        "coordination_scope_id",
        "canonical_remote",
        "intended_action_family",
    ]


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("x", "PROJECT_ENTRY_AUTHORITY_BINDING_INVALID"),
        ([], "PROJECT_ENTRY_AUTHORITY_BINDING_INVALID"),
        ({**_binding(), "extra": 1}, "PROJECT_ENTRY_AUTHORITY_BINDING_UNKNOWN_FIELD"),
        # unknown wins over incomplete
        ({"extra": 1}, "PROJECT_ENTRY_AUTHORITY_BINDING_UNKNOWN_FIELD"),
        (
            {k: v for k, v in _binding().items() if k != "goal_id"},
            "PROJECT_ENTRY_AUTHORITY_BINDING_INCOMPLETE",
        ),
        ({}, "PROJECT_ENTRY_AUTHORITY_BINDING_INCOMPLETE"),
        # binding_hash itself is optional for completeness (then fails the hash check)
        (
            {k: v for k, v in _binding().items() if k != "binding_hash"},
            "PROJECT_ENTRY_AUTHORITY_BINDING_HASH_MISMATCH",
        ),
        (_binding(issue_number="842"), "PROJECT_ENTRY_AUTHORITY_ISSUE_INVALID"),
        (_binding(issue_number=True), "PROJECT_ENTRY_AUTHORITY_ISSUE_INVALID"),
        (_binding(issue_number=0), "PROJECT_ENTRY_AUTHORITY_ISSUE_INVALID"),
        (_binding(issue_number=-3), "PROJECT_ENTRY_AUTHORITY_ISSUE_INVALID"),
        # issue is checked before the text fields
        (_binding(issue_number=0, goal_id=""), "PROJECT_ENTRY_AUTHORITY_ISSUE_INVALID"),
        (_binding(goal_id=" "), "PROJECT_ENTRY_AUTHORITY_BINDING_INCOMPLETE"),
        (_binding(repository=None), "PROJECT_ENTRY_AUTHORITY_BINDING_INCOMPLETE"),
        (_binding(coordination_scope_id=1), "PROJECT_ENTRY_AUTHORITY_BINDING_INCOMPLETE"),
        (_binding(canonical_remote=""), "PROJECT_ENTRY_AUTHORITY_BINDING_INCOMPLETE"),
        (_binding(intended_action_family=""), "PROJECT_ENTRY_AUTHORITY_BINDING_INCOMPLETE"),
        (_binding(intended_action_family="task_submit"), "PROJECT_ENTRY_AUTHORITY_ACTION_INVALID"),
        # the action is checked before the remote
        (
            _binding(intended_action_family="NOPE", canonical_remote="x"),
            "PROJECT_ENTRY_AUTHORITY_ACTION_INVALID",
        ),
        (
            _binding(canonical_remote="https://github.com/other/Nexus-new.git"),
            "PROJECT_ENTRY_AUTHORITY_REMOTE_MISMATCH",
        ),
        ({**_binding(), "binding_hash": "0" * 64}, "PROJECT_ENTRY_AUTHORITY_BINDING_HASH_MISMATCH"),
        ({**_binding(), "binding_hash": None}, "PROJECT_ENTRY_AUTHORITY_BINDING_HASH_MISMATCH"),
        ({**_binding(), "goal_id": "other"}, "PROJECT_ENTRY_AUTHORITY_BINDING_HASH_MISMATCH"),
    ],
)
def test_project_entry_binding_denials(raw: Any, message: str) -> None:
    with pytest.raises(ValueError) as raised:
        _vpe({"project_entry_authority_binding": raw})
    assert str(raised.value) == message


def test_project_entry_action_invalid_chains_the_enum_error() -> None:
    with pytest.raises(ValueError) as raised:
        _vpe({"project_entry_authority_binding": _binding(intended_action_family="NOPE")})
    assert isinstance(raised.value.__cause__, ValueError)


def test_project_entry_every_action_family_is_accepted() -> None:
    from nexus.contracts.autonomy_goal import AutonomyActionClass

    for action in AutonomyActionClass:
        result = _vpe({
            "project_entry_authority_binding": _binding(intended_action_family=action.value)
        })
        assert result["intended_action_family"] == action.value


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"repository": "James3014/other"}, "PROJECT_ENTRY_AUTHORITY_REPOSITORY_MISMATCH"),
        ({"issue_number": 843}, "PROJECT_ENTRY_AUTHORITY_ISSUE_MISMATCH"),
        ({"issue_number": "842"}, "PROJECT_ENTRY_AUTHORITY_ISSUE_MISMATCH"),
        # repository before issue
        ({"repository": "x", "issue_number": 1}, "PROJECT_ENTRY_AUTHORITY_REPOSITORY_MISMATCH"),
        ({"repository": ""}, "PROJECT_ENTRY_AUTHORITY_REPOSITORY_MISMATCH"),
    ],
)
def test_project_entry_selector_mismatch(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=f"^{message}$"):
        _vpe({"project_entry_authority_binding": _binding()}, **kwargs)


def test_project_entry_selectors_checked_before_remote_and_hash() -> None:
    raw = {**_binding(canonical_remote="x"), "binding_hash": "bad"}
    with pytest.raises(ValueError, match="^PROJECT_ENTRY_AUTHORITY_REPOSITORY_MISMATCH$"):
        _vpe({"project_entry_authority_binding": raw}, repository="other")
    with pytest.raises(ValueError, match="^PROJECT_ENTRY_AUTHORITY_REMOTE_MISMATCH$"):
        _vpe({"project_entry_authority_binding": raw})


@pytest.mark.parametrize(
    ("extra", "ok"),
    [
        ({"authority_goal_id": "goal-842"}, True),
        ({"authority_goal_id": None}, True),
        ({"authority_goal_id": "other"}, False),
        ({"authority_coordination_scope_id": "scope-842"}, True),
        ({"authority_coordination_scope_id": "other"}, False),
        ({"autonomy_goal_id": "goal-842"}, True),
        ({"autonomy_goal_id": "scope-842"}, False),
        ({"autonomy_submission_binding": {"goal_id": "goal-842"}}, True),
        ({"autonomy_submission_binding": {"goal_id": None}}, True),
        ({"autonomy_submission_binding": {}}, True),
        ({"autonomy_submission_binding": "goal-x"}, True),
        ({"autonomy_submission_binding": {"goal_id": "other"}}, False),
    ],
)
def test_project_entry_duplicates(extra: dict[str, Any], ok: bool) -> None:
    request = {"project_entry_authority_binding": _binding(), **extra}
    if ok:
        assert _vpe(request) == EXPECTED_VALUES
    else:
        with pytest.raises(ValueError, match="^PROJECT_ENTRY_AUTHORITY_DUPLICATE_MISMATCH$"):
            _vpe(request)


def test_project_entry_duplicates_checked_after_hash() -> None:
    raw = {**_binding(), "binding_hash": "bad"}
    with pytest.raises(ValueError, match="^PROJECT_ENTRY_AUTHORITY_BINDING_HASH_MISMATCH$"):
        _vpe({"project_entry_authority_binding": raw, "authority_goal_id": "other"})


# ---------------------------------------------------------------------------
# _reject_unbound_project_entry_authority_hints


def _hints(request: dict[str, Any]) -> None:
    return service_module._reject_unbound_project_entry_authority_hints(request)


@pytest.mark.parametrize("key", sorted(service_module._PROJECT_ENTRY_AUTHORITY_HINTS))
def test_unbound_hint_rejected(key: str) -> None:
    with pytest.raises(ValueError, match="^PROJECT_ENTRY_AUTHORITY_BINDING_REQUIRED$"):
        _hints({key: False})
    assert _hints({key: None}) is None
    assert _hints({key: "x", "project_entry_authority_binding": {"anything": 1}}) is None


@pytest.mark.parametrize(
    ("request_", "rejected"),
    [
        ({}, False),
        ({"contract": {"standing_grant_id": "g"}}, True),
        ({"contract": {"standing_grant_id": None}}, False),
        ({"contract": "standing_grant_id"}, False),
        ({"execution_lane": "governed"}, True),
        ({"execution_lane": "GOVERNED"}, True),
        ({"execution_lane": "GOVERNED_LITE"}, False),
        ({"execution_lane": None}, False),
        ({"execution_lane": "FAST"}, False),
        ({"project_entry_authority_binding": None, "execution_lane": "Governed"}, True),
        ({"project_entry_authority_binding": "x", "execution_lane": "Governed"}, False),
        ({"repository": "r", "issue": 1, "goal_id": "g"}, False),
    ],
)
def test_unbound_hint_contract_and_lane(request_: dict[str, Any], rejected: bool) -> None:
    if rejected:
        with pytest.raises(ValueError, match="^PROJECT_ENTRY_AUTHORITY_BINDING_REQUIRED$"):
            _hints(request_)
    else:
        assert _hints(request_) is None


# ---------------------------------------------------------------------------
# _validated_action_request

TOOL_HASH = "0" * 64


def _bound(**over: Any) -> dict[str, Any]:
    return {
        "task_id": "t1",
        "attempt_id": "a1",
        "action_id": "act1",
        "idempotency_key": "k1",
        "action_type": "TASK_RUN",
        "contract_kind": "NONE",
        "allowed_files": ["src/a.py"],
        **over,
    }


def _action(bound: dict[str, Any], **over: Any) -> dict[str, Any]:
    return {
        "task_id": "t1",
        "attempt_id": "a1",
        "action_id": "act1",
        "idempotency_key": "k1",
        "action_type": "TASK_RUN",
        "tool_manifest_hash": TOOL_HASH,
        "request_hash": canonical_request_hash(bound),
        "allowed_paths": ["src/a.py"],
        **over,
    }


def _var(request: dict[str, Any]) -> Any:
    return service_module._validated_action_request(request)


def _signed(
    bound: dict[str, Any], action_over: dict[str, Any] | None = None, /, **outer: Any
) -> dict[str, Any]:
    return {"action": _action(bound, **(action_over or {})), "bound_action_request": bound, **outer}


def test_action_request_absent_returns_a_copy() -> None:
    request = {"task_id": "x", "action_request_hash": "h"}
    effective, envelope = _var(request)
    assert effective == request and effective is not request and envelope is None


@pytest.mark.parametrize(
    ("request_", "message"),
    [
        ({"action": None}, "ACTION_ENVELOPE_INVALID"),
        ({"bound_action_request": {}}, "ACTION_ENVELOPE_INVALID"),
        ({"action": "x", "bound_action_request": {}}, "ACTION_ENVELOPE_INVALID"),
        ({"action": {}}, "BOUND_ACTION_REQUEST_REQUIRED"),
        ({"action": {}, "bound_action_request": "x"}, "BOUND_ACTION_REQUEST_REQUIRED"),
    ],
)
def test_action_request_container_denials(request_: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError) as raised:
        _var(request_)
    assert str(raised.value) == message


def test_action_request_model_validation_error_is_wrapped() -> None:
    with pytest.raises(ValueError) as raised:
        _var({"action": {"task_id": "t"}, "bound_action_request": {}})
    assert str(raised.value).startswith("ACTION_ENVELOPE_INVALID: ")
    assert raised.value.__cause__ is not None


@pytest.mark.parametrize("action_type", ["TASK_FINISH", "CANDIDATE_INTEGRATE", "TASK_RECONCILE"])
def test_action_request_type_unsupported(action_type: str) -> None:
    bound = _bound(action_type=action_type)
    with pytest.raises(ValueError, match="^ACTION_TYPE_UNSUPPORTED_FOR_TASK_SUBMISSION$"):
        _var(_signed(bound, {"action_type": action_type}))


def test_action_request_retry_type_supported() -> None:
    bound = _bound(action_type="TASK_RETRY")
    effective, envelope = _var(_signed(bound, {"action_type": "TASK_RETRY"}))
    assert effective["action_type"] == "TASK_RETRY" and envelope["action_type"] == "TASK_RETRY"


def test_action_request_hash_mismatch_checked_before_identity() -> None:
    bound = _bound()
    del bound["task_id"]
    request = _signed(bound, {"request_hash": "1" * 64})
    with pytest.raises(ValueError, match="^BOUND_ACTION_REQUEST_HASH_MISMATCH$"):
        _var(request)


@pytest.mark.parametrize(
    "field",
    ["task_id", "attempt_id", "action_id", "idempotency_key", "action_type", "contract_kind"],
)
def test_action_request_identity_missing(field: str) -> None:
    bound = _bound()
    del bound[field]
    with pytest.raises(ValueError, match=f"^ACTION_IDENTITY_MISSING: {field}$"):
        _var(_signed(bound))


def test_action_request_identity_missing_reports_the_first_field() -> None:
    bound = _bound()
    del bound["contract_kind"], bound["attempt_id"]
    with pytest.raises(ValueError, match="^ACTION_IDENTITY_MISSING: attempt_id$"):
        _var(_signed(bound))


CARD = {"task_card_path": "docs/cards/t.md", "task_card_hash": "c" * 64}


@pytest.mark.parametrize(
    ("missing", "action_over"),
    [
        ("task_card_path", {**CARD}),
        ("task_card_hash", {**CARD}),
        ("contract_hash", {"contract_hash": "d" * 64}),
    ],
)
def test_action_request_card_identity_missing(missing: str, action_over: dict[str, Any]) -> None:
    bound = _bound(**{
        k: v
        for k, v in {**CARD, "contract_hash": "d" * 64}.items()
        if k in action_over and k != missing
    })
    with pytest.raises(ValueError, match=f"^ACTION_IDENTITY_MISSING: {missing}$"):
        _var(_signed(bound, action_over))


HEAD = "e" * 40


def test_action_request_expected_head_requires_a_head_field() -> None:
    bound = _bound()
    with pytest.raises(ValueError, match="^ACTION_IDENTITY_MISSING: expected_head$"):
        _var(_signed(bound, {"expected_head": HEAD}))
    for field in ("controller_revision", "expected_head"):
        bound = _bound(**{field: HEAD})
        effective, _ = _var(_signed(bound, {"expected_head": HEAD}))
        assert effective["controller_revision"] == HEAD


def test_action_request_allowed_paths_required() -> None:
    bound = _bound()
    del bound["allowed_files"]
    with pytest.raises(ValueError, match="^ACTION_IDENTITY_MISSING: allowed_paths$"):
        _var(_signed(bound))
    bound = _bound(allowed_paths=["src/a.py"])
    del bound["allowed_files"]
    effective, _ = _var(_signed(bound))
    assert effective["allowed_files"] == ["src/a.py"] and effective["allowed_paths"] == ["src/a.py"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("task_id", "t2"),
        ("attempt_id", "a2"),
        ("action_id", "act2"),
        ("idempotency_key", "k2"),
        ("action_type", "TASK_RETRY"),
        ("contract_kind", "OWNER_INLINE"),
        ("task_card_path", "x.md"),
        ("task_card_hash", "x"),
        ("contract_hash", "x"),
    ],
)
@pytest.mark.parametrize("where", ["bound", "outer"])
def test_action_request_identity_mismatch(field: str, value: Any, where: str) -> None:
    bound = _bound(**({field: value} if where == "bound" else {}))
    request = _signed(bound, **({field: value} if where == "outer" else {}))
    with pytest.raises(ValueError, match=f"^ACTION_IDENTITY_MISMATCH: {field}$"):
        _var(request)


def test_action_request_identity_mismatch_bound_before_outer() -> None:
    bound = _bound(attempt_id="a2")
    with pytest.raises(ValueError, match="^ACTION_IDENTITY_MISMATCH: task_id$"):
        _var(_signed(bound, task_id="t9"))
    bound = _bound(task_id="t2")
    with pytest.raises(ValueError, match="^ACTION_IDENTITY_MISMATCH: task_id$"):
        _var(_signed(bound, attempt_id="a9"))


@pytest.mark.parametrize("field", ["action_request_hash", "request_hash"])
def test_action_request_outer_hash_mismatch(field: str) -> None:
    with pytest.raises(ValueError, match=f"^ACTION_IDENTITY_MISMATCH: {field}$"):
        _var(_signed(_bound(), **{field: "f" * 64}))
    bound = _bound()
    effective, _ = _var(_signed(bound, **{field: canonical_request_hash(bound)}))
    assert effective["action_request_hash"] == canonical_request_hash(bound)


def test_action_request_bound_hash_fields_are_not_compared() -> None:
    bound = _bound(request_hash="whatever", action_request_hash="also")
    effective, _ = _var(_signed(bound))
    assert effective["action_request_hash"] == canonical_request_hash(bound)
    assert effective["request_hash"] == "whatever"


@pytest.mark.parametrize("field", ["controller_revision", "expected_head"])
@pytest.mark.parametrize("where", ["bound", "outer"])
def test_action_request_head_mismatch(field: str, where: str) -> None:
    bound = _bound(**{
        "controller_revision": HEAD,
        **({field: "f" * 40} if where == "bound" else {}),
    })
    request = _signed(
        bound, {"expected_head": HEAD}, **({field: "f" * 40} if where == "outer" else {})
    )
    with pytest.raises(ValueError, match=f"^ACTION_IDENTITY_MISMATCH: {field}$"):
        _var(request)


def test_action_request_head_field_without_envelope_head_must_be_none() -> None:
    with pytest.raises(ValueError, match="^ACTION_IDENTITY_MISMATCH: controller_revision$"):
        _var(_signed(_bound(controller_revision=HEAD)))
    effective, _ = _var(_signed(_bound(controller_revision=None)))
    assert effective["controller_revision"] is None


@pytest.mark.parametrize(
    ("bound_value", "outer", "ok"),
    [
        (None, {}, True),
        ("rie-1", {}, True),
        ("rie-1", {"rie_knowledge_identity": "rie-1"}, True),
        ("rie-1", {"rie_knowledge_identity": "rie-2"}, False),
        (None, {"rie_knowledge_identity": "rie-1"}, False),
        (None, {"rie_knowledge_identity": None}, True),
    ],
)
def test_action_request_rie_knowledge_identity(
    bound_value: Any, outer: dict[str, Any], ok: bool
) -> None:
    bound = _bound(**({"rie_knowledge_identity": bound_value} if bound_value is not None else {}))
    request = _signed(bound, **outer)
    if ok:
        effective, _ = _var(request)
        assert effective.get("rie_knowledge_identity") == bound_value
    else:
        with pytest.raises(ValueError, match="^ACTION_IDENTITY_MISMATCH: rie_knowledge_identity$"):
            _var(request)


def test_action_request_rie_checked_after_heads_and_before_paths() -> None:
    bound = _bound(controller_revision="f" * 40, allowed_files=["other.py"])
    with pytest.raises(ValueError, match="^ACTION_IDENTITY_MISMATCH: controller_revision$"):
        _var(_signed(bound, rie_knowledge_identity="x"))
    bound = _bound(allowed_files=["other.py"])
    with pytest.raises(ValueError, match="^ACTION_IDENTITY_MISMATCH: rie_knowledge_identity$"):
        _var(_signed(bound, rie_knowledge_identity="x"))


LOOKUP = {"target_symbol": "pkg.mod.fn", "search_paths": ["src/a.py"]}


@pytest.mark.parametrize(
    ("bound_value", "outer", "ok"),
    [
        (None, {}, True),
        (LOOKUP, {}, True),
        (LOOKUP, {"codeintel_lookup": dict(LOOKUP)}, True),
        (LOOKUP, {"codeintel_lookup": {**LOOKUP, "target_symbol": "other"}}, False),
        (LOOKUP, {"codeintel_lookup": None}, False),
        (None, {"codeintel_lookup": dict(LOOKUP)}, False),
        (None, {"codeintel_lookup": None}, True),
    ],
)
def test_action_request_codeintel_lookup(bound_value: Any, outer: dict[str, Any], ok: bool) -> None:
    bound = _bound(**({"codeintel_lookup": bound_value} if bound_value is not None else {}))
    request = _signed(bound, **outer)
    if ok:
        effective, _ = _var(request)
        assert effective.get("codeintel_lookup") == bound_value
    else:
        with pytest.raises(ValueError, match="^ACTION_IDENTITY_MISMATCH: codeintel_lookup$"):
            _var(request)


def test_action_request_codeintel_lookup_checked_after_rie_and_before_paths() -> None:
    bound = _bound(allowed_files=["other.py"])
    with pytest.raises(ValueError, match="^ACTION_IDENTITY_MISMATCH: rie_knowledge_identity$"):
        _var(_signed(bound, rie_knowledge_identity="x", codeintel_lookup=dict(LOOKUP)))
    with pytest.raises(ValueError, match="^ACTION_IDENTITY_MISMATCH: codeintel_lookup$"):
        _var(_signed(bound, codeintel_lookup=dict(LOOKUP)))
    # an outer copy equal to the (absent) signed value passes and is not copied into the result
    effective, _ = _var(_signed(_bound(), codeintel_lookup=None))
    assert "codeintel_lookup" not in effective


@pytest.mark.parametrize(
    ("bound_over", "outer"),
    [
        ({"allowed_files": ["other.py"]}, {}),
        ({"allowed_paths": ["other.py"]}, {}),
        ({}, {"allowed_files": ["other.py"]}),
        ({}, {"allowed_paths": []}),
        ({"allowed_files": ["src/a.py", "src/a.py"]}, {}),
    ],
)
def test_action_request_allowed_paths_mismatch(
    bound_over: dict[str, Any], outer: dict[str, Any]
) -> None:
    with pytest.raises(ValueError, match="^ACTION_IDENTITY_MISMATCH: allowed_paths$"):
        _var(_signed(_bound(**bound_over), **outer))


def test_action_request_allowed_paths_compared_as_tuples() -> None:
    effective, _ = _var(_signed(_bound(allowed_files=("src/a.py",)), allowed_paths=["src/a.py"]))
    assert effective["allowed_files"] == ("src/a.py",)


def test_action_request_effective_request() -> None:
    bound = _bound(
        **CARD, contract_kind="TRACKED_TASK_CARD", extra="kept", controller_revision=HEAD
    )
    request = _signed(
        bound,
        {**CARD, "contract_kind": "TRACKED_TASK_CARD", "expected_head": HEAD},
        outer_only="dropped",
        task_id="t1",
    )
    effective, envelope = _var(request)
    assert envelope == request_action_dump(request["action"])
    assert effective == {
        **bound,
        "action": envelope,
        "bound_action_request": bound,
        "action_request_hash": canonical_request_hash(bound),
    }
    assert "outer_only" not in effective
    assert effective["bound_action_request"] is not bound
    assert effective["action"] is not envelope


def request_action_dump(action: dict[str, Any]) -> dict[str, Any]:
    from nexus.contracts.lifecycle_action import LifecycleActionEnvelope

    return LifecycleActionEnvelope.model_validate(action).model_dump(mode="json")


def test_action_request_effective_fills_identity_from_envelope() -> None:
    # bound values are equal but of other types / forms the envelope normalises
    bound = _bound(idempotency_key="k1")
    effective, envelope = _var(_signed(bound, {"idempotency_key": " k1 "}))
    assert envelope["idempotency_key"] == "k1"
    assert effective["idempotency_key"] == "k1"
    assert "task_card_path" not in effective and "contract_hash" not in effective


def test_action_request_effective_adds_allowed_files_only_when_absent() -> None:
    bound = _bound(allowed_paths=["src/a.py"])
    del bound["allowed_files"]
    effective, _ = _var(_signed(bound))
    assert effective["allowed_files"] == ["src/a.py"]
    bound = _bound(allowed_files=["src/a.py"], allowed_paths=["src/a.py"])
    effective, _ = _var(_signed(bound))
    assert effective["allowed_files"] == ["src/a.py"]


@pytest.fixture
def project_binding(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    control: dict[str, Any] = {"calls": [], "results": []}

    def validate(request: Any, **kwargs: Any) -> Any:
        control["calls"].append((dict(request), kwargs))
        result = control["results"][len(control["calls"]) - 1]
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(service_module, "_validate_project_entry_authority_binding", validate)
    return control


def test_action_request_project_binding_none(project_binding: dict[str, Any]) -> None:
    project_binding["results"] = [None]
    bound = _bound(repository="any", issue=5)
    effective, _ = _var(
        _signed(bound, project_entry_authority_binding={"x": 1}, repository="other")
    )
    assert len(project_binding["calls"]) == 1
    assert project_binding["calls"][0] == (effective, {})


PB = {"repository": "James3014/Nexus-new", "issue_number": "842"}


def test_action_request_project_binding_outer_duplicate(project_binding: dict[str, Any]) -> None:
    project_binding["results"] = [dict(PB), dict(PB)]
    request = _signed(_bound(), project_entry_authority_binding={"x": 1})
    effective, _ = _var(request)
    assert [c[0] for c in project_binding["calls"]] == [effective, request]
    project_binding["calls"].clear()
    project_binding["results"] = [dict(PB), {**PB, "goal_id": "x"}]
    with pytest.raises(ValueError, match="^PROJECT_ENTRY_AUTHORITY_BINDING_DUPLICATE_MISMATCH$"):
        _var(request)


def test_action_request_project_binding_outer_absent_is_not_revalidated(
    project_binding: dict[str, Any],
) -> None:
    project_binding["results"] = [dict(PB)]
    _var(_signed(_bound(), project_entry_authority_binding=None))
    assert len(project_binding["calls"]) == 1


def test_action_request_project_binding_outer_error_propagates(
    project_binding: dict[str, Any],
) -> None:
    project_binding["results"] = [dict(PB), ValueError("PROJECT_ENTRY_AUTHORITY_BINDING_INVALID")]
    with pytest.raises(ValueError, match="^PROJECT_ENTRY_AUTHORITY_BINDING_INVALID$"):
        _var(_signed(_bound(), project_entry_authority_binding="x"))


@pytest.mark.parametrize(
    ("bound_over", "outer", "message"),
    [
        ({"repository": "other"}, {}, "PROJECT_ENTRY_AUTHORITY_REPOSITORY_MISMATCH"),
        ({}, {"repository": "other"}, "PROJECT_ENTRY_AUTHORITY_REPOSITORY_MISMATCH"),
        ({"issue": "842"}, {}, "PROJECT_ENTRY_AUTHORITY_ISSUE_MISMATCH"),
        ({"issue_number": 841}, {}, "PROJECT_ENTRY_AUTHORITY_ISSUE_MISMATCH"),
        ({}, {"issue": 841}, "PROJECT_ENTRY_AUTHORITY_ISSUE_MISMATCH"),
        ({}, {"issue_number": None}, "PROJECT_ENTRY_AUTHORITY_ISSUE_MISMATCH"),
        # bound is checked before the outer request, repository before issue
        ({"issue": 1}, {"repository": "other"}, "PROJECT_ENTRY_AUTHORITY_ISSUE_MISMATCH"),
        ({"repository": "other", "issue": 1}, {}, "PROJECT_ENTRY_AUTHORITY_REPOSITORY_MISMATCH"),
    ],
)
def test_action_request_project_binding_selectors(
    project_binding: dict[str, Any], bound_over: dict[str, Any], outer: dict[str, Any], message: str
) -> None:
    project_binding["results"] = [dict(PB)]
    with pytest.raises(ValueError, match=f"^{message}$"):
        _var(_signed(_bound(**bound_over), **outer))


def test_action_request_project_binding_matching_selectors(project_binding: dict[str, Any]) -> None:
    project_binding["results"] = [dict(PB)]
    effective, _ = _var(
        _signed(_bound(repository="James3014/Nexus-new", issue=842), issue_number=842)
    )
    assert effective["issue"] == 842


def test_action_request_with_real_project_entry_binding() -> None:
    bound = _bound(
        project_entry_authority_binding=_binding(),
        repository="James3014/Nexus-new",
        issue_number=842,
    )
    effective, _ = _var(_signed(bound, project_entry_authority_binding=_binding()))
    assert effective["project_entry_authority_binding"] == _binding()
    with pytest.raises(ValueError, match="^PROJECT_ENTRY_AUTHORITY_BINDING_DUPLICATE_MISMATCH$"):
        _var(_signed(bound, project_entry_authority_binding=_binding(goal_id="other")))
    with pytest.raises(ValueError, match="^PROJECT_ENTRY_AUTHORITY_BINDING_HASH_MISMATCH$"):
        bad = _bound(project_entry_authority_binding={**_binding(), "binding_hash": "x"})
        _var(_signed(bad))


# ---------------------------------------------------------------------------
# facade patch targets reach the helpers at call time


def test_patch_contract_kind_reaches_tracked_dispatch_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service_module,
        "ContractKind",
        SimpleNamespace(TRACKED_TASK_CARD=SimpleNamespace(value="PATCHED")),
    )
    assert service_module._tracked_dispatch_required({"contract_kind": "PATCHED"}) is True
    assert (
        service_module._tracked_dispatch_required({"contract_kind": "TRACKED_TASK_CARD"}) is False
    )


def test_patch_hint_keys_reach_reject_unbound(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        service_module, "_PROJECT_ENTRY_AUTHORITY_HINTS", frozenset({"patched_hint"})
    )
    with pytest.raises(ValueError, match="^PROJECT_ENTRY_AUTHORITY_BINDING_REQUIRED$"):
        _hints({"patched_hint": 1})
    assert _hints({"authority_goal_id": "g"}) is None


def test_patch_autonomy_action_class_reaches_project_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []

    def action_class(value: Any) -> Any:
        seen.append(value)
        return SimpleNamespace(value="TASK_SUBMIT")

    monkeypatch.setattr(service_module, "AutonomyActionClass", action_class)
    assert _vpe({"project_entry_authority_binding": _binding()}) == EXPECTED_VALUES
    assert seen == ["TASK_SUBMIT"]


def test_patch_canonical_request_hash_reaches_project_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Any] = []
    monkeypatch.setattr(
        service_module,
        "canonical_request_hash",
        lambda payload: seen.append(dict(payload)) or "PATCHED",
    )
    raw = {**{k: v for k, v in _binding().items()}, "binding_hash": "PATCHED"}
    assert _vpe({"project_entry_authority_binding": raw}) == EXPECTED_VALUES
    assert seen == [VALUES]


def test_patch_canonical_request_hash_reaches_validated_action_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound = _bound()
    request = _signed(bound)
    monkeypatch.setattr(service_module, "canonical_request_hash", lambda payload: "1" * 64)
    with pytest.raises(ValueError, match="^BOUND_ACTION_REQUEST_HASH_MISMATCH$"):
        _var(request)


def test_patch_lifecycle_envelope_and_type_reach_validated_action_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Envelope:
        @staticmethod
        def model_validate(raw: Any) -> Any:
            raise RuntimeError("PATCHED-ENVELOPE")

    monkeypatch.setattr(service_module, "LifecycleActionEnvelope", Envelope)
    with pytest.raises(ValueError, match="^ACTION_ENVELOPE_INVALID: PATCHED-ENVELOPE$"):
        _var(_signed(_bound()))
    monkeypatch.undo()
    monkeypatch.setattr(
        service_module, "LifecycleActionType", SimpleNamespace(TASK_RUN="no", TASK_RETRY="no")
    )
    with pytest.raises(ValueError, match="^ACTION_TYPE_UNSUPPORTED_FOR_TASK_SUBMISSION$"):
        _var(_signed(_bound()))


def test_patch_project_entry_validator_reaches_validated_action_request(
    project_binding: dict[str, Any],
) -> None:
    project_binding["results"] = [ValueError("PATCHED")]
    with pytest.raises(ValueError, match="^PATCHED$"):
        _var(_signed(_bound()))


def test_patch_evaluator_loader_readback_builder_reach_validate(
    fake_admission: dict[str, Any],
) -> None:
    result = _validate(_base_request(canonical_dispatch_envelope={"env": 1}, planner_output={}))
    assert [c[0] for c in fake_admission["calls"]] == ["loader", "evaluate", "readback", "build"]
    assert result["worker_id"] == "rw"


def test_patch_validator_builder_service_reach_recover(drift: dict[str, Any]) -> None:
    assert _recover(_drift_state(), _drift_request()) is not None
    assert [c[0] for c in drift["calls"]] == ["validate", "build", "validate", "assert"]


def test_facade_patch_of_validator_reaches_coordination_bridge_only_by_import_time_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # runtime_coordination_bridge imported the facade object at import time; a later
    # facade patch does not reach it (unchanged by the split).
    sentinel = object()
    monkeypatch.setattr(service_module, "validate_workforce_dispatch_binding", sentinel)
    assert runtime_coordination_bridge.validate_workforce_dispatch_binding is not sentinel


def test_admission_round_trip_json_shape() -> None:
    # sanity: the helpers' inputs and outputs here are JSON round-trippable
    assert json.loads(json.dumps(_fresh())) == _fresh()
