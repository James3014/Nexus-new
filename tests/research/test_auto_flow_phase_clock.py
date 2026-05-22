from nexus.research.flow.phase_clock import AutoFlowPhaseClock


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
