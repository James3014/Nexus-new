from nexus.experimental.open_swe_pilot.canary_fixture import add


def test_add_returns_arithmetic_sum() -> None:
    assert add(2, 3) == 5
    assert add(-2, 2) == 0
