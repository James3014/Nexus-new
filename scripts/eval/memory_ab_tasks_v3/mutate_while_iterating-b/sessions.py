def expire_sessions(store, now):
    """Delete sessions whose 'until' is before now. Return the removed tokens, sorted.

    store maps token -> {'until': int}. A session with until == now is still live.
    """
    removed = []
    for token, session in store.items():
        if session["until"] < now:
            del store[token]
            removed.append(token)
    return sorted(removed)
