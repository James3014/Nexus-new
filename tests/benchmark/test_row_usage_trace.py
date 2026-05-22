from scripts.bench.row_usage_trace import (
    governance_event_types,
    phase_wall_from_trace,
    skill_mount_view,
)


def test_phase_wall_prefers_timing_and_falls_back_to_usage_trace():
    timing = {"phase_wall_sec": {"P": 0.1, "R": 1.5}}
    usage_trace = {"phase_wall_sec": {"P": 9.9, "X": 0.2}}

    assert phase_wall_from_trace(timing=timing, usage_trace=usage_trace) == {"P": 0.1, "R": 1.5}

    assert phase_wall_from_trace(timing={}, usage_trace=usage_trace) == {"P": 9.9, "X": 0.2}
    assert phase_wall_from_trace(timing={"phase_wall_sec": "bad"}, usage_trace={}) == {}


def test_skill_mount_view_normalizes_contracts_and_return_status():
    view = skill_mount_view(
        {
            "skill_mount_contract": {"skill_id": "nexus-root-cause-probe"},
            "skill_mount_violations": [{"reason": "skill_mount_not_confirmed_by_runtime_receipt"}, "noise"],
        }
    )

    assert view.contracts == [{"skill_id": "nexus-root-cause-probe"}]
    assert view.violations == [{"reason": "skill_mount_not_confirmed_by_runtime_receipt"}]
    assert view.status == "RETURN"


def test_skill_mount_view_accepts_plural_contracts_and_empty_status():
    assert skill_mount_view({"skill_mount_contracts": [{"skill_id": "a"}, "noise"]}).status == "PASS"
    assert skill_mount_view({}).status == "EMPTY"


def test_governance_event_types_are_unique_sorted_nonempty_strings():
    events = [
        {"event_type": "policy_gate"},
        {"event_type": ""},
        {"event_type": "skill_mount"},
        {"event_type": "policy_gate"},
        "noise",
    ]

    assert governance_event_types(events) == ["policy_gate", "skill_mount"]
