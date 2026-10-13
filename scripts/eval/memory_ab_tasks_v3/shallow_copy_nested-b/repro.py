from board import History, snapshot


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


board = [["x", None], [None, "o"]]
snap = snapshot(board)
board[0][0] = "o"
check("snapshot unaffected by later move", lambda: snap, [["x", None], [None, "o"]])

fresh = [["q"]]
copy_of = snapshot(fresh)
check("rows are new lists", lambda: copy_of[0] is fresh[0], False)

history = History()
state = [["a"]]
history.push(state)
state[0][0] = "b"
check("undo restores pushed state", lambda: history.pop(), [["a"]])
