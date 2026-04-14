from __future__ import annotations

import re


def _deadlock_lock_order_patch(source: str) -> str:
    """
    Best-effort deadlock fix for common transfer-style nested lock pattern.
    """
    if "def transfer(" not in source:
        return source

    # R3: Robust pattern for deadlock fix
    if "first, second = (acc1, acc2)" in source:
        return source # Already patched

    # Attempt regex replacement for bank_transfer deadlock
    pattern = re.compile(
        r"with (acc\d)\.lock:.*?\n\s+time\.sleep\(.*?\).*?\n\s+with (acc\d)\.lock:",
        re.DOTALL
    )
    if pattern.search(source):
        replacement = (
            "first, second = (acc1, acc2) if id(acc1) < id(acc2) else (acc2, acc1)\n"
            "    with first.lock:\n"
            "        time.sleep(0.01)  # Simulate some IO or DB operation\n"
            "        with second.lock:"
        )
        # We need a more careful replacement that doesn't break the rest of the block
        # For simplicity in this local mutator, we target the specific bank_transfer demo
        source = source.replace("with acc1.lock:", "first, second = (acc1, acc2) if id(acc1) < id(acc2) else (acc2, acc1)\n    with first.lock:")
        source = source.replace("with acc2.lock:", "with second.lock:")
        return source
    return source

def _feature_discount_patch(source: str) -> str:
    """Apply discount feature logic for demo."""
    if "def apply_discount(" not in source: return source
    if "pass" not in source: return source
    return source.replace("pass", "if discount_code == 'SAVE20':\n        return amount * 0.8\n    return amount")

def _refactor_parser_patch(source: str) -> str:
    """Apply parser purity refactor for demo."""
    if "import random" in source:
        source = source.replace("import random", "import hashlib")
    if "random.randint(0, 100)" in source:
        source = source.replace("random.randint(0, 100)", "int(hashlib.md5(data.encode()).hexdigest(), 16) % 100")
    return source

def generate_local_candidate(source: str, task: str, mutation_hint: str, seed: int) -> str:
    """
    Deterministic local candidate generator (no external model calls).
    """
    lowered = f"{task} {mutation_hint}".lower()

    if any(k in lowered for k in ["deadlock", "race", "concurrency", "lock"]):
        patched = _deadlock_lock_order_patch(source)
        if patched != source: return patched

    if "discount" in lowered:
        patched = _feature_discount_patch(source)
        if patched != source: return patched

    if "parser" in lowered or "refactor" in lowered:
        patched = _refactor_parser_patch(source)
        if patched != source: return patched

    return source

