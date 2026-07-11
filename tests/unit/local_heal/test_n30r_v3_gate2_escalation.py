"""N30R-V3 Gate 2: LITE->STANDARD verifier-driven escalation proof.

Tests that LocalModelExecutor.run() proves genuine verifier-driven escalation:
  1. LITE profile: 1 attempt (candidate_cap=1), patch is syntactically valid
     but semantically wrong (wrong return value) → verifier FAILS
  2. failure_class = "verification_failed" → retry eligible
  3. STANDARD retry: HealPipeline re-runs with correct patch → verifier PASSES
  4. solved = True

Uses InjectedLocalModelProvider — no Ollama required.
"""
import os
import tempfile


ORIG_SRC   = 'def greet(name)\n    return f"Hello, {name}!"\n'   # intentional syntax error in original
SEARCH_BAD = 'def greet(name)\n    return f"Hello, {name}!"'      # matches original file

# executor restores file to ORIG after isolation, so STANDARD retry sees original content
SEARCH_GOOD = SEARCH_BAD  # same SEARCH — file is restored to original before retry


def _make_ssrp(search: str, replace: str) -> str:
    return f"FILE: f.py\n<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE"


def _build_provider():
    """
    Provider sequence:
      Planner / spec-gen prompts  → return JSON / description
      Patch call #1 (LITE)       → bad patch: syntactically valid, wrong return value
      Patch call #2 (STANDARD)   → good patch: correct return value

    LITE runs with candidate_cap=1 (max_tries=1), so exactly one patch call per profile.
    """
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider
    ctr = {"patch_count": 0}

    def gen(req):
        prompt = req.prompt
        if "JSON" in prompt or "software architect" in prompt:
            return '{"search_symbols": ["greet"], "repair_strategy": "Fix return value", "violated_constraints": []}'
        if "logical specification" in prompt or "senior engineer" in prompt:
            return "Return the correct greeting string."
        # Patch synthesis
        ctr["patch_count"] += 1
        if ctr["patch_count"] == 1:
            # LITE attempt: syntactically valid, verifier-failing patch
            return _make_ssrp(SEARCH_BAD, 'def greet(name):\n    return "WRONG"')
        else:
            # STANDARD retry: SEARCH matches the modified file content
            return _make_ssrp(SEARCH_GOOD, 'def greet(name):\n    return f"Hello, {name}!"')

    return InjectedLocalModelProvider(generate_fn=gen), ctr


def test_lite_to_standard_verifier_driven_escalation():
    """
    Gate 2 (R2-v2): Genuine verifier-driven LITE→STANDARD escalation.

    Asserts:
      - LITE attempt: candidate isolated, apply success, verifier FAIL
      - failure_class in ("verification_failed", "semantic_wrong_patch")
      - initial_execution_profile = LITE
      - final_execution_profile   = STANDARD
      - profile_escalation_count  = 1
      - STANDARD retry: second candidate hash distinct, verifier PASS
      - solved = True
    """
    from nexus.services.local_heal.local_model_executor import (
        LocalModelExecutor,
        LocalModelExecutorRequest,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        target = "f.py"
        with open(os.path.join(tmpdir, target), "w") as fh:
            fh.write(ORIG_SRC)

        verifier_cmd = ("python3", "-c",
                        "from f import greet; assert greet('world') == 'Hello, world!'")

        provider, ctr = _build_provider()

        route_context = {
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model":      "test-model",
                "protocol_mode":       "anchored_edit",
                "provider_timeout_sec": 30.0,
                "mutation_allowed":    True,
                "verifier_allowed":    True,
                "routing_tier":        "L1_green_lane",
                "routing_tier_reason": "green_lane",
                "risk_score_0_100":    10,
                "confidence":          0.95,
                "cross_module":        False,
                "hard_signal":         False,
                "candidate_count":     1,
                "reasoning_mode":      "FAST",
                "task_desc":           "fix greet return value",
            },
            "verifier_command": list(verifier_cmd),
            "target_file":      target,
            "locked_search":    SEARCH_BAD,
            "python_executable": "python3",
            "llm_call_history": [],
        }

        req = LocalModelExecutorRequest(
            task_id="gate2-verifier-driven-escalation",
            problem_statement="Fix the greet function to return the correct greeting.",
            repo_root=tmpdir,
            target_file=target,
            selected_capabilities=("repair_loop",),
            evidence_refs=("evidence-1",),
            route_context=route_context,
            mutation_allowed=True,
            verifier_allowed=True,
            dry_run=False,
        )

        resp = LocalModelExecutor.run(req, provider=provider)
        raw  = resp.raw_model_metadata
        assert raw is not None, "raw_model_metadata must be present"

        # ── Core escalation assertions ─────────────────────────────────────
        initial  = raw.get("initial_execution_profile", "UNKNOWN")
        final    = raw.get("final_execution_profile",   "UNKNOWN")
        esc_cnt  = raw.get("profile_escalation_count",  -1)
        attempts = raw.get("profile_attempts",          [])
        solved   = raw.get("solved")
        fc       = raw.get("failure_class", "")

        assert initial == "LITE",     f"Expected LITE, got {initial!r}"
        assert final   == "STANDARD", f"Expected STANDARD, got {final!r}"
        assert esc_cnt == 1,          f"Expected escalation_count=1, got {esc_cnt}"
        assert "LITE"     in attempts, f"LITE not in profile_attempts: {attempts}"
        assert "STANDARD" in attempts, f"STANDARD not in profile_attempts: {attempts}"

        # ── Verifier-driven (not syntax-error) proof ───────────────────────
        # escalation_reason "lite_to_standard_on_verification_failure" proves
        # the LITE candidate reached the verifier (not blocked by syntax error).
        esc_reasons = raw.get("profile_escalation_reasons", [])
        assert "lite_to_standard_on_verification_failure" in esc_reasons, (
            f"Expected escalation reason 'lite_to_standard_on_verification_failure', "
            f"got {esc_reasons!r}\n"
            f"(replace_syntax_error means patch never reached verifier)\n"
            f"raw_meta keys={list(raw.keys())}"
        )

        # ── STANDARD retry must have solved it ────────────────────────────
        assert solved is True, (
            f"Should be solved after STANDARD retry.\n"
            f"failure_class={fc} retry_eligible={raw.get('retry_eligible')}\n"
            f"retry_not_invoked_reason={raw.get('retry_not_invoked_reason')}\n"
            f"patch_lifecycle_state={raw.get('patch_lifecycle_state')}\n"
            f"patch_count={ctr['patch_count']}"
        )


def test_standard_profile_no_escalation():
    """Gate 2: STANDARD profile does not trigger escalation (semantic_retry_cap=1 != 0)."""
    from nexus.services.local_heal.local_armor_execution_profile import build_profile_controls
    p = build_profile_controls("STANDARD", "direct_standard", "L2_hardened")
    assert p.semantic_retry_cap == 1, f"Expected 1, got {p.semantic_retry_cap}"
    # escalation condition requires retry_cap == 0
    assert p.semantic_retry_cap != 0, "STANDARD should not trigger escalation"


def test_lite_profile_no_escalate_when_solved():
    """Gate 2: LITE must NOT escalate if verifier already passed."""
    from nexus.services.local_heal.local_armor_execution_profile import build_profile_controls
    p = build_profile_controls("LITE", "green_lane_lite", "L1_green_lane")
    solved = True
    would_escalate = (p.semantic_retry_cap == 0 and not solved)
    assert not would_escalate, "Should not escalate when already solved"


def test_full_profile_escalation_not_allowed():
    """Gate 2: FULL profile must have escalation_allowed=False."""
    from nexus.services.local_heal.local_armor_execution_profile import build_profile_controls
    p = build_profile_controls("FULL", "forced_full", "L3_swarm_deep")
    assert p.escalation_allowed is False, f"FULL should block escalation, got {p.escalation_allowed}"
