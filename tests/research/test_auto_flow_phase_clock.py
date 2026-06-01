from nexus.research.flow.phase_clock import AutoFlowPhaseClock, apply_auto_flow_timing_payload


def test_auto_flow_phase_clock_records_ordered_phase_wall_times():
    ticks = iter([10.0, 10.25, 11.0, 11.5])
    clock = AutoFlowPhaseClock(now=lambda: next(ticks))

    assert clock.mark("P") == 0.25
    assert clock.mark("X") == 0.75
    assert clock.mark("D") == 0.5
    assert clock.phase_wall_sec == {"P": 0.25, "X": 0.75, "D": 0.5}


def test_auto_flow_phase_clock_rounds_to_four_decimals():
    ticks = iter([1.0, 1.333333, 1.666666])
    clock = AutoFlowPhaseClock(now=lambda: next(ticks))

    assert clock.mark("P") == 0.3333
    assert clock.mark("X") == 0.3333


def test_auto_flow_phase_clock_can_restart_before_late_phase():
    ticks = iter([10.0, 11.0, 12.0, 12.75])
    clock = AutoFlowPhaseClock(now=lambda: next(ticks))

    assert clock.mark("R") == 1.0
    clock.restart()

    assert clock.mark("A") == 0.75
    assert clock.phase_wall_sec == {"R": 1.0, "A": 0.75}


def test_apply_auto_flow_timing_payload_updates_timing_and_usage_trace():
    payload = {"timing": {}, "nexus_usage_trace": {}}
    phase_wall = {"P": 0.1, "X": 0.2}
    breakdown = {"target_io_sec": 0.01}

    apply_auto_flow_timing_payload(
        payload,
        cli_elapsed_sec=1.23456,
        phase_wall_sec=phase_wall,
        breakdown_sec=breakdown,
    )

    assert payload["timing"] == {
        "cli_elapsed_sec": 1.2346,
        "phase_wall_sec": phase_wall,
        "breakdown_sec": breakdown,
    }
    assert payload["nexus_usage_trace"]["phase_wall_sec"] == phase_wall
