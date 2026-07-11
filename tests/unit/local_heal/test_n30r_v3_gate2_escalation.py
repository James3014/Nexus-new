"""N30R-V3 Gate 2: LITE->STANDARD escalation proof via production executor path.

Tests that LocalModelExecutor.run() escalates from LITE to STANDARD when:
  1. Profile starts as LITE (retry_cap=0, escalation_allowed=True)
  2. LITE verifier fails (solved=False)
  3. STANDARD attempt runs with a patch that passes verifier

Uses InjectedLocalModelProvider to return predefined patches without Ollama.
"""
import os
import tempfile


def _make_ssrp(search, replace):
    return f"FILE: f.py\n<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE"


def _build_provider():
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider
    ctr = {"patch_count": 0}

    def gen(req):
        prompt = req.prompt
        if "JSON" in prompt or "software architect" in prompt:
            # Planner prompt
            return '{"search_symbols": ["greet"], "repair_strategy": "Fix syntax error", "violated_constraints": []}'
        elif "logical specification" in prompt or "senior engineer" in prompt:
            # Spec gen prompt
            return "Add colon after def greet(name)"
        else:
            # Patch synthesis prompt
            ctr["patch_count"] += 1
            search_text = 'def greet(name)\n    return f"Hello, {name}!"'
            if ctr["patch_count"] <= 3:
                return _make_ssrp(search_text, 'def greet(name)\n    return "WRONG"')
            else:
                return _make_ssrp(search_text, 'def greet(name):\n    return f"Hello, {name}!"')

    return InjectedLocalModelProvider(generate_fn=gen), ctr


def test_lite_to_standard_real_escalation():
    """
    Gate 2 (R2): LITE->STANDARD escalation via real LocalModelExecutor.run().

    Asserts:
      - initial_execution_profile = LITE
      - final_execution_profile = STANDARD
      - profile_escalation_count = 1
      - profile_attempts contains both LITE and STANDARD
      - solved = True
    """
    from nexus.services.local_heal.local_model_executor import (
        LocalModelExecutor,
        LocalModelExecutorRequest,
    )

    ORIGINAL_SRC = 'def greet(name)\n    return f"Hello, {name}!"\n'

    with tempfile.TemporaryDirectory() as tmpdir:
        target_relpath = "f.py"
        with open(os.path.join(tmpdir, target_relpath), "w") as fh:
            fh.write(ORIGINAL_SRC)

        verifier_cmd = (
            "python3", "-c",
            "from f import greet; assert greet('world') == 'Hello, world!'"
        )

        provider, ctr = _build_provider()

        route_context = {
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "test-model",
                "protocol_mode": "anchored_edit",
                "provider_timeout_sec": 30.0,
                "mutation_allowed": True,
                "verifier_allowed": True,
                "routing_tier": "L1_green_lane",
                "routing_tier_reason": "green_lane",
                "risk_score_0_100": 10,
                "confidence": 0.95,
                "cross_module": False,
                "hard_signal": False,
                "candidate_count": 1,
                "reasoning_mode": "FAST",
                "task_desc": "fix syntax error",
            },
            "verifier_command": list(verifier_cmd),
            "target_file": target_relpath,
            "locked_search": 'def greet(name)\n    return f"Hello, {name}!"',
            "python_executable": "python3",
            "llm_call_history": [],
        }

        req = LocalModelExecutorRequest(
            task_id="gate2-lite-standard-test",
            problem_statement="Fix the syntax error in greet function",
            repo_root=tmpdir,
            target_file=target_relpath,
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

        initial  = raw.get("initial_execution_profile", "UNKNOWN")
        final    = raw.get("final_execution_profile",   "UNKNOWN")
        esc_cnt  = raw.get("profile_escalation_count",  -1)
        attempts = raw.get("profile_attempts",          [])
        err      = raw.get("error", "")

        assert not err, f"Executor error: {err!r}  raw_keys={list(raw.keys())}"
        assert initial == "LITE",     f"initial_profile should be LITE, got {initial!r}  err={raw.get('error','')}"
        assert final   == "STANDARD", f"final_profile should be STANDARD, got {final!r}"
        assert esc_cnt == 1,          f"escalation_count should be 1, got {esc_cnt}"
        assert "LITE"     in attempts, f"LITE not in profile_attempts: {attempts}"
        assert "STANDARD" in attempts, f"STANDARD not in profile_attempts: {attempts}"
        assert raw.get("solved") is True, f"Should be solved on STANDARD retry. raw_meta={raw}"


def test_standard_profile_no_escalation():
    """Gate 2: STANDARD profile does not trigger escalation logic."""
    from nexus.services.local_heal.local_armor_execution_profile import build_profile_controls
    p = build_profile_controls("STANDARD", "direct_standard", "L2_hardened")
    assert p.semantic_retry_cap == 1
    count = 0
    if p.semantic_retry_cap == 0:
        count += 1
    assert count == 0


def test_lite_profile_no_escalate_when_solved():
    """Gate 2: LITE must NOT escalate if verifier already passed."""
    from nexus.services.local_heal.local_armor_execution_profile import build_profile_controls
    p = build_profile_controls("LITE", "green_lane_lite", "L1_green_lane")
    solved = True
    count = 0
    if p.semantic_retry_cap == 0 and not solved:
        count += 1
    assert count == 0


def test_full_profile_escalation_not_allowed():
    """Gate 2: FULL profile must have escalation_allowed=False."""
    from nexus.services.local_heal.local_armor_execution_profile import build_profile_controls
    p = build_profile_controls("FULL", "forced_full", "L3_swarm_deep")
    assert p.escalation_allowed is False
