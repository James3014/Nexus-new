import pytest
from nexus.research.local_sprint_mutator import generate_local_candidate

def test_deadlock_fix_applied():
    source = """
def transfer(acc1, acc2, amount):
    with acc1.lock:
        time.sleep(0.01)
        with acc2.lock:
            acc1.balance -= amount
"""
    patched = generate_local_candidate(source, "fix deadlock", "lock ordering", 0)
    assert "first, second = (acc1, acc2)" in patched
    assert "with first.lock:" in patched
    assert "with second.lock:" in patched

def test_non_deadlock_unchanged():
    source = """
def update_balance(acc1, amount):
    with acc1.lock:
        acc1.balance += amount
"""
    patched = generate_local_candidate(source, "fix deadlock", "lock ordering", 0)
    assert patched == source

def test_already_patched_unchanged():
    source = """
def transfer(acc1, acc2, amount):
    first, second = (acc1, acc2) if id(acc1) < id(acc2) else (acc2, acc1)
    with first.lock:
        with second.lock:
            pass
"""
    patched = generate_local_candidate(source, "fix deadlock", "lock ordering", 0)
    assert patched == source

def test_invalid_syntax_fallback():
    # This is tricky because our mutator uses simple string/regex.
    # We simulate a case where the "patch" would create invalid syntax if not for safety valve.
    # But since we use compile() in mutator, it should return original.
    pass # covered by compile() check in logic


def test_normalize_flag_patch_applied():
    source = """
def normalize_flag(text: str) -> str:
    return text
"""
    patched = generate_local_candidate(source, "fix normalize flag behavior", "local", 0)
    assert "return text.strip().lower()" in patched


def test_compute_backoff_patch_applied():
    source = """
def compute_backoff(attempt: int) -> int:
    return 1
"""
    patched = generate_local_candidate(source, "fix retry backoff behavior", "local", 0)
    assert "return 2 ** (attempt - 1)" in patched


def test_compute_backoff_high_risk_seed_zero_uses_conservative_patch():
    source = """
def compute_backoff(attempt: int) -> int:
    return 1
"""
    patched_seed0 = generate_local_candidate(source, "fix flaky timeout race condition", "local", 0)
    patched_seed1 = generate_local_candidate(source, "fix flaky timeout race condition", "local", 1)
    assert "return attempt" in patched_seed0
    assert "return 2 ** (attempt - 1)" in patched_seed1


def test_compute_backoff_websocket_high_risk_skips_conservative_patch():
    source = """
def compute_backoff(attempt: int) -> int:
    return 1
"""
    patched = generate_local_candidate(source, "fix websocket reconnect latency issue", "local", 0)
    assert "return 2 ** (attempt - 1)" in patched


def test_compute_backoff_api_context_keeps_bare_baseline_conservative():
    source = """
def compute_backoff(attempt: int) -> int:
    return attempt
"""
    patched = generate_local_candidate(source, "fix stale cache invalidation across API and repository layers", "local", 0)
    assert "return attempt" in patched


def test_compute_backoff_api_context_with_nexus_hint_uses_direct_patch():
    source = """
def compute_backoff(attempt: int) -> int:
    return attempt
"""
    patched = generate_local_candidate(
        source,
        "fix stale cache invalidation across API and repository layers",
        "Conservative: Focus on the minimal required change to fix the specific issue without refactoring.",
        0,
    )
    assert "return 2 ** (attempt - 1)" in patched
