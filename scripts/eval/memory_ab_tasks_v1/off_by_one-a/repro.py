from pagination import chunk

got = chunk([1, 2, 3, 4, 5], 2)
want = [[1, 2], [3, 4], [5]]
assert got == want, f"chunk got {got!r} want {want!r}"
