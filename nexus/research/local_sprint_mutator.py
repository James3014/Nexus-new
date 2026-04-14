from __future__ import annotations

import re


def _deadlock_lock_order_patch(source: str) -> str:
    """
    R4: Hardened deadlock fix for nested transfer pattern.
    Only applies if nested acc1/acc2 lock structure is detected.
    """
    if "def transfer(" not in source:
        return source
    if "first, second = (acc1, acc2)" in source:
        return source # Already patched

    # Precise nested pattern: with acc1.lock -> with acc2.lock
    pattern = re.compile(
        r"(?P<indent>\s+)with (?P<a1>acc1)\.lock:.*?\n(?P<inner_indent>\s+)with (?P<a2>acc2)\.lock:",
        re.DOTALL
    )
    
    match = pattern.search(source)
    if not match:
        return source

    indent = match.group("indent")
    # Replace the outer lock entry with order assignment
    replacement = (
        f"{indent}first, second = (acc1, acc2) if id(acc1) < id(acc2) else (acc2, acc1)\n"
        f"{indent}with first.lock:\n"
        f"{match.group('inner_indent')}with second.lock:"
    )
    
    # We must be careful to only replace the matched entry point
    # Using string replace here is safer if we know the unique context, 
    # but regex sub with limited count is better.
    new_source = pattern.sub(replacement, source, count=1)
    
    # AST Safety Valve
    try:
        compile(new_source, "<mutator_patch>", "exec")
        return new_source
    except SyntaxError:
        return source

def _feature_discount_patch(source: str) -> str:
    """Apply discount feature logic for demo."""
    if "def apply_discount(" not in source: return source
    if "pass" not in source: return source
    new_source = source.replace("pass", "if discount_code == 'SAVE20':\n        return amount * 0.8\n    return amount")
    try:
        compile(new_source, "<feature_patch>", "exec")
        return new_source
    except SyntaxError:
        return source

def _refactor_parser_patch(source: str) -> str:
    """Apply parser purity refactor for demo."""
    new_source = source
    if "import random" in source:
        new_source = new_source.replace("import random", "import hashlib")
    if "random.randint(0, 100)" in source:
        new_source = new_source.replace("random.randint(0, 100)", "int(hashlib.md5(data.encode()).hexdigest(), 16) % 100")
    
    if new_source == source:
        return source
        
    try:
        compile(new_source, "<refactor_patch>", "exec")
        return new_source
    except SyntaxError:
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

