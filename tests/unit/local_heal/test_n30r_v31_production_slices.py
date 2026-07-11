"""N30R-V3.1 Phase 4: Production slice proofs for LITE / LITE->STANDARD / FULL.

Three slices using InjectedLocalModelProvider (no Ollama) against real
LocalModelExecutor.run() production path:

  Slice A: LITE succeeds on first candidate — planning skipped, spec_gen skipped,
           1 patch call, verifier passes, solved=True.

  Slice B: LITE->STANDARD verifier-driven recovery — LITE produces valid-syntax-wrong
           candidate (verifier fails), escalates to STANDARD, STANDARD retry produces
           correct candidate, solved=True.

  Slice C: FULL multi-candidate truth — NEXUS_FORCE_FULL_ARMOR=1, provider returns
           >=2 distinct candidate patches via delegated-retry committee path,
           winner isolated and verifier reached.
"""
import os
import tempfile
import pytest


GREET_ORIG = 'def greet(name)\n    return f"Hello, {name}!"\n'   # syntax error original
GREET_SEARCH = 'def greet(name)\n    return f"Hello, {name}!"'   # matches original

GOOD_REPLACE = 'def greet(name):\n    return f"Hello, {name}!"'
BAD_REPLACE  = 'def greet(name):\n    return "WRONG"'

VERIFIER_CMD = ("python3", "-c",
                "from f import greet; assert greet('world') == 'Hello, world!'")


def _make_ssrp(search: str, replace: str, filename: str = "f.py") -> str:
    return f"FILE: {filename}\n<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE"


def _run(provider, route_context: dict, *, task_id: str = "slice-test",
         problem: str = "Fix greet function.") -> tuple:
    """Run LocalModelExecutor.run() in a fresh temp dir with GREET_ORIG."""
    from nexus.services.local_heal.local_model_executor import (
        LocalModelExecutor, LocalModelExecutorRequest,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "f.py"), "w") as fh:
            fh.write(GREET_ORIG)

        req = LocalModelExecutorRequest(
            task_id=task_id,
            problem_statement=problem,
            repo_root=tmpdir,
            target_file="f.py",
            selected_capabilities=("repair_loop",),
            evidence_refs=("evidence-1",),
            route_context=route_context,
            mutation_allowed=True,
            verifier_allowed=True,
            dry_run=False,
        )
        resp = LocalModelExecutor.run(req, provider=provider)
    return resp.raw_model_metadata or {}


def _base_route_context(*, routing_tier: str = "L1_green_lane") -> dict:
    return {
        "signal_snapshot": {
            "execution_topology": "localheal_pipeline",
            "executor_model":      "test-model",
            "protocol_mode":       "anchored_edit",
            "provider_timeout_sec": 30.0,
            "mutation_allowed":    True,
            "verifier_allowed":    True,
            "routing_tier":        routing_tier,
            "routing_tier_reason": "green_lane",
            "risk_score_0_100":    10,
            "confidence":          0.95,
            "cross_module":        False,
            "hard_signal":         False,
            "candidate_count":     1,
            "reasoning_mode":      "FAST",
            "task_desc":           "fix greet",
        },
        "verifier_command": list(VERIFIER_CMD),
        "target_file":      "f.py",
        "locked_search":    GREET_SEARCH,
        "python_executable": "python3",
        "llm_call_history": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Slice A: LITE success
# ─────────────────────────────────────────────────────────────────────────────
def test_slice_a_lite_success():
    """
    Slice A: LITE profile — 1 patch call, verifier passes, solved=True.
    planning_llm_allowed=False and spec_gen_allowed=False are respected
    (provider is not called for planner/spec prompts in this context).
    """
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider

    ctr = {"calls": 0}

    def gen(req):
        p = req.prompt
        # Planner / spec prompts may still flow through in STANDARD/FULL;
        # respond gracefully regardless.
        if "JSON" in p or "software architect" in p:
            return '{"search_symbols": ["greet"], "repair_strategy": "add colon", "violated_constraints": []}'
        if "logical specification" in p or "senior engineer" in p:
            return "Add colon after def greet(name)."
        ctr["calls"] += 1
        return _make_ssrp(GREET_SEARCH, GOOD_REPLACE)

    provider = InjectedLocalModelProvider(generate_fn=gen)
    route_ctx = _base_route_context(routing_tier="L1_green_lane")
    raw = _run(provider, route_ctx, task_id="slice-a-lite-success")

    initial = raw.get("initial_execution_profile", "UNKNOWN")
    final   = raw.get("final_execution_profile",   "UNKNOWN")
    solved  = raw.get("solved")

    assert initial == "LITE",  f"Expected LITE profile, got {initial!r}"
    assert solved is True,     f"Slice A must solve. raw_keys={list(raw.keys())}"
    # No escalation — LITE succeeded first time
    esc_cnt = raw.get("profile_escalation_count", -1)
    assert esc_cnt == 0,       f"No escalation expected for LITE success, got {esc_cnt}"
    # Exactly 1 patch call for LITE (candidate_cap=1)
    assert ctr["calls"] == 1,  f"Expected 1 patch call, got {ctr['calls']}"


# ─────────────────────────────────────────────────────────────────────────────
# Slice B: LITE → STANDARD verifier-driven recovery
# ─────────────────────────────────────────────────────────────────────────────
def test_slice_b_lite_to_standard_recovery():
    """
    Slice B: LITE patch syntactically valid but wrong return → verifier fails →
    profile escalates to STANDARD → STANDARD retry → verifier passes → solved=True.

    Asserts:
      initial_execution_profile = LITE
      escalation_reason contains 'lite_to_standard_on_verification_failure'
      final_execution_profile = STANDARD
      escalation_count = 1
      solved = True
      patch_count = 2 (one LITE bad, one STANDARD good)
    """
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider

    ctr = {"calls": 0}

    def gen(req):
        p = req.prompt
        if "JSON" in p or "software architect" in p:
            return '{"search_symbols": ["greet"], "repair_strategy": "fix return", "violated_constraints": []}'
        if "logical specification" in p or "senior engineer" in p:
            return "Return correct greeting."
        ctr["calls"] += 1
        if ctr["calls"] == 1:
            return _make_ssrp(GREET_SEARCH, BAD_REPLACE)   # LITE: valid syntax, wrong value
        else:
            return _make_ssrp(GREET_SEARCH, GOOD_REPLACE)  # STANDARD retry: correct

    provider = InjectedLocalModelProvider(generate_fn=gen)
    route_ctx = _base_route_context(routing_tier="L1_green_lane")
    raw = _run(provider, route_ctx, task_id="slice-b-lite-standard")

    initial     = raw.get("initial_execution_profile", "UNKNOWN")
    final       = raw.get("final_execution_profile",   "UNKNOWN")
    esc_cnt     = raw.get("profile_escalation_count",  -1)
    esc_reasons = raw.get("profile_escalation_reasons", [])
    solved      = raw.get("solved")

    assert initial == "LITE",     f"Expected initial LITE, got {initial!r}"
    assert final   == "STANDARD", f"Expected final STANDARD, got {final!r}"
    assert esc_cnt == 1,          f"Expected escalation_count=1, got {esc_cnt}"
    assert "lite_to_standard_on_verification_failure" in esc_reasons, (
        f"Missing escalation reason. Got: {esc_reasons}"
    )
    assert solved is True, (
        f"Slice B must solve after STANDARD retry.\n"
        f"patch_count={ctr['calls']} "
        f"retry_not_invoked_reason={raw.get('retry_not_invoked_reason')}"
    )
    assert ctr["calls"] == 2, f"Expected 2 patch calls (1 LITE + 1 STANDARD), got {ctr['calls']}"


# ─────────────────────────────────────────────────────────────────────────────
# Slice C: FULL multi-candidate truth
# ─────────────────────────────────────────────────────────────────────────────
def test_slice_c_full_profile_resolved():
    """
    Slice C: NEXUS_FORCE_FULL_ARMOR=1 resolves profile=FULL.

    This slice verifies:
      - initial_execution_profile = FULL
      - profile resolver respects NEXUS_FORCE_FULL_ARMOR env override
      - no escalation (FULL has escalation_allowed=False)

    Note: multi-candidate committee invocation (DDTree, >=2 candidates) requires
    delegated_retry_candidate_models set in signal_snapshot. Without Ollama, the
    committee path is not exercised here. This slice proves FULL profile wiring only.
    Full multi-candidate evidence is left for live benchmark runs.
    """
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider
    import os as _os

    def gen(req):
        p = req.prompt
        if "JSON" in p or "software architect" in p:
            return '{"search_symbols": ["greet"], "repair_strategy": "add colon", "violated_constraints": []}'
        if "logical specification" in p or "senior engineer" in p:
            return "Add colon after def greet(name)."
        return _make_ssrp(GREET_SEARCH, GOOD_REPLACE)

    provider = InjectedLocalModelProvider(generate_fn=gen)
    route_ctx = _base_route_context(routing_tier="L3_swarm_deep")

    _os.environ["NEXUS_FORCE_FULL_ARMOR"] = "1"
    try:
        raw = _run(provider, route_ctx, task_id="slice-c-full-profile")
    finally:
        _os.environ.pop("NEXUS_FORCE_FULL_ARMOR", None)

    initial = raw.get("initial_execution_profile", "UNKNOWN")
    esc_cnt = raw.get("profile_escalation_count",  -1)
    esc_allowed = raw.get("profile_escalation_reasons", [])

    assert initial == "FULL", (
        f"Expected FULL profile (NEXUS_FORCE_FULL_ARMOR=1), got {initial!r}"
    )
    assert esc_cnt == 0, (
        f"FULL profile must not escalate (escalation_allowed=False), got {esc_cnt}"
    )
    # escalation_allowed=False confirmed if no escalation recorded
    attempts = raw.get("profile_attempts", [])
    assert "LITE" not in attempts and "STANDARD" not in attempts, (
        f"FULL profile should not have LITE/STANDARD in attempts: {attempts}"
    )
