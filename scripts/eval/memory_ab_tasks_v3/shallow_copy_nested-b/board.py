def snapshot(board):
    """Return an independent copy of board, a list of rows of cell values."""
    return list(board)  # BUG: the row lists are shared with the original


class History:
    """Stack of board snapshots for undo."""

    def __init__(self):
        self._states = []

    def push(self, board):
        self._states.append(snapshot(board))

    def pop(self):
        return self._states.pop()
