from __future__ import annotations

import re


def _deadlock_lock_order_patch(source: str) -> str:
    """
    Best-effort deadlock fix for common transfer-style nested lock pattern.
    """
    if "def transfer(" not in source:
        return source
    if "with acc1.lock" not in source or "with acc2.lock" not in source:
        return source

    pattern = re.compile(
        r"with acc1\.lock:\n\s+time\.sleep\(0\.01\)\s*#.*?\n\s+with acc2\.lock:\n\s+if acc1\.balance >= amount:\n\s+acc1\.balance -= amount\n\s+acc2\.balance \+= amount",
        re.DOTALL,
    )
    replacement = (
        "first, second = (acc1, acc2) if id(acc1) < id(acc2) else (acc2, acc1)\n"
        "    with first.lock:\n"
        "        time.sleep(0.01)  # Simulate some IO or DB operation\n"
        "        with second.lock:\n"
        "            if acc1.balance >= amount:\n"
        "                acc1.balance -= amount\n"
        "                acc2.balance += amount"
    )
    return pattern.sub(replacement, source)


def generate_local_candidate(source: str, task: str, mutation_hint: str, seed: int) -> str:
    """
    Deterministic local candidate generator (no external model calls).
    """
    lowered = f"{task} {mutation_hint}".lower()
    if any(k in lowered for k in ["deadlock", "race", "concurrency", "lock"]):
        patched = _deadlock_lock_order_patch(source)
        if patched != source:
            return patched
    return source
