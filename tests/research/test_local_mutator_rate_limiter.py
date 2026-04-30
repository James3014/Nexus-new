import pytest
from nexus.research.local_sprint_mutator import generate_local_candidate

def test_feature_structural_patch_applied():
    source = """
def rate_limiter(ip: str):
    pass
"""
    # Lowered task will contain "feature"
    task = "implement feature rate limiter"
    hint = "structural"
    patched = generate_local_candidate(source, task, hint, 0)
    # Since 'rate' and 'limit' are present, it should use _patch_rate_limiter_prune
    # But _patch_rate_limiter_prune returns source because window_sec is missing.
    # Then it falls back to _structural_feature_patch
    assert "pass" not in patched
    assert "return None" in patched

def test_rate_limiter_pass_to_full_patch():
    source = """
class RateLimiter:
    def __init__(self, limit=2, window_sec=1.0):
        self.limit = limit
        self.window_sec = window_sec
        self.hits = []

    def allow(self):
        pass
"""
    task = "feature-rate-limiter"
    patched = generate_local_candidate(source, task, "local", 0)
    assert "self.hits = [h for h in self.hits if now - h < self.window_sec]" in patched
    assert "return True" in patched
    assert "import time" in patched

def test_rate_limiter_missing_now_patch():
    source = """
class RateLimiter:
    def __init__(self, limit=2, window_sec=1.0):
        self.limit = limit
        self.window_sec = window_sec
        self.hits = []

    def allow(self):
        if len(self.hits) >= self.limit:
            return False
        self.hits.append(time.time())
        return True
"""
    task = "feature-rate-limiter"
    patched = generate_local_candidate(source, task, "local", 0)
    # Should use time.time() instead of now
    assert "time.time() - h < self.window_sec" in patched

def test_refactor_structural_patch_applied():
    source = """
def old_parser(data: str):
    pass
"""
    # Lowered task will contain "refactor"
    task = "refactor old parser to new one"
    hint = "structural"
    patched = generate_local_candidate(source, task, hint, 0)
    assert "pass" not in patched
    assert "return None" in patched
    assert "Structural injection" in patched

def test_non_structural_unchanged():
    source = """
def bugfix_something():
    pass
"""
    # "fix" or "bug" should not trigger structural patch if no 'feature'/'refactor'
    task = "fix a bug"
    hint = "local"
    patched = generate_local_candidate(source, task, hint, 0)
    assert patched == source

def test_rate_limiter_prune_patch_applied():
    source = """
import time
class RateLimiter:
    def __init__(self, limit=2, window_sec=1.0):
        self.limit = limit
        self.window_sec = window_sec
        self.hits = []

    def allow(self):
        now = time.time()
        # BUG: no pruning of stale hits
        if len(self.hits) >= self.limit:
            return False
        self.hits.append(now)
        return True
"""
    task = "Implement rolling window prune for rate limiter"
    hint = "local"
    patched = generate_local_candidate(source, task, hint, 0)
    assert "self.hits = [h for h in self.hits if now - h < self.window_sec]" in patched
    assert "if len(self.hits) >= self.limit:" in patched


def test_rlm_belief_budget_requires_evidence_for_medium_or_high_risk():
    source = """
def rlm_harder_v2_repair_budget(confidence, risk):
    return {'rounds': 1, 'needs_evidence': False}
"""
    patched = generate_local_candidate(
        source,
        "Fix repair budget selection so low confidence and high risk require extra evidence-gathering rounds.",
        "local",
        0,
    )
    namespace = {}
    exec(patched, namespace)

    assert namespace["rlm_harder_v2_repair_budget"](0.42, "high") == {"rounds": 3, "needs_evidence": True}
    assert namespace["rlm_harder_v2_repair_budget"](0.74, "medium") == {"rounds": 3, "needs_evidence": True}
    assert namespace["rlm_harder_v2_repair_budget"](0.91, "low") == {"rounds": 1, "needs_evidence": False}
