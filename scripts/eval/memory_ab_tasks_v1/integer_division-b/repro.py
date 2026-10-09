from ratios import percent

got = percent(1, 3)
assert abs(got - 33.333) <= 0.01, f"percent(1, 3) got {got!r} want ~33.33"
