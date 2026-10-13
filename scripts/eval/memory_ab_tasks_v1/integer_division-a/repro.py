from stats import average

got = average([1, 2])
assert abs(got - 1.5) <= 1e-9, f"average([1, 2]) got {got!r} want 1.5"
