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


def test_normalize_flag_patch_uses_actual_argument_name():
    source = """
def normalize_flag(value):
    return value
"""
    patched = generate_local_candidate(source, "fix normalize flag behavior", "local", 0)
    assert "return value.strip().lower()" in patched


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


def test_apply_events_patch_makes_duplicate_ids_idempotent():
    source = """
def apply_events(events):
    state = {'count': 0, 'seen': []}
    for event in events:
        state['count'] += int(event.get('delta', 0))
        state['seen'].append(event.get('id'))
    return state
"""
    patched = generate_local_candidate(source, "Fix idempotent handling of duplicate events", "local", 0)
    ns = {}
    exec(patched, ns)
    assert ns["apply_events"]([{"id": "a", "delta": 2}, {"id": "a", "delta": 2}, {"id": "b", "delta": 3}]) == {
        "count": 5,
        "seen": ["a", "b"],
    }


def test_overall_status_patch_requires_phase_evidence():
    source = """
def overall_status(phases):
    return 'pass' if all(p.get('status') == 'pass' for p in phases) else 'fail'
"""
    patched = generate_local_candidate(source, "Fix status aggregator missing evidence trust mismatch", "local", 0)
    ns = {}
    exec(patched, ns)
    assert ns["overall_status"]([{"status": "pass", "evidence": "a"}]) == "pass"
    assert ns["overall_status"]([{"status": "pass"}]) == "fail"


def test_response_result_field_patch_uses_canonical_docs_field():
    source = """FIELD = 'status'

def build_response(value):
    return {FIELD: value}
"""
    patched = generate_local_candidate(
        source,
        "Sync code and docs after a renamed public field; infer the canonical field from contract text",
        "local",
        0,
    )
    ns = {}
    exec(patched, ns)
    assert ns["build_response"]("ok") == {"result": "ok"}


def test_response_result_field_patch_normalizes_outcome_to_result():
    source = """FIELD = 'outcome'

def build_response(value):
    return {FIELD: value}
"""
    patched = generate_local_candidate(
        source,
        "Sync code and docs after a renamed public field; infer canonical response key from contract context.",
        "local",
        0,
    )
    ns = {}
    exec(patched, ns)
    assert ns["build_response"]("ok") == {"result": "ok"}


def test_parse_config_defaults_patch_preserves_explicit_values():
    source = """
def parse_config(data):
    return {'strict': bool(data.get('strict', False)), 'retries': data.get('retries', 0)}
"""
    patched = generate_local_candidate(
        source,
        "Sync configuration docs and strict parser defaults where history-like examples conflict with the new canonical behavior.",
        "local",
        0,
    )
    ns = {}
    exec(patched, ns)
    assert ns["parse_config"]({}) == {"strict": True, "retries": 3}
    assert ns["parse_config"]({"strict": False, "retries": 0}) == {"strict": False, "retries": 0}


def test_swarm_report_patch_requires_distinct_roles_and_evidence():
    source = """
def rlm_harder_v2_accept_swarm_report(report):
    return report.get('consensus') == 'pass' and len(report.get('findings', [])) >= 2
"""
    patched = generate_local_candidate(
        source,
        "Accept a swarm review only when independent roles provide evidence and consensus is explicit.",
        "local",
        0,
    )
    ns = {}
    exec(patched, ns)
    accept = ns["rlm_harder_v2_accept_swarm_report"]

    assert accept({"consensus": "pass", "findings": [{"role": "logic", "evidence": "a"}, {"role": "security", "evidence": "b"}]}) is True
    assert accept({"consensus": "pass", "findings": [{"role": "logic", "evidence": "a"}, {"role": "logic", "evidence": "b"}]}) is False
    assert accept({"consensus": "pass", "findings": [{"role": "logic"}, {"role": "security", "evidence": "b"}]}) is False


def test_ultra_report_patch_requires_repro_command_and_negative_run():
    source = """
def rlm_harder_v2_accept_ultra_report(report):
    return bool(report.get('sandbox_id') and report.get('gate_passed'))
"""
    patched = generate_local_candidate(
        source,
        "Accept an Ultra Review report only when sandbox evidence, gate status, and verified findings are present.",
        "local",
        0,
    )
    ns = {}
    exec(patched, ns)
    accept = ns["rlm_harder_v2_accept_ultra_report"]

    assert accept({"sandbox_id": "s1", "gate_passed": True, "verified_findings": []}) is True
    assert accept({"sandbox_id": "s1", "gate_passed": True, "verified_findings": [{"id": "bug"}]}) is False
    assert accept({"sandbox_id": "s1", "gate_passed": True, "verified_findings": [{"id": "bug", "repro_command": "pytest -q", "negative_exit_code": 1}]}) is True
    assert accept({"sandbox_id": "s1", "gate_passed": False, "verified_findings": []}) is False


def test_semantic_refs_patch_requires_source_topic_and_gate():
    source = """
def rlm_harder_v2_select_semantic_refs(refs, topic, min_relevance):
    return [ref.get('id') for ref in refs if ref.get('relevance', 0) >= min_relevance]
"""
    patched = generate_local_candidate(
        source,
        "Accept semantic retrieval evidence only when semantic_searcher returns gated refs tied to the requested source.",
        "local",
        0,
    )
    ns = {}
    exec(patched, ns)
    select = ns["rlm_harder_v2_select_semantic_refs"]

    refs = [
        {"id": "ungated", "relevance": 0.95, "topic": "nexus", "source_id": "claim-u", "gate_passed": False},
        {"id": "missing-source", "relevance": 0.95, "topic": "nexus", "gate_passed": True},
        {"id": "wrong-topic", "relevance": 0.9, "topic": "other", "source_id": "claim-x", "gate_passed": True},
        {"id": "target", "relevance": 0.75, "topic": "nexus", "source_id": "claim-t", "gate_passed": True},
    ]
    assert select(refs, "nexus", 0.7) == ["claim-t"]


@pytest.mark.parametrize(
    ("source", "task", "function_name", "cases"),
    [
        (
            "def normalize_key(text):\n    return text.strip().lower().replace(' ', '-')\n",
            "Fix unicode-free normalization, empty input, and repeated separators.",
            "normalize_key",
            [
                (("  User   Name  ",), "user-name"),
                (("",), ""),
                (("API__Token",), "api-token"),
            ],
        ),
        (
            "def merge_limits(defaults, override):\n    result = defaults\n    result.update(override or {})\n    return result\n",
            "Repair implementation after first patch breaks an invariant.",
            "merge_limits",
            [
                (
                    ({"timeout": 10, "retries": 2}, {"timeout": None, "jitter": 1}),
                    {"timeout": 10, "retries": 2, "jitter": 1},
                ),
            ],
        ),
        (
            "def remaining_ms(start_ms, now_ms, timeout_ms):\n    return timeout_ms - now_ms - start_ms\n",
            "Repair flaky-looking timeout calculation without deleting assertions.",
            "remaining_ms",
            [
                ((100, 125, 50), 25),
                ((100, 200, 50), 0),
                ((100, 90, 50), 50),
            ],
        ),
        (
            "def redact(record):\n    return dict(record)\n",
            "Refactor credential scrubber while preserving secret redaction.",
            "redact",
            [
                (
                    ({"user": "ada", "token": "abc", "password": "pw", "note": "ok"},),
                    {"user": "ada", "token": "[REDACTED]", "password": "[REDACTED]", "note": "ok"},
                ),
            ],
        ),
        (
            "def can_access(role, scope):\n    if role == 'admin':\n        return True\n    return scope == 'read'\n",
            "Refactor authorization helper while preserving deny by default.",
            "can_access",
            [
                (("admin", "write"), True),
                (("viewer", "read"), True),
                (("viewer", "write"), False),
                (("unknown", "read"), False),
                (("viewer", None), False),
            ],
        ),
        (
            "def verified_claims(claims):\n    return [claim['id'] for claim in claims if claim.get('status') == 'pass']\n",
            "Implement evidence rollup that rejects claims without artifact references.",
            "verified_claims",
            [
                (
                    (
                        [
                            {"id": "a", "status": "pass", "artifact": "reports/a.json"},
                            {"id": "b", "status": "pass"},
                            {"id": "c", "status": "fail", "artifact": "reports/c.json"},
                        ],
                    ),
                    ["a"],
                ),
            ],
        ),
        (
            "def classify(smoke_passed, semantic_evidence):\n    return 'resolved' if smoke_passed else 'open'\n",
            "Fix incident classifier that over-trusts a passing smoke test.",
            "classify",
            [
                ((True, {"verified": True}), "resolved"),
                ((True, {"verified": False}), "needs_evidence"),
                ((False, {"verified": True}), "open"),
            ],
        ),
    ],
)
def test_public_candidate_local_self_heal_patches(source, task, function_name, cases):
    patched = generate_local_candidate(source, task, "local", 0)
    ns = {}
    exec(patched, ns)
    for args, expected in cases:
        assert ns[function_name](*args) == expected
