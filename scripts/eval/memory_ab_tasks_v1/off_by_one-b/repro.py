from tail import last_k

got = last_k([1, 2, 3, 4], 2)
assert got == [3, 4], f"last_k got {got!r} want [3, 4]"
